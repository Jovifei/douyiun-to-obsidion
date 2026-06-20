"""conftest for bridge tests — sets up FastAPI client with test fixtures."""
import pytest
import httpx
from httpx import ASGITransport
from pathlib import Path

from src.queue import db


@pytest.fixture
async def client(tmp_db, tmp_vault):
    """Create httpx.AsyncClient with ASGITransport for testing."""
    from src.bridge.main import create_app

    conn, db_path = tmp_db
    vault_root = tmp_vault

    # Initialize the database schema using the same connection
    conn.row_factory = None  # Reset to ensure schema creation works
    conn = db.init_db(db_path)

    # Create app with test dependencies
    app = create_app(conn=conn, vault_root=vault_root)

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
