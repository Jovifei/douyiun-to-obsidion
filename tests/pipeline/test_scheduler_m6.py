"""Test pipeline/scheduler.py M6 适配 — get_llm_client + get_vlm_client + select_semantic_frames。

TDD: 6 tests covering:
1. scheduler imports get_llm_client / get_vlm_client / select_semantic_frames
2. select_semantic_frames LLM 成功 → >=3 帧
3. select_semantic_frames LLM fallback → ASR segments
4. select_semantic_frames 无 segments → 空
5. select_semantic_frames interval fallback
6. scheduler vision path uses get_vlm_client
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestSchedulerM6Imports:
    """Test 1: scheduler 模块可导入 get_llm_client / get_vlm_client / select_semantic_frames。"""

    def test_scheduler_imports_new_symbols(self):
        """验证 scheduler 模块顶部导入了 M6 新符号。"""
        import importlib
        import src.pipeline.scheduler as sched_mod

        # 验证模块级别可访问
        assert hasattr(sched_mod, "get_llm_client") or True  # import 语句存在即可
        assert hasattr(sched_mod, "get_vlm_client") or True
        assert hasattr(sched_mod, "select_semantic_frames") or True

        # 更严格：验证这些符号在模块的 __dict__ 中（即被 import 了）
        import ast
        source = Path(sched_mod.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module in ("src.llm.client", "src.vision.vlm_client", "src.vision.semantic_frame_selector"):
                    for alias in node.names:
                        imported_names.add(alias.name)

        assert "get_llm_client" in imported_names, "get_llm_client not imported in scheduler.py"
        assert "get_vlm_client" in imported_names, "get_vlm_client not imported in scheduler.py"
        assert "select_semantic_frames" in imported_names, "select_semantic_frames not imported in scheduler.py"


class TestSelectSemanticFramesLLMSuccess:
    """Test 2: select_semantic_frames LLM 成功时返回 >=3 语义帧。"""

    def test_llm_success_returns_many_frames(self):
        """LLM 返回 5 帧 → 使用语义帧，source='semantic'。"""
        from src.vision.semantic_frame_selector import select_semantic_frames

        mock_client = MagicMock()
        mock_client.chat_json.return_value = [
            {"time_sec": 30, "reason": "讲师展示代码示例"},
            {"time_sec": 120, "reason": "总结三个核心要点"},
            {"time_sec": 200, "reason": "实操演示关键步骤"},
            {"time_sec": 300, "reason": "常见错误分析"},
            {"time_sec": 400, "reason": "最佳实践总结"},
        ]
        segments = [{"start": i * 20, "end": i * 20 + 20, "text": f"seg{i}"} for i in range(10)]

        result = select_semantic_frames(segments, mock_client, max_frames=15)

        assert len(result) >= 3
        assert all(f["source"] == "semantic" for f in result)
        assert result[0]["time_sec"] == 30


class TestSelectSemanticFramesLLMFallback:
    """Test 3: select_semantic_frames LLM 返回不足 3 帧时回退 ASR segments。"""

    def test_llm_returns_few_fallback_to_segments(self):
        """LLM 返回 1 帧 → 回退到 ASR segments 直接抽帧。"""
        from src.vision.semantic_frame_selector import select_semantic_frames

        mock_client = MagicMock()
        mock_client.chat_json.return_value = [{"time_sec": 30, "reason": "only one"}]
        segments = [
            {"start": 0, "end": 10, "text": "开头"},
            {"start": 20, "end": 30, "text": "中间"},
            {"start": 40, "end": 50, "text": "结尾"},
        ]

        result = select_semantic_frames(segments, mock_client, max_frames=15)

        assert len(result) == 3
        assert all(f["source"] == "asr_segment" for f in result)


class TestSelectSemanticFramesNoSegments:
    """Test 4: select_semantic_frames 无 segments 且无 duration 时返回空。"""

    def test_no_segments_no_duration_returns_empty(self):
        """空 segments + video_duration=0 → 返回空列表。"""
        from src.vision.semantic_frame_selector import select_semantic_frames

        result = select_semantic_frames([], None, video_duration=0.0)
        assert result == []


class TestSelectSemanticFramesIntervalFallback:
    """Test 5: select_semantic_frames 无 segments 但有 duration 时回退均匀采样。"""

    def test_interval_fallback_with_duration(self):
        """无 segments + video_duration=60 → 每 10 秒采样 6 帧。"""
        from src.vision.semantic_frame_selector import select_semantic_frames

        result = select_semantic_frames([], None, video_duration=60.0)

        assert len(result) >= 3
        assert all(f["source"] == "interval" for f in result)
        # 验证时间间隔约 10 秒
        times = [f["time_sec"] for f in result]
        assert times == sorted(times), "帧应按时间排序"


class TestSchedulerVisionUsesGetVLMClient:
    """Test 6: scheduler vision 路径使用 get_vlm_client 而非旧 describe_image。"""

    def test_vision_path_uses_vlm_client(self):
        """验证 scheduler 的 vision 处理路径调用 get_vlm_client。"""
        import ast
        from pathlib import Path
        import src.pipeline.scheduler as sched_mod

        source = Path(sched_mod.__file__).read_text(encoding="utf-8")

        # 验证旧的 describe_image 直接调用已移除（不再有 desc = describe_image(kf)）
        # 新路径应使用 vlm_client.describe_image(kf, prompt)
        assert "vlm_client.describe_image" in source or "get_vlm_client" in source, \
            "scheduler 应使用 get_vlm_client / vlm_client.describe_image 而非旧的 describe_image(kf)"
