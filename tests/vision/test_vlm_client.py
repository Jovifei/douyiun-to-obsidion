"""Test VLM client — M3 Task 5.

Spec ref: D-M3-2 视觉分层（关键帧→OCR→VLM）
VLM 走 mimo-v2-omni API (chat/completions + image_url)。
VLM 失败不阻塞笔记生成，返回降级文本。
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.vision.vlm_client import describe_image


# ---------------------------------------------------------------------------
# 1. describe_image 函数存在，签名正确
# ---------------------------------------------------------------------------

def test_describe_image_signature():
    """函数存在且参数签名匹配 spec。"""
    import inspect
    sig = inspect.signature(describe_image)
    params = list(sig.parameters.keys())
    assert "image_path" in params
    assert "prompt" in params
    assert "api_key" in params
    assert "base_url" in params


# ---------------------------------------------------------------------------
# 2. 正常调用返回描述文本
# ---------------------------------------------------------------------------

def test_describe_image_returns_text(tmp_path: Path):
    """正常 API 调用返回描述文本。"""
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # fake JPEG

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "画面中显示一个人在讲台上讲解 Python 代码"}}],
    }

    with patch("src.vision.vlm_client.httpx.post", return_value=mock_resp):
        result = describe_image(img, prompt="描述画面", api_key="test-key")

    assert isinstance(result, str)
    assert "Python" in result


# ---------------------------------------------------------------------------
# 3. 调用 mimo-v2-omni API 格式正确
# ---------------------------------------------------------------------------

def test_api_format_correct(tmp_path: Path):
    """验证 API 请求格式：model=mimo-v2-omni, image_url data URL。"""
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "描述"}}],
    }

    with patch("src.vision.vlm_client.httpx.post", return_value=mock_resp) as mock_post:
        describe_image(img, prompt="描述画面", api_key="sk-test", base_url="https://test.com/v1")

        call_args = mock_post.call_args
        assert "https://test.com/v1/chat/completions" == call_args[0][0]
        assert call_args[1]["headers"]["Authorization"] == "Bearer sk-test"
        body = call_args[1]["json"]
        assert body["model"] == "mimo-v2-omni"
        content = body["messages"][0]["content"]
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "描述画面"
        assert content[1]["type"] == "image_url"
        assert "data:image/jpeg;base64," in content[1]["image_url"]["url"]


# ---------------------------------------------------------------------------
# 4. 默认 prompt 正确
# ---------------------------------------------------------------------------

def test_default_prompt(tmp_path: Path):
    """未指定 prompt 时使用默认 prompt。"""
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "描述"}}],
    }

    with patch("src.vision.vlm_client.httpx.post", return_value=mock_resp) as mock_post:
        describe_image(img, prompt=None, api_key="test-key")

        body = mock_post.call_args[1]["json"]
        assert "抖音" in body["messages"][0]["content"][0]["text"]


# ---------------------------------------------------------------------------
# 5. API 超时 → 返回降级文本
# ---------------------------------------------------------------------------

def test_timeout_returns_degraded_text(tmp_path: Path):
    """API 超时返回降级文本，不抛异常。"""
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

    with patch("src.vision.vlm_client.httpx.post", side_effect=httpx.TimeoutException("timeout")):
        result = describe_image(img, prompt="描述画面", api_key="test-key")

    assert isinstance(result, str)
    assert "VLM 超时" in result
    assert "画面内容未提取" in result


# ---------------------------------------------------------------------------
# 6. API 错误 → 返回降级文本
# ---------------------------------------------------------------------------

def test_api_error_returns_degraded_text(tmp_path: Path):
    """非 200 响应返回降级文本，不抛异常。"""
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"

    with patch("src.vision.vlm_client.httpx.post", return_value=mock_resp):
        result = describe_image(img, prompt="描述画面", api_key="bad-key")

    assert isinstance(result, str)
    assert "VLM 调用失败" in result
    assert "401" in result


# ---------------------------------------------------------------------------
# 7. 图片不存在 → 返回空字符串
# ---------------------------------------------------------------------------

def test_nonexistent_image_returns_empty_string():
    """不存在的图片路径返回空字符串。"""
    fake_img = Path("/nonexistent/path/frame.jpg")
    result = describe_image(fake_img, prompt="描述画面", api_key="test-key")
    assert result == ""


# ---------------------------------------------------------------------------
# 8. 网络错误 → 返回降级文本
# ---------------------------------------------------------------------------

def test_network_error_returns_degraded_text(tmp_path: Path):
    """网络异常返回降级文本，不抛异常。"""
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

    with patch("src.vision.vlm_client.httpx.post", side_effect=httpx.RequestError("network error")):
        result = describe_image(img, prompt="描述画面", api_key="test-key")

    assert isinstance(result, str)
    assert "VLM 调用失败" in result
