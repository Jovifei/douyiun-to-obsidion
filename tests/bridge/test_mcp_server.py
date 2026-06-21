"""MCP server tests — M2 Task 2 TDD (RED phase).

验证 asr_transcribe MCP 工具注册。
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from src.bridge.mcp_server import MCPToolServer, asr_transcribe_tool


class TestMCPToolServer:
    """MCPToolServer 基础契约。"""

    def test_server_has_asr_transcribe(self):
        """server 注册了 asr_transcribe 工具。"""
        server = MCPToolServer()
        assert "asr_transcribe" in server.tools

    def test_asr_transcribe_tool_metadata(self):
        """asr_transcribe 工具有正确的元数据。"""
        tool = asr_transcribe_tool
        assert tool["name"] == "asr_transcribe"
        assert "audio_path" in tool["parameters"]["properties"]
        assert tool["parameters"]["required"] == ["audio_path"]


class TestASRTranscribeTool:
    """asr_transcribe 工具函数测试。"""

    def test_asr_transcribe_returns_dict(self, tmp_path):
        """asr_transcribe 返回包含 text/segments/source/confidence 的 dict。"""
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake-wav-data")

        mock_response = {
            "text": "测试转写结果",
            "segments": [{"start": 0.0, "end": 2.0, "text": "测试转写结果"}],
            "source": "mimo_asr",
            "confidence": 0.9,
        }
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = json.dumps(mock_response)

        with patch("src.bridge.mcp_server.subprocess.run", return_value=mock_proc):
            result = asr_transcribe_tool["function"](audio_path=str(audio_file))

        assert isinstance(result, dict)
        assert "text" in result
        assert "segments" in result
        assert "source" in result
        assert "confidence" in result
        assert result["text"] == "测试转写结果"
