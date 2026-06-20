"""Test metadata extractor.

Spec ref: specs/douyin-extraction/spec.md
- Scenario: 完整元数据
- Scenario: uploader_id 提取失败 -> 留空字符串，任务不失败
"""
import pytest

from src.extractors.metadata import extract_metadata, extract_uploader_id


def test_extract_uploader_id_from_sec_uid():
    url = "https://www.douyin.com/user/MS4wLjABAAAAxYz123abc"
    assert extract_uploader_id(url) == "MS4wLjABAAAAxYz123abc"


def test_extract_uploader_id_no_user_path():
    assert extract_uploader_id("https://www.douyin.com/some/other") == ""
    assert extract_uploader_id("") == ""


def test_extract_metadata_full():
    info = {
        "title": "测试视频标题",
        "uploader": "测试作者",
        "uploader_url": "https://www.douyin.com/user/MS4wLjABAAAAsecUID",
        "duration": 180,
        "upload_date": "20260619",
        "thumbnail": "https://p9.douyinpic.com/xxx.jpg",
    }
    md = extract_metadata(info)
    assert md["title"] == "测试视频标题"
    assert md["uploader"] == "测试作者"
    assert md["uploader_id"] == "MS4wLjABAAAAsecUID"
    assert md["duration_seconds"] == 180
    assert md["uploaded_at"] == "2026-06-19T00:00:00"
    assert md["thumbnail"] == "https://p9.douyinpic.com/xxx.jpg"


def test_extract_metadata_missing_uploader_url():
    info = {
        "title": "x", "uploader": "y", "uploader_url": "",
        "duration": 10, "upload_date": "20260101", "thumbnail": "t",
    }
    md = extract_metadata(info)
    assert md["uploader_id"] == ""


def test_extract_metadata_invalid_date():
    """Boundary: invalid upload_date format -> uploaded_at empty string."""
    info = {
        "title": "x", "uploader": "y", "uploader_url": "https://www.douyin.com/user/X",
        "duration": 10, "upload_date": "not-a-date", "thumbnail": "t",
    }
    md = extract_metadata(info)
    assert md["uploaded_at"] == ""
