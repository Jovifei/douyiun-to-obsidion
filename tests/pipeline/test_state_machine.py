"""Test pipeline/state_machine.py — 4 状态合法转移校验 + 审计日志。

Spec ref: specs/task-queue-pipeline/spec.md Requirement "状态机" + "状态转移审计日志"

TDD: 8 tests covering:
1. test_valid_transitions_all_legal_paths
2. test_invalid_transition_pending_to_writing (跳跃)
3. test_invalid_transition_done_to_pending (终态逆)
4. test_invalid_transition_failed_to_any
5. test_validate_transition_returns_bool
6. test_transition_calls_update_status (mock db.update_status)
7. test_transition_logs_state_transition (mock logging)
8. test_transition_with_error_code (failed 转移带 error_code/error_message)
"""
from unittest.mock import MagicMock, patch

import pytest

from src.pipeline.state_machine import (
    VALID_TRANSITIONS,
    IllegalTransitionError,
    validate_transition,
    transition,
)


# ── Test 1: 合法转移全覆盖 ──────────────────────────────────────────────


class TestValidTransitionsAllLegalPaths:
    """test_valid_transitions_all_legal_paths — 5 条合法路径全部 True"""

    def test_pending_to_fetching(self):
        assert validate_transition("pending", "fetching") is True

    def test_fetching_to_writing(self):
        assert validate_transition("fetching", "writing") is True

    def test_writing_to_done(self):
        assert validate_transition("writing", "done") is True

    def test_fetching_to_failed(self):
        assert validate_transition("fetching", "failed") is True

    def test_writing_to_failed(self):
        assert validate_transition("writing", "failed") is True


# ── Test 2: pending → writing 跳跃 ──────────────────────────────────────


class TestInvalidPendingToWriting:
    """test_invalid_transition_pending_to_writing — 跳过 fetching 非法"""

    def test_pending_to_writing(self):
        assert validate_transition("pending", "writing") is False


# ── Test 3: done → pending 终态逆 ──────────────────────────────────────


class TestInvalidDoneToPending:
    """test_invalid_transition_done_to_pending — 终态不可逆"""

    def test_done_to_pending(self):
        assert validate_transition("done", "pending") is False

    def test_done_to_fetching(self):
        assert validate_transition("done", "fetching") is False

    def test_done_to_writing(self):
        assert validate_transition("done", "writing") is False

    def test_done_to_failed(self):
        assert validate_transition("done", "failed") is False


# ── Test 4: failed → 任何状态 ───────────────────────────────────────────


class TestInvalidFailedToAny:
    """test_invalid_transition_failed_to_any — failed 终态不可逆"""

    def test_failed_to_pending(self):
        assert validate_transition("failed", "pending") is False

    def test_failed_to_fetching(self):
        assert validate_transition("failed", "fetching") is False

    def test_failed_to_writing(self):
        assert validate_transition("failed", "writing") is False

    def test_failed_to_done(self):
        assert validate_transition("failed", "done") is False


# ── Test 5: validate_transition 返回 bool ──────────────────────────────


class TestValidateTransitionReturnsBool:
    """test_validate_transition_returns_bool — 返回值类型为 bool"""

    def test_legal_returns_true_type(self):
        result = validate_transition("pending", "fetching")
        assert isinstance(result, bool)
        assert result is True

    def test_illegal_returns_false_type(self):
        result = validate_transition("done", "pending")
        assert isinstance(result, bool)
        assert result is False


# ── Test 6: transition 调用 db.update_status ────────────────────────────


class TestTransitionCallsUpdateStatus:
    """test_transition_calls_update_status — mock db.update_status，验证参数传递"""

    @patch("src.pipeline.state_machine.db")
    def test_calls_update_status_with_correct_args(self, mock_db):
        """transition 应调用 db.update_status(conn, task_id, to_status, ...)"""
        mock_conn = MagicMock()
        mock_db.update_status = MagicMock()

        transition(
            mock_conn,
            task_id=42,
            to_status="writing",
            from_status="fetching",
            correlation_id="corr-001",
        )

        mock_db.update_status.assert_called_once_with(
            mock_conn,
            42,
            "writing",
            error_code=None,
            error_message=None,
        )


# ── Test 7: transition 记录审计日志 ─────────────────────────────────────


class TestTransitionLogsStateTransition:
    """test_transition_logs_state_transition — mock logging，验证 INFO 日志"""

    @patch("src.pipeline.state_machine.db")
    @patch("src.pipeline.state_machine.logger")
    def test_logs_info_state_transition(self, mock_logger, mock_db):
        """transition 应记录 INFO state_transition 日志"""
        mock_conn = MagicMock()

        transition(
            mock_conn,
            task_id=7,
            to_status="done",
            from_status="writing",
            correlation_id="corr-999",
        )

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args[0][0] == "state_transition"
        log_data = call_args[1]
        assert log_data["task_id"] == 7
        assert log_data["from_status"] == "writing"
        assert log_data["to_status"] == "done"
        assert log_data["correlation_id"] == "corr-999"
        assert "timestamp" in log_data


# ── Test 8: transition 带 error_code ────────────────────────────────────


class TestTransitionRaisesIllegalTransitionError:
    """transition() 应在非法转移时抛 IllegalTransitionError（而非 ValueError）"""

    @patch("src.pipeline.state_machine.db")
    def test_done_to_pending_raises(self, mock_db):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = {"status": "done"}

        with pytest.raises(IllegalTransitionError, match="illegal.*done.*pending"):
            transition(mock_conn, task_id=1, to_status="pending")

    @patch("src.pipeline.state_machine.db")
    def test_pending_to_writing_raises(self, mock_db):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchone.return_value = {"status": "pending"}

        with pytest.raises(IllegalTransitionError, match="illegal.*pending.*writing"):
            transition(mock_conn, task_id=1, to_status="writing")

    def test_exception_is_subclass_of_value_error(self):
        """IllegalTransitionError 是 ValueError 子类，调用方 catch ValueError 仍能接住"""
        assert issubclass(IllegalTransitionError, ValueError)


class TestTransitionWithErrorCode:
    """test_transition_with_error_code — failed 转移带 error_code/error_message"""

    @patch("src.pipeline.state_machine.db")
    @patch("src.pipeline.state_machine.logger")
    def test_passes_error_code_to_update_status(self, mock_logger, mock_db):
        """transition 带 error_code 时应传递给 db.update_status"""
        mock_conn = MagicMock()

        transition(
            mock_conn,
            task_id=99,
            to_status="failed",
            from_status="fetching",
            correlation_id="corr-err-1",
            error_code="download_error",
            error_message="network timeout",
        )

        mock_db.update_status.assert_called_once_with(
            mock_conn,
            99,
            "failed",
            error_code="download_error",
            error_message="network timeout",
        )

    @patch("src.pipeline.state_machine.db")
    @patch("src.pipeline.state_machine.logger")
    def test_error_code_in_audit_log(self, mock_logger, mock_db):
        """transition 带 error_code 时日志中也包含 error_code"""
        mock_conn = MagicMock()

        transition(
            mock_conn,
            task_id=99,
            to_status="failed",
            from_status="fetching",
            correlation_id="corr-err-2",
            error_code="parse_error",
        )

        log_data = mock_logger.info.call_args[1]
        assert log_data["error_code"] == "parse_error"


# ── Bonus: VALID_TRANSITIONS 是 source of truth ─────────────────────────


class TestValidTransitionsDict:
    """VALID_TRANSITIONS dict 应包含所有合法转移"""

    def test_pending_allows_fetching_and_failed(self):
        assert VALID_TRANSITIONS["pending"] == {"fetching", "failed"}

    def test_fetching_allows_writing_and_failed(self):
        assert VALID_TRANSITIONS["fetching"] == {"writing", "failed"}

    def test_writing_allows_done_and_failed(self):
        assert VALID_TRANSITIONS["writing"] == {"done", "failed"}

    def test_done_is_terminal(self):
        assert VALID_TRANSITIONS["done"] == set()

    def test_failed_is_terminal(self):
        assert VALID_TRANSITIONS["failed"] == set()
