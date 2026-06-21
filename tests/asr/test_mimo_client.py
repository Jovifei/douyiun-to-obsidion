"""MimoASRClient 单元测试 — M2 Task 2 TDD (RED phase).

验证 MimoASRClient 通过 openclaw MCP 工具 asr_transcribe 调用 mimo-v2.5-asr API。
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.asr import ASRClient, ASRResult
from src.asr.mimo_client import MimoASRClient, ASRError


class TestMimoASRClientInheritance:
    """MimoASRClient 继承 ASRClient ABC。"""

    def test_inherits_asr_client(self):
        """MimoASRClient 是 ASRClient 的子类。"""
        assert issubclass(MimoASRClient, ASRClient)

    def test_can_instantiate(self):
        """可以正常实例化 MimoASRClient。"""
        client = MimoASRClient()
        assert isinstance(client, ASRClient)


class TestTranscribeNormal:
    """正常转写场景。"""

    def test_transcribe_calls_mcp_tool(self, tmp_path: Path):
        """transcribe 调用 MCP 工具 asr_transcribe。"""
        # Create a fake audio file
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake-wav-data")

        mock_mcp_response = {
            "text": "这是一段测试语音",
            "segments": [{"start": 0.0, "end": 2.5, "text": "这是一段测试语音"}],
            "source": "mimo_asr",
            "confidence": 0.92,
        }

        client = MimoASRClient()
        with patch.object(client, "_call_mcp_tool", return_value=mock_mcp_response) as mock_call:
            result = client.transcribe(audio_file)

            mock_call.assert_called_once_with("asr_transcribe", audio_path=str(audio_file))
            assert isinstance(result, ASRResult)
            assert result.text == "这是一段测试语音"
            assert result.source == "mimo_asr"
            assert result.confidence == 0.92
            assert len(result.segments) == 1

    def test_transcribe_returns_asr_result(self, tmp_path: Path):
        """transcribe 返回正确的 ASRResult 实例。"""
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake-wav-data")

        mock_mcp_response = {
            "text": "转写结果",
            "segments": [],
            "source": "mimo_asr",
            "confidence": 0.85,
        }

        client = MimoASRClient()
        with patch.object(client, "_call_mcp_tool", return_value=mock_mcp_response):
            result = client.transcribe(audio_file)

            assert isinstance(result, ASRResult)
            assert result.source == "mimo_asr"


class TestTranscribeTimeout:
    """MCP 调用超时场景。"""

    def test_timeout_raises_asr_error(self, tmp_path: Path):
        """MCP 调用超时抛 ASRError(\"asr_timeout\")。"""
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake-wav-data")

        client = MimoASRClient()
        with patch.object(client, "_call_mcp_tool", side_effect=TimeoutError("MCP call timed out")):
            with pytest.raises(ASRError) as exc_info:
                client.transcribe(audio_file)
            assert exc_info.value.code == "asr_timeout"


class TestTranscribeEmptyResult:
    """MCP 返回空结果场景。"""

    def test_empty_text_raises_asr_error(self, tmp_path: Path):
        """MCP 返回空文本抛 ASRError(\"empty_result\")。"""
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake-wav-data")

        mock_mcp_response = {
            "text": "",
            "segments": [],
            "source": "mimo_asr",
            "confidence": 0.0,
        }

        client = MimoASRClient()
        with patch.object(client, "_call_mcp_tool", return_value=mock_mcp_response):
            with pytest.raises(ASRError) as exc_info:
                client.transcribe(audio_file)
            assert exc_info.value.code == "empty_result"

    def test_empty_segments_raises_asr_error(self, tmp_path: Path):
        """MCP 返回空 segments 抛 ASRError(\"empty_result\")。"""
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake-wav-data")

        mock_mcp_response = {
            "text": "  ",  # whitespace only
            "segments": [],
            "source": "mimo_asr",
            "confidence": 0.0,
        }

        client = MimoASRClient()
        with patch.object(client, "_call_mcp_tool", return_value=mock_mcp_response):
            with pytest.raises(ASRError) as exc_info:
                client.transcribe(audio_file)
            assert exc_info.value.code == "empty_result"
