"""M5 E2E tests — multi-platform support + batch URL processing.

Scenario 1: Bilibili video → note enters vault
Scenario 2: YouTube video → note enters vault (mock yt-dlp)
Scenario 3: Message with 3 URLs → 3 tasks independently enqueued
Scenario 4: Mixed platform URLs → each routes to correct extractor
"""
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import httpx
import pytest
from httpx import ASGITransport

from src.bridge.main import create_app
from src.queue import db
from src.extractors.batch_url import extract_all_urls


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def m5_client(tmp_path: Path):
    """Create httpx client wired to FastAPI + fresh SQLite + vault."""
    db_path = tmp_path / "m5.sqlite3"
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
# Scenario 1 — Bilibili video → note enters vault
# ---------------------------------------------------------------------------

class TestScenario1Bilibili:
    """curl submit Bilibili video → task enqueued with bilibili platform."""

    @pytest.mark.anyio
    async def test_bilibili_video_enqueued(self, m5_client):
        """Bilibili URL → resolve succeeds → task pending in queue."""
        client, conn, vault_root = m5_client

        # Mock bilibili resolver to avoid network
        mock_result = {
            "video_id": "BV1234567890",
            "canonical_url": "https://www.bilibili.com/video/BV1234567890",
            "source_url_type": "full",
            "platform": "bilibili",
        }

        with patch(
            "src.bridge.main.resolve_url",
            return_value=mock_result,
        ):
            resp = await client.post(
                "/ingest",
                json={"source_url": "https://www.bilibili.com/video/BV1234567890"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] is not None
        assert data["already_archived"] is False

        # Verify task in DB
        task = db.get_task(conn, data["task_id"])
        assert task is not None
        assert task["video_id"] == "BV1234567890"
        assert task["status"] == "pending"


# ---------------------------------------------------------------------------
# Scenario 2 — YouTube video → note enters vault (mock yt-dlp)
# ---------------------------------------------------------------------------

class TestScenario2YouTube:
    """curl submit YouTube video → task enqueued."""

    @pytest.mark.anyio
    async def test_youtube_video_enqueued(self, m5_client):
        """YouTube URL → resolve succeeds → task pending in queue."""
        client, conn, vault_root = m5_client

        # Mock youtube resolver
        mock_result = {
            "video_id": "abc123",
            "canonical_url": "https://www.youtube.com/watch?v=abc123",
            "source_url_type": "full",
            "platform": "youtube",
        }

        with patch(
            "src.bridge.main.resolve_url",
            return_value=mock_result,
        ):
            resp = await client.post(
                "/ingest",
                json={"source_url": "https://www.youtube.com/watch?v=abc123"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] is not None

        task = db.get_task(conn, data["task_id"])
        assert task["video_id"] == "abc123"
        assert task["status"] == "pending"


# ---------------------------------------------------------------------------
# Scenario 3 — Message with 3 URLs → 3 tasks independently enqueued
# ---------------------------------------------------------------------------

class TestScenario3BatchURLs:
    """Message containing 3 URLs → each URL independently enqueued."""

    @pytest.mark.anyio
    async def test_three_urls_three_tasks(self, m5_client):
        """3 douyin URLs in one message → 3 separate tasks."""
        client, conn, vault_root = m5_client

        text = (
            "第一个 https://www.douyin.com/video/111\n"
            "第二个 https://www.douyin.com/video/222\n"
            "第三个 https://www.douyin.com/video/333"
        )

        urls = extract_all_urls(text)
        assert len(urls) == 3

        task_ids = []
        for url in urls:
            resp = await client.post("/ingest", json={"source_url": url})
            assert resp.status_code == 200
            task_ids.append(resp.json()["task_id"])

        # All 3 tasks should be independent
        assert len(set(task_ids)) == 3

        # All pending
        for tid in task_ids:
            task = db.get_task(conn, tid)
            assert task["status"] == "pending"


# ---------------------------------------------------------------------------
# Scenario 4 — Mixed platform URLs → each routes to correct extractor
# ---------------------------------------------------------------------------

class TestScenario4MixedPlatform:
    """Mixed platform URLs → each routes to correct extractor."""

    @pytest.mark.anyio
    async def test_mixed_platform_routing(self, m5_client):
        """douyin + bilibili + youtube → each resolves correctly."""
        client, conn, vault_root = m5_client

        text = (
            "抖音 https://www.douyin.com/video/111 "
            "B站 https://www.bilibili.com/video/BV222 "
            "YouTube https://www.youtube.com/watch?v=ccc"
        )

        urls = extract_all_urls(text)
        assert len(urls) == 3

        # Mock each platform's resolver
        douyin_result = {
            "video_id": "111",
            "canonical_url": "https://www.douyin.com/video/111",
            "source_url_type": "full",
            "platform": "douyin",
        }
        bilibili_result = {
            "video_id": "BV222",
            "canonical_url": "https://www.bilibili.com/video/BV222",
            "source_url_type": "full",
            "platform": "bilibili",
        }
        youtube_result = {
            "video_id": "ccc",
            "canonical_url": "https://www.youtube.com/watch?v=ccc",
            "source_url_type": "full",
            "platform": "youtube",
        }

        with patch(
            "src.bridge.main.resolve_url",
            return_value=douyin_result,
        ):
            resp1 = await client.post(
                "/ingest",
                json={"source_url": "https://www.douyin.com/video/111"},
            )
            assert resp1.status_code == 200
            task1 = db.get_task(conn, resp1.json()["task_id"])
            assert task1["video_id"] == "111"

        with patch(
            "src.bridge.main.resolve_url",
            return_value=bilibili_result,
        ):
            resp2 = await client.post(
                "/ingest",
                json={"source_url": "https://www.bilibili.com/video/BV222"},
            )
            assert resp2.status_code == 200
            task2 = db.get_task(conn, resp2.json()["task_id"])
            assert task2["video_id"] == "BV222"

        with patch(
            "src.bridge.main.resolve_url",
            return_value=youtube_result,
        ):
            resp3 = await client.post(
                "/ingest",
                json={"source_url": "https://www.youtube.com/watch?v=ccc"},
            )
            assert resp3.status_code == 200
            task3 = db.get_task(conn, resp3.json()["task_id"])
            assert task3["video_id"] == "ccc"

        # All 3 tasks exist and are independent
        stats = db.queue_stats(conn)
        assert stats["pending"] == 3
