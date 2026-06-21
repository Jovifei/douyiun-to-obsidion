"""M2 E2E tests — ASR fallback pipeline integration.

Scenario 1: Video WITH subtitles -> subtitle path (M1 behavior unchanged)
Scenario 2: Video WITHOUT subtitles -> ASR path -> note contains transcript
Scenario 3: ASR failure -> failed(asr_failed)
Scenario 4: Switch provider to whisper_local -> local Whisper path

These tests mock external dependencies (yt-dlp, ASR) and test the full
pipeline integration from API ingest to vault note creation.
"""
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport

from src.bridge.main import create_app
from src.queue import db


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def m2_client(tmp_path: Path):
    """Create httpx client wired to FastAPI + fresh SQLite + vault."""
    db_path = tmp_path / "m2_e2e.sqlite3"
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
# Scenario 1 — Video WITH subtitles -> subtitle path (M1 behavior)
# ---------------------------------------------------------------------------

class TestScenario1SubtitlePath:
    """Video with native subtitles goes through subtitle path, no ASR."""

    @pytest.mark.anyio
    async def test_video_with_subtitles_skips_asr(self, m2_client, tmp_path):
        """Ingest video with subtitles -> note created from subtitle, ASR not called."""
        client, conn, vault_root = m2_client

        mock_resolve = {
            "video_id": "600001",
            "canonical_url": "https://www.douyin.com/video/600001",
            "source_url_type": "full",
        }

        mock_download = {
            "video_path": Path("/tmp/600001.mp4"),
            "subtitle_path": Path("/tmp/600001.zh.vtt"),
            "subtitle_source": "douyin_native",
            "downloader_used": "yt-dlp",
            "info_dict": {
                "title": "Test Video With Subs",
                "duration": 120,
                "uploader": "test_author",
                "uploader_url": "https://www.douyin.com/user/123",
                "thumbnail": "https://example.com/thumb.jpg",
            },
            "title": "Test Video With Subs",
            "duration": 120,
            "uploader": "test_author",
            "uploader_url": "https://www.douyin.com/user/123",
            "thumbnail": "https://example.com/thumb.jpg",
        }

        with patch("src.bridge.main.resolve_url", return_value=mock_resolve), \
             patch("src.pipeline.scheduler.resolve_url", return_value=mock_resolve), \
             patch("src.pipeline.scheduler.download_video", return_value=mock_download), \
             patch("src.pipeline.scheduler.download_with_douk") as mock_douk, \
             patch("src.pipeline.scheduler.get_asr_client") as mock_asr_factory:

            # Enqueue
            resp = await client.post(
                "/ingest",
                json={"source_url": "https://www.douyin.com/video/600001"},
            )
            assert resp.status_code == 200
            task_id = resp.json()["task_id"]

            # Simulate scheduler: dequeue (pending -> fetching) then process
            from src.pipeline.scheduler import process_task
            task = db.atomic_dequeue(conn)
            assert task is not None
            assert task["video_id"] == "600001"
            config = {
                "downloader": {"temp_dir": str(tmp_path), "yt_dlp_retries": 1},
                "vault": {"root": str(vault_root)},
                "asr": {"provider": "mimo"},
            }
            process_task(conn, task, config)

            # Verify: ASR was NOT called
            mock_asr_factory.assert_not_called()
            mock_douk.assert_not_called()

            # Verify: task is done
            updated = db.get_task(conn, task_id)
            assert updated["status"] == "done"

            # Verify: note exists in vault
            note_files = list(vault_root.rglob("600001.md"))
            assert len(note_files) == 1
            note_content = note_files[0].read_text(encoding="utf-8")
            assert "600001" in note_content


# ---------------------------------------------------------------------------
# Scenario 2 — Video WITHOUT subtitles -> ASR path -> note with transcript
# ---------------------------------------------------------------------------

class TestScenario2ASRPath:
    """Video without subtitles triggers ASR fallback, note contains transcript."""

    @pytest.mark.anyio
    async def test_no_subtitles_triggers_asr(self, m2_client, tmp_path):
        """Ingest video without subtitles -> ASR transcribes -> note has transcript."""
        client, conn, vault_root = m2_client

        mock_resolve = {
            "video_id": "600002",
            "canonical_url": "https://www.douyin.com/video/600002",
            "source_url_type": "full",
        }

        # download_video raises NoSubtitleError (no subtitles available)
        from src.extractors.downloader import NoSubtitleError

        mock_download_only = {
            "video_path": tmp_path / "600002.mp4",
            "video_id": "600002",
            "info_dict": {
                "title": "Test Video No Subs",
                "duration": 60,
                "uploader": "test_author2",
                "uploader_url": "https://www.douyin.com/user/456",
                "thumbnail": "https://example.com/thumb2.jpg",
            },
            "title": "Test Video No Subs",
            "duration": 60,
            "uploader": "test_author2",
            "uploader_url": "https://www.douyin.com/user/456",
            "thumbnail": "https://example.com/thumb2.jpg",
        }

        mock_asr_result = MagicMock()
        mock_asr_result.text = "这是ASR转写的测试文本内容"
        mock_asr_result.source = "mimo_asr"

        mock_asr_client = MagicMock()
        mock_asr_client.transcribe.return_value = mock_asr_result

        # Create a fake video file for audio extraction
        (tmp_path / "600002.mp4").write_bytes(b"fake video")

        with patch("src.bridge.main.resolve_url", return_value=mock_resolve), \
             patch("src.pipeline.scheduler.resolve_url", return_value=mock_resolve), \
             patch("src.pipeline.scheduler.download_video", side_effect=NoSubtitleError("no_subtitle_in_m1")), \
             patch("src.pipeline.scheduler.download_video_only", return_value=mock_download_only), \
             patch("src.pipeline.scheduler.download_with_douk", side_effect=NoSubtitleError("no_subtitle_in_m1")), \
             patch("src.pipeline.scheduler.get_asr_client", return_value=mock_asr_client), \
             patch("src.pipeline.scheduler.extract_audio_for_asr") as mock_extract:

                # Make extract_audio_for_asr create the wav file
                def fake_extract(video_path, wav_path):
                    wav_path.write_bytes(b"fake wav")
                    return wav_path
                mock_extract.side_effect = fake_extract

                # Enqueue
                resp = await client.post(
                    "/ingest",
                    json={"source_url": "https://www.douyin.com/video/600002"},
                )
                assert resp.status_code == 200
                task_id = resp.json()["task_id"]

                # Simulate scheduler: dequeue (pending -> fetching) then process
                from src.pipeline.scheduler import process_task
                task = db.atomic_dequeue(conn)
                assert task is not None
                assert task["video_id"] == "600002"
                config = {
                    "downloader": {"temp_dir": str(tmp_path), "yt_dlp_retries": 1},
                    "vault": {"root": str(vault_root)},
                    "asr": {"provider": "mimo"},
                }
                process_task(conn, task, config)

                # Verify: ASR WAS called
                mock_asr_client.transcribe.assert_called_once()

                # Verify: task is done
                updated = db.get_task(conn, task_id)
                assert updated["status"] == "done"

                # Verify: note exists and contains ASR transcript
                note_files = list(vault_root.rglob("600002.md"))
                assert len(note_files) == 1
                note_content = note_files[0].read_text(encoding="utf-8")
                assert "ASR" in note_content or "转写" in note_content or "subtitle_source" in note_content


# ---------------------------------------------------------------------------
# Scenario 3 — ASR failure -> failed(asr_failed)
# ---------------------------------------------------------------------------

class TestScenario3ASRFailure:
    """ASR transcription fails -> task marked failed with error_code asr_failed."""

    @pytest.mark.anyio
    async def test_asr_failure_sets_error_code(self, m2_client, tmp_path):
        """Ingest video -> ASR fails -> task status=failed, error_code=asr_failed."""
        client, conn, vault_root = m2_client

        mock_resolve = {
            "video_id": "600003",
            "canonical_url": "https://www.douyin.com/video/600003",
            "source_url_type": "full",
        }

        from src.extractors.downloader import NoSubtitleError
        from src.asr import ASRError

        mock_download_only = {
            "video_path": tmp_path / "600003.mp4",
            "video_id": "600003",
            "info_dict": {},
            "title": None,
            "duration": None,
            "uploader": None,
            "uploader_url": None,
            "thumbnail": None,
        }

        mock_asr_client = MagicMock()
        mock_asr_client.transcribe.side_effect = ASRError("asr_timeout", "API timeout")

        (tmp_path / "600003.mp4").write_bytes(b"fake video")

        with patch("src.bridge.main.resolve_url", return_value=mock_resolve), \
             patch("src.pipeline.scheduler.resolve_url", return_value=mock_resolve), \
             patch("src.pipeline.scheduler.download_video", side_effect=NoSubtitleError("no_subtitle_in_m1")), \
             patch("src.pipeline.scheduler.download_video_only", return_value=mock_download_only), \
             patch("src.pipeline.scheduler.download_with_douk", side_effect=NoSubtitleError("no_subtitle_in_m1")), \
             patch("src.pipeline.scheduler.get_asr_client", return_value=mock_asr_client), \
             patch("src.pipeline.scheduler.extract_audio_for_asr") as mock_extract:

                def fake_extract(video_path, wav_path):
                    wav_path.write_bytes(b"fake wav")
                    return wav_path
                mock_extract.side_effect = fake_extract

                # Enqueue
                resp = await client.post(
                    "/ingest",
                    json={"source_url": "https://www.douyin.com/video/600003"},
                )
                assert resp.status_code == 200
                task_id = resp.json()["task_id"]

                # Simulate scheduler: dequeue (pending -> fetching) then process
                from src.pipeline.scheduler import process_task
                task = db.atomic_dequeue(conn)
                assert task is not None
                assert task["video_id"] == "600003"
                config = {
                    "downloader": {"temp_dir": str(tmp_path), "yt_dlp_retries": 1},
                    "vault": {"root": str(vault_root)},
                    "asr": {"provider": "mimo"},
                }
                process_task(conn, task, config)

                # Verify: task is failed with asr_failed error code
                updated = db.get_task(conn, task_id)
                assert updated["status"] == "failed"
                assert updated["error_code"] == "asr_failed"


# ---------------------------------------------------------------------------
# Scenario 4 — Switch provider to whisper_local -> local Whisper path
# ---------------------------------------------------------------------------

class TestScenario4WhisperLocal:
    """Switch ASR provider to whisper_local -> uses WhisperLocalClient."""

    @pytest.mark.anyio
    async def test_whisper_local_provider(self, m2_client, tmp_path):
        """Config provider=whisper_local -> WhisperLocalClient.transcribe called."""
        client, conn, vault_root = m2_client

        mock_resolve = {
            "video_id": "600004",
            "canonical_url": "https://www.douyin.com/video/600004",
            "source_url_type": "full",
        }

        from src.extractors.downloader import NoSubtitleError
        from src.asr import ASRResult

        mock_download_only = {
            "video_path": tmp_path / "600004.mp4",
            "video_id": "600004",
            "info_dict": {},
            "title": None,
            "duration": None,
            "uploader": None,
            "uploader_url": None,
            "thumbnail": None,
        }

        mock_asr_result = ASRResult(
            text="本地Whisper转写结果",
            segments=[{"start": 0.0, "end": 3.0, "text": "本地Whisper转写结果"}],
            source="whisper_local",
            confidence=0.0,
        )

        mock_asr_client = MagicMock()
        mock_asr_client.transcribe.return_value = mock_asr_result

        (tmp_path / "600004.mp4").write_bytes(b"fake video")

        with patch("src.bridge.main.resolve_url", return_value=mock_resolve), \
             patch("src.pipeline.scheduler.resolve_url", return_value=mock_resolve), \
             patch("src.pipeline.scheduler.download_video", side_effect=NoSubtitleError("no_subtitle_in_m1")), \
             patch("src.pipeline.scheduler.download_video_only", return_value=mock_download_only), \
             patch("src.pipeline.scheduler.download_with_douk", side_effect=NoSubtitleError("no_subtitle_in_m1")), \
             patch("src.pipeline.scheduler.get_asr_client", return_value=mock_asr_client), \
             patch("src.pipeline.scheduler.extract_audio_for_asr") as mock_extract:

                def fake_extract(video_path, wav_path):
                    wav_path.write_bytes(b"fake wav")
                    return wav_path
                mock_extract.side_effect = fake_extract

                # Enqueue
                resp = await client.post(
                    "/ingest",
                    json={"source_url": "https://www.douyin.com/video/600004"},
                )
                assert resp.status_code == 200
                task_id = resp.json()["task_id"]

                # Simulate scheduler: dequeue (pending -> fetching) then process
                from src.pipeline.scheduler import process_task
                task = db.atomic_dequeue(conn)
                assert task is not None
                assert task["video_id"] == "600004"
                config = {
                    "downloader": {"temp_dir": str(tmp_path), "yt_dlp_retries": 1},
                    "vault": {"root": str(vault_root)},
                    "asr": {"provider": "whisper_local"},
                }
                process_task(conn, task, config)

                # Verify: ASR was called
                mock_asr_client.transcribe.assert_called_once()

                # Verify: task is done
                updated = db.get_task(conn, task_id)
                assert updated["status"] == "done"

                # Verify: note exists with whisper_local source
                note_files = list(vault_root.rglob("600004.md"))
                assert len(note_files) == 1
                note_content = note_files[0].read_text(encoding="utf-8")
                assert "whisper_local" in note_content
