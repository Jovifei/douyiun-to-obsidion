"""ASR 统一接口 — M2 Task 1。

定义 ASRResult、ASRClient ABC 及 get_asr_client 工厂函数，
为后续 MimoASRClient / WhisperLocalClient 实现提供契约。
"""
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


# ── ASRError ──────────────────────────────────────────────


class ASRError(Exception):
    """ASR 转写错误。"""

    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message or code
        super().__init__(self.message)


# ── ASRResult ──────────────────────────────────────────────


@dataclass
class ASRResult:
    """ASR 转录结果。"""

    text: str
    segments: list[dict[str, Any]] = field(default_factory=list)
    source: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ASRResult:
        """从 dict 还原。"""
        return cls(**data)


# ── ASRClient ABC ──────────────────────────────────────────


class ASRClient(ABC):
    """ASR 客户端抽象基类。"""

    @abstractmethod
    def transcribe(self, audio_path: Path) -> ASRResult:
        """转录音频文件并返回 ASRResult。"""
        ...


# ── 占位实现（Task 2 / Task 4 实现） ───────────────────────


class MimoASRClient(ASRClient):
    """MiMo ASR 客户端 — Task 2 实现。"""

    def transcribe(self, audio_path: Path) -> ASRResult:
        raise NotImplementedError("MimoASRClient.transcribe 将在 Task 2 实现")


from src.asr.local_whisper import WhisperLocalClient  # noqa: F401


# ── 工厂函数 ───────────────────────────────────────────────

_PROVIDER_MAP: dict[str, type[ASRClient]] = {
    "mimo": MimoASRClient,
    "whisper_local": WhisperLocalClient,
}


def get_asr_client(config: dict[str, Any]) -> ASRClient:
    """根据配置返回对应的 ASRClient 实例。

    Args:
        config: 项目配置字典，需含 asr.provider 字段。

    Returns:
        对应 provider 的 ASRClient 实例。

    Raises:
        ValueError: 未知的 provider。
    """
    provider = config.get("asr", {}).get("provider", "")
    cls = _PROVIDER_MAP.get(provider)
    if cls is None:
        raise ValueError(f"unknown ASR provider: {provider!r}")
    return cls()
