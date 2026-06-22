"""Test pipeline/scheduler.py M3 集成 — LLM 总结 + 视觉理解。

TDD: 6 tests covering:
1. LLM 总结成功 → 笔记 ## 摘要 含要点 + summary_status=done
2. LLM 总结失败 → 笔记 ## 摘要 含降级文字 + summary_status=failed
3. vision.enabled=true + 口播类 → 关键帧段写"视觉理解已禁用"（summary_only 不触发 VLM）
4. vision.enabled=true + PPT 类 → 关键帧段含 OCR 文字 + VLM 描述
5. vision.enabled=false → 关键帧段写"视觉理解已禁用"
6. LLM + VLM 串行（不并行）验证
"""
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from src.queue import db
from src.llm import SummaryResult, LLMError
from src.vision.heuristic_router import RoutingDecision


@pytest.fixture(autouse=True)
def _reset_structlog():
    """每个测试前后重置 structlog 状态。"""
    from src.utils.logging_config import _reset_logging
    _reset_logging()
    yield
    _reset_logging()


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_config(tmp_path: Path, vision_enabled: bool = False) -> dict:
    """构造测试用 config dict。"""
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
        "llm": {"provider": "mimo"},
        "vision": {"enabled": vision_enabled},
    }


def _init_conn(db_path) -> sqlite3.Connection:
    """用 db.init_db 初始化。"""
    return db.init_db(db_path)


def _enqueue_task(conn, correlation_id: str | None = None) -> int:
    """入队一条测试任务。"""
    cid = correlation_id or str(uuid.uuid4())
    return db.enqueue(
        conn,
        video_id="1234567890123",
        source_url="https://v.douyin.com/test/",
        source_url_type="short_link",
        correlation_id=cid,
    )


def _mock_download_result(tmp_dir: Path, video_id: str = "1234567890123") -> dict:
    """构造 download_video 成功返回值。"""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    video_path = tmp_dir / f"{video_id}.mp4"
    subtitle_path = tmp_dir / f"{video_id}.zh.vtt"
    video_path.write_bytes(b"fake video")
    subtitle_path.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhello world test subtitle\n")
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


# ── Test 1: LLM 总结成功 ──────────────────────────────────────────────────


class TestLLMSummarySuccess:
    """LLM 总结成功 → 笔记 ## 摘要 含要点 + summary_status=done"""

    @patch("src.pipeline.scheduler.write_note")
    @patch("src.pipeline.scheduler.build_note_body")
    @patch("src.pipeline.scheduler.build_frontmatter")
    @patch("src.pipeline.scheduler.extract_metadata", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.download_video")
    @patch("src.pipeline.scheduler.resolve_url", return_value={"canonical_url": "https://canonical.url/", "source_url_type": "full", "video_id": "1234567890123"})
    def test_llm_success_writes_key_points(
        self, mock_resolve, mock_download, mock_meta,
        mock_fm, mock_body, mock_write, tmp_path
    ):
        db_path = tmp_path / "test.sqlite3"
        conn = _init_conn(db_path)
        task_id = _enqueue_task(conn)
        config = _make_config(tmp_path)

        mock_download.return_value = _mock_download_result(Path(config["downloader"]["temp_dir"]))
        mock_write.return_value = Path("note.md")

        # Mock LLM 成功返回
        mock_summary = SummaryResult(
            summary_text="总结文本",
            key_points=["要点1", "要点2", "要点3"],
            model="mimo-v2.5-pro",
            source="mimo_llm",
            confidence=0.9,
        )

        # Mock build_note_body 返回包含 key_points 的内容
        def fake_build_note_body(**kwargs):
            summary = kwargs.get("summary_result")
            if summary and summary.key_points:
                points = "\n".join(f"- {p}" for p in summary.key_points)
                return f"## 摘要\n\n{points}\n"
            return "## 摘要\n\n无内容\n"

        mock_body.side_effect = fake_build_note_body

        # Mock build_frontmatter 返回包含 summary_status 的 dict
        def fake_build_frontmatter(data):
            fm = {k: data[k] for k in data}
            fm["summary_status"] = data.get("summary_status", "not_run")
            fm["ai_summary_model"] = data.get("ai_summary_model")
            fm["processing_mode"] = data.get("processing_mode", "subtitle_only")
            fm["summary"] = data.get("summary", "")
            return fm

        mock_fm.side_effect = fake_build_frontmatter

        with patch("src.pipeline.scheduler.get_summarizer") as mock_get_summarizer:
            mock_summarizer = MagicMock()
            mock_summarizer.summarize.return_value = mock_summary
            mock_get_summarizer.return_value = mock_summarizer

            from src.pipeline.scheduler import run_once
            run_once(db_path, config)

        task = db.get_task(conn, task_id)
        assert task is not None
        assert task["status"] == "done"

        # 验证 build_note_body 被调用时传入了 summary_result
        mock_body.assert_called_once()
        call_kwargs = mock_body.call_args[1]
        assert call_kwargs["summary_result"] is not None
        assert call_kwargs["summary_result"].key_points == ["要点1", "要点2", "要点3"]

        # 验证 build_frontmatter 传入了 summary_status=done
        mock_fm.assert_called_once()
        fm_data = mock_fm.call_args[0][0]
        assert fm_data["summary_status"] == "done"
        assert fm_data["ai_summary_model"] == "mimo-v2.5-pro"


# ── Test 2: LLM 总结失败 ──────────────────────────────────────────────────


class TestLLMSummaryFailure:
    """LLM 总结失败 → 笔记 ## 摘要 含降级文字 + summary_status=failed"""

    @patch("src.pipeline.scheduler.write_note")
    @patch("src.pipeline.scheduler.build_note_body")
    @patch("src.pipeline.scheduler.build_frontmatter")
    @patch("src.pipeline.scheduler.extract_metadata", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.download_video")
    @patch("src.pipeline.scheduler.resolve_url", return_value={"canonical_url": "https://canonical.url/", "source_url_type": "full", "video_id": "1234567890123"})
    def test_llm_failure_writes_fallback(
        self, mock_resolve, mock_download, mock_meta,
        mock_fm, mock_body, mock_write, tmp_path
    ):
        db_path = tmp_path / "test.sqlite3"
        conn = _init_conn(db_path)
        task_id = _enqueue_task(conn)
        config = _make_config(tmp_path)

        mock_download.return_value = _mock_download_result(Path(config["downloader"]["temp_dir"]))
        mock_write.return_value = Path("note.md")

        def fake_build_note_body(**kwargs):
            summary = kwargs.get("summary_result")
            error_msg = kwargs.get("summary_error")
            if summary and summary.key_points:
                points = "\n".join(f"- {p}" for p in summary.key_points)
                return f"## 摘要\n\n{points}\n"
            elif error_msg:
                return f"## 摘要\n\nLLM 总结失败：{error_msg}\n"
            return "## 摘要\n\n无内容\n"

        mock_body.side_effect = fake_build_note_body

        def fake_build_frontmatter(data):
            fm = {k: data[k] for k in data}
            fm["summary_status"] = data.get("summary_status", "not_run")
            fm["ai_summary_model"] = data.get("ai_summary_model")
            fm["processing_mode"] = data.get("processing_mode", "subtitle_only")
            fm["summary"] = data.get("summary", "")
            return fm

        mock_fm.side_effect = fake_build_frontmatter

        with patch("src.pipeline.scheduler.get_summarizer") as mock_get_summarizer:
            mock_summarizer = MagicMock()
            mock_summarizer.summarize.side_effect = LLMError("llm_timeout", "API 超时")
            mock_get_summarizer.return_value = mock_summarizer

            from src.pipeline.scheduler import run_once
            run_once(db_path, config)

        task = db.get_task(conn, task_id)
        assert task is not None
        assert task["status"] == "done"

        # 验证 build_note_body 被调用时传入了 summary_error
        mock_body.assert_called_once()
        call_kwargs = mock_body.call_args[1]
        assert call_kwargs.get("summary_result") is None
        assert "llm_timeout" in call_kwargs.get("summary_error", "")

        # 验证 build_frontmatter 传入了 summary_status=failed
        mock_fm.assert_called_once()
        fm_data = mock_fm.call_args[0][0]
        assert fm_data["summary_status"] == "failed"


# ── Test 3: vision.enabled=true + 口播类 → 关键帧段写"视觉理解已禁用" ─────


class TestVisionEnabledSummaryOnly:
    """vision.enabled=true + 口播类 → 关键帧段写"视觉理解已禁用"（summary_only 不触发 VLM）"""

    @patch("src.pipeline.scheduler.write_note")
    @patch("src.pipeline.scheduler.build_note_body")
    @patch("src.pipeline.scheduler.build_frontmatter")
    @patch("src.pipeline.scheduler.extract_metadata", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.download_video")
    @patch("src.pipeline.scheduler.resolve_url", return_value={"canonical_url": "https://canonical.url/", "source_url_type": "full", "video_id": "1234567890123"})
    def test_summary_only_skips_vlm(
        self, mock_resolve, mock_download, mock_meta,
        mock_fm, mock_body, mock_write, tmp_path
    ):
        db_path = tmp_path / "test.sqlite3"
        conn = _init_conn(db_path)
        task_id = _enqueue_task(conn)
        config = _make_config(tmp_path, vision_enabled=True)

        mock_download.return_value = _mock_download_result(Path(config["downloader"]["temp_dir"]))
        mock_write.return_value = Path("note.md")

        def fake_build_note_body(**kwargs):
            vlm_result = kwargs.get("vlm_result")
            if vlm_result:
                return "## 关键帧\n\nVLM 描述内容\n"
            return "## 关键帧\n\n视觉理解已禁用\n"

        mock_body.side_effect = fake_build_note_body

        def fake_build_frontmatter(data):
            fm = {k: data[k] for k in data}
            fm["summary_status"] = data.get("summary_status", "not_run")
            fm["ai_summary_model"] = data.get("ai_summary_model")
            fm["processing_mode"] = data.get("processing_mode", "subtitle_only")
            fm["summary"] = data.get("summary", "")
            return fm

        mock_fm.side_effect = fake_build_frontmatter

        with patch("src.pipeline.scheduler.get_summarizer") as mock_get_summarizer, \
             patch("src.pipeline.scheduler.classify_video", return_value=RoutingDecision.SUMMARY_ONLY):
            mock_summarizer = MagicMock()
            mock_summarizer.summarize.return_value = SummaryResult(
                summary_text="总结", key_points=["要点1"], model="mimo-v2.5-pro",
                source="mimo_llm", confidence=0.9,
            )
            mock_get_summarizer.return_value = mock_summarizer

            from src.pipeline.scheduler import run_once
            run_once(db_path, config)

        task = db.get_task(conn, task_id)
        assert task["status"] == "done"

        # 验证 build_note_body 被调用时 vlm_result 为 None（summary_only 不触发 VLM）
        mock_body.assert_called_once()
        call_kwargs = mock_body.call_args[1]
        assert call_kwargs.get("vlm_result") is None

        # 验证 processing_mode
        mock_fm.assert_called_once()
        fm_data = mock_fm.call_args[0][0]
        assert fm_data["processing_mode"] == "subtitle_only"


# ── Test 4: vision.enabled=true + PPT 类 → 关键帧段含 OCR + VLM ──────────


class TestVisionEnabledSummaryWithVLM:
    """vision.enabled=true + PPT 类 → 关键帧段含 OCR 文字 + VLM 描述"""

    @patch("src.pipeline.scheduler.write_note")
    @patch("src.pipeline.scheduler.build_note_body")
    @patch("src.pipeline.scheduler.build_frontmatter")
    @patch("src.pipeline.scheduler.extract_metadata", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.download_video")
    @patch("src.pipeline.scheduler.resolve_url", return_value={"canonical_url": "https://canonical.url/", "source_url_type": "full", "video_id": "1234567890123"})
    def test_ppt_video_triggers_vlm(
        self, mock_resolve, mock_download, mock_meta,
        mock_fm, mock_body, mock_write, tmp_path
    ):
        db_path = tmp_path / "test.sqlite3"
        conn = _init_conn(db_path)
        task_id = _enqueue_task(conn)
        config = _make_config(tmp_path, vision_enabled=True)

        mock_download.return_value = _mock_download_result(Path(config["downloader"]["temp_dir"]))
        mock_write.return_value = Path("note.md")

        def fake_build_note_body(**kwargs):
            vlm_result = kwargs.get("vlm_result")
            ocr_texts = kwargs.get("ocr_texts")
            if vlm_result:
                parts = []
                if ocr_texts:
                    parts.append("OCR: " + "; ".join(ocr_texts))
                parts.append("VLM: " + vlm_result)
                return "## 关键帧\n\n" + "\n".join(parts) + "\n"
            return "## 关键帧\n\n视觉理解已禁用\n"

        mock_body.side_effect = fake_build_note_body

        def fake_build_frontmatter(data):
            fm = {k: data[k] for k in data}
            fm["summary_status"] = data.get("summary_status", "not_run")
            fm["ai_summary_model"] = data.get("ai_summary_model")
            fm["processing_mode"] = data.get("processing_mode", "subtitle_only")
            fm["summary"] = data.get("summary", "")
            return fm

        mock_fm.side_effect = fake_build_frontmatter

        with patch("src.pipeline.scheduler.get_summarizer") as mock_get_summarizer, \
             patch("src.pipeline.scheduler.classify_video", return_value=RoutingDecision.SUMMARY_WITH_VLM), \
             patch("src.pipeline.scheduler.extract_keyframes") as mock_extract, \
             patch("src.pipeline.scheduler.extract_text_from_image", return_value="OCR 文字内容"), \
             patch("src.pipeline.scheduler.get_vlm_client") as mock_get_vlm:
            mock_summarizer = MagicMock()
            mock_summarizer.summarize.return_value = SummaryResult(
                summary_text="总结", key_points=["要点1"], model="mimo-v2.5-pro",
                source="mimo_llm", confidence=0.9,
            )
            mock_get_summarizer.return_value = mock_summarizer
            mock_extract.return_value = [Path("/tmp/frame1.jpg")]
            mock_vlm_client = MagicMock()
            mock_vlm_client.describe_image.return_value = "PPT 展示了流程图"
            mock_get_vlm.return_value = mock_vlm_client

            from src.pipeline.scheduler import run_once
            run_once(db_path, config)

        task = db.get_task(conn, task_id)
        assert task["status"] == "done"

        # 验证 build_note_body 被调用时 vlm_result 非空
        mock_body.assert_called_once()
        call_kwargs = mock_body.call_args[1]
        assert call_kwargs.get("vlm_result") is not None
        assert "PPT" in call_kwargs["vlm_result"]
        assert call_kwargs.get("ocr_texts") is not None

        # 验证 processing_mode=subtitle_vlm
        mock_fm.assert_called_once()
        fm_data = mock_fm.call_args[0][0]
        assert fm_data["processing_mode"] == "subtitle_vlm"


# ── Test 5: vision.enabled=false → 关键帧段写"视觉理解已禁用" ─────────────


class TestVisionDisabled:
    """vision.enabled=false → 关键帧段写"视觉理解已禁用" """

    @patch("src.pipeline.scheduler.write_note")
    @patch("src.pipeline.scheduler.build_note_body")
    @patch("src.pipeline.scheduler.build_frontmatter")
    @patch("src.pipeline.scheduler.extract_metadata", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.download_video")
    @patch("src.pipeline.scheduler.resolve_url", return_value={"canonical_url": "https://canonical.url/", "source_url_type": "full", "video_id": "1234567890123"})
    def test_vision_disabled_writes_placeholder(
        self, mock_resolve, mock_download, mock_meta,
        mock_fm, mock_body, mock_write, tmp_path
    ):
        db_path = tmp_path / "test.sqlite3"
        conn = _init_conn(db_path)
        task_id = _enqueue_task(conn)
        config = _make_config(tmp_path, vision_enabled=False)

        mock_download.return_value = _mock_download_result(Path(config["downloader"]["temp_dir"]))
        mock_write.return_value = Path("note.md")

        def fake_build_note_body(**kwargs):
            vlm_result = kwargs.get("vlm_result")
            if vlm_result:
                return "## 关键帧\n\nVLM 描述\n"
            return "## 关键帧\n\n视觉理解已禁用\n"

        mock_body.side_effect = fake_build_note_body

        def fake_build_frontmatter(data):
            fm = {k: data[k] for k in data}
            fm["summary_status"] = data.get("summary_status", "not_run")
            fm["ai_summary_model"] = data.get("ai_summary_model")
            fm["processing_mode"] = data.get("processing_mode", "subtitle_only")
            fm["summary"] = data.get("summary", "")
            return fm

        mock_fm.side_effect = fake_build_frontmatter

        with patch("src.pipeline.scheduler.get_summarizer") as mock_get_summarizer:
            mock_summarizer = MagicMock()
            mock_summarizer.summarize.return_value = SummaryResult(
                summary_text="总结", key_points=["要点1"], model="mimo-v2.5-pro",
                source="mimo_llm", confidence=0.9,
            )
            mock_get_summarizer.return_value = mock_summarizer

            from src.pipeline.scheduler import run_once
            run_once(db_path, config)

        task = db.get_task(conn, task_id)
        assert task["status"] == "done"

        # 验证 build_note_body 被调用时 vlm_result 为 None
        mock_body.assert_called_once()
        call_kwargs = mock_body.call_args[1]
        assert call_kwargs.get("vlm_result") is None

        # 验证 processing_mode=subtitle_only
        mock_fm.assert_called_once()
        fm_data = mock_fm.call_args[0][0]
        assert fm_data["processing_mode"] == "subtitle_only"


# ── Test 6: LLM + VLM 串行（不并行）验证 ──────────────────────────────────


class TestLLMVLMSerial:
    """LLM + VLM 串行（不并行）验证"""

    @patch("src.pipeline.scheduler.write_note")
    @patch("src.pipeline.scheduler.build_note_body")
    @patch("src.pipeline.scheduler.build_frontmatter")
    @patch("src.pipeline.scheduler.extract_metadata", return_value={"title": "t"})
    @patch("src.pipeline.scheduler.download_video")
    @patch("src.pipeline.scheduler.resolve_url", return_value={"canonical_url": "https://canonical.url/", "source_url_type": "full", "video_id": "1234567890123"})
    def test_llm_and_vlm_run_serially(
        self, mock_resolve, mock_download, mock_meta,
        mock_fm, mock_body, mock_write, tmp_path
    ):
        db_path = tmp_path / "test.sqlite3"
        conn = _init_conn(db_path)
        task_id = _enqueue_task(conn)
        config = _make_config(tmp_path, vision_enabled=True)

        mock_download.return_value = _mock_download_result(Path(config["downloader"]["temp_dir"]))
        mock_write.return_value = Path("note.md")

        mock_body.return_value = "## 摘要\n\n要点\n"
        mock_fm.return_value = {"summary_status": "done", "processing_mode": "subtitle_vlm"}

        call_order = []

        def track_llm_call(*args, **kwargs):
            call_order.append("llm")
            return SummaryResult(
                summary_text="总结", key_points=["要点1"], model="mimo-v2.5-pro",
                source="mimo_llm", confidence=0.9,
            )

        def track_vlm_call(*args, **kwargs):
            call_order.append("vlm")
            return "PPT 描述"

        mock_vlm_client = MagicMock()
        mock_vlm_client.describe_image.side_effect = track_vlm_call

        with patch("src.pipeline.scheduler.get_summarizer") as mock_get_summarizer, \
             patch("src.pipeline.scheduler.classify_video", return_value=RoutingDecision.SUMMARY_WITH_VLM), \
             patch("src.pipeline.scheduler.extract_keyframes") as mock_extract, \
             patch("src.pipeline.scheduler.extract_text_from_image", return_value="OCR"), \
             patch("src.pipeline.scheduler.get_vlm_client", return_value=mock_vlm_client):
            mock_summarizer = MagicMock()
            mock_summarizer.summarize.side_effect = track_llm_call
            mock_get_summarizer.return_value = mock_summarizer
            mock_extract.return_value = [Path("/tmp/frame1.jpg")]

            from src.pipeline.scheduler import run_once
            run_once(db_path, config)

        task = db.get_task(conn, task_id)
        assert task["status"] == "done"

        # 验证 LLM 先执行，VLM 后执行（串行）
        assert call_order == ["llm", "vlm"], f"Expected serial execution [llm, vlm], got {call_order}"
