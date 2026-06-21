"""M3 E2E tests — LLM summary + vision understanding pipeline integration.

Scenario 1: Video WITH subtitles -> AI summary (summary_status=done)
Scenario 2: Video WITHOUT subtitles -> ASR + LLM summary
Scenario 3: LLM timeout -> note still has subtitle (summary_status=failed)
Scenario 4: vision.enabled=false -> keyframe section shows "视觉理解已禁用"
Scenario 5: vision.enabled=true + 口播类 -> keyframe section not triggered (summary_only)

These tests mock external dependencies (yt-dlp, ASR, LLM, VLM) and test the full
pipeline integration from API ingest to vault note creation.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport

from src.bridge.main import create_app
from src.llm import SummaryResult
from src.queue import db
from src.vision.heuristic_router import RoutingDecision


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def m3_client(tmp_path: Path):
    """Create httpx client wired to FastAPI + fresh SQLite + vault."""
    db_path = tmp_path / "m3_e2e.sqlite3"
    vault_root = tmp_path / "vault"
    (vault_root / "inbox" / "douyin").mkdir(parents=True, exist_ok=True)

    conn = db.init_db(db_path)
    app = create_app(conn=conn, vault_root=vault_root)

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, conn, vault_root


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ---------------------------------------------------------------------------
# Scenario 1 — Video WITH subtitles -> AI summary (summary_status=done)
# ---------------------------------------------------------------------------

class TestScenario1SubtitleWithLLM:
    """Video with subtitles + LLM enabled -> note contains AI summary."""

    @pytest.mark.anyio
    async def test_video_with_subtitles_has_ai_summary(self, m3_client, tmp_path):
        """Ingest video with subtitles -> LLM summarizes -> note has summary_status=done."""
        client, conn, vault_root = m3_client

        mock_resolve = {
            "video_id": "700001",
            "canonical_url": "https://www.douyin.com/video/700001",
            "source_url_type": "full",
        }

        mock_download = {
            "video_path": tmp_path / "700001.mp4",
            "subtitle_path": tmp_path / "700001.zh.vtt",
            "subtitle_source": "douyin_native",
            "downloader_used": "yt-dlp",
            "info_dict": {
                "title": "Test Video LLM Summary",
                "duration": 120,
                "uploader": "test_author",
                "uploader_url": "https://www.douyin.com/user/123",
                "thumbnail": "https://example.com/thumb.jpg",
            },
            "title": "Test Video LLM Summary",
            "duration": 120,
            "uploader": "test_author",
            "uploader_url": "https://www.douyin.com/user/123",
            "thumbnail": "https://example.com/thumb.jpg",
        }

        # Create fake subtitle file
        (tmp_path / "700001.zh.vtt").write_text(
            "WEBVTT\n\n00:00:01.000 --> 00:00:05.000\n这是测试字幕内容\n",
            encoding="utf-8",
        )

        # Mock LLM summarizer
        mock_summary = SummaryResult(
            summary_text="这是一段测试总结",
            key_points=["要点一：测试内容", "要点二：验证流程"],
            model="mimo-v2.5-pro",
            source="mimo_llm",
        )
        mock_summarizer = MagicMock()
        mock_summarizer.summarize.return_value = mock_summary

        with patch("src.bridge.main.resolve_url", return_value=mock_resolve), \
             patch("src.pipeline.scheduler.resolve_url", return_value=mock_resolve), \
             patch("src.pipeline.scheduler.download_video", return_value=mock_download), \
             patch("src.pipeline.scheduler.download_with_douk") as mock_douk, \
             patch("src.pipeline.scheduler.get_asr_client") as mock_asr_factory, \
             patch("src.pipeline.scheduler.get_summarizer", return_value=mock_summarizer):

            # Enqueue
            resp = await client.post(
                "/ingest",
                json={"source_url": "https://www.douyin.com/video/700001"},
            )
            assert resp.status_code == 200
            task_id = resp.json()["task_id"]

            # Simulate scheduler
            from src.pipeline.scheduler import process_task
            task = db.atomic_dequeue(conn)
            assert task is not None
            assert task["video_id"] == "700001"
            config = {
                "downloader": {"temp_dir": str(tmp_path), "yt_dlp_retries": 1},
                "vault": {"root": str(vault_root)},
                "asr": {"provider": "mimo"},
                "llm": {"provider": "mimo"},
                "vision": {"enabled": False},
            }
            process_task(conn, task, config)

            # Verify: LLM WAS called
            mock_summarizer.summarize.assert_called_once()

            # Verify: task is done
            updated = db.get_task(conn, task_id)
            assert updated["status"] == "done"

            # Verify: note exists with AI summary
            note_files = list(vault_root.rglob("700001.md"))
            assert len(note_files) == 1
            note_content = note_files[0].read_text(encoding="utf-8")
            assert "summary_status: done" in note_content
            assert "要点一" in note_content


# ---------------------------------------------------------------------------
# Scenario 2 — Video WITHOUT subtitles -> ASR + LLM summary
# ---------------------------------------------------------------------------

class TestScenario2ASRWithLLM:
    """Video without subtitles -> ASR transcribes -> LLM summarizes."""

    @pytest.mark.anyio
    async def test_no_subtitles_asr_then_llm(self, m3_client, tmp_path):
        """Ingest video without subtitles -> ASR + LLM -> note has transcript + summary."""
        client, conn, vault_root = m3_client

        mock_resolve = {
            "video_id": "700002",
            "canonical_url": "https://www.douyin.com/video/700002",
            "source_url_type": "full",
        }

        from src.extractors.downloader import NoSubtitleError

        mock_download_only = {
            "video_path": tmp_path / "700002.mp4",
            "video_id": "700002",
            "info_dict": {
                "title": "Test Video ASR+LLM",
                "duration": 60,
                "uploader": "test_author2",
                "uploader_url": "https://www.douyin.com/user/456",
                "thumbnail": "https://example.com/thumb2.jpg",
            },
            "title": "Test Video ASR+LLM",
            "duration": 60,
            "uploader": "test_author2",
            "uploader_url": "https://www.douyin.com/user/456",
            "thumbnail": "https://example.com/thumb2.jpg",
        }

        # Mock ASR result
        mock_asr_result = MagicMock()
        mock_asr_result.text = "这是ASR转写的测试文本内容"
        mock_asr_result.source = "mimo_asr"
        mock_asr_result.segments = [{"start": 0.0, "end": 3.0, "text": "这是ASR转写的测试文本内容"}]

        mock_asr_client = MagicMock()
        mock_asr_client.transcribe.return_value = mock_asr_result

        # Mock LLM summarizer
        mock_summary = SummaryResult(
            summary_text="ASR转写后的总结",
            key_points=["要点一：ASR转写成功", "要点二：LLM总结成功"],
            model="mimo-v2.5-pro",
            source="mimo_llm",
        )
        mock_summarizer = MagicMock()
        mock_summarizer.summarize.return_value = mock_summary

        # Create fake video file
        (tmp_path / "700002.mp4").write_bytes(b"fake video")

        with patch("src.bridge.main.resolve_url", return_value=mock_resolve), \
             patch("src.pipeline.scheduler.resolve_url", return_value=mock_resolve), \
             patch("src.pipeline.scheduler.download_video", side_effect=NoSubtitleError("no_subtitle_in_m1")), \
             patch("src.pipeline.scheduler.download_video_only", return_value=mock_download_only), \
             patch("src.pipeline.scheduler.download_with_douk", side_effect=NoSubtitleError("no_subtitle_in_m1")), \
             patch("src.pipeline.scheduler.get_asr_client", return_value=mock_asr_client), \
             patch("src.pipeline.scheduler.extract_audio_for_asr") as mock_extract, \
             patch("src.pipeline.scheduler.get_summarizer", return_value=mock_summarizer):

            def fake_extract(video_path, wav_path):
                wav_path.write_bytes(b"fake wav")
                return wav_path
            mock_extract.side_effect = fake_extract

            # Enqueue
            resp = await client.post(
                "/ingest",
                json={"source_url": "https://www.douyin.com/video/700002"},
            )
            assert resp.status_code == 200
            task_id = resp.json()["task_id"]

            # Simulate scheduler
            from src.pipeline.scheduler import process_task
            task = db.atomic_dequeue(conn)
            assert task is not None
            assert task["video_id"] == "700002"
            config = {
                "downloader": {"temp_dir": str(tmp_path), "yt_dlp_retries": 1},
                "vault": {"root": str(vault_root)},
                "asr": {"provider": "mimo"},
                "llm": {"provider": "mimo"},
                "vision": {"enabled": False},
            }
            process_task(conn, task, config)

            # Verify: ASR WAS called
            mock_asr_client.transcribe.assert_called_once()

            # Verify: LLM WAS called (with ASR transcript)
            mock_summarizer.summarize.assert_called_once()

            # Verify: task is done
            updated = db.get_task(conn, task_id)
            assert updated["status"] == "done"

            # Verify: note exists with transcript + summary
            note_files = list(vault_root.rglob("700002.md"))
            assert len(note_files) == 1
            note_content = note_files[0].read_text(encoding="utf-8")
            assert "summary_status: done" in note_content
            assert "ASR" in note_content or "转写" in note_content


# ---------------------------------------------------------------------------
# Scenario 3 — LLM timeout -> note still has subtitle (summary_status=failed)
# ---------------------------------------------------------------------------

class TestScenario3LLMTimeout:
    """LLM timeout -> note still created with subtitle, summary_status=failed."""

    @pytest.mark.anyio
    async def test_llm_timeout_preserves_subtitle(self, m3_client, tmp_path):
        """Ingest video -> LLM times out -> note has subtitle + summary_status=failed."""
        client, conn, vault_root = m3_client

        mock_resolve = {
            "video_id": "700003",
            "canonical_url": "https://www.douyin.com/video/700003",
            "source_url_type": "full",
        }

        mock_download = {
            "video_path": tmp_path / "700003.mp4",
            "subtitle_path": tmp_path / "700003.zh.vtt",
            "subtitle_source": "douyin_native",
            "downloader_used": "yt-dlp",
            "info_dict": {
                "title": "Test Video LLM Timeout",
                "duration": 90,
                "uploader": "test_author3",
                "uploader_url": "https://www.douyin.com/user/789",
                "thumbnail": "https://example.com/thumb3.jpg",
            },
            "title": "Test Video LLM Timeout",
            "duration": 90,
            "uploader": "test_author3",
            "uploader_url": "https://www.douyin.com/user/789",
            "thumbnail": "https://example.com/thumb3.jpg",
        }

        # Create fake subtitle file
        (tmp_path / "700003.zh.vtt").write_text(
            "WEBVTT\n\n00:00:01.000 --> 00:00:05.000\n超时测试字幕内容\n",
            encoding="utf-8",
        )

        # Mock LLM summarizer to raise timeout
        from src.llm import LLMError
        mock_summarizer = MagicMock()
        mock_summarizer.summarize.side_effect = LLMError("llm_timeout")

        with patch("src.bridge.main.resolve_url", return_value=mock_resolve), \
             patch("src.pipeline.scheduler.resolve_url", return_value=mock_resolve), \
             patch("src.pipeline.scheduler.download_video", return_value=mock_download), \
             patch("src.pipeline.scheduler.download_with_douk") as mock_douk, \
             patch("src.pipeline.scheduler.get_asr_client") as mock_asr_factory, \
             patch("src.pipeline.scheduler.get_summarizer", return_value=mock_summarizer):

            # Enqueue
            resp = await client.post(
                "/ingest",
                json={"source_url": "https://www.douyin.com/video/700003"},
            )
            assert resp.status_code == 200
            task_id = resp.json()["task_id"]

            # Simulate scheduler
            from src.pipeline.scheduler import process_task
            task = db.atomic_dequeue(conn)
            assert task is not None
            assert task["video_id"] == "700003"
            config = {
                "downloader": {"temp_dir": str(tmp_path), "yt_dlp_retries": 1},
                "vault": {"root": str(vault_root)},
                "asr": {"provider": "mimo"},
                "llm": {"provider": "mimo"},
                "vision": {"enabled": False},
            }
            process_task(conn, task, config)

            # Verify: LLM WAS called (and failed)
            mock_summarizer.summarize.assert_called_once()

            # Verify: task is still done (not failed)
            updated = db.get_task(conn, task_id)
            assert updated["status"] == "done"

            # Verify: note exists with subtitle + summary_status=failed
            note_files = list(vault_root.rglob("700003.md"))
            assert len(note_files) == 1
            note_content = note_files[0].read_text(encoding="utf-8")
            assert "summary_status: failed" in note_content
            # Subtitle content should still be present
            assert "超时测试字幕内容" in note_content


# ---------------------------------------------------------------------------
# Scenario 4 — vision.enabled=false -> keyframe section shows disabled
# ---------------------------------------------------------------------------

class TestScenario4VisionDisabled:
    """vision.enabled=false -> keyframe section shows '视觉理解已禁用'."""

    @pytest.mark.anyio
    async def test_vision_disabled_shows_placeholder(self, m3_client, tmp_path):
        """Ingest video -> vision disabled -> note keyframe section shows disabled text."""
        client, conn, vault_root = m3_client

        mock_resolve = {
            "video_id": "700004",
            "canonical_url": "https://www.douyin.com/video/700004",
            "source_url_type": "full",
        }

        mock_download = {
            "video_path": tmp_path / "700004.mp4",
            "subtitle_path": tmp_path / "700004.zh.vtt",
            "subtitle_source": "douyin_native",
            "downloader_used": "yt-dlp",
            "info_dict": {
                "title": "Test Video Vision Disabled",
                "duration": 60,
                "uploader": "test_author4",
                "uploader_url": "https://www.douyin.com/user/101",
                "thumbnail": "https://example.com/thumb4.jpg",
            },
            "title": "Test Video Vision Disabled",
            "duration": 60,
            "uploader": "test_author4",
            "uploader_url": "https://www.douyin.com/user/101",
            "thumbnail": "https://example.com/thumb4.jpg",
        }

        # Create fake subtitle file
        (tmp_path / "700004.zh.vtt").write_text(
            "WEBVTT\n\n00:00:01.000 --> 00:00:05.000\n视觉禁用测试\n",
            encoding="utf-8",
        )

        # Mock LLM summarizer (success)
        mock_summary = SummaryResult(
            summary_text="视觉禁用测试总结",
            key_points=["要点一"],
            model="mimo-v2.5-pro",
            source="mimo_llm",
        )
        mock_summarizer = MagicMock()
        mock_summarizer.summarize.return_value = mock_summary

        with patch("src.bridge.main.resolve_url", return_value=mock_resolve), \
             patch("src.pipeline.scheduler.resolve_url", return_value=mock_resolve), \
             patch("src.pipeline.scheduler.download_video", return_value=mock_download), \
             patch("src.pipeline.scheduler.download_with_douk") as mock_douk, \
             patch("src.pipeline.scheduler.get_asr_client") as mock_asr_factory, \
             patch("src.pipeline.scheduler.get_summarizer", return_value=mock_summarizer):

            # Enqueue
            resp = await client.post(
                "/ingest",
                json={"source_url": "https://www.douyin.com/video/700004"},
            )
            assert resp.status_code == 200
            task_id = resp.json()["task_id"]

            # Simulate scheduler with vision.enabled=False
            from src.pipeline.scheduler import process_task
            task = db.atomic_dequeue(conn)
            assert task is not None
            assert task["video_id"] == "700004"
            config = {
                "downloader": {"temp_dir": str(tmp_path), "yt_dlp_retries": 1},
                "vault": {"root": str(vault_root)},
                "asr": {"provider": "mimo"},
                "llm": {"provider": "mimo"},
                "vision": {"enabled": False},
            }
            process_task(conn, task, config)

            # Verify: task is done
            updated = db.get_task(conn, task_id)
            assert updated["status"] == "done"

            # Verify: note keyframe section shows disabled
            note_files = list(vault_root.rglob("700004.md"))
            assert len(note_files) == 1
            note_content = note_files[0].read_text(encoding="utf-8")
            assert "视觉理解已禁用" in note_content
            assert "summary_status: done" in note_content


# ---------------------------------------------------------------------------
# Scenario 5 — vision.enabled=true + 口播类 -> summary_only (no VLM)
# ---------------------------------------------------------------------------

class TestScenario5VisionEnabledOralType:
    """vision.enabled=true + 口播类 -> keyframe section not triggered (summary_only)."""

    @pytest.mark.anyio
    async def test_vision_oral_type_skips_vlm(self, m3_client, tmp_path):
        """Ingest video -> vision enabled + oral type -> no VLM processing."""
        client, conn, vault_root = m3_client

        mock_resolve = {
            "video_id": "700005",
            "canonical_url": "https://www.douyin.com/video/700005",
            "source_url_type": "full",
        }

        mock_download = {
            "video_path": tmp_path / "700005.mp4",
            "subtitle_path": tmp_path / "700005.zh.vtt",
            "subtitle_source": "douyin_native",
            "downloader_used": "yt-dlp",
            "info_dict": {
                "title": "Test Video Oral Type",
                "duration": 120,
                "uploader": "test_author5",
                "uploader_url": "https://www.douyin.com/user/202",
                "thumbnail": "https://example.com/thumb5.jpg",
            },
            "title": "Test Video Oral Type",
            "duration": 120,
            "uploader": "test_author5",
            "uploader_url": "https://www.douyin.com/user/202",
            "thumbnail": "https://example.com/thumb5.jpg",
        }

        # Create fake subtitle file (dense subtitles = oral type)
        dense_subs = "\n".join(
            [f"00:00:{i:02d}.000 --> 00:00:{i+1:02d}.000\n这是口播类视频的密集字幕内容第{i}段"
             for i in range(60)])
        (tmp_path / "700005.zh.vtt").write_text(
            f"WEBVTT\n\n{dense_subs}\n",
            encoding="utf-8",
        )

        # Create fake video file
        (tmp_path / "700005.mp4").write_bytes(b"fake video")

        # Mock LLM summarizer (success)
        mock_summary = SummaryResult(
            summary_text="口播类视频总结",
            key_points=["要点一：口播内容"],
            model="mimo-v2.5-pro",
            source="mimo_llm",
        )
        mock_summarizer = MagicMock()
        mock_summarizer.summarize.return_value = mock_summary

        # Mock heuristic router to return SUMMARY_ONLY (oral type)
        mock_classify = MagicMock(return_value=RoutingDecision.SUMMARY_ONLY)

        with patch("src.bridge.main.resolve_url", return_value=mock_resolve), \
             patch("src.pipeline.scheduler.resolve_url", return_value=mock_resolve), \
             patch("src.pipeline.scheduler.download_video", return_value=mock_download), \
             patch("src.pipeline.scheduler.download_with_douk") as mock_douk, \
             patch("src.pipeline.scheduler.get_asr_client") as mock_asr_factory, \
             patch("src.pipeline.scheduler.get_summarizer", return_value=mock_summarizer), \
             patch("src.pipeline.scheduler.classify_video", mock_classify), \
             patch("src.pipeline.scheduler.extract_keyframes") as mock_kf, \
             patch("src.pipeline.scheduler.extract_text_from_image") as mock_ocr, \
             patch("src.pipeline.scheduler.describe_image") as mock_vlm:

            # Enqueue
            resp = await client.post(
                "/ingest",
                json={"source_url": "https://www.douyin.com/video/700005"},
            )
            assert resp.status_code == 200
            task_id = resp.json()["task_id"]

            # Simulate scheduler with vision.enabled=True
            from src.pipeline.scheduler import process_task
            task = db.atomic_dequeue(conn)
            assert task is not None
            assert task["video_id"] == "700005"
            config = {
                "downloader": {"temp_dir": str(tmp_path), "yt_dlp_retries": 1},
                "vault": {"root": str(vault_root)},
                "asr": {"provider": "mimo"},
                "llm": {"provider": "mimo"},
                "vision": {"enabled": True, "keyframe_max": 30, "scene_threshold": 0.4},
            }
            process_task(conn, task, config)

            # Verify: task is done
            updated = db.get_task(conn, task_id)
            assert updated["status"] == "done"

            # Verify: classify_video WAS called (routing happened)
            mock_classify.assert_called_once()

            # Verify: keyframe extraction NOT called (summary_only path)
            mock_kf.assert_not_called()
            mock_ocr.assert_not_called()
            mock_vlm.assert_not_called()

            # Verify: note keyframe section shows disabled (no VLM result)
            note_files = list(vault_root.rglob("700005.md"))
            assert len(note_files) == 1
            note_content = note_files[0].read_text(encoding="utf-8")
            assert "视觉理解已禁用" in note_content
            assert "summary_status: done" in note_content
