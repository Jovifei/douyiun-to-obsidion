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


# ── 实际实现导入 ─────────────────────────────────────────────


def _get_mimo_client_class():
    from src.asr.mimo_client import MimoASRClient
    return MimoASRClient


def _get_whisper_client_class():
    from src.asr.local_whisper import WhisperLocalClient
    return WhisperLocalClient


# ── 工厂函数 ───────────────────────────────────────────────


def get_asr_client(config: dict[str, Any]) -> ASRClient:
    """根据配置返回对应的 ASRClient 实例。

    Args:
        config: 项目配置字典，需含 asr.provider 字段。
            - provider="mimo" 时读取 mimo.api_key / mimo.base_url
            - provider="whisper_local" 时读取 whisper.model / whisper.device

    Returns:
        对应 provider 的 ASRClient 实例。

    Raises:
        ValueError: 未知的 provider。
    """
    asr_config = config.get("asr", {})
    provider = asr_config.get("provider", "")

    if provider == "mimo":
        cls = _get_mimo_client_class()
        mimo_cfg = asr_config.get("mimo", {})
        api_key = mimo_cfg.get("api_key", "")
        base_url = mimo_cfg.get("base_url", "https://token-plan-cn.xiaomimimo.com/v1")
        return cls(api_key=api_key, base_url=base_url)
    elif provider == "whisper_local":
        cls = _get_whisper_client_class()
        whisper_cfg = asr_config.get("whisper", {})
        return cls(
            model_name=whisper_cfg.get("model", "Belle-whisper-large-v3-turbo-zh"),
            device=whisper_cfg.get("device", "cuda"),
            compute_type=whisper_cfg.get("compute_type", "int8_float16"),
        )
    else:
        raise ValueError(f"unknown ASR provider: {provider!r}")
