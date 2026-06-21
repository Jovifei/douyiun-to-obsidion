"""MimoASRClient 单元测试 — M2 Task 2。

验证 MimoASRClient 通过 mimo-v2.5-asr API (chat/completions + input_audio) 转写。
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.asr import ASRClient, ASRResult
from src.asr.mimo_client import MimoASRClient, ASRError


class TestMimoASRClientInheritance:
    """MimoASRClient 继承 ASRClient ABC。"""

    def test_inherits_asr_client(self):
        assert issubclass(MimoASRClient, ASRClient)

    def test_can_instantiate(self):
        client = MimoASRClient(api_key="test-key")
        assert isinstance(client, ASRClient)


class TestTranscribeNormal:
    """正常转写场景。"""

    def test_transcribe_returns_asr_result(self, tmp_path: Path):
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"RIFF" + b"\x00" * 100)  # fake WAV

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "这是一段测试语音"}}],
            "usage": {"prompt_tokens": 100, "prompt_tokens_details": {"audio_tokens": 80}},
        }

        client = MimoASRClient(api_key="test-key")
        with patch("src.asr.mimo_client.httpx.post", return_value=mock_resp):
            result = client.transcribe(audio_file)

        assert isinstance(result, ASRResult)
        assert result.text == "这是一段测试语音"
        assert result.source == "mimo_asr"
        assert result.confidence > 0
        assert len(result.segments) == 1

    def test_transcribe_sends_correct_api_format(self, tmp_path: Path):
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"RIFF" + b"\x00" * 100)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "结果"}}],
            "usage": {"prompt_tokens": 50, "prompt_tokens_details": {"audio_tokens": 40}},
        }

        client = MimoASRClient(api_key="sk-test", base_url="https://test.com/v1")
        with patch("src.asr.mimo_client.httpx.post", return_value=mock_resp) as mock_post:
            client.transcribe(audio_file)

            call_args = mock_post.call_args
            assert "https://test.com/v1/chat/completions" == call_args[0][0]
            assert call_args[1]["headers"]["Authorization"] == "Bearer sk-test"
            body = call_args[1]["json"]
            assert body["model"] == "mimo-v2.5-asr"
            assert body["messages"][0]["content"][0]["type"] == "input_audio"
            assert "data:audio/wav;base64," in body["messages"][0]["content"][0]["input_audio"]["data"]


class TestTranscribeTimeout:
    """API 超时场景。"""

    def test_timeout_raises_asr_error(self, tmp_path: Path):
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"RIFF" + b"\x00" * 100)

        client = MimoASRClient(api_key="test-key")
        with patch("src.asr.mimo_client.httpx.post", side_effect=httpx.TimeoutException("timeout")):
            with pytest.raises(ASRError) as exc_info:
                client.transcribe(audio_file)
            assert "asr_timeout" in exc_info.value.code


class TestTranscribeApiError:
    """API 错误场景。"""

    def test_non_200_raises_asr_error(self, tmp_path: Path):
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"RIFF" + b"\x00" * 100)

        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"

        client = MimoASRClient(api_key="bad-key")
        with patch("src.asr.mimo_client.httpx.post", return_value=mock_resp):
            with pytest.raises(ASRError) as exc_info:
                client.transcribe(audio_file)
            assert "asr_api_error_401" in exc_info.value.code


class TestTranscribeEmptyResult:
    """API 返回空结果场景。"""

    def test_empty_text_raises_asr_error(self, tmp_path: Path):
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"RIFF" + b"\x00" * 100)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": ""}}],
            "usage": {"prompt_tokens": 10, "prompt_tokens_details": {"audio_tokens": 5}},
        }

        client = MimoASRClient(api_key="test-key")
        with patch("src.asr.mimo_client.httpx.post", return_value=mock_resp):
            with pytest.raises(ASRError) as exc_info:
                client.transcribe(audio_file)
            assert "empty_result" in exc_info.value.code
