"""vault 路径计算。

Spec ref: specs/obsidian-archive-writer/spec.md Requirement: vault 路径计算。
- 笔记：inbox/douyin/{YYYY-MM}/{video_id}.md
- 附件：attachments/douyin/{video_id}/{filename}
- 月份按"完成时刻"（spec Scenario: 跨月写入）。
"""
from datetime import datetime
from pathlib import Path


def calc_note_path(vault_root: Path, video_id: str, captured_at: datetime) -> Path:
    """计算笔记文件路径。"""
    month = captured_at.strftime("%Y-%m")
    return vault_root / "inbox" / "douyin" / month / f"{video_id}.md"


def calc_cover_path(vault_root: Path, video_id: str, filename: str = "cover.jpg") -> Path:
    """计算封面附件路径。"""
    return vault_root / "attachments" / "douyin" / video_id / filename
