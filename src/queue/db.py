"""SQLite task queue — D-4 v2 修订：4 状态严格机（pending/fetching/writing/done/failed）。

Spec ref: specs/task-queue-pipeline/spec.md
"""
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 状态转移表：from_status -> set of allowed to_status
_VALID_TRANSITIONS = {
    "pending": {"fetching", "failed"},
    "fetching": {"writing", "failed"},
    "writing": {"done", "failed"},
    "done": set(),
    "failed": set(),
}


def init_db(db_path: Path | str) -> sqlite3.Connection:
    """创建 task 表，返回 connection（row_factory=sqlite3.Row）。"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA_SQL)
    return conn


def enqueue(
    conn: sqlite3.Connection,
    video_id: str,
    source_url: str,
    source_url_type: str,
    correlation_id: str,
    payload: dict | None = None,
) -> int:
    """入队新任务，返回 task_id。status='pending', claimed_at=NULL。"""
    payload_json = json.dumps(payload, ensure_ascii=False) if payload else "{}"
    cur = conn.execute(
        """INSERT INTO task (video_id, source_url, source_url_type, correlation_id, payload_json)
           VALUES (?, ?, ?, ?, ?)""",
        (video_id, source_url, source_url_type, correlation_id, payload_json),
    )
    conn.commit()
    return cur.lastrowid


def atomic_dequeue(conn: sqlite3.Connection) -> dict | None:
    """原子 dequeue：单条 SQL 挑选+占用+置 fetching（B4）。

    返回任务 dict 或 None（队列空）。
    """
    cur = conn.execute(
        """UPDATE task
           SET claimed_at = CURRENT_TIMESTAMP,
               status = 'fetching',
               updated_at = CURRENT_TIMESTAMP
           WHERE id = (
             SELECT id FROM task
             WHERE status = 'pending' AND claimed_at IS NULL
             ORDER BY id LIMIT 1
           )
           RETURNING *"""
    )
    row = cur.fetchone()
    conn.commit()
    return dict(row) if row else None


def reclaim_zombie_tasks(
    conn: sqlite3.Connection, timeout_minutes: int = 30
) -> int:
    """复活 zombie 任务：status IN ('fetching','writing') 且 claimed_at 超时。

    返回被复活的任务数。
    """
    cutoff_dt = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
    cutoff = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")

    cur = conn.execute(
        """UPDATE task
           SET status = 'pending', claimed_at = NULL, updated_at = CURRENT_TIMESTAMP
           WHERE status IN ('fetching', 'writing')
             AND claimed_at IS NOT NULL
             AND claimed_at < ?""",
        (cutoff,),
    )
    conn.commit()
    return cur.rowcount


def update_status(
    conn: sqlite3.Connection,
    task_id: int,
    new_status: str,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    """状态转移，非法转移抛 ValueError。"""
    row = conn.execute("SELECT status FROM task WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise ValueError(f"task {task_id} not found")
    current = row["status"]
    if current == new_status:
        return  # 同状态 noop
    allowed = _VALID_TRANSITIONS.get(current, set())
    if new_status not in allowed:
        raise ValueError(
            f"illegal transition {current} -> {new_status}"
        )
    conn.execute(
        """UPDATE task
           SET status=?, error_code=?, error_message=?, updated_at=CURRENT_TIMESTAMP
           WHERE id=?""",
        (new_status, error_code, error_message, task_id),
    )
    conn.commit()


def get_task(conn: sqlite3.Connection, task_id: int) -> dict | None:
    """查单任务，返回 dict 或 None。"""
    row = conn.execute("SELECT * FROM task WHERE id=?", (task_id,)).fetchone()
    return dict(row) if row else None


def queue_stats(conn: sqlite3.Connection) -> dict[str, int]:
    """返回 {pending, fetching, writing, done, failed, failed_today, done_today}。"""
    rows = conn.execute(
        """SELECT status, COUNT(*) as cnt FROM task GROUP BY status"""
    ).fetchall()
    stats = {s: 0 for s in ("pending", "fetching", "writing", "done", "failed")}
    for r in rows:
        if r["status"] in stats:
            stats[r["status"]] = r["cnt"]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM task WHERE status='failed' AND date(created_at)=?",
        (today,),
    ).fetchone()
    stats["failed_today"] = row["cnt"]
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM task WHERE status='done' AND date(created_at)=?",
        (today,),
    ).fetchone()
    stats["done_today"] = row["cnt"]
    return stats


_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS task (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id TEXT NOT NULL,
  source_url TEXT NOT NULL,
  source_url_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'fetching', 'writing', 'done', 'failed')),
  claimed_at TIMESTAMP NULL,
  error_code TEXT NULL,
  error_message TEXT NULL,
  correlation_id TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_task_status_claimed ON task(status, claimed_at);
"""
