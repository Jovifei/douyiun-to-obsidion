"""Curl E2E tests — automated scenarios 3/4/5 from plan §11.A.

Scenario 3: Duplicate detection → already_archived
Scenario 4: Zombie task reclaim after restart
Scenario 5: Cookie expired → error_code

Scenarios 1, 2, 6, 7 require real Douyin URLs / manual network
manipulation and live in scripts/manual_e2e_test.ps1.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from src.bridge.main import create_app
from src.queue import db
from src.pipeline.state_machine import transition


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def e2e_client(tmp_path: Path):
    """Create httpx client wired to FastAPI + fresh SQLite + vault."""
    db_path = tmp_path / "e2e.sqlite3"
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
# Scenario 3 — duplicate detection
# ---------------------------------------------------------------------------

class TestScenario3DuplicateDetection:
    """curl same URL twice (without force) → second returns already_archived."""

    @pytest.mark.anyio
    async def test_second_ingest_returns_already_archived(self, e2e_client):
        client, conn, vault_root = e2e_client

        # First ingest — enqueue normally
        resp1 = await client.post(
            "/ingest",
            json={"source_url": "https://www.douyin.com/video/300001"},
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["task_id"] is not None
        assert data1["already_archived"] is False

        # Simulate task completion: create note file in vault
        note_dir = vault_root / "inbox" / "douyin" / datetime.now().strftime("%Y-%m")
        note_dir.mkdir(parents=True, exist_ok=True)
        (note_dir / "300001.md").write_text("---\ntitle: test\n---\n\n# 300001\n")

        # Second ingest — should detect duplicate
        resp2 = await client.post(
            "/ingest",
            json={"source_url": "https://www.douyin.com/video/300001"},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["already_archived"] is True
        assert data2["note_path"] is not None
        assert "300001.md" in data2["note_path"]

    @pytest.mark.anyio
    async def test_force_overrides_duplicate(self, e2e_client):
        """force=true bypasses duplicate detection."""
        client, conn, vault_root = e2e_client

        # First ingest
        resp1 = await client.post(
            "/ingest",
            json={"source_url": "https://www.douyin.com/video/300002"},
        )
        assert resp1.status_code == 200

        # Create note file
        note_dir = vault_root / "inbox" / "douyin" / datetime.now().strftime("%Y-%m")
        note_dir.mkdir(parents=True, exist_ok=True)
        (note_dir / "300002.md").write_text("existing")

        # force=true bypasses duplicate
        resp2 = await client.post(
            "/ingest",
            json={"source_url": "https://www.douyin.com/video/300002", "force": True},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["already_archived"] is False
        assert data2["task_id"] is not None


# ---------------------------------------------------------------------------
# Scenario 4 — zombie task reclaim
# ---------------------------------------------------------------------------

def _insert_zombie(conn, video_id: str, minutes_ago: int = 60) -> None:
    """Insert a zombie task (fetching + stale claimed_at) directly into DB."""
    stale_time = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    conn.execute(
        "INSERT INTO task (video_id, source_url, source_url_type, "
        "correlation_id, payload_json, status, claimed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (video_id, f"https://www.douyin.com/video/{video_id}", "full",
         f"zombie-{video_id}", "{}", "fetching", stale_time),
    )
    conn.commit()


class TestScenario4ZombieReclaim:
    """After process crash, pending tasks with stale claimed_at are reclaimed."""

    @pytest.mark.anyio
    async def test_zombie_reclaim_on_startup(self, e2e_client):
        """Simulate crash: task stuck in 'fetching' with old claimed_at.
        On startup, reclaim_zombie_tasks moves it back to 'pending'."""
        client, conn, vault_root = e2e_client

        _insert_zombie(conn, "400001", minutes_ago=60)

        # Verify it's in 'fetching'
        row = conn.execute("SELECT * FROM task WHERE video_id='400001'").fetchone()
        assert row["status"] == "fetching"

        # Simulate startup reclaim (same logic as bridge startup hook)
        reclaimed = db.reclaim_zombie_tasks(conn, timeout_minutes=30)
        assert reclaimed >= 1

        # Verify reclaimed to 'pending'
        row = conn.execute("SELECT * FROM task WHERE video_id='400001'").fetchone()
        assert row["status"] == "pending"
        assert row["claimed_at"] is None

    @pytest.mark.anyio
    async def test_zombie_reclaim_enables_task_via_api(self, e2e_client):
        """After reclaim, zombie task becomes visible to dequeue and can be
        re-processed (end-to-end zombie recovery)."""
        client, conn, vault_root = e2e_client

        _insert_zombie(conn, "400002", minutes_ago=60)

        # Reclaim zombie
        reclaimed = db.reclaim_zombie_tasks(conn, timeout_minutes=30)
        assert reclaimed >= 1

        # Verify it's now pending and can be dequeued
        row = conn.execute("SELECT * FROM task WHERE video_id='400002'").fetchone()
        assert row["status"] == "pending"

        # Dequeue it (simulates scheduler picking it up)
        task = db.atomic_dequeue(conn)
        assert task is not None
        assert task["video_id"] == "400002"
        assert task["status"] == "fetching"

    @pytest.mark.anyio
    async def test_fresh_task_not_reclaimed(self, e2e_client):
        """A recently claimed task is NOT reclaimed (within timeout window)."""
        client, conn, vault_root = e2e_client

        _insert_zombie(conn, "400003", minutes_ago=5)

        reclaimed = db.reclaim_zombie_tasks(conn, timeout_minutes=30)
        # Should NOT reclaim the fresh task
        row = conn.execute("SELECT * FROM task WHERE video_id='400003'").fetchone()
        assert row["status"] == "fetching"


# ---------------------------------------------------------------------------
# Scenario 5 — cookie expired
# ---------------------------------------------------------------------------

class TestScenario5CookieExpired:
    """Wrong cookies → task fails with error_code='cookie_expired'."""

    @pytest.mark.anyio
    async def test_cookie_expired_error_code(self, e2e_client):
        """Simulate cookie expired error → verify error_code in DB."""
        client, conn, vault_root = e2e_client

        # Enqueue + dequeue
        task_id = db.enqueue(
            conn=conn,
            video_id="500001",
            source_url="https://www.douyin.com/video/500001",
            source_url_type="full",
            correlation_id="cookie-test",
        )
        task = db.atomic_dequeue(conn)
        assert task is not None

        # Simulate what the scheduler does on cookie error:
        # transition task from fetching → failed with error_code
        transition(
            conn, task_id, "failed",
            from_status="fetching",
            correlation_id="cookie-test",
            error_code="cookie_expired",
            error_message="Cookie expired: HTTP 403",
        )

        # Verify error_code persisted in DB
        updated = db.get_task(conn, task_id)
        assert updated["status"] == "failed"
        assert updated["error_code"] == "cookie_expired"
        assert "Cookie expired" in updated["error_message"]

    @pytest.mark.anyio
    async def test_cookie_expired_via_api_task_status(self, e2e_client):
        """After cookie error, GET /tasks/{id} returns error_code."""
        client, conn, vault_root = e2e_client

        # Enqueue + dequeue
        task_id = db.enqueue(
            conn=conn,
            video_id="500002",
            source_url="https://www.douyin.com/video/500002",
            source_url_type="full",
            correlation_id="cookie-test-2",
        )
        task = db.atomic_dequeue(conn)

        # Simulate cookie error
        transition(
            conn, task_id, "failed",
            from_status="fetching",
            correlation_id="cookie-test-2",
            error_code="cookie_expired",
            error_message="Cookie expired: HTTP 403",
        )

        # Query via API
        resp = await client.get(f"/tasks/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert data["error_code"] == "cookie_expired"
