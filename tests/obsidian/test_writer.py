"""Test obsidian writer: atomic write + cover download + YAML roundtrip.

Spec ref: specs/obsidian-archive-writer/spec.md
- Requirement: 原子写入 (D-7)
- Requirement: 附件管理 (封面下载失败不阻塞)
- Requirement: frontmatter schema (YAML roundtrip)
"""
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from src.obsidian.writer import write_note


# --- fixtures ---


def _make_frontmatter(video_id: str = "7234567890123") -> dict:
    """构造完整的 frontmatter dict（17 + 3 状态字段）。"""
    return {
        "title": "测试视频标题",
        "video_id": video_id,
        "source_url": "https://v.douyin.com/iAbCdEf/",
        "source_url_type": "short",
        "author": "测试作者",
        "uploader_id": "U123",
        "duration_seconds": 120,
        "uploaded_at": "2026-06-18T10:00:00+08:00",
        "captured_at": "2026-06-19T15:30:00+08:00",
        "cover_url": "https://example.com/cover.jpg",
        "local_cover_path": "",
        "subtitle_source": "douyin_native",
        "subtitle_language": "zh",
        "pipeline_version": "1.0",
        "status": "done",
        "downloader_used": "ytdlp",
        "correlation_id": "test-uuid-001",
    }


NOTE_BODY = "## 摘要\n\n测试内容\n"


# --- tests ---


def test_write_note_creates_md_file(tmp_vault: Path):
    """WHEN write_note completes THEN .md file exists on disk."""
    video_id = "7234567890123"
    frontmatter = _make_frontmatter(video_id)
    capture_time = datetime(2026, 6, 19, 15, 30, 0)

    note_path = write_note(
        vault_root=tmp_vault,
        video_id=video_id,
        frontmatter_dict=frontmatter,
        note_body=NOTE_BODY,
        cover_url="https://example.com/cover.jpg",
        capture_time=capture_time,
    )

    assert note_path.exists(), f"note file should exist: {note_path}"
    assert note_path.suffix == ".md"


def test_write_note_atomic_no_tmp残留(tmp_vault: Path):
    """WHEN write_note succeeds THEN no .tmp file remains."""
    video_id = "v_atomic"
    frontmatter = _make_frontmatter(video_id)
    capture_time = datetime(2026, 6, 19, 15, 30, 0)

    note_path = write_note(
        vault_root=tmp_vault,
        video_id=video_id,
        frontmatter_dict=frontmatter,
        note_body=NOTE_BODY,
        cover_url="https://example.com/cover.jpg",
        capture_time=capture_time,
    )

    tmp_file = note_path.with_suffix(".md.tmp")
    assert not tmp_file.exists(), f".tmp should not remain: {tmp_file}"


def test_write_note_failure_deletes_tmp(tmp_vault: Path):
    """WHEN disk write fails THEN .tmp is cleaned up, no .md left."""
    video_id = "v_fail"
    frontmatter = _make_frontmatter(video_id)
    capture_time = datetime(2026, 6, 19, 15, 30, 0)

    with patch.object(Path, "write_text", side_effect=IOError("disk full")):
        try:
            write_note(
                vault_root=tmp_vault,
                video_id=video_id,
                frontmatter_dict=frontmatter,
                note_body=NOTE_BODY,
                cover_url="https://example.com/cover.jpg",
                capture_time=capture_time,
            )
        except IOError:
            pass  # expected

    # Verify no .md or .tmp files remain
    from src.obsidian.path_calc import calc_note_path
    note_path = calc_note_path(tmp_vault, video_id, capture_time)
    assert not note_path.exists(), f".md should not exist after failure: {note_path}"
    assert not note_path.with_suffix(".md.tmp").exists(), ".tmp should be cleaned up"


def test_write_note_cover_download_failure(tmp_vault: Path):
    """WHEN httpx download fails THEN note is still written, local_cover_path=''."""
    video_id = "v_nocover"
    frontmatter = _make_frontmatter(video_id)
    capture_time = datetime(2026, 6, 19, 15, 30, 0)

    with patch("src.obsidian.writer.httpx") as mock_httpx:
        mock_httpx.get.side_effect = Exception("network error")
        note_path = write_note(
            vault_root=tmp_vault,
            video_id=video_id,
            frontmatter_dict=frontmatter,
            note_body=NOTE_BODY,
            cover_url="https://example.com/cover.jpg",
            capture_time=capture_time,
        )

    assert note_path.exists(), "note should still be written"
    content = note_path.read_text(encoding="utf-8")
    fm = yaml.safe_load(content.split("---\n", 2)[1])
    assert fm["local_cover_path"] == "", "local_cover_path should be empty on failure"
    assert fm["cover_url"] == "https://example.com/cover.jpg", "cover_url preserved"


def test_write_note_yaml_roundtrip(tmp_vault: Path):
    """WHEN note written THEN yaml.safe_load can read back all frontmatter."""
    video_id = "v_yaml"
    frontmatter = _make_frontmatter(video_id)
    capture_time = datetime(2026, 6, 19, 15, 30, 0)

    note_path = write_note(
        vault_root=tmp_vault,
        video_id=video_id,
        frontmatter_dict=frontmatter,
        note_body=NOTE_BODY,
        cover_url="https://example.com/cover.jpg",
        capture_time=capture_time,
    )

    content = note_path.read_text(encoding="utf-8")
    # Extract YAML between --- markers
    parts = content.split("---\n", 2)
    assert len(parts) >= 3, "frontmatter should be wrapped in ---"
    fm = yaml.safe_load(parts[1])
    assert fm["video_id"] == video_id
    assert fm["title"] == "测试视频标题"
    assert fm["author"] == "测试作者"
    assert fm["duration_seconds"] == 120
    assert fm["summary_status"] == "not_run"
    assert fm["pipeline_version"] == "1.0"


def test_write_note_path_calc_integration(tmp_vault: Path):
    """WHEN video_id='7234567890123', captured_at=2026-06-19
    THEN path = vault_root/inbox/douyin/2026-06/7234567890123.md"""
    video_id = "7234567890123"
    frontmatter = _make_frontmatter(video_id)
    capture_time = datetime(2026, 6, 19, 15, 30, 0)

    note_path = write_note(
        vault_root=tmp_vault,
        video_id=video_id,
        frontmatter_dict=frontmatter,
        note_body=NOTE_BODY,
        cover_url="https://example.com/cover.jpg",
        capture_time=capture_time,
    )

    expected = tmp_vault / "inbox" / "douyin" / "2026-06" / f"{video_id}.md"
    assert note_path == expected, f"expected {expected}, got {note_path}"
