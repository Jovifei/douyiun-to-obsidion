"""Test note body builder (5 sections).

Spec ref: specs/obsidian-archive-writer/spec.md
- Requirement: 笔记正文结构（5 段）
- Scenario: M1 完整笔记正文
"""
from src.obsidian.note_builder import build_note_body


def test_note_body_has_5_sections():
    """WHEN 构建笔记正文
    THEN 含 ## 摘要 / ## 字幕全文 / ## 关键帧 / ## 元数据 / ## 链接。"""
    body = build_note_body(
        subtitle_vtt="WEBVTT\n00:00:01 --> 00:00:02\nTest line",
        metadata={"source_url": "https://www.douyin.com/video/v1",
                  "author": "作者", "duration_seconds": 180,
                  "cover_url": "https://x.jpg"},
        local_cover_path="attachments/douyin/v1/cover.jpg",
        correlation_id="c1",
        raw_input="https://v.douyin.com/x/",
        processing_time_seconds=30,
    )
    assert "## 摘要" in body
    assert "## 字幕全文" in body
    assert "## 关键帧" in body
    assert "## 元数据" in body
    assert "## 链接" in body


def test_summary_section_m1_placeholder():
    """WHEN M1 阶段
    THEN ## 摘要 仅占位提示文字。"""
    body = build_note_body(
        subtitle_vtt="", metadata={}, local_cover_path="",
        correlation_id="c1", raw_input="", processing_time_seconds=0,
    )
    assert "M1 阶段无 LLM 总结" in body


def test_cover_embedded_with_obsidian_syntax():
    """WHEN local_cover_path 存在
    THEN 正文用 ![[path]] 嵌入。"""
    body = build_note_body(
        subtitle_vtt="", metadata={"cover_url": "https://x.jpg"},
        local_cover_path="attachments/douyin/v1/cover.jpg",
        correlation_id="c1", raw_input="", processing_time_seconds=0,
    )
    assert "![[attachments/douyin/v1/cover.jpg]]" in body
