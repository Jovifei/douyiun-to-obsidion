"""Pipeline 错误码枚举 + classify_exception()。

Spec ref: tasks.md §12 — 日志与可观测性
"""
from enum import Enum

from src.extractors.downloader import NoSubtitleError
from src.asr import ASRError


class ErrorCode(Enum):
    """错误码枚举，映射 pipeline 失败场景。"""
    NO_SUBTITLE_IN_M1 = "no_subtitle_in_m1"
    DOWNLOAD_FAILED_ALL_TOOLS = "download_failed_all_tools"
    COOKIE_EXPIRED = "cookie_expired"
    INCOMPLETE_FRONTMATTER = "incomplete_frontmatter"
    WRITE_FAILED = "write_failed"
    ASR_FAILED = "asr_failed"
    UNKNOWN = "unknown_error"


def classify_exception(error: Exception) -> ErrorCode:
    """根据异常类型 + 消息字符串映射到 ErrorCode。

    Args:
        error: 捕获的异常

    Returns:
        对应的 ErrorCode 枚举值
    """
    if isinstance(error, NoSubtitleError):
        return ErrorCode.NO_SUBTITLE_IN_M1

    if isinstance(error, ASRError):
        return ErrorCode.ASR_FAILED

    error_str = str(error).lower()

    if "cookie" in error_str:
        return ErrorCode.COOKIE_EXPIRED

    try:
        import yt_dlp
        if isinstance(error, yt_dlp.utils.DownloadError):
            return ErrorCode.DOWNLOAD_FAILED_ALL_TOOLS
    except ImportError:
        pass

    if "douk" in error_str or "download" in error_str:
        return ErrorCode.DOWNLOAD_FAILED_ALL_TOOLS

    if "frontmatter" in error_str:
        return ErrorCode.INCOMPLETE_FRONTMATTER

    if isinstance(error, OSError):
        return ErrorCode.WRITE_FAILED

    return ErrorCode.UNKNOWN
