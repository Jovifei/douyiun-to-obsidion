"""笔记正文构建（5 段结构）。

Spec ref: specs/obsidian-archive-writer/spec.md Requirement: 笔记正文结构。
段落顺序：摘要 -> 字幕全文 -> 关键帧 -> 元数据 -> 链接。
M3: LLM 总结 + 视觉理解集成。
"""
from typing import Any


def _render_subtitle(vtt_content: str) -> str:
    """简单渲染 VTT 为可读文本（保留时间戳）。M1 不做复杂解析。"""
    if not vtt_content:
        return "（无字幕内容）"
    # 去掉 WEBVTT 头，保留 cue 时间行 + 文本
    lines = vtt_content.splitlines()
    if lines and lines[0].startswith("WEBVTT"):
        lines = lines[1:]
    return "\n".join(lines).strip()


def build_note_body(
    subtitle_vtt: str,
    metadata: dict,
    local_cover_path: str,
    correlation_id: str,
    raw_input: str,
    processing_time_seconds: int,
    summary_result: Any = None,
    summary_error: str | None = None,
    vlm_result: str | None = None,
    ocr_texts: list[str] | None = None,
) -> str:
    """构建笔记正文（5 段）。

    Args:
        subtitle_vtt: VTT 字幕内容。
        metadata: 视频元数据。
        local_cover_path: 本地封面路径。
        correlation_id: 关联 ID。
        raw_input: 原始输入（飞书消息）。
        processing_time_seconds: 处理耗时。
        summary_result: LLM 总结结果（SummaryResult 或 None）。
        summary_error: LLM 总结错误码（str 或 None）。
        vlm_result: VLM 描述文本（str 或 None）。
        ocr_texts: OCR 提取的文字列表（list[str] 或 None）。
    """
    sections = []

    # 1. 摘要（M3: LLM 总结，M1 兼容）
    if summary_result and summary_result.key_points:
        points = "\n".join(f"- {p}" for p in summary_result.key_points)
        sections.append(f"## 摘要\n\n{points}\n")
    elif summary_error:
        sections.append(f"## 摘要\n\nLLM 总结失败：{summary_error}\n")
    else:
        # M1 兼容：无 LLM 调用时显示占位文字
        sections.append("## 摘要\n\nM1 阶段无 LLM 总结，待 M3 填充。\n")

    # 2. 字幕全文
    sections.append(f"## 字幕全文\n\n```\n{_render_subtitle(subtitle_vtt)}\n```\n")

    # 3. 关键帧（M3: VLM 视觉理解）
    if vlm_result:
        # VLM 成功：逐帧写入描述
        parts = []
        if ocr_texts:
            for i, text in enumerate(ocr_texts, 1):
                parts.append(f"**帧 {i} OCR**: {text}")
        parts.append(f"**VLM 描述**: {vlm_result}")
        sections.append("## 关键帧\n\n" + "\n\n".join(parts) + "\n")
    else:
        # VLM 未执行或失败：写占位文字
        sections.append("## 关键帧\n\n视觉理解已禁用\n")

    # 4. 元数据
    meta_lines = []
    if local_cover_path:
        meta_lines.append(f"封面： ![[{local_cover_path}]]")
    elif metadata.get("cover_url"):
        meta_lines.append(f"封面： [外部链接]({metadata['cover_url']})")
    if metadata.get("source_url"):
        meta_lines.append(f"原始 URL： {metadata['source_url']}")
    if metadata.get("author"):
        meta_lines.append(f"作者： {metadata['author']}")
    if metadata.get("duration_seconds"):
        meta_lines.append(f"时长： {metadata['duration_seconds']} 秒")
    sections.append("## 元数据\n\n" + "\n\n".join(meta_lines) + "\n")

    # 5. 链接
    sections.append(
        "## 链接\n\n"
        f"- 飞书触发消息： {raw_input}\n"
        f"- correlation_id： `{correlation_id}`\n"
        f"- 处理耗时： {processing_time_seconds} 秒\n"
    )

    return "\n".join(sections)
