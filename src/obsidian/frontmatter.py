"""frontmatter schema：17 字段 + D-10 三状态字段。

Spec ref: specs/obsidian-archive-writer/spec.md Requirement: frontmatter schema。
M1 默认：summary_status=not_run, processing_mode=subtitle_only, ai_summary_model=null。
M3: 接受 summary_status, processing_mode, ai_summary_model, summary 字段。
"""
from typing import Any, Dict


REQUIRED_FIELDS = [
    "title", "video_id", "source_url", "source_url_type",
    "author", "uploader_id", "duration_seconds", "uploaded_at",
    "captured_at", "cover_url", "local_cover_path",
    "subtitle_source", "subtitle_language", "pipeline_version",
    "status", "downloader_used", "correlation_id",
]


class IncompleteFrontmatterError(Exception):
    """frontmatter SHALL 字段缺失。"""


def build_frontmatter(data: dict) -> Dict[str, Any]:
    """构建 frontmatter dict。M1 默认填充 3 状态字段，M3 支持覆盖。

    Raises: IncompleteFrontmatterError 当任一 REQUIRED_FIELDS 缺失。
    """
    for f in REQUIRED_FIELDS:
        if f not in data:
            raise IncompleteFrontmatterError(f"missing field: {f}")

    fm = {f: data[f] for f in REQUIRED_FIELDS}
    # D-10 状态字段（M1 默认值，M3 允许覆盖）
    fm["summary_status"] = data.get("summary_status", "not_run")
    fm["processing_mode"] = data.get("processing_mode", "subtitle_only")
    fm["ai_summary_model"] = data.get("ai_summary_model", None)
    # M3 字段
    fm["summary"] = data.get("summary", "")
    fm["vlm_results"] = data.get("vlm_results", [])
    return fm
