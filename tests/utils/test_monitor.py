"""Test src/utils/monitor.py — 飞书 webhook 告警。

TDD: 5 tests covering:
1. test_send_feishu_alert_returns_true_on_success — 正常调用 httpx.post 返回 True
2. test_send_feishu_alert_returns_false_on_timeout — 网络超时返回 False（不抛异常）
3. test_send_feishu_alert_returns_false_on_empty_url — webhook_url 为空直接跳过返回 False
4. test_is_alert_duplicate_returns_true_within_cooldown — 30 分钟内同类型告警去重
5. test_is_alert_duplicate_returns_false_after_cooldown — 超过冷却期可再次发送
"""
from unittest.mock import MagicMock, patch

import pytest


class TestSendFeishuAlertReturnsTrueOnSuccess:
    """test_send_feishu_alert_returns_true_on_success — 正常调用 httpx.post 返回 True"""

    def test_returns_true_on_success(self):
        from src.utils.monitor import send_feishu_alert

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("src.utils.monitor.httpx") as mock_httpx:
            mock_httpx.post.return_value = mock_response
            result = send_feishu_alert(
                webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/test",
                title="Test Alert",
                content="This is a test",
            )

        assert result is True


class TestSendFeishuAlertReturnsFalseOnTimeout:
    """test_send_feishu_alert_returns_false_on_timeout — 网络超时返回 False（不抛异常）"""

    def test_returns_false_on_timeout(self):
        from src.utils.monitor import send_feishu_alert

        with patch("src.utils.monitor.httpx") as mock_httpx:
            mock_httpx.post.side_effect = Exception("timeout")
            result = send_feishu_alert(
                webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/test",
                title="Test Alert",
                content="This is a test",
            )

        assert result is False


class TestSendFeishuAlertReturnsFalseOnEmptyUrl:
    """test_send_feishu_alert_returns_false_on_empty_url — webhook_url 为空直接跳过返回 False"""

    def test_returns_false_on_empty_url(self):
        from src.utils.monitor import send_feishu_alert

        result = send_feishu_alert(
            webhook_url="",
            title="Test Alert",
            content="This is a test",
        )

        assert result is False


class TestIsAlertDuplicateReturnsTrueWithinCooldown:
    """test_is_alert_duplicate_returns_true_within_cooldown — 30 分钟内同类型告警去重"""

    def test_returns_true_within_cooldown(self):
        from src.utils.monitor import is_alert_duplicate, _alert_cache

        _alert_cache.clear()
        alert_key = "test_duplicate_key"

        with patch("src.utils.monitor.time") as mock_time:
            mock_time.time.return_value = 1000.0
            # 第一次发送
            assert is_alert_duplicate(alert_key, cooldown_minutes=30) is False
            # 更新缓存（模拟发送成功）
            _alert_cache[alert_key] = 1000.0

            # 10 分钟后检查（仍在冷却期）
            mock_time.time.return_value = 1600.0
            assert is_alert_duplicate(alert_key, cooldown_minutes=30) is True

        _alert_cache.clear()


class TestIsAlertDuplicateReturnsFalseAfterCooldown:
    """test_is_alert_duplicate_returns_false_after_cooldown — 超过冷却期可再次发送"""

    def test_returns_false_after_cooldown(self):
        from src.utils.monitor import is_alert_duplicate, _alert_cache

        _alert_cache.clear()
        alert_key = "test_cooldown_key"

        with patch("src.utils.monitor.time") as mock_time:
            mock_time.time.return_value = 1000.0
            # 第一次发送
            assert is_alert_duplicate(alert_key, cooldown_minutes=30) is False
            # 更新缓存（模拟发送成功）
            _alert_cache[alert_key] = 1000.0

            # 31 分钟后检查（超过冷却期）
            mock_time.time.return_value = 2860.0
            assert is_alert_duplicate(alert_key, cooldown_minutes=30) is False

        _alert_cache.clear()
