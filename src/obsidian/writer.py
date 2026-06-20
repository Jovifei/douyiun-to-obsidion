"""Obsidian 笔记原子写入。

Spec ref: specs/obsidian-archive-writer/spec.md
- Requirement: 原子写入 (D-7): .tmp + os.rename
- Requirement: 附件管理: 封面下载失败不阻塞
"""
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

import httpx
import yaml

from src.obsidian.frontmatter import build_frontmatter
from src.obsidian.path_calc import calc_cover_path, calc_note_path


def _download_cover(cover_url: str, dest_path: Path) -> bool:
    """下载封面到 dest_path。失败返回 False，不抛异常。"""
    if not cover_url:
        return False
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        resp = httpx.get(cover_url, timeout=30)
        resp.raise_for_status()
        dest_path.write_bytes(resp.content)
        return True
    except Exception:
        return False


def write_note(
    vault_root: Path,
    video_id: str,
    frontmatter_dict: Dict[str, Any],
    note_body: str,
    cover_url: str,
    capture_time: datetime,
) -> str:
    """完整写入流程：封面下载 + YAML frontmatter + 原子写入。

    Returns: note_path (str)
    """
    note_path = calc_note_path(vault_root, video_id, capture_time)
    cover_path = calc_cover_path(vault_root, video_id)

    # 下载封面（失败不阻塞）
    if _download_cover(cover_url, cover_path):
        frontmatter_dict["local_cover_path"] = str(
            cover_path.relative_to(vault_root)
        )
    else:
        frontmatter_dict["local_cover_path"] = ""

    # 构建完整内容
    fm = build_frontmatter(frontmatter_dict)
    fm_yaml = yaml.dump(
        fm,
        allow_unicode=True,
        default_flow_style=False,
    )
    full_content = f"---\n{fm_yaml}---\n{note_body}"

    # 原子写入: .tmp -> rename
    note_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = note_path.with_suffix(".md.tmp")
    try:
        tmp_path.write_text(full_content, encoding="utf-8")
        os.rename(str(tmp_path), str(note_path))
    except Exception:
        # 写入失败，清理 .tmp
        if tmp_path.exists():
            tmp_path.unlink()
        raise

    return note_path
