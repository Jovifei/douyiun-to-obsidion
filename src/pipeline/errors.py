"""Pipeline 错误码枚举 + classify_exception() + is_retryable()。

Spec ref: tasks.md §12 — 日志与可观测性
D-M4-2: 退避序列 [0, 5, 30, 120, 600]
"""
from enum import Enum

from src.extractors.downloader import NoSubtitleError
from src.asr import ASRError

# 可重试的错误消息子串（小写匹配）
_RETRYABLE_MESSAGE_PATTERNS: list[str] = [
    "network timeout",
    "connection reset",
    "connection refused",
    "connection aborted",
    "temporarily unavailable",
    "service unavailable",
    "503",
    "502",
    "429",
    "timed out",
    "timeout",
]

# 不可重试的错误消息子串（优先级高于可重试）
_NON_RETRYABLE_MESSAGE_PATTERNS: list[str] = [
    "404",
    "403",
    "not found",
    "forbidden",
]


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


def is_retryable(error: Exception) -> bool:
    """判断异常是否可重试（用于下载失败的指数退避）。

    规则：
    - NoSubtitleError → 不可重试（内容问题，非网络）
    - TimeoutError → 可重试
    - OSError → 可重试（ConnectionReset 等网络层错误）
    - 其他异常：检查消息是否匹配可重试/不可重试模式

    Args:
        error: 捕获的异常

    Returns:
        True 表示可重试，False 表示不可重试
    """
    # 明确不可重试的异常类型
    if isinstance(error, NoSubtitleError):
        return False

    # 明确可重试的异常类型
    if isinstance(error, (TimeoutError, OSError)):
        return True

    # 按消息内容判断
    error_str = str(error).lower()

    # 不可重试模式优先检查
    for pattern in _NON_RETRYABLE_MESSAGE_PATTERNS:
        if pattern in error_str:
            return False

    # 可重试模式检查
    for pattern in _RETRYABLE_MESSAGE_PATTERNS:
        if pattern in error_str:
            return True

    return False
