"""LLM Client 统一抽象层 — M6 Task 1。

定义 LLMClient ABC、OpenAICompatibleLLM、OllamaLocalLLM 及 get_llm_client 工厂，
为后续语义选帧、本地+云端切换提供统一 LLM 调用接口。
"""
import json
import os
from abc import ABC, abstractmethod

import httpx
import ollama

# ── LLMClientError ──────────────────────────────────────────


class LLMClientError(Exception):
    """LLM 调用错误。"""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message or code
        super().__init__(self.message)


# ── LLMClient ABC ──────────────────────────────────────────


class LLMClient(ABC):
    """LLM 客户端抽象基类。"""

    @abstractmethod
    def chat(self, messages: list[dict], model: str | None = None) -> str:
        """发送聊天消息并返回文本响应。"""
        ...

    def chat_json(self, messages: list[dict], model: str | None = None) -> dict:
        """发送聊天消息并解析 JSON 响应。

        默认实现：调用 chat() 后解析返回的 JSON 字符串。
        支持 ```json``` 包裹的响应格式。
        """
        content = self.chat(messages, model=model)
        return _parse_json_response(content)


# ── JSON 解析辅助 ───────────────────────────────────────────


def _parse_json_response(content: str) -> dict:
    """从 LLM 响应文本中解析 JSON 对象。

    支持格式：
    1. 纯 JSON: {"key_points": [...]}
    2. Markdown 代码块: ```json\n{...}\n```
    3. 普通代码块: ```\n{...}\n```
    """
    text = content.strip()

    # 处理 ```json ... ``` 包裹
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()

    # 找到第一个 { 和最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    raise LLMClientError(
        "json_parse_error",
        f"无法从 LLM 响应中解析 JSON: {content[:200]}",
    )


# ── OpenAICompatibleLLM ────────────────────────────────────


class OpenAICompatibleLLM(LLMClient):
    """OpenAI-compatible API 客户端。

    覆盖 mimo / DeepSeek / 智谱 / 本地 Ollama 等任何 OpenAI-compatible 端点。
    """

    def __init__(self, base_url: str, api_key: str, default_model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )

    def chat(self, messages: list[dict], model: str | None = None) -> str:
        """发送聊天消息并返回文本响应。"""
        try:
            resp = self._client.post(
                "/chat/completions",
                json={
                    "model": model or self.default_model,
                    "messages": messages,
                },
            )
        except httpx.TimeoutException:
            raise LLMClientError("timeout", "LLM 请求超时")
        except httpx.RequestError as e:
            raise LLMClientError("network_error", f"LLM 网络错误: {e}")

        if resp.status_code != 200:
            raise LLMClientError(
                "api_error",
                f"LLM API 错误 {resp.status_code}: {resp.text[:200]}",
            )

        content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        return content


# ── OllamaLocalLLM ─────────────────────────────────────────


class OllamaLocalLLM(LLMClient):
    """本地 Ollama 客户端（零 API 成本）。

    直接走 python-ollama SDK。
    """

    def __init__(self, model: str = "qwen2.5:7b", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        self._client = ollama.Client(host=base_url)

    def chat(self, messages: list[dict], model: str | None = None) -> str:
        """发送聊天消息并返回文本响应。"""
        response = self._client.chat(
            model=model or self.model,
            messages=messages,
        )
        return response.message.content


# ── 工厂函数 ───────────────────────────────────────────────


def get_llm_client(config: dict) -> LLMClient:
    """根据 config["llm"]["provider"] 返回对应 LLMClient 实例。

    Args:
        config: 项目配置字典，需含 llm.provider 字段。
            - provider="openai_compatible" 时读取 llm.openai_compatible 配置
            - provider="ollama_local" 时读取 llm.ollama_local 配置

    Returns:
        对应 provider 的 LLMClient 实例。

    Raises:
        ValueError: 未知的 provider。
    """
    llm_config = config.get("llm", {})
    provider = llm_config.get("provider", "")

    if provider == "openai_compatible":
        cfg = llm_config.get("openai_compatible", {})
        api_key_env = cfg.get("api_key_env", "")
        api_key = os.environ.get(api_key_env, "") if api_key_env else ""
        return OpenAICompatibleLLM(
            base_url=cfg.get("base_url", ""),
            api_key=api_key,
            default_model=cfg.get("model", ""),
        )
    elif provider == "ollama_local":
        cfg = llm_config.get("ollama_local", {})
        return OllamaLocalLLM(
            model=cfg.get("model", "qwen2.5:7b"),
            base_url=cfg.get("base_url", "http://localhost:11434"),
        )
    else:
        raise ValueError(f"unknown LLM provider: {provider!r}")
