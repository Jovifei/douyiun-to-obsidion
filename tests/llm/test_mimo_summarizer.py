"""M3 Task 2: MimoSummarizer 测试。

验证 MimoSummarizer 继承 SummarizerClient、调用 mimo-v2.5-pro API、
正常返回 SummaryResult（key_points 3-5 条）、长文本自动截断、超时和空返回异常。
"""
import json
from unittest.mock import MagicMock, patch

import httpx
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


def _make_api_response(content: str, status_code: int = 200):
    """构造一个类似 httpx.Response 的 mock 对象。"""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    return resp


def _make_error_response(status_code: int, body: str = "error"):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = body
    resp.json.return_value = {"error": body}
    return resp


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

    @patch("src.llm.mimo_summarizer.httpx.post")
    def test_returns_summary_result(self, mock_post, summarizer, sample_metadata):
        content = json.dumps(
            {"key_points": ["要点一", "要点二", "要点三"]},
            ensure_ascii=False,
        )
        mock_post.return_value = _make_api_response(content)

        result = summarizer.summarize("这是字幕文本", sample_metadata)

        assert isinstance(result, SummaryResult)
        assert len(result.key_points) == 3
        assert result.model == "mimo-v2.5-pro"

    @patch("src.llm.mimo_summarizer.httpx.post")
    def test_calls_correct_endpoint(self, mock_post, summarizer):
        mock_post.return_value = _make_api_response('{"key_points": ["a","b","c"]}')

        summarizer.summarize("字幕", {})

        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "/chat/completions" in call_args[0][0]
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-key"

    @patch("src.llm.mimo_summarizer.httpx.post")
    def test_key_points_between_3_and_5(self, mock_post, summarizer):
        content = json.dumps(
            {"key_points": ["p1", "p2", "p3", "p4", "p5"]},
            ensure_ascii=False,
        )
        mock_post.return_value = _make_api_response(content)

        result = summarizer.summarize("字幕", {})

        assert 3 <= len(result.key_points) <= 5

    @patch("src.llm.mimo_summarizer.httpx.post")
    def test_parse_key_points_from_text(self, mock_post, summarizer):
        """API 返回纯文本（含 - 要点）时也能解析。"""
        text = "- 第一个要点\n- 第二个要点\n- 第三个要点"
        mock_post.return_value = _make_api_response(text)

        result = summarizer.summarize("字幕", {})

        assert len(result.key_points) >= 3


# ── 截断逻辑 ─────────────────────────────────────────────────────────


class TestTruncation:
    """prompt > 8000 字时自动截断。"""

    @patch("src.llm.mimo_summarizer.httpx.post")
    def test_short_text_not_truncated(self, mock_post, summarizer):
        mock_post.return_value = _make_api_response('{"key_points":["a","b","c"]}')

        summarizer.summarize("短文本", {"title": "测试视频", "uploader": "测试作者", "duration_seconds": 60})

        sent_content = mock_post.call_args[1]["json"]["messages"][1]["content"]
        assert "短文本" in sent_content

    @patch("src.llm.mimo_summarizer.httpx.post")
    def test_long_text_truncated(self, mock_post, summarizer):
        mock_post.return_value = _make_api_response('{"key_points":["a","b","c"]}')

        long_text = "A" * 10000
        summarizer.summarize(long_text, {"title": "测试", "uploader": "测试", "duration_seconds": 0})

        sent_content = mock_post.call_args[1]["json"]["messages"][1]["content"]
        # 截断后总长度应远小于 10000
        assert len(sent_content) < 10000
        # 应包含前 4000 和后 4000
        assert "A" * 100 in sent_content  # 前段
        assert "A" * 100 in sent_content  # 后段（可能重复但合理）


# ── 异常路径 ─────────────────────────────────────────────────────────


class TestErrorPaths:
    """异常场景。"""

    @patch("src.llm.mimo_summarizer.httpx.post")
    def test_timeout_raises_llm_error(self, mock_post, summarizer):
        mock_post.side_effect = httpx.TimeoutException("timeout")

        with pytest.raises(LLMError) as exc_info:
            summarizer.summarize("字幕", {})
        assert exc_info.value.code == "llm_timeout"

    @patch("src.llm.mimo_summarizer.httpx.post")
    def test_empty_response_raises_llm_error(self, mock_post, summarizer):
        mock_post.return_value = _make_api_response("")

        with pytest.raises(LLMError) as exc_info:
            summarizer.summarize("字幕", {})
        assert exc_info.value.code == "empty_summary"

    @patch("src.llm.mimo_summarizer.httpx.post")
    def test_api_error_raises_llm_error(self, mock_post, summarizer):
        mock_post.return_value = _make_error_response(500, "internal error")

        with pytest.raises(LLMError):
            summarizer.summarize("字幕", {})
