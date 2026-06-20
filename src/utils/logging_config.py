"""structlog JSON 配置 — configure_logging() 函数式 API。

Spec ref: tasks.md §12 — 日志与可观测性
"""
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import structlog


def configure_logging(config: dict, module_name: str = "default") -> None:
    """配置 structlog：JSON 格式、日志路径 logs/{module}/{YYYY-MM-DD}.log。

    Args:
        config: 项目配置字典，需含 logging.level / logging.dir / logging.rotation
        module_name: 模块名，用于子目录命名（如 "scheduler"）
    """
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

    # 配置 stdlib handler — 活跃日志文件名 = {YYYY-MM-DD}.log（spec 要求）
    # TimedRotatingFileHandler 的 baseFilename 用当天日期，午夜轮转时自动更新
    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d")
    log_file = str(log_subdir / f"{today_str}.log")
    handler = TimedRotatingFileHandler(
        filename=log_file,
        when=when,
        backupCount=30,
        encoding="utf-8",
    )
    # 午夜轮转后新文件名也带日期（suffix 是空，baseFilename 每次轮转时重新计算）
    handler.suffix = "%Y-%m-%d"
    handler.setLevel(level)

    # 配置 structlog — 使用 ProcessorFormatter 传递额外参数
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 使用 ProcessorFormatter 包装 handler
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
        foreign_pre_chain=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
        ],
    )
    handler.setFormatter(formatter)

    # 添加 handler 到 root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)
