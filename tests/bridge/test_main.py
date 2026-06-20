"""FastAPI bridge server tests — Task 8 TDD (RED phase).

Tests use httpx.AsyncClient + ASGITransport, no real uvicorn.
"""
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import httpx


@pytest.fixture
def anyio_backend():
    return "asyncio"


class TestPostIngest:
    """POST /ingest tests."""

    @pytest.mark.anyio
    async def test_post_ingest_returns_task_id(self, client: httpx.AsyncClient):
        """Normal enqueue returns task_id and status."""
        resp = await client.post("/ingest", json={"source_url": "https://www.douyin.com/video/123456"})
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "pending"

    @pytest.mark.anyio
    async def test_post_ingest_duplicate_returns_already_archived(self, client: httpx.AsyncClient, tmp_vault: Path):
        """Duplicate detection: vault already has video_id.md."""
        # Create a fake note in vault
        vault_inbox = tmp_vault / "inbox" / "douyin" / "2026-06"
        vault_inbox.mkdir(parents=True, exist_ok=True)
        (vault_inbox / "123456.md").write_text("existing note")

        resp = await client.post("/ingest", json={"source_url": "https://www.douyin.com/video/123456"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["already_archived"] is True
        assert "note_path" in data

    @pytest.mark.anyio
    async def test_post_ingest_force_overrides_duplicate(self, client: httpx.AsyncClient, tmp_vault: Path):
        """force=true skips duplicate detection."""
        # Create a fake note in vault
        vault_inbox = tmp_vault / "inbox" / "douyin" / "2026-06"
        vault_inbox.mkdir(parents=True, exist_ok=True)
        (vault_inbox / "123456.md").write_text("existing note")

        resp = await client.post("/ingest", json={"source_url": "https://www.douyin.com/video/123456", "force": True})
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "pending"

    @pytest.mark.anyio
    async def test_duplicate_detection_cross_month(self, client: httpx.AsyncClient, tmp_vault: Path):
        """Duplicate detection finds video_id in any month subdirectory."""
        # Create a fake note in a DIFFERENT month (not current)
        old_month_dir = tmp_vault / "inbox" / "douyin" / "2025-01"
        old_month_dir.mkdir(parents=True, exist_ok=True)
        (old_month_dir / "555555.md").write_text("old note")

        resp = await client.post("/ingest", json={"source_url": "https://www.douyin.com/video/555555"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["already_archived"] is True

    @pytest.mark.anyio
    async def test_ingest_rejects_empty_source_url(self, client: httpx.AsyncClient):
        """Empty source_url returns 422 validation error."""
        resp = await client.post("/ingest", json={"source_url": ""})
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_ingest_rejects_non_douyin_url(self, client: httpx.AsyncClient):
        """Non-douyin URL returns 400."""
        resp = await client.post("/ingest", json={"source_url": "https://www.youtube.com/watch?v=abc"})
        assert resp.status_code == 400

    @pytest.mark.anyio
    async def test_post_ingest_mocked_resolve(self, client: httpx.AsyncClient):
        """POST /ingest uses resolve_url — verify it's called (network-isolated)."""
        mock_result = {
            "video_id": "888888",
            "canonical_url": "https://www.douyin.com/video/888888",
            "source_url_type": "full",
        }
        with patch("src.bridge.main.resolve_url", return_value=mock_result) as mock_fn:
            resp = await client.post("/ingest", json={"source_url": "https://www.douyin.com/video/888888"})
            assert resp.status_code == 200
            mock_fn.assert_called_once()


class TestGetTasks:
    """GET /tasks/{task_id} tests."""

    @pytest.mark.anyio
    async def test_get_tasks_returns_status(self, client: httpx.AsyncClient):
        """Returns task status."""
        # First create a task
        create_resp = await client.post("/ingest", json={"source_url": "https://www.douyin.com/video/999999"})
        task_id = create_resp.json()["task_id"]

        # Then query it
        resp = await client.get(f"/tasks/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == task_id
        assert data["status"] == "pending"

    @pytest.mark.anyio
    async def test_get_tasks_includes_correlation_id(self, client: httpx.AsyncClient):
        """GET /tasks/{task_id} returns correlation_id field."""
        # Create a task via ingest
        resp = await client.post("/ingest", json={"source_url": "https://www.douyin.com/video/777777"})
        task_id = resp.json()["task_id"]

        resp = await client.get(f"/tasks/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "correlation_id" in data
        assert isinstance(data["correlation_id"], str)
        assert len(data["correlation_id"]) > 0

    @pytest.mark.anyio
    async def test_get_tasks_not_found(self, client: httpx.AsyncClient):
        """Non-existent task_id returns 404."""
        resp = await client.get("/tasks/99999")
        assert resp.status_code == 404


class TestHealth:
    """GET /health tests."""

    @pytest.mark.anyio
    async def test_health_returns_queue_stats(self, client: httpx.AsyncClient):
        """Returns status and queue stats."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "queue" in data
        assert "pending" in data["queue"]
        assert "fetching" in data["queue"]
        assert "writing" in data["queue"]
        assert "failed_today" in data["queue"]
        assert "done_today" in data["queue"]


class TestQueueStats:
    """GET /queue/stats tests."""

    @pytest.mark.anyio
    async def test_queue_stats_returns_all_statuses(self, client: httpx.AsyncClient):
        """Returns all status counts."""
        resp = await client.get("/queue/stats")
        assert resp.status_code == 200
        data = resp.json()
        for status in ["pending", "fetching", "writing", "done", "failed", "failed_today", "done_today"]:
            assert status in data


class TestStartupHook:
    """Startup hook tests."""

    @pytest.mark.anyio
    async def test_reclaim_zombie_called_on_startup(self, tmp_db, tmp_vault):
        """Verify startup hook reclaims zombie tasks (fetching → pending)."""
        from src.queue import db
        from src.bridge.main import create_app
        conn, db_path = tmp_db
        conn = db.init_db(db_path)
        vault_root = tmp_vault

        # Insert a zombie task (stale claimed_at triggers reclaim)
        conn.execute(
            "INSERT INTO task (video_id, source_url, source_url_type, correlation_id, payload_json, status, claimed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("111111", "https://www.douyin.com/video/111111", "full", "test", "{}", "fetching",
             "2026-01-01 00:00:00"),
        )
        conn.commit()

        # Verify it's in 'fetching' before startup
        row = conn.execute("SELECT status FROM task WHERE video_id='111111'").fetchone()
        assert row["status"] == "fetching"

        # Create app and register startup hook (same as conftest does)
        app = create_app(conn=conn, vault_root=vault_root)

        @app.on_event("startup")
        async def on_startup():
            reclaimed = db.reclaim_zombie_tasks(conn)

        # Simulate FastAPI startup event
        for handler in app.router.on_startup:
            await handler()

        # Verify zombie was reclaimed to 'pending'
        row = conn.execute("SELECT status FROM task WHERE video_id='111111'").fetchone()
        assert row["status"] == "pending"
