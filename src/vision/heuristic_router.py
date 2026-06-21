"""启发式分流 — M3 Task 6。

根据字幕密度和场景变化率判断视频类型，决定处理路径。
Spec ref: D-M3-3 启发式分流
"""
from enum import Enum


class RoutingDecision(str, Enum):
    """分流决策枚举。"""

    SUMMARY_ONLY = "summary_only"          # 口播类，只跑 LLM 总结
    SUMMARY_WITH_VLM = "summary_with_vlm"  # PPT/图表类，总结+OCR+VLM
    OCR_ONLY = "ocr_only"                  # 纯画面无语音类（极端边缘）


# 启发式阈值（D-M3-3）
_SUBTITLE_DENSITY_HIGH = 0.5   # 字/秒，高于此值视为口播密集
_SUBTITLE_DENSITY_LOW = 0.3    # 字/秒，低于此值视为字幕稀疏
_SCENE_RATE_LOW = 0.3          # 场景变化率，低于此值视为画面稳定
_SCENE_RATE_HIGH = 0.5         # 场景变化率，高于此值视为画面变化频繁


def classify_video(
    subtitle_text: str,
    video_duration: float,
    keyframe_count: int,
) -> RoutingDecision:
    """根据字幕密度和场景变化率判断视频类型。

    字幕密度 = len(subtitle_text) / video_duration
    场景变化率 = keyframe_count / (video_duration / 10)

    Args:
        subtitle_text: 字幕文本
        video_duration: 视频时长（秒）
        keyframe_count: 关键帧数量

    Returns:
        RoutingDecision 分流决策
    """
    # 边界: 关键帧为 0 → 无视觉素材，只做总结
    if keyframe_count == 0:
        return RoutingDecision.SUMMARY_ONLY

    # 边界: 字幕为空且有关键帧 → 纯画面，OCR only
    if not subtitle_text or not subtitle_text.strip():
        return RoutingDecision.OCR_ONLY

    # 计算指标
    subtitle_density = len(subtitle_text) / video_duration
    scene_change_rate = keyframe_count / (video_duration / 10)

    # 字幕密度高 + 场景变化低 → 口播类
    if subtitle_density >= _SUBTITLE_DENSITY_HIGH and scene_change_rate <= _SCENE_RATE_LOW:
        return RoutingDecision.SUMMARY_ONLY

    # 字幕密度低 + 场景变化高 → PPT/图表类
    if subtitle_density <= _SUBTITLE_DENSITY_LOW and scene_change_rate >= _SCENE_RATE_HIGH:
        return RoutingDecision.SUMMARY_WITH_VLM

    # 混合类 → 保守策略，走 VLM
    return RoutingDecision.SUMMARY_WITH_VLM
