"""Test src/pipeline/errors.py — is_retryable 分类函数。

M4 Task 2: 下载重试指数退避 + 可重试错误分类。

TDD: 5 tests covering:
1. is_retryable 函数存在
2. DownloadError("network timeout") → True
3. DownloadError("404 Not Found") → False
4. NoSubtitleError → False
5. TimeoutError → True
6. OSError → True
"""
import pytest

from src.pipeline.errors import is_retryable
from src.extractors.downloader import NoSubtitleError


class TestIsRetryableExists:
    """is_retryable 函数存在"""

    def test_function_is_callable(self):
        assert callable(is_retryable)


class TestIsRetryableDownloadNetworkTimeout:
    """DownloadError("network timeout") → True（可重试）"""

    def test_network_timeout_is_retryable(self):
        import yt_dlp
        error = yt_dlp.utils.DownloadError("network timeout")
        assert is_retryable(error) is True


class TestIsRetryableDownload404:
    """DownloadError("404 Not Found") → False（不可重试）"""

    def test_not_found_is_not_retryable(self):
        import yt_dlp
        error = yt_dlp.utils.DownloadError("404 Not Found")
        assert is_retryable(error) is False


class TestIsRetryableNoSubtitle:
    """NoSubtitleError → False（不可重试）"""

    def test_no_subtitle_not_retryable(self):
        error = NoSubtitleError("no subtitle in m1")
        assert is_retryable(error) is False


class TestIsRetryableTimeoutError:
    """TimeoutError → True（可重试）"""

    def test_timeout_error_is_retryable(self):
        error = TimeoutError("connection timed out")
        assert is_retryable(error) is True


class TestIsRetryableOSError:
    """OSError → True（可重试，网络层 OSError 如 ConnectionReset）"""

    def test_os_error_is_retryable(self):
        error = OSError("Connection reset by peer")
        assert is_retryable(error) is True
