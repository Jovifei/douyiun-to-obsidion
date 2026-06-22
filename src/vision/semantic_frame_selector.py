"""语义选帧 — 用 LLM 从 ASR segments 识别关键时间点，回退 ASR segments 直接抽帧。

Spec ref: D-M6-4 — mimo-v2.5-pro 语义分析 + ASR segments 回退

回退链：
1. LLM 返回 >=3 帧 → 使用语义帧（source="semantic"）
2. LLM 返回 <3 帧 或 API 失败 → fallback ASR segments 直接抽帧（source="asr_segment"）
3. 无 segments → 均匀采样每 10 秒（source="interval"）
"""
import math

from src.llm.client import LLMClient, LLMClientError

SEMANTIC_SELECT_PROMPT = """\
你是视频分析助手。以下是一段视频的带时间戳语音转写文本。
请识别 **3-10 个知识重点时刻**，即说话人正在强调关键知识点、展示示例、或总结要点的瞬间。

要求：
- 只返回 JSON 数组，不含任何额外文本
- 每项含 time_sec（秒数，整数）和 reason（一句话说明为什么是重点）
- time_sec 必须来自下方 segments 的 start 时间（或非常接近）
- 最多返回 {max_frames} 项

segments：
{segments_text}

输出格式：
```json
[{{"time_sec": 30, "reason": "讲师展示代码示例"}}, ...]
```"""


def select_semantic_frames(
    asr_segments: list[dict],
    llm_client: LLMClient | None = None,
    max_frames: int = 15,
    video_duration: float = 0.0,
) -> list[dict]:
    """从 ASR segments 识别关键时间点（语义选帧）。

    Args:
        asr_segments: ASR 转写 segments，每项含 start/end/text。
        llm_client: LLM 客户端（可选，None 时跳过语义分析）。
        max_frames: 最大返回帧数。
        video_duration: 视频时长（秒），用于无 segments 时均匀采样。

    Returns:
        list[dict]，每项含 time_sec + reason + source。
    """
    if not asr_segments and video_duration <= 0:
        return []

    # 尝试 LLM 语义选帧
    if llm_client is not None and asr_segments:
        try:
            segments_text = "\n".join(
                f"[{s.get('start', 0):.1f}s - {s.get('end', 0):.1f}s] {s.get('text', '')}"
                for s in asr_segments[:50]
            )
            prompt = SEMANTIC_SELECT_PROMPT.format(
                max_frames=max_frames, segments_text=segments_text
            )
            result = llm_client.chat_json([{"role": "user", "content": prompt}])
            if isinstance(result, list) and len(result) >= 3:
                frames = []
                for item in result[:max_frames]:
                    time_sec = item.get("time_sec")
                    if time_sec is not None:
                        frames.append({
                            "time_sec": int(time_sec),
                            "reason": item.get("reason", ""),
                            "source": "semantic",
                        })
                if len(frames) >= 3:
                    return frames
        except (LLMClientError, Exception):
            pass  # fallback

    # 回退：ASR segments 直接抽帧
    if asr_segments:
        return [
            {"time_sec": int(s.get("start", 0)), "reason": "", "source": "asr_segment"}
            for s in asr_segments[:max_frames]
        ]

    # 最终回退：均匀采样（每 10 秒）
    num_frames = min(max_frames, math.ceil(video_duration / 10))
    return [
        {"time_sec": i * 10, "reason": "", "source": "interval"}
        for i in range(num_frames)
    ]
