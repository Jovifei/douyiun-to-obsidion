"""structlog JSON 配置 — configure_logging() 函数式 API。

Spec ref: tasks.md §12 — 日志与可观测性

日志输出方式：structlog PrintLoggerFactory → JSONRenderer → 直接写文件。
不走 stdlib logging handler，避免 filter_by_level / kwargs 传递问题。
"""
import sys
from datetime import datetime
from pathlib import Path

import structlog


_configured = False


def configure_logging(config: dict, module_name: str = "default") -> None:
    """配置 structlog：JSON 格式、日志直接写入 logs/{module}/{YYYY-MM-DD}.log。

    幂等：多次调用只配置一次。测试可通过 _reset_logging() 重置。

    Args:
        config: 项目配置字典，需含 logging.level / logging.dir
        module_name: 模块名，用于子目录命名（如 "scheduler"）
    """
    global _configured
    if _configured:
        return

    log_config = config.get("logging", {})
    level = log_config.get("level", "INFO").upper()
    log_dir = Path(log_config.get("dir", "logs"))
    rotation = log_config.get("rotation", "daily")

    # 创建日志目录
    log_subdir = log_dir / module_name
    log_subdir.mkdir(parents=True, exist_ok=True)

    # 日志文件路径：logs/{module}/{YYYY-MM-DD}.log
    today_str = datetime.now().strftime("%Y-%m-%d")
    log_file = log_subdir / f"{today_str}.log"

    # structlog 直接写文件，不走 stdlib
    log_file_handle = open(str(log_file), "a", encoding="utf-8")
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(
            file=log_file_handle
        ),
        wrapper_class=structlog.BoundLogger,
        cache_logger_on_first_use=True,
    )

    _log_file_handle = log_file_handle
    _configured = True


_log_file_handle = None


def _reset_logging() -> None:
    """重置 logging 配置状态（仅供测试用）。

    清除 structlog 的 logger 缓存：reset_defaults 只重置 configure 参数，
    不清除已缓存的 logger 实例。必须用 cache_logger_on_first_use=False
    配合一次 get_logger 调用来清除旧缓存。
    """
    global _configured, _log_file_handle
    if _log_file_handle:
        try:
            _log_file_handle.flush()
            _log_file_handle.close()
        except Exception:
            pass
        _log_file_handle = None
    _configured = False
    structlog.reset_defaults()
    # 强制 structlog 清除内部 logger 缓存
    structlog.configure(
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=False,
    )
    # 触发一次 get_logger 让旧缓存失效
    _throwaway = structlog.get_logger("__reset__")
