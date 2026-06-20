"""Test vault path calculation.

Spec ref: specs/obsidian-archive-writer/spec.md
- Scenario: 标准路径 -> inbox/douyin/{YYYY-MM}/{video_id}.md
- Scenario: 跨月写入 -> 按"完成时刻"月份
"""
from datetime import datetime
from pathlib import Path

from src.obsidian.path_calc import calc_note_path, calc_cover_path


def test_standard_path():
    """WHEN video_id='7234567890123', captured_at=2026-06-19
    THEN 笔记路径 = .../inbox/douyin/2026-06/7234567890123.md。"""
    vault = Path("E:/vault")
    p = calc_note_path(vault, video_id="7234567890123",
                       captured_at=datetime(2026, 6, 19, 10, 0, 0))
    assert p == Path("E:/vault/inbox/douyin/2026-06/7234567890123.md")


def test_cross_month_uses_completion_time():
    """WHEN 6/30 23:59 触发，7/1 00:01 完成
    THEN 文件路径按 7 月算。"""
    vault = Path("E:/vault")
    completion = datetime(2026, 7, 1, 0, 1, 0)
    p = calc_note_path(vault, video_id="v1", captured_at=completion)
    assert "2026-07" in str(p)


def test_cover_path():
    """WHEN video_id='v1'
    THEN cover = vault/attachments/douyin/v1/cover.jpg。"""
    vault = Path("E:/vault")
    p = calc_cover_path(vault, video_id="v1")
    assert p == Path("E:/vault/attachments/douyin/v1/cover.jpg")
