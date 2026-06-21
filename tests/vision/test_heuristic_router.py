"""Test heuristic router — M3 Task 6.

Spec ref: D-M3-3 启发式分流
字幕密度 + 场景变化率 → 3 档分流（summary_only / summary_with_vlm / ocr_only）
"""
import inspect

import pytest

from src.vision.heuristic_router import RoutingDecision, classify_video


# ---------------------------------------------------------------------------
# 1. RoutingDecision 枚举值正确
# ---------------------------------------------------------------------------

def test_routing_decision_enum_values():
    """RoutingDecision 包含 3 个枚举值。"""
    assert RoutingDecision.SUMMARY_ONLY.value == "summary_only"
    assert RoutingDecision.SUMMARY_WITH_VLM.value == "summary_with_vlm"
    assert RoutingDecision.OCR_ONLY.value == "ocr_only"


def test_routing_decision_has_three_members():
    """RoutingDecision 恰好 3 个成员。"""
    members = list(RoutingDecision)
    assert len(members) == 3


# ---------------------------------------------------------------------------
# 2. classify_video 函数签名
# ---------------------------------------------------------------------------

def test_classify_video_signature():
    """函数存在且参数签名匹配 spec。"""
    sig = inspect.signature(classify_video)
    params = list(sig.parameters.keys())
    assert "subtitle_text" in params
    assert "video_duration" in params
    assert "keyframe_count" in params


# ---------------------------------------------------------------------------
# 3. 字幕密度 > 0.5 且 场景变化率 < 0.3 → summary_only
# ---------------------------------------------------------------------------

def test_high_subtitle_low_scene_change_returns_summary_only():
    """字幕密度 > 0.5字/秒 且 场景变化率 < 0.3 → summary_only。"""
    # subtitle_text=100字, duration=60s → density=1.67 > 0.5
    # keyframe_count=5, duration=60s → rate = 5/(60/10) = 0.83
    # 调整: keyframe_count=1, duration=60s → rate = 1/(60/10) = 0.17 < 0.3
    result = classify_video(
        subtitle_text="字" * 100,
        video_duration=60.0,
        keyframe_count=1,
    )
    assert result == RoutingDecision.SUMMARY_ONLY


# ---------------------------------------------------------------------------
# 4. 字幕密度 < 0.3 且 场景变化率 > 0.5 → summary_with_vlm
# ---------------------------------------------------------------------------

def test_low_subtitle_high_scene_change_returns_summary_with_vlm():
    """字幕密度 < 0.3字/秒 且 场景变化率 > 0.5 → summary_with_vlm。"""
    # subtitle_text=10字, duration=60s → density=0.17 < 0.3
    # keyframe_count=10, duration=60s → rate = 10/(60/10) = 1.67 > 0.5
    result = classify_video(
        subtitle_text="字" * 10,
        video_duration=60.0,
        keyframe_count=10,
    )
    assert result == RoutingDecision.SUMMARY_WITH_VLM


# ---------------------------------------------------------------------------
# 5. 混合类（边界条件）→ summary_with_vlm（保守策略）
# ---------------------------------------------------------------------------

def test_mixed_returns_summary_with_vlm_conservative():
    """混合类（字幕密度和场景变化率都不在极端区间）→ summary_with_vlm。"""
    # subtitle_text=20字, duration=60s → density=0.33 (0.3~0.5之间)
    # keyframe_count=3, duration=60s → rate = 3/(60/10) = 0.5 (边界)
    result = classify_video(
        subtitle_text="字" * 20,
        video_duration=60.0,
        keyframe_count=3,
    )
    assert result == RoutingDecision.SUMMARY_WITH_VLM


# ---------------------------------------------------------------------------
# 6. 字幕为空 且 有关键帧 → ocr_only
# ---------------------------------------------------------------------------

def test_empty_subtitle_with_keyframes_returns_ocr_only():
    """字幕为空 且 有关键帧 → ocr_only。"""
    result = classify_video(
        subtitle_text="",
        video_duration=60.0,
        keyframe_count=5,
    )
    assert result == RoutingDecision.OCR_ONLY


def test_empty_subtitle_whitespace_only_with_keyframes_returns_ocr_only():
    """字幕纯空白 且 有关键帧 → ocr_only。"""
    result = classify_video(
        subtitle_text="   \n\t  ",
        video_duration=60.0,
        keyframe_count=3,
    )
    assert result == RoutingDecision.OCR_ONLY


# ---------------------------------------------------------------------------
# 7. 关键帧为 0 → summary_only（无视觉素材）
# ---------------------------------------------------------------------------

def test_zero_keyframes_returns_summary_only():
    """关键帧为 0 → summary_only（无视觉素材）。"""
    result = classify_video(
        subtitle_text="字" * 100,
        video_duration=60.0,
        keyframe_count=0,
    )
    assert result == RoutingDecision.SUMMARY_ONLY


def test_zero_keyframes_sparse_subtitle_returns_summary_only():
    """关键帧为 0 即使字幕稀少也 → summary_only。"""
    result = classify_video(
        subtitle_text="字" * 5,
        video_duration=60.0,
        keyframe_count=0,
    )
    assert result == RoutingDecision.SUMMARY_ONLY


# ---------------------------------------------------------------------------
# 8. 边界值: 密度恰好等于阈值
# ---------------------------------------------------------------------------

def test_subtitle_density_exactly_05_keyframe_low():
    """字幕密度恰好 0.5 字/秒 + 场景变化率低 → summary_only。"""
    # subtitle_text=30字, duration=60s → density=0.5 (等于 0.5)
    # keyframe_count=1, duration=60s → rate=0.17 < 0.3
    result = classify_video(
        subtitle_text="字" * 30,
        video_duration=60.0,
        keyframe_count=1,
    )
    assert result == RoutingDecision.SUMMARY_ONLY


def test_scene_rate_exactly_05_subtitle_low():
    """场景变化率恰好 0.5 + 字幕密度低 → summary_with_vlm。"""
    # subtitle_text=10字, duration=60s → density=0.17 < 0.3
    # keyframe_count=3, duration=60s → rate=3/(60/10)=0.5 (等于 0.5)
    result = classify_video(
        subtitle_text="字" * 10,
        video_duration=60.0,
        keyframe_count=3,
    )
    assert result == RoutingDecision.SUMMARY_WITH_VLM
