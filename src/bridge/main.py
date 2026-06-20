"""FastAPI bridge server — Task 8: HTTP API for task ingestion and status.

Spec ref: tasks.md §4
Port: 8765 (D-9 locked)
"""
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.queue import db
from src.extractors.douyin_resolver import resolve_url, ResolverError


class IngestRequest(BaseModel):
    source_url: str
    force: bool = False


class IngestResponse(BaseModel):
    task_id: int | None = None
    status: str | None = None
    already_archived: bool = False
    note_path: str | None = None


class TaskResponse(BaseModel):
    id: int
    video_id: str
    source_url: str
    status: str
    note_path: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    correlation_id: str
    created_at: str
    updated_at: str


class HealthResponse(BaseModel):
    status: str
    queue: dict[str, int]


class QueueStatsResponse(BaseModel):
    pending: int
    fetching: int
    writing: int
    done: int
    failed: int
    failed_today: int
    done_today: int


def create_app(conn: sqlite3.Connection | None = None, vault_root: Path | str | None = None) -> FastAPI:
    """Create FastAPI app with optional dependencies for testing."""
    app = FastAPI(title="douyin-bridge", version="0.1.0")

    # Store dependencies
    _deps = {"conn": conn, "vault_root": Path(vault_root) if vault_root else None}

    @app.post("/ingest", response_model=IngestResponse)
    async def ingest(req: IngestRequest):
        if not req.source_url.strip():
            raise HTTPException(status_code=422, detail="source_url cannot be empty")

        try:
            result = resolve_url(req.source_url)
        except ResolverError as e:
            raise HTTPException(status_code=400, detail=str(e))

        video_id = result["video_id"]
        source_url_type = result["source_url_type"]
        canonical_url = result["canonical_url"]

        # Duplicate detection — search all month subdirectories
        if not req.force and _deps["vault_root"]:
            douyin_dir = _deps["vault_root"] / "inbox" / "douyin"
            matches = list(douyin_dir.glob(f"**/{video_id}.md"))
            if matches:
                return IngestResponse(
                    already_archived=True,
                    note_path=str(matches[0]),
                )

        # Enqueue task
        correlation_id = str(uuid.uuid4())
        task_id = db.enqueue(
            conn=_deps["conn"],
            video_id=video_id,
            source_url=canonical_url,
            source_url_type=source_url_type,
            correlation_id=correlation_id,
        )

        return IngestResponse(task_id=task_id, status="pending")

    @app.get("/tasks/{task_id}", response_model=TaskResponse)
    async def get_task(task_id: int):
        task = db.get_task(_deps["conn"], task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")

        # Build note_path for completed tasks
        note_path = None
        if task["status"] == "done" and _deps["vault_root"]:
            # Parse created_at to get month
            created = task.get("created_at", "")
            if created:
                try:
                    dt = datetime.fromisoformat(created)
                    month_dir = dt.strftime("%Y-%m")
                    note_path = str(_deps["vault_root"] / "inbox" / "douyin" / month_dir / f"{task['video_id']}.md")
                except ValueError:
                    pass

        return TaskResponse(
            id=task["id"],
            video_id=task["video_id"],
            source_url=task["source_url"],
            status=task["status"],
            note_path=note_path,
            error_code=task.get("error_code"),
            error_message=task.get("error_message"),
            correlation_id=task.get("correlation_id", ""),
            created_at=task.get("created_at", ""),
            updated_at=task.get("updated_at", ""),
        )

    @app.get("/health", response_model=HealthResponse)
    async def health():
        stats = db.queue_stats(_deps["conn"])
        return HealthResponse(status="ok", queue=stats)

    @app.get("/queue/stats", response_model=QueueStatsResponse)
    async def queue_stats():
        stats = db.queue_stats(_deps["conn"])
        return QueueStatsResponse(**stats)

    return app


def main():
    """Entry point for uvicorn."""
    import yaml
    import uvicorn

    # Load config
    config_path = Path("config.yaml")
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f)
    else:
        config = {}

    host = config.get("server", {}).get("host", "127.0.0.1")
    port = config.get("server", {}).get("port", 8765)
    db_path = config.get("queue", {}).get("db_path", "data/queue.sqlite3")
    vault_root = config.get("vault", {}).get("root", ".")

    # Init DB
    conn = db.init_db(db_path)

    # Create app
    app = create_app(conn=conn, vault_root=vault_root)

    # Startup hook: reclaim zombie tasks
    @app.on_event("startup")
    async def on_startup():
        reclaimed = db.reclaim_zombie_tasks(conn)
        if reclaimed > 0:
            print(f"Reclaimed {reclaimed} zombie tasks")

    # Run server
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
