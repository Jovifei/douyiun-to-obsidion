"""语义选帧单元测试 — M6 Task 3。

验证 select_semantic_frames 的三级回退链：
1. LLM 返回 >=3 帧 → 语义帧
2. LLM 返回 <3 帧 / 异常 → ASR segments 直接抽帧
3. 无 segments → 均匀采样

TDD: 6 tests covering:
1. test_returns_llm_frames_when_enough
2. test_fallback_to_segments_when_llm_returns_few
3. test_fallback_to_interval_when_no_segments
4. test_fallback_on_llm_error
5. test_no_segments_no_duration_returns_empty
6. test_max_frames_respected
"""
from unittest.mock import MagicMock

import pytest

from src.vision.semantic_frame_selector import select_semantic_frames


class TestSelectSemanticFrames:
    """select_semantic_frames 核心行为测试。"""

    def test_returns_llm_frames_when_enough(self):
        """LLM 返回 >=3 帧时使用语义帧。"""
        mock_client = MagicMock()
        mock_client.chat_json.return_value = [
            {"time_sec": 30, "reason": "讲师展示代码"},
            {"time_sec": 120, "reason": "总结要点"},
            {"time_sec": 200, "reason": "实操演示"},
        ]
        segments = [{"start": i * 20, "end": i * 20 + 20, "text": f"seg{i}"} for i in range(10)]
        result = select_semantic_frames(segments, mock_client)
        assert len(result) == 3
        assert result[0]["time_sec"] == 30
        assert result[0]["source"] == "semantic"

    def test_fallback_to_segments_when_llm_returns_few(self):
        """LLM 返回 <3 帧时回退到 ASR segments。"""
        mock_client = MagicMock()
        mock_client.chat_json.return_value = [{"time_sec": 30, "reason": "one frame only"}]
        segments = [{"start": 0, "end": 10, "text": "a"}, {"start": 20, "end": 30, "text": "b"}]
        result = select_semantic_frames(segments, mock_client, max_frames=15)
        assert len(result) == 2
        assert result[0]["source"] == "asr_segment"

    def test_fallback_to_interval_when_no_segments(self):
        """无 segments 时回退到均匀采样。"""
        mock_client = MagicMock()
        mock_client.chat_json.return_value = [{"time_sec": 10, "reason": "x"}]
        result = select_semantic_frames([], mock_client, video_duration=60)
        assert len(result) >= 3
        assert result[0]["source"] == "interval"

    def test_fallback_on_llm_error(self):
        """LLM 异常时回退到 ASR segments。"""
        mock_client = MagicMock()
        mock_client.chat_json.side_effect = Exception("API error")
        segments = [{"start": 5, "end": 15, "text": "x"}, {"start": 25, "end": 35, "text": "y"}]
        result = select_semantic_frames(segments, mock_client)
        assert len(result) == 2

    def test_no_segments_no_duration_returns_empty(self):
        """无 segments 且无 duration 时返回空列表。"""
        result = select_semantic_frames([], None)
        assert result == []

    def test_max_frames_respected(self):
        """max_frames 限制生效。"""
        mock_client = MagicMock()
        mock_client.chat_json.return_value = [{"time_sec": i * 10, "reason": f"f{i}"} for i in range(20)]
        segments = [{"start": i * 10, "end": i * 10 + 10, "text": f"seg{i}"} for i in range(20)]
        result = select_semantic_frames(segments, mock_client, max_frames=5)
        assert len(result) == 5
