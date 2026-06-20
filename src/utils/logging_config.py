"""structlog JSON 配置 — configure_logging() 函数式 API。

Spec ref: tasks.md §12 — 日志与可观测性
"""
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from datetime import datetime

import structlog


_configured = False


def configure_logging(config: dict, module_name: str = "default") -> None:
    """配置 structlog：JSON 格式、日志路径 logs/{module}/{YYYY-MM-DD}.log。

    幂等：多次调用只配置一次。

    Args:
        config: 项目配置字典，需含 logging.level / logging.dir / logging.rotation
        module_name: 模块名，用于子目录命名（如 "scheduler"）
    """
    global _configured
    if _configured:
        return

    log_config = config.get("logging", {})
    level = getattr(logging, log_config.get("level", "INFO").upper(), logging.INFO)
    log_dir = Path(log_config.get("dir", "logs"))
    rotation = log_config.get("rotation", "daily")

    # rotation 映射: daily → D, hourly → H, etc.
    rotation_map = {"daily": "D", "hourly": "H", "weekly": "W0", "monthly": "M"}
    when = rotation_map.get(rotation.lower(), "D")

    # 创建日志目录
    log_subdir = log_dir / module_name
    log_subdir.mkdir(parents=True, exist_ok=True)

    # 活跃日志文件名 = {YYYY-MM-DD}.log（spec 要求）
    today_str = datetime.now().strftime("%Y-%m-%d")
    log_file = str(log_subdir / f"{today_str}.log")
    handler = TimedRotatingFileHandler(
        filename=log_file,
        when=when,
        backupCount=30,
        encoding="utf-8",
    )
    handler.suffix = "%Y-%m-%d"
    handler.setLevel(level)

    # 先配置 stdlib root logger（structlog 的 filter_by_level 依赖它）
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)

    # 再配置 structlog — 用 PrintLoggerFactory（不走 stdlib，避免 kwargs 传递问题）
    structlog.configure(
        processors=[
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # ProcessorFormatter 包装 handler
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
        foreign_pre_chain=[
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
        ],
    )
    handler.setFormatter(formatter)

    _configured = True
