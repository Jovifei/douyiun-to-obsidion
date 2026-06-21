"""LLM 总结接口测试 — M3 Task 1。

验证 SummaryResult、SummarizerClient ABC、get_summarizer 工厂函数。
"""
import pytest

from src.llm import (
    LLMError,
    LocalSummarizer,
    MimoSummarizer,
    SummarizerClient,
    SummaryResult,
    get_summarizer,
)


# ── SummaryResult ──────────────────────────────────────────


class TestSummaryResult:
    """SummaryResult dataclass 基础契约。"""

    def test_five_fields_instantiation(self):
        """五个字段可实例化。"""
        result = SummaryResult(
            summary_text="这是一条总结",
            key_points=["要点一", "要点二"],
            model="mimo-v2.5",
            source="mimo",
            confidence=0.92,
        )
        assert result.summary_text == "这是一条总结"
        assert result.key_points == ["要点一", "要点二"]
        assert result.model == "mimo-v2.5"
        assert result.source == "mimo"
        assert result.confidence == 0.92

    def test_default_values(self):
        """默认值合理。"""
        result = SummaryResult(summary_text="摘要")
        assert result.key_points == []
        assert result.model == ""
        assert result.source == ""
        assert result.confidence == 0.0


# ── SummarizerClient ABC ──────────────────────────────────


class TestSummarizerClientABC:
    """SummarizerClient 抽象基类契约。"""

    def test_summarize_method_exists(self):
        """summarize 方法签名正确。"""
        import inspect

        sig = inspect.signature(SummarizerClient.summarize)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "subtitle_text" in params
        assert "metadata" in params
        assert sig.return_annotation == SummaryResult

    def test_cannot_instantiate_directly(self):
        """不能直接实例化 SummarizerClient。"""
        with pytest.raises(TypeError):
            SummarizerClient()  # type: ignore[abstract]


# ── get_summarizer 工厂 ────────────────────────────────────


class TestGetSummarizer:
    """工厂函数 get_summarizer 路由。"""

    def test_mimo_provider(self):
        """provider=mimo 返回 MimoSummarizer。"""
        client = get_summarizer({"llm": {"provider": "mimo"}})
        assert isinstance(client, MimoSummarizer)

    def test_local_provider(self):
        """provider=local 返回 LocalSummarizer。"""
        client = get_summarizer({"llm": {"provider": "local"}})
        assert isinstance(client, LocalSummarizer)

    def test_unknown_provider_raises(self):
        """未知 provider 抛出 ValueError。"""
        with pytest.raises(ValueError, match="unknown.*provider"):
            get_summarizer({"llm": {"provider": "nonexistent"}})


# ── LLMError ──────────────────────────────────────────────


class TestLLMError:
    """LLMError 异常类契约。"""

    def test_error_code_and_message(self):
        """code 和 message 字段正确。"""
        err = LLMError(code="llm_timeout", message="请求超时")
        assert err.code == "llm_timeout"
        assert err.message == "请求超时"
        assert str(err) == "请求超时"

    def test_default_message_from_code(self):
        """未提供 message 时使用 code。"""
        err = LLMError(code="llm_network_error")
        assert err.message == "llm_network_error"
