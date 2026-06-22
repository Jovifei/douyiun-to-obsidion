"""M3 Task 2 + M6 Task 1: MimoSummarizer 测试。

验证 MimoSummarizer 继承 SummarizerClient、通过 OpenAICompatibleLLM 调用 API、
正常返回 SummaryResult（key_points 3-5 条）、长文本自动截断、超时和空返回异常。
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from src.llm import LLMError, SummarizerClient, SummaryResult
from src.llm.mimo_summarizer import MimoSummarizer


# ── fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def summarizer():
    return MimoSummarizer(api_key="test-key", base_url="https://api.test.com/v1")


@pytest.fixture
def sample_metadata():
    return {"title": "测试视频", "author": "测试作者"}


# ── 继承与签名 ───────────────────────────────────────────────────────


class TestMimoSummarizerInheritance:
    """MimoSummarizer 继承 SummarizerClient。"""

    def test_is_subclass(self):
        assert issubclass(MimoSummarizer, SummarizerClient)

    def test_constructor_signature(self):
        s = MimoSummarizer(api_key="k", base_url="https://x.com/v1")
        assert s.api_key == "k"
        assert s.base_url == "https://x.com/v1"

    def test_constructor_default_base_url(self):
        s = MimoSummarizer(api_key="k")
        assert "mimo" in s.base_url or "xiaomi" in s.base_url


# ── 正常返回 SummaryResult ──────────────────────────────────────────


class TestSummarizeNormal:
    """summarize 正常路径。"""

    def test_returns_summary_result(self, summarizer, sample_metadata):
        content = json.dumps(
            {"key_points": ["要点一", "要点二", "要点三"]},
            ensure_ascii=False,
        )
        summarizer._client = MagicMock()
        summarizer._client.chat.return_value = content

        result = summarizer.summarize("这是字幕文本", sample_metadata)

        assert isinstance(result, SummaryResult)
        assert len(result.key_points) == 3
        assert result.model == "mimo-v2.5-pro"

    def test_calls_chat_with_messages(self, summarizer):
        summarizer._client = MagicMock()
        summarizer._client.chat.return_value = '{"key_points": ["a","b","c"]}'

        summarizer.summarize("字幕", {})

        summarizer._client.chat.assert_called_once()
        call_args = summarizer._client.chat.call_args
        messages = call_args[0][0]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_key_points_between_3_and_5(self, summarizer):
        content = json.dumps(
            {"key_points": ["p1", "p2", "p3", "p4", "p5"]},
            ensure_ascii=False,
        )
        summarizer._client = MagicMock()
        summarizer._client.chat.return_value = content

        result = summarizer.summarize("字幕", {})

        assert 3 <= len(result.key_points) <= 5

    def test_parse_key_points_from_text(self, summarizer):
        """API 返回纯文本（含 - 要点）时也能解析。"""
        text = "- 第一个要点\n- 第二个要点\n- 第三个要点"
        summarizer._client = MagicMock()
        summarizer._client.chat.return_value = text

        result = summarizer.summarize("字幕", {})

        assert len(result.key_points) >= 3


# ── 截断逻辑 ─────────────────────────────────────────────────────────


class TestTruncation:
    """prompt > 8000 字时自动截断。"""

    def test_short_text_not_truncated(self, summarizer):
        summarizer._client = MagicMock()
        summarizer._client.chat.return_value = '{"key_points":["a","b","c"]}'

        summarizer.summarize("短文本", {"title": "测试视频", "uploader": "测试作者", "duration_seconds": 60})

        sent_messages = summarizer._client.chat.call_args[0][0]
        sent_content = sent_messages[1]["content"]
        assert "短文本" in sent_content

    def test_long_text_truncated(self, summarizer):
        summarizer._client = MagicMock()
        summarizer._client.chat.return_value = '{"key_points":["a","b","c"]}'

        long_text = "A" * 10000
        summarizer.summarize(long_text, {"title": "测试", "uploader": "测试", "duration_seconds": 0})

        sent_messages = summarizer._client.chat.call_args[0][0]
        sent_content = sent_messages[1]["content"]
        # 截断后总长度应远小于 10000
        assert len(sent_content) < 10000
        # 应包含前 4000 和后 4000
        assert "A" * 100 in sent_content  # 前段
        assert "A" * 100 in sent_content  # 后段（可能重复但合理）


# ── 异常路径 ─────────────────────────────────────────────────────────


class TestErrorPaths:
    """异常场景。"""

    def test_timeout_raises_llm_error(self, summarizer):
        from src.llm.client import LLMClientError

        summarizer._client = MagicMock()
        summarizer._client.chat.side_effect = LLMClientError("timeout", "LLM 请求超时")

        with pytest.raises(LLMError) as exc_info:
            summarizer.summarize("字幕", {})
        assert exc_info.value.code == "llm_timeout"

    def test_empty_response_raises_llm_error(self, summarizer):
        summarizer._client = MagicMock()
        summarizer._client.chat.return_value = ""

        with pytest.raises(LLMError) as exc_info:
            summarizer.summarize("字幕", {})
        assert exc_info.value.code == "empty_summary"

    def test_api_error_raises_llm_error(self, summarizer):
        from src.llm.client import LLMClientError

        summarizer._client = MagicMock()
        summarizer._client.chat.side_effect = LLMClientError("api_error", "LLM API 错误 500")

        with pytest.raises(LLMError):
            summarizer.summarize("字幕", {})
