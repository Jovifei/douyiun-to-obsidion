"""Test src/utils/logging_config.py — structlog JSON 配置。

TDD: 3 tests covering:
1. test_logging_config_creates_log_dir — 配置后 logs/ 目录存在
2. test_logging_config_json_format — 日志输出是 JSON
3. test_logging_config_correlation_id_injected — 日志含 correlation_id
"""
import json
from pathlib import Path

import pytest
import structlog


@pytest.fixture(autouse=True)
def _reset_structlog():
    """每个测试前后重置 structlog 状态，确保测试隔离。"""
    from src.utils.logging_config import _reset_logging
    _reset_logging()
    yield
    _reset_logging()


class TestLoggingConfigCreatesLogDir:
    """test_logging_config_creates_log_dir — 配置后 logs/ 目录存在"""

    def test_log_dir_created(self, tmp_path):
        from src.utils.logging_config import configure_logging

        log_dir = tmp_path / "logs" / "scheduler"
        config = {
            "logging": {
                "level": "INFO",
                "dir": str(tmp_path / "logs"),
                "rotation": "daily",
            }
        }

        configure_logging(config, module_name="scheduler")

        assert log_dir.exists(), f"Log directory {log_dir} should exist"


class TestLoggingConfigJsonFormat:
    """test_logging_config_json_format — 日志输出是 JSON"""

    def test_log_output_is_json(self, tmp_path):
        from src.utils.logging_config import configure_logging

        config = {
            "logging": {
                "level": "INFO",
                "dir": str(tmp_path / "logs"),
                "rotation": "daily",
            }
        }

        configure_logging(config, module_name="test_json")

        logger = structlog.get_logger("test_json")
        logger.info("test_event", key="value")

        log_file = tmp_path / "logs" / "test_json"
        log_files = list(log_file.glob("*.log"))
        assert len(log_files) > 0, "Should have created a log file"

        with open(log_files[0], "r", encoding="utf-8") as f:
            line = f.readline().strip()
            if line:
                parsed = json.loads(line)
                assert "event" in parsed, f"JSON log should have 'event' key: {parsed}"
                assert parsed["event"] == "test_event"


class TestLoggingConfigCorrelationIdInjected:
    """test_logging_config_correlation_id_injected — 日志含 correlation_id"""

    def test_correlation_id_in_log(self, tmp_path):
        from src.utils.logging_config import configure_logging

        config = {
            "logging": {
                "level": "INFO",
                "dir": str(tmp_path / "logs"),
                "rotation": "daily",
            }
        }

        configure_logging(config, module_name="test_corr")

        logger = structlog.get_logger("test_corr")
        logger.info("test_event", correlation_id="abc-123-def")

        log_file = tmp_path / "logs" / "test_corr"
        log_files = list(log_file.glob("*.log"))
        assert len(log_files) > 0

        with open(log_files[0], "r", encoding="utf-8") as f:
            line = f.readline().strip()
            if line:
                parsed = json.loads(line)
                assert "correlation_id" in parsed, f"JSON log should have 'correlation_id': {parsed}"
                assert parsed["correlation_id"] == "abc-123-def"
