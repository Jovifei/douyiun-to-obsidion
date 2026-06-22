"""Test VLM client v2 -- M6 Task 2.

Spec ref: VLMClient ABC + 多 provider 实现
VLMClient 抽象基类 → OllamaVLMClient / CloudVLMClient
get_vlm_client(config) 按配置路由到具体 provider。
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.vision.vlm_client import (
    VLMClient,
    VLMClientError,
    OllamaVLMClient,
    CloudVLMClient,
    get_vlm_client,
)


# ---------------------------------------------------------------------------
# 1. VLMClient ABC 不能直接实例化
# ---------------------------------------------------------------------------

class TestVLMClientABC:
    """VLMClient 是抽象基类，不可直接实例化。"""

    def test_cannot_instantiate_directly(self):
        """直接实例化 VLMClient 应抛出 TypeError。"""
        with pytest.raises(TypeError):
            VLMClient()

    def test_subclass_must_implement_describe_image(self):
        """子类未实现 describe_image 应抛出 TypeError。"""

        class IncompleteClient(VLMClient):
            pass

        with pytest.raises(TypeError):
            IncompleteClient()

    def test_concrete_subclass_works(self):
        """子类实现 describe_image 后可正常实例化。"""

        class DummyClient(VLMClient):
            def describe_image(self, image_path: Path, prompt: str) -> str:
                return "ok"

        client = DummyClient()
        assert client.describe_image(Path("x.jpg"), "test") == "ok"


# ---------------------------------------------------------------------------
# 2. OllamaVLMClient — 调用 ollama SDK
# ---------------------------------------------------------------------------

class TestOllamaVLMClient:
    """OllamaVLMClient 走 python-ollama SDK。"""

    def test_calls_ollama_sdk(self, tmp_path: Path):
        """正常调用时走 ollama.chat。"""
        img = tmp_path / "frame.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        mock_response = MagicMock()
        mock_response.message.content = "画面中有人在讲解"
        mock_chat = MagicMock(return_value=mock_response)

        client = OllamaVLMClient(model="qwen2.5-vl:7b", base_url="http://localhost:11434")
        with patch("src.vision.vlm_client.ollama.chat", mock_chat):
            result = client.describe_image(img, prompt="描述画面")

        assert result == "画面中有人在讲解"
        mock_chat.assert_called_once()
        call_kwargs = mock_chat.call_args
        assert call_kwargs[1]["model"] == "qwen2.5-vl:7b"

    def test_timeout_returns_fallback(self, tmp_path: Path):
        """ollama 超时返回降级文本。"""
        import ollama as _ollama_mod

        img = tmp_path / "frame.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        mock_chat = MagicMock(side_effect=_ollama_mod.ResponseError("timeout"))

        client = OllamaVLMClient(model="qwen2.5-vl:7b", base_url="http://localhost:11434")
        with patch("src.vision.vlm_client.ollama.chat", mock_chat):
            result = client.describe_image(img, prompt="描述画面")

        assert isinstance(result, str)
        assert "VLM" in result

    def test_file_not_found_returns_empty(self):
        """图片文件不存在返回空字符串。"""
        client = OllamaVLMClient(model="qwen2.5-vl:7b", base_url="http://localhost:11434")
        result = client.describe_image(Path("/nonexistent/path.jpg"), prompt="描述画面")
        assert result == ""


# ---------------------------------------------------------------------------
# 3. CloudVLMClient — 调用 httpx.post
# ---------------------------------------------------------------------------

class TestCloudVLMClient:
    """CloudVLMClient 走 httpx.post (OpenAI-compatible vision API)。"""

    def test_calls_httpx_post(self, tmp_path: Path):
        """正常调用时走 httpx.post。"""
        img = tmp_path / "frame.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "画面显示代码编辑器"}}],
        }

        client = CloudVLMClient(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
        )
        with patch("src.vision.vlm_client.httpx.post", return_value=mock_resp) as mock_post:
            result = client.describe_image(img, prompt="描述画面")

        assert result == "画面显示代码编辑器"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert "test-key" in call_kwargs[1]["headers"]["Authorization"]

    def test_timeout_returns_fallback(self, tmp_path: Path):
        """httpx 超时返回降级文本。"""
        img = tmp_path / "frame.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        client = CloudVLMClient(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
        )
        with patch("src.vision.vlm_client.httpx.post", side_effect=httpx.TimeoutException("timeout")):
            result = client.describe_image(img, prompt="描述画面")

        assert "VLM" in result

    def test_file_not_found_returns_empty(self):
        """图片文件不存在返回空字符串。"""
        client = CloudVLMClient(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-model",
        )
        result = client.describe_image(Path("/nonexistent/path.jpg"), prompt="描述画面")
        assert result == ""


# ---------------------------------------------------------------------------
# 4. get_vlm_client 工厂函数
# ---------------------------------------------------------------------------

class TestGetVLMClient:
    """get_vlm_client 按 config 路由到具体 provider。"""

    def test_ollama_provider(self):
        """provider=ollama 返回 OllamaVLMClient。"""
        config = {
            "vision": {
                "enabled": True,
                "provider": "ollama",
                "ollama": {
                    "model": "qwen2.5-vl:7b",
                    "base_url": "http://localhost:11434",
                },
            }
        }
        client = get_vlm_client(config)
        assert isinstance(client, OllamaVLMClient)

    def test_cloud_api_provider(self):
        """provider=cloud_api 返回 CloudVLMClient。"""
        config = {
            "vision": {
                "enabled": True,
                "provider": "cloud_api",
                "cloud_api": {
                    "base_url": "https://api.example.com/v1",
                    "model": "test-model",
                    "api_key_env": "VLM_API_KEY",
                },
            }
        }
        with patch.dict("os.environ", {"VLM_API_KEY": "test-key"}):
            client = get_vlm_client(config)
        assert isinstance(client, CloudVLMClient)

    def test_disabled_returns_none(self):
        """enabled=false 返回 None。"""
        config = {"vision": {"enabled": False}}
        client = get_vlm_client(config)
        assert client is None

    def test_unknown_provider_raises(self):
        """未知 provider 抛出 VLMClientError。"""
        config = {"vision": {"enabled": True, "provider": "unknown_provider"}}
        with pytest.raises(VLMClientError):
            get_vlm_client(config)
