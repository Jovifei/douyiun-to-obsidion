"""Test frontmatter schema (17 fields + D-10 3 status fields).

Spec ref: specs/obsidian-archive-writer/spec.md
- Scenario: M1 完整 frontmatter
- Scenario: 字段不可缺失 -> raise
- Scenario: 状态字段防误判（D-10）
"""
import pytest

from src.obsidian.frontmatter import build_frontmatter, IncompleteFrontmatterError


def _minimal_valid_input():
    return {
        "title": "测试标题",
        "video_id": "v1",
        "source_url": "https://www.douyin.com/video/v1",
        "source_url_type": "full",
        "author": "作者",
        "uploader_id": "sec_uid_xxx",
        "duration_seconds": 180,
        "uploaded_at": "2026-06-19T00:00:00",
        "captured_at": "2026-06-19T10:00:00",
        "cover_url": "https://p9.douyinpic.com/x.jpg",
        "local_cover_path": "attachments/douyin/v1/cover.jpg",
        "subtitle_source": "douyin_native",
        "subtitle_language": "zh",
        "pipeline_version": "1.0",
        "status": "done",
        "downloader_used": "ytdlp",
        "correlation_id": "uuid-xxx",
    }


def test_m1_full_frontmatter_has_status_fields():
    """WHEN M1 完整 frontmatter
    THEN 含 summary_status=not_run, processing_mode=subtitle_only, ai_summary_model=null。"""
    fm = build_frontmatter(_minimal_valid_input())
    assert "summary_status" in fm
    assert fm["summary_status"] == "not_run"
    assert fm["processing_mode"] == "subtitle_only"
    assert fm["ai_summary_model"] is None


def test_m1_default_status_values():
    fm = build_frontmatter(_minimal_valid_input())
    assert fm["summary"] == ""
    assert fm["vlm_results"] == []
    assert fm["pipeline_version"] == "1.0"


def test_missing_correlation_id_raises():
    """WHEN correlation_id 缺失
    THEN raise IncompleteFrontmatterError。"""
    data = _minimal_valid_input()
    del data["correlation_id"]
    with pytest.raises(IncompleteFrontmatterError):
        build_frontmatter(data)


def test_missing_title_raises():
    data = _minimal_valid_input()
    del data["title"]
    with pytest.raises(IncompleteFrontmatterError):
        build_frontmatter(data)


def test_status_field_d10_filter():
    """WHEN M1 笔记 frontmatter summary_status='not_run'
    THEN DataView WHERE summary_status != 'done' 能匹配（模拟检查）。"""
    fm = build_frontmatter(_minimal_valid_input())
    assert fm["summary_status"] != "done"
