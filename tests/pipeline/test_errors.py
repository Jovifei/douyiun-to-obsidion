"""Test src/pipeline/errors.py — ErrorCode 枚举 + classify_exception。

TDD: 4 tests covering:
4. test_error_code_enum_values — ErrorCode 6 个枚举值正确
5. test_classify_exception_no_subtitle — NoSubtitleError → NO_SUBTITLE_IN_M1
6. test_classify_exception_download_failed — DownloadError → DOWNLOAD_FAILED_ALL_TOOLS
7. test_classify_exception_cookie — "cookie" in error → COOKIE_EXPIRED
"""
import pytest

from src.pipeline.errors import ErrorCode, classify_exception


class TestErrorCodeEnumValues:
    """test_error_code_enum_values — ErrorCode 6 个枚举值正确"""

    def test_enum_has_all_values(self):
        expected_values = {
            "NO_SUBTITLE_IN_M1",
            "DOWNLOAD_FAILED_ALL_TOOLS",
            "COOKIE_EXPIRED",
            "INCOMPLETE_FRONTMATTER",
            "WRITE_FAILED",
            "UNKNOWN",
        }
        actual_values = {e.name for e in ErrorCode}
        assert actual_values == expected_values, f"Missing: {expected_values - actual_values}, Extra: {actual_values - expected_values}"


class TestClassifyExceptionNoSubtitle:
    """test_classify_exception_no_subtitle — NoSubtitleError → NO_SUBTITLE_IN_M1"""

    def test_no_subtitle_error(self):
        from src.extractors.downloader import NoSubtitleError

        error = NoSubtitleError("no_subtitle_in_m1")
        result = classify_exception(error)
        assert result == ErrorCode.NO_SUBTITLE_IN_M1


class TestClassifyExceptionDownloadFailed:
    """test_classify_exception_download_failed — DownloadError → DOWNLOAD_FAILED_ALL_TOOLS"""

    def test_download_error(self):
        import yt_dlp

        error = yt_dlp.utils.DownloadError("network error")
        result = classify_exception(error)
        assert result == ErrorCode.DOWNLOAD_FAILED_ALL_TOOLS


class TestClassifyExceptionCookie:
    """test_classify_exception_cookie — "cookie" in error → COOKIE_EXPIRED"""

    def test_cookie_in_message(self):
        error = Exception("cookie has expired")
        result = classify_exception(error)
        assert result == ErrorCode.COOKIE_EXPIRED
