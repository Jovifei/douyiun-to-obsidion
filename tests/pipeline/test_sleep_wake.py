"""Test src/utils/sleep_wake.py — clock jump 检测。

TDD: 4 tests covering:
1. test_normal_sleep_returns_false — 正常 5 秒循环间隔 → False
2. test_large_clock_jump_returns_true — clock jump > 60s（PC 睡眠恢复）→ True
3. test_threshold_boundary_returns_false — clock jump = 60s 恰好阈值 → False（不误触发）
4. test_first_run_returns_true — 首次启动（last=None）→ True
"""
from unittest.mock import patch

import pytest


class TestDetectSleepWakeNormalSleep:
    """test_normal_sleep_returns_false — 正常 5 秒循环间隔 → False"""

    def test_returns_false_for_normal_interval(self):
        from src.utils.sleep_wake import detect_sleep_wake

        with patch("src.utils.sleep_wake.time") as mock_time:
            mock_time.time.return_value = 1000.0
            assert detect_sleep_wake(995.0, threshold=60) is False


class TestDetectSleepWakeLargeClockJump:
    """test_large_clock_jump_returns_true — clock jump > 60s（PC 睡眠恢复）→ True"""

    def test_returns_true_for_large_jump(self):
        from src.utils.sleep_wake import detect_sleep_wake

        with patch("src.utils.sleep_wake.time") as mock_time:
            mock_time.time.return_value = 1000.0
            assert detect_sleep_wake(880.0, threshold=60) is True


class TestDetectSleepWakeThresholdBoundary:
    """test_threshold_boundary_returns_false — clock jump = 60s 恰好阈值 → False（不误触发）"""

    def test_returns_false_at_exact_threshold(self):
        from src.utils.sleep_wake import detect_sleep_wake

        with patch("src.utils.sleep_wake.time") as mock_time:
            mock_time.time.return_value = 1000.0
            assert detect_sleep_wake(940.0, threshold=60) is False


class TestDetectSleepWakeFirstRun:
    """test_first_run_returns_true — 首次启动（last=None）→ True"""

    def test_returns_true_when_last_is_none(self):
        from src.utils.sleep_wake import detect_sleep_wake

        assert detect_sleep_wake(None, threshold=60) is True
