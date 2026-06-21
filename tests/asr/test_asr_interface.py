"""ASR 统一接口测试 — M2 Task 1。

验证 ASRResult、ASRClient ABC、get_asr_client 工厂函数。
"""
from pathlib import Path

import pytest

from src.asr import ASRClient, ASRResult, get_asr_client


# ── ASRResult ──────────────────────────────────────────────


class TestASRResult:
    """ASRResult dataclass 基础契约。"""

    def test_four_fields_instantiation(self):
        """四个字段可实例化。"""
        result = ASRResult(
            text="你好世界",
            segments=[],
            source="mimo",
            confidence=0.95,
        )
        assert result.text == "你好世界"
        assert result.segments == []
        assert result.source == "mimo"
        assert result.confidence == 0.95

    def test_serialization_roundtrip(self):
        """可序列化为 dict 并还原。"""
        result = ASRResult(
            text="测试文本",
            segments=[{"start": 0.0, "end": 1.5, "text": "测试文本"}],
            source="whisper_local",
            confidence=0.88,
        )
        d = result.to_dict()
        assert d["text"] == "测试文本"
        assert d["source"] == "whisper_local"
        assert d["confidence"] == 0.88
        assert isinstance(d["segments"], list)

        restored = ASRResult.from_dict(d)
        assert restored == result


# ── ASRClient ABC ──────────────────────────────────────────


class TestASRClientABC:
    """ASRClient 抽象基类契约。"""

    def test_transcribe_method_exists(self):
        """transcribe 方法签名正确。"""
        import inspect

        sig = inspect.signature(ASRClient.transcribe)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "audio_path" in params
        assert sig.return_annotation == ASRResult

    def test_cannot_instantiate_directly(self):
        """不能直接实例化 ASRClient。"""
        with pytest.raises(TypeError):
            ASRClient()  # type: ignore[abstract]


# ── get_asr_client 工厂 ────────────────────────────────────


class TestGetASRClient:
    """工厂函数 get_asr_client 路由。"""

    def test_mimo_provider(self):
        """provider=mimo 返回 MimoASRClient。"""
        from src.asr.mimo_client import MimoASRClient

        client = get_asr_client({"asr": {"provider": "mimo", "mimo": {"api_key": "test"}}})
        assert isinstance(client, MimoASRClient)

    def test_whisper_local_provider(self):
        """provider=whisper_local 返回 WhisperLocalClient。"""
        from src.asr.local_whisper import WhisperLocalClient

        client = get_asr_client({"asr": {"provider": "whisper_local", "whisper": {}}})
        assert isinstance(client, WhisperLocalClient)

    def test_unknown_provider_raises(self):
        """未知 provider 抛出 ValueError。"""
        with pytest.raises(ValueError, match="unknown.*provider"):
            get_asr_client({"asr": {"provider": "nonexistent"}})
