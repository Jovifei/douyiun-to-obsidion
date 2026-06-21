"""Test pipeline/scheduler.py — 单 worker 串行调度器。

Spec ref: specs/task-queue-pipeline/spec.md + tasks.md §6

TDD: 7 tests covering:
1. test_run_once_happy_path — mock all, verify task status=done
2. test_run_once_no_subtitle_fails — subtitle_source=none → failed + error_code
3. test_run_once_download_fails_tries_douk — DownloadError → douk fallback
4. test_run_once_douk_also_fails — both tools fail → failed
5. test_run_once_write_failure — writer raises → failed
6. test_run_once_correlation_id_propagated — UUID 贯穿日志
7. test_run_once_cleanup_temp_files — .mp4/.vtt deleted after write
"""
import logging
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from src.queue import db


@pytest.fixture(autouse=True)
def _reset_structlog():
    """每个测试前后重置 structlog 状态，确保日志文件隔离。"""
    from src.utils.logging_config import _reset_logging
    _reset_logging()
    yield
    _reset_logging()


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_config(tmp_path: Path) -> dict:
    """构造测试用 config dict（嵌套结构，与 config.yaml 对齐）。"""
    return {
        "vault": {"root": str(tmp_path / "vault")},
        "downloader": {
            "temp_dir": str(tmp_path / "tmp"),
            "cookies_path": "",
            "douk_path": "",
            "yt_dlp_retries": 3,
        },
        "queue": {"db_path": str(tmp_path / "test.db"), "zombie_timeout_minutes": 30},
        "logging": {"level": "INFO", "dir": str(tmp_path / "logs"), "rotation": "daily"},
    }


def _init_conn(db_path) -> sqlite3.Connection:
    """用 db.init_db 初始化（设置 row_factory=sqlite3.Row）。"""
    return db.init_db(db_path)


def _enqueue_task(conn, correlation_id: str | None = None) -> int:
    """入队一条测试任务，返回 task_id。"""
    cid = correlation_id or str(uuid.uuid4())
    return db.enqueue(
        conn,
        video_id="1234567890123",
        source_url="https://v.douyin.com/test/",
        source_url_type="short_link",
        correlation_id=cid,
    )


def _mock_download_result(tmp_dir: Path, video_id: str = "1234567890123") -> dict:
    """构造 download_video 成功返回值，同时写入假文件。"""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    video_path = tmp_dir / f"{video_id}.mp4"
    subtitle_path = tmp_dir / f"{video_id}.zh.vtt"
    video_path.write_bytes(b"fake video")
    subtitle_path.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhello\n")
    return {
        "video_path": video_path,
        "subtitle_path": subtitle_path,
        "subtitle_source": "douyin_native",
        "downloader_used": "yt-dlp",
        "info_dict": {
            "title": "Test Video",
            "uploader": "Author",
            "uploader_url": "https://www.douyin.com/user/sec_uid_abc",
            "duration": 60,
            "upload_date": "20260619",
            "thumbnail": "https://example.com/thumb.jpg",
            "subtitles": {"zh": [{}]},
            "automatic_captions": {},
        },
        "title": "Test Video",
        "duration": 60,
        "uploader": "Author",
        "uploader_url": "https://www.douyin.com/user/sec_uid_abc",
        "thumbnail": "https://example.com/thumb.jpg",
    }


# ── Test 1: Happy path ────────────────────────────────────────────────────


class TestRunOnceHappyPath:
    """test_run_once_happy_path — mock 所有 extractor + writer，验证 task status=done"""

    @patch("src.pipeline.scheduler.write_note")
    @patch("src.pipeline.scheduler.build_note_body", return_value="body")
    @patch("src.pipeline.scheduler.build_frontmatter", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.extract_metadata", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.download_video")
    @patch("src.pipeline.scheduler.resolve_url", return_value={"canonical_url": "https://canonical.url/", "source_url_type": "full", "video_id": "1234567890123"})
    def test_task_status_becomes_done(
        self, mock_resolve, mock_download, mock_meta,
        mock_fm, mock_body, mock_write, tmp_path
    ):
        db_path = tmp_path / "test.sqlite3"
        conn = _init_conn(db_path)
        task_id = _enqueue_task(conn)
        config = _make_config(tmp_path)

        mock_download.return_value = _mock_download_result(Path(config["downloader"]["temp_dir"]))
        mock_write.return_value = Path("inbox/douyin/2026-06/1234567890123.md")

        from src.pipeline.scheduler import run_once
        run_once(db_path, config)

        task = db.get_task(conn, task_id)
        assert task is not None
        assert task["status"] == "done"


# ── Test 2: No subtitle fails ─────────────────────────────────────────────


class TestRunOnceNoSubtitleFails:
    """test_run_once_no_subtitle_fails — NoSubtitleError → ASR fallback → failed(asr_failed) when no ASR configured."""

    @patch("src.pipeline.scheduler.download_video")
    @patch("src.pipeline.scheduler.resolve_url", return_value={"canonical_url": "https://canonical.url/", "source_url_type": "full", "video_id": "1234567890123"})
    def test_task_status_becomes_failed_no_subtitle(
        self, mock_resolve, mock_download, tmp_path
    ):
        """M2: NoSubtitleError now triggers ASR fallback. Without ASR config, error_code=asr_failed."""
        from src.extractors.downloader import NoSubtitleError

        db_path = tmp_path / "test.sqlite3"
        conn = _init_conn(db_path)
        task_id = _enqueue_task(conn)
        config = _make_config(tmp_path)

        mock_download.side_effect = NoSubtitleError("no_subtitle_in_m1")

        from src.pipeline.scheduler import run_once
        run_once(db_path, config)

        task = db.get_task(conn, task_id)
        assert task["status"] == "failed"
        # M2: NoSubtitleError triggers ASR fallback; without ASR config → asr_failed
        assert task["error_code"] == "asr_failed"


# ── Test 3: Download fails → DouK fallback ────────────────────────────────


class TestRunOnceDownloadFailsTriesDouk:
    """test_run_once_download_fails_tries_douk — mock download_video raises → douk fallback"""

    @patch("src.pipeline.scheduler.write_note", return_value=Path("note.md"))
    @patch("src.pipeline.scheduler.build_note_body", return_value="body")
    @patch("src.pipeline.scheduler.build_frontmatter", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.extract_metadata", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.download_with_douk")
    @patch("src.pipeline.scheduler.download_video")
    @patch("src.pipeline.scheduler.resolve_url", return_value={"canonical_url": "https://canonical.url/", "source_url_type": "full", "video_id": "1234567890123"})
    def test_douk_called_when_ytdlp_fails(
        self, mock_resolve, mock_ytdlp, mock_douk,
        mock_meta, mock_fm, mock_body, mock_write, tmp_path
    ):
        import yt_dlp

        db_path = tmp_path / "test.sqlite3"
        conn = _init_conn(db_path)
        task_id = _enqueue_task(conn)
        config = _make_config(tmp_path)
        config["downloader"]["douk_path"] = "/usr/bin/douk"

        mock_ytdlp.side_effect = yt_dlp.utils.DownloadError("network error")
        mock_douk.return_value = _mock_download_result(Path(config["downloader"]["temp_dir"]))
        mock_douk.return_value["downloader_used"] = "douk"

        from src.pipeline.scheduler import run_once
        run_once(db_path, config)

        mock_douk.assert_called_once()
        task = db.get_task(conn, task_id)
        assert task["status"] == "done"


# ── Test 4: DouK also fails ──────────────────────────────────────────────


class TestRunOnceDoukAlsoFails:
    """test_run_once_douk_also_fails — both tools fail → task status=failed"""

    @patch("src.pipeline.scheduler.download_with_douk")
    @patch("src.pipeline.scheduler.download_video")
    @patch("src.pipeline.scheduler.resolve_url", return_value={"canonical_url": "https://canonical.url/", "source_url_type": "full", "video_id": "1234567890123"})
    def test_both_fail_task_becomes_failed(
        self, mock_resolve, mock_ytdlp, mock_douk, tmp_path
    ):
        import yt_dlp
        from src.extractors.douk_fallback import DoukDownloadError

        db_path = tmp_path / "test.sqlite3"
        conn = _init_conn(db_path)
        task_id = _enqueue_task(conn)
        config = _make_config(tmp_path)
        config["downloader"]["douk_path"] = "/usr/bin/douk"

        mock_ytdlp.side_effect = yt_dlp.utils.DownloadError("network error")
        mock_douk.side_effect = DoukDownloadError("douk_failed")

        from src.pipeline.scheduler import run_once
        run_once(db_path, config)

        task = db.get_task(conn, task_id)
        assert task["status"] == "failed"
        assert task["error_code"] == "download_failed_all_tools"


# ── Test 4b: DouK success but info_dict=None → metadata fallback ───────────


class TestRunOnceDoukSuccessMetadataFallback:
    """test_run_once_douk_success_metadata_fallback — DouK succeeds with info_dict=None, task still done."""

    @patch("src.pipeline.scheduler.write_note", return_value=Path("note.md"))
    @patch("src.pipeline.scheduler.build_note_body", return_value="body")
    @patch("src.pipeline.scheduler.build_frontmatter", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.extract_metadata", return_value={
        "title": "", "uploader": "", "uploader_id": "",
        "duration_seconds": 0, "uploaded_at": "", "thumbnail": "",
    })
    @patch("src.pipeline.scheduler.download_with_douk")
    @patch("src.pipeline.scheduler.download_video")
    @patch("src.pipeline.scheduler.resolve_url", return_value={"canonical_url": "https://canonical.url/", "source_url_type": "full", "video_id": "1234567890123"})
    def test_douk_success_with_none_info_dict_still_done(
        self, mock_resolve, mock_ytdlp, mock_douk,
        mock_meta, mock_fm, mock_body, mock_write, tmp_path
    ):
        import yt_dlp

        db_path = tmp_path / "test.sqlite3"
        conn = _init_conn(db_path)
        task_id = _enqueue_task(conn)
        config = _make_config(tmp_path)
        config["downloader"]["douk_path"] = "/usr/bin/douk"

        mock_ytdlp.side_effect = yt_dlp.utils.DownloadError("network error")

        # DouK succeeds but returns info_dict=None (the bug scenario)
        tmp_dir = Path(config["downloader"]["temp_dir"])
        tmp_dir.mkdir(parents=True, exist_ok=True)
        subtitle_path = tmp_dir / "1234567890123.zh.vtt"
        subtitle_path.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhello\n")
        mock_douk.return_value = {
            "video_path": tmp_dir / "1234567890123.mp4",
            "subtitle_path": subtitle_path,
            "subtitle_source": "douk_native",
            "downloader_used": "douk",
            "info_dict": None,  # <-- the bug: DouK doesn't produce info_dict
        }

        from src.pipeline.scheduler import run_once
        run_once(db_path, config)

        mock_douk.assert_called_once()
        # extract_metadata should have been called with {} (not None)
        mock_meta.assert_called_once_with({})
        task = db.get_task(conn, task_id)
        assert task["status"] == "done"


# ── Test 5: Write failure ─────────────────────────────────────────────────


class TestRunOnceWriteFailure:
    """test_run_once_write_failure — mock writer raises → task status=failed"""

    @patch("src.pipeline.scheduler.write_note", side_effect=OSError("disk full"))
    @patch("src.pipeline.scheduler.build_note_body", return_value="body")
    @patch("src.pipeline.scheduler.build_frontmatter", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.extract_metadata", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.download_video")
    @patch("src.pipeline.scheduler.resolve_url", return_value={"canonical_url": "https://canonical.url/", "source_url_type": "full", "video_id": "1234567890123"})
    def test_write_error_task_becomes_failed(
        self, mock_resolve, mock_download, mock_meta,
        mock_fm, mock_body, mock_write, tmp_path
    ):
        db_path = tmp_path / "test.sqlite3"
        conn = _init_conn(db_path)
        task_id = _enqueue_task(conn)
        config = _make_config(tmp_path)

        mock_download.return_value = _mock_download_result(Path(config["downloader"]["temp_dir"]))

        from src.pipeline.scheduler import run_once
        run_once(db_path, config)

        task = db.get_task(conn, task_id)
        assert task["status"] == "failed"
        assert task["error_code"] == "write_failed"


# ── Test 6: correlation_id propagated ─────────────────────────────────────


class TestRunOnceCorrelationIdPropagated:
    """test_run_once_correlation_id_propagated — 验证 correlation_id 贯穿"""

    @patch("src.pipeline.scheduler.transition")
    @patch("src.pipeline.scheduler.write_note", return_value=Path("note.md"))
    @patch("src.pipeline.scheduler.build_note_body", return_value="body")
    @patch("src.pipeline.scheduler.build_frontmatter", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.extract_metadata", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.download_video")
    @patch("src.pipeline.scheduler.resolve_url", return_value={"canonical_url": "https://canonical.url/", "source_url_type": "full", "video_id": "1234567890123"})
    def test_correlation_id_in_log_output(
        self, mock_resolve, mock_download, mock_meta,
        mock_fm, mock_body, mock_write, mock_transition, tmp_path
    ):
        db_path = tmp_path / "test.sqlite3"
        conn = _init_conn(db_path)
        cid = str(uuid.uuid4())
        task_id = _enqueue_task(conn, correlation_id=cid)
        config = _make_config(tmp_path)

        mock_download.return_value = _mock_download_result(Path(config["downloader"]["temp_dir"]))

        from src.pipeline.scheduler import run_once
        run_once(db_path, config)

        # flush structlog 文件句柄，确保日志落盘
        from src.utils.logging_config import _log_file_handle
        if _log_file_handle:
            _log_file_handle.flush()

        # structlog 现在写文件，读 log 文件验证 correlation_id
        log_dir = Path(config["logging"]["dir"]) / "scheduler"
        log_files = list(log_dir.glob("*.log")) if log_dir.exists() else []
        log_content = ""
        for lf in log_files:
            log_content += lf.read_text(encoding="utf-8")

        assert cid in log_content, f"correlation_id {cid} not found in log files (dir={log_dir}, files={log_files})"


# ── Test 7: Cleanup temp files ────────────────────────────────────────────


class TestRunOnceCleanupTempFiles:
    """test_run_once_cleanup_temp_files — 验证临时 .mp4/.vtt 被删"""

    @patch("src.pipeline.scheduler.write_note", return_value=Path("note.md"))
    @patch("src.pipeline.scheduler.build_note_body", return_value="body")
    @patch("src.pipeline.scheduler.build_frontmatter", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.extract_metadata", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.download_video")
    @patch("src.pipeline.scheduler.resolve_url", return_value={"canonical_url": "https://canonical.url/", "source_url_type": "full", "video_id": "1234567890123"})
    def test_temp_files_deleted_after_write(
        self, mock_resolve, mock_download, mock_meta,
        mock_fm, mock_body, mock_write, tmp_path
    ):
        db_path = tmp_path / "test.sqlite3"
        conn = _init_conn(db_path)
        _enqueue_task(conn)
        config = _make_config(tmp_path)

        dl_result = _mock_download_result(Path(config["downloader"]["temp_dir"]))
        mock_download.return_value = dl_result

        video_path = dl_result["video_path"]
        subtitle_path = dl_result["subtitle_path"]
        assert video_path.exists()
        assert subtitle_path.exists()

        from src.pipeline.scheduler import run_once
        run_once(db_path, config)

        assert not video_path.exists(), f"{video_path} should be deleted"
        assert not subtitle_path.exists(), f"{subtitle_path} should be deleted"
