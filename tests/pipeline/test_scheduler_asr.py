"""Test pipeline/scheduler.py — M2 Task 5: ASR 分支改造。

Spec ref: D-M2-3, D-M2-2
TDD: 5 tests covering:
1. 无字幕 + mimo provider → 调 extract_audio_for_asr + MimoASRClient.transcribe → subtitle_source="mimo_asr"
2. 无字幕 + whisper_local provider → 调 WhisperLocalClient → subtitle_source="whisper_local"
3. ASR 失败 → failed(asr_failed)
4. 有字幕 → 不调 ASR（M1 行为不变）
5. download_video_only 函数存在且只下载视频不抓字幕
"""
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from src.queue import db


@pytest.fixture(autouse=True)
def _reset_structlog():
    """每个测试前后重置 structlog 状态。"""
    from src.utils.logging_config import _reset_logging
    _reset_logging()
    yield
    _reset_logging()


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_config(tmp_path: Path, asr_provider: str = "mimo") -> dict:
    """构造测试用 config dict（含 asr 配置）。"""
    return {
        "vault": {"root": str(tmp_path / "vault")},
        "downloader": {
            "temp_dir": str(tmp_path / "tmp"),
            "cookies_path": "",
            "douk_path": "",
            "yt_dlp_retries": 3,
        },
        "asr": {"provider": asr_provider},
        "queue": {"db_path": str(tmp_path / "test.db"), "zombie_timeout_minutes": 30},
        "logging": {"level": "INFO", "dir": str(tmp_path / "logs"), "rotation": "daily"},
    }


def _init_conn(db_path) -> sqlite3.Connection:
    return db.init_db(db_path)


def _enqueue_task(conn, correlation_id: str | None = None) -> int:
    cid = correlation_id or str(uuid.uuid4())
    return db.enqueue(
        conn,
        video_id="1234567890123",
        source_url="https://v.douyin.com/test/",
        source_url_type="short_link",
        correlation_id=cid,
    )


# ── Test 1: 无字幕 + mimo → ASR ──────────────────────────────────────────


class TestNoSubtitleWithMimoAsr:
    """无字幕 + mimo provider → extract_audio_for_asr + MimoASRClient.transcribe"""

    @patch("src.pipeline.scheduler.get_asr_client")
    @patch("src.pipeline.scheduler.extract_audio_for_asr")
    @patch("src.pipeline.scheduler.download_video_only")
    @patch("src.asr.audio_preprocess.split_audio_chunks")
    @patch("src.pipeline.scheduler.write_note", return_value=Path("note.md"))
    @patch("src.pipeline.scheduler.build_note_body", return_value="body")
    @patch("src.pipeline.scheduler.build_frontmatter", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.extract_metadata", return_value={"title": "t"})
    @patch("src.pipeline.scheduler._download_with_fallback")
    @patch("src.pipeline.scheduler.resolve_url", return_value={
        "canonical_url": "https://canonical.url/",
        "source_url_type": "full",
        "video_id": "1234567890123"
    })
    def test_no_subtitle_mimo_provider_uses_asr(
        self, mock_resolve, mock_dl_fallback, mock_meta, mock_fm, mock_body, mock_write,
        mock_split, mock_dl_only, mock_extract_audio, mock_get_asr, tmp_path
    ):
        from src.asr import ASRResult

        db_path = tmp_path / "test.sqlite3"
        conn = _init_conn(db_path)
        task_id = _enqueue_task(conn)
        config = _make_config(tmp_path, asr_provider="mimo")
        tmp_dir = Path(config["downloader"]["temp_dir"])

        # _download_with_fallback 返回无字幕结果
        mock_dl_fallback.return_value = {
            "video_path": tmp_dir / "1234567890123.mp4",
            "subtitle_path": None,
            "subtitle_source": None,
            "downloader_used": "yt-dlp",
            "info_dict": {"title": "Test"},
        }

        # download_video_only 返回视频
        mock_dl_only.return_value = {"video_path": tmp_dir / "1234567890123.mp4"}

        # extract_audio_for_asr 返回 WAV 路径
        wav_path = tmp_dir / "1234567890123.wav"
        mock_extract_audio.return_value = wav_path

        # split_audio_chunks 返回单片（不需要分片）
        mock_split.return_value = [wav_path]

        # get_asr_client 返回 mock mimo client
        mock_asr_client = MagicMock()
        mock_asr_client.transcribe.return_value = ASRResult(
            text="转写文本", segments=[], source="mimo_asr", confidence=0.9
        )
        mock_get_asr.return_value = mock_asr_client

        from src.pipeline.scheduler import run_once
        run_once(db_path, config)

        # 验证调用链
        mock_dl_fallback.assert_called_once()
        mock_dl_only.assert_called_once()
        mock_extract_audio.assert_called_once()
        mock_asr_client.transcribe.assert_called_once()

        # 验证 subtitle_source
        task = db.get_task(conn, task_id)
        assert task["status"] == "done"

        # 验证 frontmatter 中 subtitle_source=mimo_asr
        fm_call = mock_fm.call_args[0][0]
        assert fm_call["subtitle_source"] == "mimo_asr"


# ── Test 2: 无字幕 + whisper_local → ASR ──────────────────────────────────


class TestNoSubtitleWithWhisperLocalAsr:
    """无字幕 + whisper_local provider → WhisperLocalClient"""

    @patch("src.pipeline.scheduler.get_asr_client")
    @patch("src.pipeline.scheduler.extract_audio_for_asr")
    @patch("src.pipeline.scheduler.download_video_only")
    @patch("src.asr.audio_preprocess.split_audio_chunks")
    @patch("src.pipeline.scheduler.write_note", return_value=Path("note.md"))
    @patch("src.pipeline.scheduler.build_note_body", return_value="body")
    @patch("src.pipeline.scheduler.build_frontmatter", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.extract_metadata", return_value={"title": "t"})
    @patch("src.pipeline.scheduler._download_with_fallback")
    @patch("src.pipeline.scheduler.resolve_url", return_value={
        "canonical_url": "https://canonical.url/",
        "source_url_type": "full",
        "video_id": "1234567890123"
    })
    def test_no_subtitle_whisper_local_provider_uses_asr(
        self, mock_resolve, mock_dl_fallback, mock_meta, mock_fm, mock_body, mock_write,
        mock_split, mock_dl_only, mock_extract_audio, mock_get_asr, tmp_path
    ):
        from src.asr import ASRResult

        db_path = tmp_path / "test.sqlite3"
        conn = _init_conn(db_path)
        task_id = _enqueue_task(conn)
        config = _make_config(tmp_path, asr_provider="whisper_local")
        tmp_dir = Path(config["downloader"]["temp_dir"])

        # _download_with_fallback 返回无字幕结果
        mock_dl_fallback.return_value = {
            "video_path": tmp_dir / "1234567890123.mp4",
            "subtitle_path": None,
            "subtitle_source": None,
            "downloader_used": "yt-dlp",
            "info_dict": {"title": "Test"},
        }

        # download_video_only 返回视频
        mock_dl_only.return_value = {"video_path": tmp_dir / "1234567890123.mp4"}

        # extract_audio_for_asr 返回 WAV 路径
        wav_path = tmp_dir / "1234567890123.wav"
        mock_extract_audio.return_value = wav_path

        # split_audio_chunks 返回单片（不需要分片）
        mock_split.return_value = [wav_path]

        # get_asr_client 返回 mock whisper client
        mock_asr_client = MagicMock()
        mock_asr_client.transcribe.return_value = ASRResult(
            text="转写文本", segments=[], source="whisper_local", confidence=0.0
        )
        mock_get_asr.return_value = mock_asr_client

        from src.pipeline.scheduler import run_once
        run_once(db_path, config)

        # 验证调用链
        mock_dl_fallback.assert_called_once()
        mock_dl_only.assert_called_once()
        mock_extract_audio.assert_called_once()
        mock_asr_client.transcribe.assert_called_once()

        # 验证 subtitle_source
        task = db.get_task(conn, task_id)
        assert task["status"] == "done"

        fm_call = mock_fm.call_args[0][0]
        assert fm_call["subtitle_source"] == "whisper_local_asr"


# ── Test 3: ASR 失败 → failed ──────────────────────────────────────────────


class TestAsrFailure:
    """ASR 失败 → failed(asr_failed)"""

    @patch("src.pipeline.scheduler.get_asr_client")
    @patch("src.pipeline.scheduler.extract_audio_for_asr")
    @patch("src.pipeline.scheduler.download_video_only")
    @patch("src.pipeline.scheduler._download_with_fallback")
    @patch("src.pipeline.scheduler.resolve_url", return_value={
        "canonical_url": "https://canonical.url/",
        "source_url_type": "full",
        "video_id": "1234567890123"
    })
    def test_asr_failure_task_becomes_failed(
        self, mock_resolve, mock_dl_fallback, mock_dl_only, mock_extract_audio, mock_get_asr, tmp_path
    ):
        from src.asr import ASRError

        db_path = tmp_path / "test.sqlite3"
        conn = _init_conn(db_path)
        task_id = _enqueue_task(conn)
        config = _make_config(tmp_path, asr_provider="mimo")
        tmp_dir = Path(config["downloader"]["temp_dir"])

        # _download_with_fallback 返回无字幕结果
        mock_dl_fallback.return_value = {
            "video_path": tmp_dir / "1234567890123.mp4",
            "subtitle_path": None,
            "subtitle_source": None,
            "downloader_used": "yt-dlp",
            "info_dict": {"title": "Test"},
        }

        # download_video_only 返回视频
        mock_dl_only.return_value = {"video_path": tmp_dir / "1234567890123.mp4"}

        # extract_audio_for_asr 返回 WAV
        wav_path = tmp_dir / "1234567890123.wav"
        mock_extract_audio.return_value = wav_path

        # get_asr_client 返回 mock client，transcribe 抛 ASRError
        mock_asr_client = MagicMock()
        mock_asr_client.transcribe.side_effect = ASRError("asr_timeout")
        mock_get_asr.return_value = mock_asr_client

        from src.pipeline.scheduler import run_once
        run_once(db_path, config)

        task = db.get_task(conn, task_id)
        assert task["status"] == "failed"
        assert task["error_code"] == "asr_failed"


# ── Test 4: 有字幕 → 不调 ASR（M1 行为不变）────────────────────────────────


class TestWithSubtitleNoAsr:
    """有字幕 → 不调 ASR（M1 行为不变）"""

    @patch("src.pipeline.scheduler.get_asr_client")
    @patch("src.pipeline.scheduler.extract_audio_for_asr")
    @patch("src.pipeline.scheduler.download_video_only")
    @patch("src.pipeline.scheduler.write_note", return_value=Path("note.md"))
    @patch("src.pipeline.scheduler.build_note_body", return_value="body")
    @patch("src.pipeline.scheduler.build_frontmatter", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.extract_metadata", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.download_video")
    @patch("src.pipeline.scheduler.resolve_url", return_value={
        "canonical_url": "https://canonical.url/",
        "source_url_type": "full",
        "video_id": "1234567890123"
    })
    def test_with_subtitle_no_asr_called(
        self, mock_resolve, mock_download, mock_meta, mock_fm, mock_body, mock_write,
        mock_dl_only, mock_extract_audio, mock_get_asr, tmp_path
    ):
        db_path = tmp_path / "test.sqlite3"
        conn = _init_conn(db_path)
        task_id = _enqueue_task(conn)
        config = _make_config(tmp_path, asr_provider="mimo")
        tmp_dir = Path(config["downloader"]["temp_dir"])

        # download_video 返回带字幕的结果
        tmp_dir.mkdir(parents=True, exist_ok=True)
        video_path = tmp_dir / "1234567890123.mp4"
        subtitle_path = tmp_dir / "1234567890123.zh.vtt"
        video_path.write_bytes(b"fake video")
        subtitle_path.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhello\n")

        mock_download.return_value = {
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

        from src.pipeline.scheduler import run_once
        run_once(db_path, config)

        # M1 行为：有字幕时走 download_video，不走 download_video_only
        mock_download.assert_called_once()
        mock_dl_only.assert_not_called()
        mock_extract_audio.assert_not_called()
        mock_get_asr.assert_not_called()

        task = db.get_task(conn, task_id)
        assert task["status"] == "done"


# ── Test 5: download_video_only 函数存在 ────────────────────────────────────


class TestDownloadVideoOnlyExists:
    """download_video_only 函数存在且只下载视频不抓字幕"""

    def test_download_video_only_exists_and_callable(self):
        """验证 download_video_only 函数存在且签名正确。"""
        from src.extractors.downloader import download_video_only
        import inspect

        # 验证函数存在且可调用
        assert callable(download_video_only)

        # 验证签名：url, out_dir, cookies_path
        sig = inspect.signature(download_video_only)
        params = list(sig.parameters.keys())
        assert "url" in params
        assert "out_dir" in params
        assert "cookies_path" in params

    def test_download_video_only_no_subtitles_in_opts(self):
        """验证 download_video_only 不请求字幕。"""
        from src.extractors import downloader
        import inspect

        # 获取源码
        source = inspect.getsource(downloader.download_video_only)

        # 验证不包含字幕相关选项
        assert "writesubtitles" not in source
        assert "writeautomaticsub" not in source
        assert "subtitleslangs" not in source
