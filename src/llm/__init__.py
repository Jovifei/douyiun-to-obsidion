"""LLM 总结统一接口 — M3 Task 1。

定义 SummaryResult、SummarizerClient ABC 及 get_summarizer 工厂函数，
为后续 MimoSummarizer / LocalSummarizer 实现提供契约。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ── LLMError ──────────────────────────────────────────────


class LLMError(Exception):
    """LLM 总结错误。"""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message or code
        super().__init__(self.message)


# ── SummaryResult ──────────────────────────────────────────


@dataclass
class SummaryResult:
    """LLM 总结结果。"""

    summary_text: str
    key_points: list[str] = field(default_factory=list)
    model: str = ""
    source: str = ""
    confidence: float = 0.0


# ── SummarizerClient ABC ──────────────────────────────────


class SummarizerClient(ABC):
    """LLM 总结客户端抽象基类。"""

    @abstractmethod
    def summarize(self, subtitle_text: str, metadata: dict) -> SummaryResult:
        """总结字幕文本并返回 SummaryResult。"""
        ...


# ── 实际实现导入 ─────────────────────────────────────────────


from src.llm.mimo_summarizer import MimoSummarizer  # noqa: E402


class LocalSummarizer(SummarizerClient):
    """本地 LLM 总结客户端占位。"""

    def summarize(self, subtitle_text: str, metadata: dict) -> SummaryResult:
        raise NotImplementedError("Task 2")


# ── 工厂函数 ───────────────────────────────────────────────


def get_summarizer(config: dict[str, Any]) -> SummarizerClient:
    """根据配置返回对应的 SummarizerClient 实例。

    Args:
        config: 项目配置字典，需含 llm.provider 字段。
            - provider="mimo" 时返回 MimoSummarizer
            - provider="local" 时返回 LocalSummarizer

    Returns:
        对应 provider 的 SummarizerClient 实例。

    Raises:
        ValueError: 未知的 provider。
    """
    llm_config = config.get("llm", {})
    provider = llm_config.get("provider", "")

    if provider == "mimo":
        return MimoSummarizer()
    elif provider == "local":
        return LocalSummarizer()
    else:
        raise ValueError(f"unknown LLM provider: {provider!r}")
