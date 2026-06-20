"""笔记正文构建（5 段结构）。

Spec ref: specs/obsidian-archive-writer/spec.md Requirement: 笔记正文结构。
段落顺序：摘要 -> 字幕全文 -> 关键帧 -> 元数据 -> 链接。
"""


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
) -> str:
    """构建笔记正文（5 段）。"""
    sections = []

    # 1. 摘要（M1 占位）
    sections.append("## 摘要\n\nM1 阶段无 LLM 总结，待 M3 填充。\n")

    # 2. 字幕全文
    sections.append(f"## 字幕全文\n\n```\n{_render_subtitle(subtitle_vtt)}\n```\n")

    # 3. 关键帧（M1 占位）
    sections.append("## 关键帧\n\nM1 阶段不抽取关键帧，待 M3 填充。\n")

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
