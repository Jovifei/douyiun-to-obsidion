"""LLM Client 测试 — M6 Task 1。

验证 LLMClient ABC、OpenAICompatibleLLM、OllamaLocalLLM、get_llm_client 工厂。
"""
from unittest.mock import MagicMock, patch

import pytest

from src.llm.client import (
    LLMClient,
    LLMClientError,
    OllamaLocalLLM,
    OpenAICompatibleLLM,
    get_llm_client,
)


# ── LLMClientError ──────────────────────────────────────────


class TestLLMClientError:
    """LLMClientError 异常类契约。"""

    def test_code_and_message(self):
        """code 和 message 字段正确。"""
        err = LLMClientError(code="api_error", message="请求失败")
        assert err.code == "api_error"
        assert err.message == "请求失败"
        assert str(err) == "请求失败"

    def test_default_message_from_code(self):
        """未提供 message 时使用 code。"""
        err = LLMClientError(code="timeout")
        assert err.message == "timeout"


# ── LLMClient ABC ──────────────────────────────────────────


class TestLLMClientABC:
    """LLMClient 抽象基类契约。"""

    def test_cannot_instantiate_directly(self):
        """不能直接实例化 LLMClient。"""
        with pytest.raises(TypeError):
            LLMClient()  # type: ignore[abstract]

    def test_chat_method_exists(self):
        """chat 方法签名正确。"""
        import inspect

        sig = inspect.signature(LLMClient.chat)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "messages" in params
        assert sig.return_annotation == str

    def test_chat_json_method_exists(self):
        """chat_json 方法签名正确。"""
        import inspect

        sig = inspect.signature(LLMClient.chat_json)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "messages" in params
        assert sig.return_annotation == dict


# ── OpenAICompatibleLLM ────────────────────────────────────


class TestOpenAICompatibleLLM:
    """OpenAICompatibleLLM 实现契约。"""

    @patch("src.llm.client.httpx.Client")
    def test_chat_returns_string(self, mock_client_cls):
        """chat 返回字符串。"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "hello"}}]
        }
        mock_client_cls.return_value.post.return_value = mock_resp

        client = OpenAICompatibleLLM(
            base_url="https://api.test.com/v1",
            api_key="test-key",
            default_model="test-model",
        )
        result = client.chat([{"role": "user", "content": "hi"}])

        assert isinstance(result, str)
        assert result == "hello"

    @patch("src.llm.client.httpx.Client")
    def test_chat_uses_default_model(self, mock_client_cls):
        """chat 未指定 model 时使用 default_model。"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        mock_client_cls.return_value.post.return_value = mock_resp

        client = OpenAICompatibleLLM(
            base_url="https://api.test.com/v1",
            api_key="key",
            default_model="mimo-v2.5-pro",
        )
        client.chat([{"role": "user", "content": "test"}])

        call_json = mock_client_cls.return_value.post.call_args[1]["json"]
        assert call_json["model"] == "mimo-v2.5-pro"

    @patch("src.llm.client.httpx.Client")
    def test_chat_override_model(self, mock_client_cls):
        """chat 指定 model 时覆盖 default_model。"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        mock_client_cls.return_value.post.return_value = mock_resp

        client = OpenAICompatibleLLM(
            base_url="https://api.test.com/v1",
            api_key="key",
            default_model="default-model",
        )
        client.chat(
            [{"role": "user", "content": "test"}],
            model="override-model",
        )

        call_json = mock_client_cls.return_value.post.call_args[1]["json"]
        assert call_json["model"] == "override-model"

    @patch("src.llm.client.httpx.Client")
    def test_chat_timeout_raises_error(self, mock_client_cls):
        """超时抛出 LLMClientError。"""
        import httpx

        mock_client_cls.return_value.post.side_effect = httpx.TimeoutException(
            "timeout"
        )

        client = OpenAICompatibleLLM(
            base_url="https://api.test.com/v1",
            api_key="key",
            default_model="model",
        )
        with pytest.raises(LLMClientError, match="超时"):
            client.chat([{"role": "user", "content": "test"}])

    @patch("src.llm.client.httpx.Client")
    def test_chat_api_error_raises_error(self, mock_client_cls):
        """API 非 200 响应抛出 LLMClientError。"""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "internal error"
        mock_client_cls.return_value.post.return_value = mock_resp

        client = OpenAICompatibleLLM(
            base_url="https://api.test.com/v1",
            api_key="key",
            default_model="model",
        )
        with pytest.raises(LLMClientError, match="API 错误"):
            client.chat([{"role": "user", "content": "test"}])

    @patch("src.llm.client.httpx.Client")
    def test_chat_json_parses_json_response(self, mock_client_cls):
        """chat_json 解析 JSON 响应。"""
        import json

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        content = json.dumps(
            {"key_points": ["a", "b", "c"]}, ensure_ascii=False
        )
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": content}}]
        }
        mock_client_cls.return_value.post.return_value = mock_resp

        client = OpenAICompatibleLLM(
            base_url="https://api.test.com/v1",
            api_key="key",
            default_model="model",
        )
        result = client.chat_json([{"role": "user", "content": "test"}])

        assert isinstance(result, dict)
        assert result["key_points"] == ["a", "b", "c"]

    @patch("src.llm.client.httpx.Client")
    def test_chat_json_strips_markdown_fence(self, mock_client_cls):
        """chat_json 能处理 ```json``` 包裹的响应。"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        content = '```json\n{"key_points": ["x", "y"]}\n```'
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": content}}]
        }
        mock_client_cls.return_value.post.return_value = mock_resp

        client = OpenAICompatibleLLM(
            base_url="https://api.test.com/v1",
            api_key="key",
            default_model="model",
        )
        result = client.chat_json([{"role": "user", "content": "test"}])

        assert result["key_points"] == ["x", "y"]

    @patch("src.llm.client.httpx.Client")
    def test_chat_json_raises_on_invalid_json(self, mock_client_cls):
        """chat_json 遇到无效 JSON 抛出 LLMClientError。"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "not json at all"}}]
        }
        mock_client_cls.return_value.post.return_value = mock_resp

        client = OpenAICompatibleLLM(
            base_url="https://api.test.com/v1",
            api_key="key",
            default_model="model",
        )
        with pytest.raises(LLMClientError, match="无法从 LLM 响应中解析 JSON"):
            client.chat_json([{"role": "user", "content": "test"}])


# ── OllamaLocalLLM ─────────────────────────────────────────


class TestOllamaLocalLLM:
    """OllamaLocalLLM 实现契约。"""

    @patch("src.llm.client.ollama")
    def test_chat_calls_ollama_sdk(self, mock_ollama):
        """chat 调用 ollama SDK。"""
        mock_response = MagicMock()
        mock_response.message.content = "response text"
        mock_ollama.Client.return_value.chat.return_value = mock_response

        client = OllamaLocalLLM(model="qwen2.5:7b")
        result = client.chat([{"role": "user", "content": "hi"}])

        assert result == "response text"
        mock_ollama.Client.return_value.chat.assert_called_once()

    @patch("src.llm.client.ollama")
    def test_chat_uses_correct_model(self, mock_ollama):
        """chat 使用指定的 model。"""
        mock_response = MagicMock()
        mock_response.message.content = "ok"
        mock_ollama.Client.return_value.chat.return_value = mock_response

        client = OllamaLocalLLM(model="llama3:8b")
        client.chat([{"role": "user", "content": "test"}])

        call_kwargs = mock_ollama.Client.return_value.chat.call_args[1]
        assert call_kwargs["model"] == "llama3:8b"


# ── get_llm_client 工厂 ───────────────────────────────────


class TestGetLLMClient:
    """工厂函数 get_llm_client 路由。"""

    @patch("src.llm.client.os.environ", {"LLM_API_KEY": "env-key"})
    def test_openai_compatible_provider(self):
        """provider=openai_compatible 返回 OpenAICompatibleLLM。"""
        config = {
            "llm": {
                "provider": "openai_compatible",
                "openai_compatible": {
                    "base_url": "https://api.test.com/v1",
                    "model": "test-model",
                    "api_key_env": "LLM_API_KEY",
                },
            }
        }
        client = get_llm_client(config)
        assert isinstance(client, OpenAICompatibleLLM)

    @patch("src.llm.client.ollama")
    def test_ollama_local_provider(self, mock_ollama):
        """provider=ollama_local 返回 OllamaLocalLLM。"""
        config = {
            "llm": {
                "provider": "ollama_local",
                "ollama_local": {
                    "model": "qwen2.5:7b",
                    "base_url": "http://localhost:11434",
                },
            }
        }
        client = get_llm_client(config)
        assert isinstance(client, OllamaLocalLLM)

    def test_unknown_provider_raises(self):
        """未知 provider 抛出 ValueError。"""
        config = {"llm": {"provider": "nonexistent"}}
        with pytest.raises(ValueError, match="unknown.*provider"):
            get_llm_client(config)
