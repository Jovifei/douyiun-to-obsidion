"""Pipeline state machine — 4 状态合法转移校验 + 审计日志。

D-4 v2: pending → fetching → writing → done | failed
终态 done / failed 不可逆，非法转移抛 IllegalTransitionError。

Spec ref: specs/task-queue-pipeline/spec.md Requirement "状态机" + "状态转移审计日志"
"""
import logging
from datetime import datetime, timezone

from src.queue import db

logger = logging.getLogger(__name__)


class IllegalTransitionError(ValueError):
    """非法状态转移（如 done→pending、pending→writing）。"""
    pass


# source of truth for valid transitions
VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"fetching", "failed"},  # pending→failed 是有意扩展：URL 校验失败在 fetch 之前就能判
    "fetching": {"writing", "failed"},
    "writing": {"done", "failed"},
    "done": set(),
    "failed": set(),
}


def validate_transition(from_status: str, to_status: str) -> bool:
    """检查转移是否合法。纯函数，无 I/O。"""
    allowed = VALID_TRANSITIONS.get(from_status, set())
    return to_status in allowed


def transition(
    conn,
    task_id: int,
    to_status: str,
    from_status: str | None = None,
    correlation_id: str = "",
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    """执行状态转移：校验 + db.update_status + 审计日志。

    Args:
        conn: SQLite connection (row_factory=sqlite3.Row).
        task_id: 目标任务 ID。
        to_status: 目标状态。
        from_status: 已知的当前状态（可选，日志用）。
        correlation_id: 关联 ID（日志用）。
        error_code: 错误码（failed 转移时传入）。
        error_message: 错误消息（failed 转移时传入）。
    """
    # 如果调用方没给 from_status，从 DB 读
    if from_status is None:
        row = conn.execute(
            "SELECT status FROM task WHERE id=?", (task_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"task {task_id} not found")
        from_status = row["status"]

    # 校验合法转移
    if not validate_transition(from_status, to_status):
        raise IllegalTransitionError(
            f"illegal transition {from_status} -> {to_status}"
        )

    # 执行 DB 更新
    db.update_status(
        conn,
        task_id,
        to_status,
        error_code=error_code,
        error_message=error_message,
    )

    # 审计日志
    logger.info(
        "state_transition",
        task_id=task_id,
        from_status=from_status,
        to_status=to_status,
        correlation_id=correlation_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        error_code=error_code,
    )
