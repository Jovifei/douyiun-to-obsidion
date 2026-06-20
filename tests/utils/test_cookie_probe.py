"""Test src/utils/cookie_probe.py — cookie HTTP 探活。

TDD: 3 tests covering:
8. test_cookie_probe_success — mock httpx 返回 200 → True
9. test_cookie_probe_failure — mock httpx 返回 401 → False
10. test_cookie_probe_file_not_found — cookies.txt 不存在 → False
"""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


class TestCookieProbeSuccess:
    """test_cookie_probe_success — mock httpx 返回 200 → True"""

    @patch("src.utils.cookie_probe.httpx")
    def test_probe_returns_true_on_200(self, mock_httpx, tmp_path):
        from src.utils.cookie_probe import probe_cookie

        # 创建临时 cookies.txt
        cookies_file = tmp_path / "cookies.txt"
        cookies_file.write_text("example.com\tTRUE\t/\tFALSE\t0\ttoken\tabc123\n")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx.Client.return_value.__enter__.return_value.get.return_value = mock_response

        result = probe_cookie(
            cookies_path=str(cookies_file),
            test_url="https://v.douyin.com/test/",
        )

        assert result is True


class TestCookieProbeFailure:
    """test_cookie_probe_failure — mock httpx 返回 401 → False"""

    @patch("src.utils.cookie_probe.httpx")
    def test_probe_returns_false_on_401(self, mock_httpx, tmp_path):
        from src.utils.cookie_probe import probe_cookie

        # 创建临时 cookies.txt
        cookies_file = tmp_path / "cookies.txt"
        cookies_file.write_text("example.com\tTRUE\t/\tFALSE\t0\ttoken\tabc123\n")

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_httpx.Client.return_value.__enter__.return_value.get.return_value = mock_response

        result = probe_cookie(
            cookies_path=str(cookies_file),
            test_url="https://v.douyin.com/test/",
        )

        assert result is False


class TestCookieProbeFileNotFound:
    """test_cookie_probe_file_not_found — cookies.txt 不存在 → False"""

    def test_probe_returns_false_when_file_missing(self, tmp_path):
        from src.utils.cookie_probe import probe_cookie

        nonexistent = tmp_path / "nonexistent_cookies.txt"
        result = probe_cookie(
            cookies_path=str(nonexistent),
            test_url="https://v.douyin.com/test/",
        )

        assert result is False
