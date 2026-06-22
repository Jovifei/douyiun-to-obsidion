"""VLM Client — M3 Task 5 + M6 Task 2。

VLMClient ABC + 多 provider 实现。
旧 describe_image() 函数保留向后兼容。
"""
import base64
import os
from abc import ABC, abstractmethod
from pathlib import Path

import httpx
import ollama

_DEFAULT_PROMPT = "这是一段抖音知识视频的关键帧，请用一句话描述画面中的关键信息"


# ---------------------------------------------------------------------------
# 自定义异常
# ---------------------------------------------------------------------------

class VLMClientError(Exception):
    """VLM 客户端通用异常。"""


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------

class VLMClient(ABC):
    """VLM 客户端抽象基类。

    所有 VLM provider 必须实现 describe_image 方法。
    """

    @abstractmethod
    def describe_image(self, image_path: Path, prompt: str) -> str:
        """描述图片内容。

        Args:
            image_path: 图片文件路径。
            prompt: 用户 prompt。

        Returns:
            描述文本，失败时返回降级文本（不抛异常）。
        """
        ...


# ---------------------------------------------------------------------------
# Ollama VLM Client
# ---------------------------------------------------------------------------

class OllamaVLMClient(VLMClient):
    """走 python-ollama SDK 的 VLM 客户端。"""

    def __init__(self, model: str = "qwen2.5-vl:7b", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    def describe_image(self, image_path: Path, prompt: str) -> str:
        """调用 ollama.chat 描述图片。"""
        if not image_path.exists():
            return ""

        try:
            response = ollama.chat(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [str(image_path)],
                    }
                ],
            )
            return response.message.content or ""
        except Exception as e:
            return f"VLM 调用失败：{e}"


# ---------------------------------------------------------------------------
# Cloud VLM Client (OpenAI-compatible vision API)
# ---------------------------------------------------------------------------

class CloudVLMClient(VLMClient):
    """走 httpx.post 的 Cloud VLM 客户端 (OpenAI-compatible vision API)。"""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    def describe_image(self, image_path: Path, prompt: str) -> str:
        """调用 OpenAI-compatible vision API 描述图片。"""
        if not image_path.exists():
            return ""

        effective_prompt = prompt if prompt else _DEFAULT_PROMPT

        # 读图片 -> base64 data URL
        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()
        data_url = f"data:image/jpeg;base64,{img_b64}"

        try:
            resp = httpx.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": effective_prompt},
                                {"type": "image_url", "image_url": {"url": data_url}},
                            ],
                        }
                    ],
                },
                timeout=30,
            )
        except httpx.TimeoutException:
            return "VLM 超时，画面内容未提取"
        except httpx.RequestError as e:
            return f"VLM 调用失败：{e}"

        if resp.status_code != 200:
            return f"VLM 调用失败：{resp.status_code}"

        result = resp.json()
        return result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()


# ---------------------------------------------------------------------------
# 工厂函数
# ---------------------------------------------------------------------------

def get_vlm_client(config: dict) -> VLMClient | None:
    """按 config["vision"] 路由到具体 provider。

    Args:
        config: 完整配置字典，需包含 vision 配置段。

    Returns:
        VLMClient 实例，vision.enabled=false 时返回 None。

    Raises:
        VLMClientError: 未知 provider 时抛出。
    """
    vision_cfg = config.get("vision", {})
    if not vision_cfg.get("enabled", False):
        return None

    provider = vision_cfg.get("provider", "")
    if provider == "ollama":
        ollama_cfg = vision_cfg.get("ollama", {})
        return OllamaVLMClient(
            model=ollama_cfg.get("model", "qwen2.5-vl:7b"),
            base_url=ollama_cfg.get("base_url", "http://localhost:11434"),
        )
    elif provider == "cloud_api":
        cloud_cfg = vision_cfg.get("cloud_api", {})
        api_key_env = cloud_cfg.get("api_key_env", "VLM_API_KEY")
        api_key = os.environ.get(api_key_env, "")
        return CloudVLMClient(
            base_url=cloud_cfg.get("base_url", "https://token-plan-cn.xiaomimimo.com/v1"),
            api_key=api_key,
            model=cloud_cfg.get("model", "mimo-v2-omni"),
        )
    else:
        raise VLMClientError(f"未知的 VLM provider: {provider}")


# ---------------------------------------------------------------------------
# 向后兼容: 旧 describe_image() 函数
# ---------------------------------------------------------------------------

def describe_image(
    image_path: Path,
    prompt: str | None = None,
    api_key: str = "",
    base_url: str = "https://token-plan-cn.xiaomimimo.com/v1",
) -> str:
    """调用 VLM API 描述图片内容（向后兼容旧接口）。

    内部改用 CloudVLMClient 实现。
    """
    if not image_path.exists():
        return ""

    effective_prompt = prompt if prompt is not None else _DEFAULT_PROMPT
    client = CloudVLMClient(base_url=base_url, api_key=api_key, model="mimo-v2-omni")
    return client.describe_image(image_path, effective_prompt)
