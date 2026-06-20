"""Test SQLite queue: enqueue / atomic_dequeue / reclaim_zombie / update_status.

Spec ref: specs/task-queue-pipeline/spec.md
- Scenario: 新任务入队 → status='pending', claimed_at=NULL
- Scenario: 单 worker dequeue → status='fetching', claimed_at=now()
- Scenario: 队列为空 → dequeue 返回 None
- Scenario: 进程崩溃后重启（fetching 卡住）→ reclaim 后回 pending
- Scenario: 正常运行中不复活（claimed_at < 30min）
- Scenario: status 枚举约束 → 设 'processing' 应被 CHECK 拒绝
"""
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from src.queue.db import (
    init_db,
    enqueue,
    atomic_dequeue,
    reclaim_zombie_tasks,
    update_status,
    get_task,
    queue_stats,
)


@pytest.fixture
def db(tmp_path):
    """初始化 db 并返回 connection（row_factory=Row）。"""
    db_path = tmp_path / "q.sqlite3"
    conn = init_db(db_path)
    yield conn
    conn.close()


# ── Step 6.1: RED tests ────────────────────────────────────────────────


class TestInitDb:
    """test_init_db_creates_table — 建表后 sqlite_master 含 task 表"""

    def test_creates_table(self, db):
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='task'"
        ).fetchone()
        assert row is not None
        assert row["name"] == "task"


class TestEnqueue:
    """入队测试"""

    def test_returns_task_id(self, db):
        """入队返回 int id"""
        tid = enqueue(
            db,
            video_id="v1",
            source_url="https://v.douyin.com/x/",
            source_url_type="short",
            correlation_id="c1",
        )
        assert isinstance(tid, int)
        assert tid > 0

    def test_default_status_pending_claimed_at_null(self, db):
        """入队后 status='pending', claimed_at IS NULL"""
        tid = enqueue(
            db,
            video_id="v2",
            source_url="https://v.douyin.com/y/",
            source_url_type="short",
            correlation_id="c2",
        )
        row = db.execute(
            "SELECT status, claimed_at FROM task WHERE id=?", (tid,)
        ).fetchone()
        assert row["status"] == "pending"
        assert row["claimed_at"] is None


class TestAtomicDequeue:
    """原子 dequeue 测试"""

    def test_sets_fetching_and_claimed_at(self, db):
        """dequeue 后 status='fetching', claimed_at 非 null"""
        enqueue(
            db,
            video_id="v1",
            source_url="u1",
            source_url_type="short",
            correlation_id="c1",
        )
        task = atomic_dequeue(db)
        assert task is not None
        assert task["status"] == "fetching"
        assert task["claimed_at"] is not None

    def test_empty_queue_returns_none(self, db):
        """队列为空时 dequeue 返回 None"""
        assert atomic_dequeue(db) is None

    def test_fifo_order(self, db):
        """入 3 条，dequeue 顺序按 id"""
        ids = []
        for i in range(3):
            tid = enqueue(
                db,
                video_id=f"v{i}",
                source_url=f"u{i}",
                source_url_type="short",
                correlation_id=f"c{i}",
            )
            ids.append(tid)

        dequeued = []
        for _ in range(3):
            t = atomic_dequeue(db)
            assert t is not None
            dequeued.append(t["id"])

        assert dequeued == ids  # FIFO


class TestReclaimZombie:
    """zombie 复活测试"""

    def test_reclaim_zombie_fetching(self, db):
        """fetching 任务 claimed_at = 1 小时前 → reclaim 后回 pending"""
        tid = enqueue(
            db,
            video_id="v1",
            source_url="u1",
            source_url_type="short",
            correlation_id="c1",
        )
        atomic_dequeue(db)  # 置 fetching
        old_time = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        db.execute("UPDATE task SET claimed_at=? WHERE id=?", (old_time, tid))
        db.commit()

        reclaimed = reclaim_zombie_tasks(db, timeout_minutes=30)
        assert reclaimed == 1
        row = db.execute(
            "SELECT status, claimed_at FROM task WHERE id=?", (tid,)
        ).fetchone()
        assert row["status"] == "pending"
        assert row["claimed_at"] is None

    def test_reclaim_zombie_writing(self, db):
        """writing 任务 claimed_at 超时 → 也回 pending"""
        tid = enqueue(
            db,
            video_id="v1",
            source_url="u1",
            source_url_type="short",
            correlation_id="c1",
        )
        atomic_dequeue(db)
        db.execute("UPDATE task SET status='writing' WHERE id=?", (tid,))
        db.commit()
        old_time = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        db.execute("UPDATE task SET claimed_at=? WHERE id=?", (old_time, tid))
        db.commit()

        reclaimed = reclaim_zombie_tasks(db, timeout_minutes=30)
        assert reclaimed == 1
        row = db.execute(
            "SELECT status FROM task WHERE id=?", (tid,)
        ).fetchone()
        assert row["status"] == "pending"

    def test_recent_not_reclaimed(self, db):
        """claimed_at = 5min 前（仍在处理）→ 不复活"""
        tid = enqueue(
            db,
            video_id="v1",
            source_url="u1",
            source_url_type="short",
            correlation_id="c1",
        )
        atomic_dequeue(db)
        reclaimed = reclaim_zombie_tasks(db, timeout_minutes=30)
        assert reclaimed == 0


class TestUpdateStatus:
    """状态转移测试"""

    def test_valid_transition(self, db):
        """pending → fetching → writing → done 全链合法"""
        tid = enqueue(
            db,
            video_id="v1",
            source_url="u1",
            source_url_type="short",
            correlation_id="c1",
        )

        # pending → fetching
        atomic_dequeue(db)
        row = db.execute(
            "SELECT status FROM task WHERE id=?", (tid,)
        ).fetchone()
        assert row["status"] == "fetching"

        # fetching → writing
        update_status(db, tid, "writing")
        row = db.execute(
            "SELECT status FROM task WHERE id=?", (tid,)
        ).fetchone()
        assert row["status"] == "writing"

        # writing → done
        update_status(db, tid, "done")
        row = db.execute(
            "SELECT status FROM task WHERE id=?", (tid,)
        ).fetchone()
        assert row["status"] == "done"

    def test_fetching_to_failed_valid(self, db):
        """fetching → failed 合法"""
        tid = enqueue(
            db,
            video_id="v1",
            source_url="u1",
            source_url_type="short",
            correlation_id="c1",
        )
        atomic_dequeue(db)
        update_status(db, tid, "failed", error_code="download_error")
        row = db.execute(
            "SELECT status, error_code FROM task WHERE id=?", (tid,)
        ).fetchone()
        assert row["status"] == "failed"
        assert row["error_code"] == "download_error"

    def test_invalid_transition_raises(self, db):
        """done → pending 非法转移抛 ValueError"""
        tid = enqueue(
            db,
            video_id="v1",
            source_url="u1",
            source_url_type="short",
            correlation_id="c1",
        )
        atomic_dequeue(db)
        update_status(db, tid, "writing")
        update_status(db, tid, "done")

        with pytest.raises(ValueError, match="illegal.*transition"):
            update_status(db, tid, "pending")

    def test_pending_to_writing_raises(self, db):
        """pending → writing（跳过 fetching）非法"""
        tid = enqueue(
            db,
            video_id="v1",
            source_url="u1",
            source_url_type="short",
            correlation_id="c1",
        )
        with pytest.raises(ValueError, match="illegal.*transition"):
            update_status(db, tid, "writing")

    def test_same_status_noop(self, db):
        """同状态转移（如 fetching → fetching）不抛错但也不改"""
        tid = enqueue(
            db,
            video_id="v1",
            source_url="u1",
            source_url_type="short",
            correlation_id="c1",
        )
        atomic_dequeue(db)
        # fetching → fetching should be allowed (no-op)
        update_status(db, tid, "fetching")
        row = db.execute(
            "SELECT status FROM task WHERE id=?", (tid,)
        ).fetchone()
        assert row["status"] == "fetching"


class TestCheckConstraint:
    """CHECK 约束测试"""

    def test_rejects_processing(self, db):
        """直接 SQL 设 status='processing' 应被 CHECK 拒"""
        tid = enqueue(
            db,
            video_id="v1",
            source_url="u1",
            source_url_type="short",
            correlation_id="c1",
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE task SET status='processing' WHERE id=?", (tid,))
            db.commit()


class TestQueueStats:
    """队列统计测试"""

    def test_counts(self, db):
        """建若干条不同状态任务后查 stats 正确"""
        # pending
        for i in range(3):
            enqueue(
                db,
                video_id=f"p{i}",
                source_url=f"u{i}",
                source_url_type="short",
                correlation_id=f"c{i}",
            )
        # fetching (dequeue 2)
        for _ in range(2):
            atomic_dequeue(db)

        # writing (move one to writing)
        tid = enqueue(
            db,
            video_id="pw",
            source_url="uw",
            source_url_type="short",
            correlation_id="cw",
        )
        t = atomic_dequeue(db)
        update_status(db, t["id"], "writing")

        # done (move another to done)
        tid2 = enqueue(
            db,
            video_id="pd",
            source_url="ud",
            source_url_type="short",
            correlation_id="cd",
        )
        t2 = atomic_dequeue(db)
        update_status(db, t2["id"], "writing")
        update_status(db, t2["id"], "done")

        # failed
        tid3 = enqueue(
            db,
            video_id="pf",
            source_url="uf",
            source_url_type="short",
            correlation_id="cf",
        )
        t3 = atomic_dequeue(db)
        update_status(db, t3["id"], "failed", error_code="test_error")

        stats = queue_stats(db)
        # 3 pending 入队 - 2 dequeued = 1 + 2 more (pw, pd) = 3, but pw/pd were dequeued
        # Let's recount:
        # p0, p1, p2 (3 pending) → dequeue p0, p1 → 1 pending (p2)
        # pw → enqueued → dequeued → writing → 1 writing
        # pd → enqueued → dequeued → writing → done → 1 done
        # pf → enqueued → dequeued → failed → 1 failed
        # pending: p2 = 1
        # fetching: p0 went to writing, p1 still fetching? No - p0,p1 were dequeued, both set to fetching
        #   but p0 was not moved further, p1 was not moved further. Wait, no.
        # Let me trace more carefully:
        # First loop (3 times): enqueue p0, p1, p2 → all pending
        # Second loop (2 times): dequeue → p0=fetching, p1=fetching → 2 fetching
        # Then: enqueue pw → dequeue pw → update_status(pw, writing) → 1 writing, 2 fetching still
        # Then: enqueue pd → dequeue pd → update_status(pd, writing) → update_status(pd, done) → 1 done
        # Then: enqueue pf → dequeue pf → update_status(pf, failed) → 1 failed
        # So: pending=1 (p2), fetching=2 (p0,p1), writing=1 (pw), done=1 (pd), failed=1 (pf)
        assert stats["pending"] == 1
        assert stats["fetching"] == 2
        assert stats["writing"] == 1
        assert stats["done"] == 1
        assert stats["failed"] == 1


class TestGetTask:
    """get_task 测试"""

    def test_returns_full_record(self, db):
        """get_task 返回完整记录"""
        tid = enqueue(
            db,
            video_id="v_full",
            source_url="https://v.douyin.com/full/",
            source_url_type="short",
            correlation_id="corr-full-123",
            payload={"title": "test", "author": "tester"},
        )
        task = get_task(db, tid)
        assert task is not None
        assert task["id"] == tid
        assert task["video_id"] == "v_full"
        assert task["source_url"] == "https://v.douyin.com/full/"
        assert task["source_url_type"] == "short"
        assert task["status"] == "pending"
        assert task["correlation_id"] == "corr-full-123"
        assert task["claimed_at"] is None
        assert task["error_code"] is None
        assert task["error_message"] is None
        assert "test" in task["payload_json"]

    def test_returns_none_for_missing(self, db):
        """get_task 对不存在的 id 返回 None"""
        assert get_task(db, 99999) is None
