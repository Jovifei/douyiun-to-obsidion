"""Test DouK-Downloader fallback.

Spec ref: specs/douyin-extraction/spec.md
- Scenario: yt-dlp 失败 → DouK 成功 → downloader_used='douk'
- Scenario: DouK 命令未找到 → DoukDownloadError("douk_unavailable")
- Scenario: DouK 执行失败 → DoukDownloadError("douk_failed: ...")
"""
import pytest

from src.extractors.douk_fallback import (
    download_with_douk,
    DoukNotConfiguredError,
    DoukDownloadError,
)
from src.extractors.downloader import NoSubtitleError


def test_douk_not_configured_raises():
    """空 douk_path 抛 DoukNotConfiguredError。"""
    with pytest.raises(DoukNotConfiguredError):
        download_with_douk(
            video_id="123",
            canonical_url="https://www.douyin.com/video/123",
            out_dir="/tmp/x",
            douk_path="",
        )


def test_douk_success(monkeypatch, tmp_path):
    """DouK subprocess returncode=0 → dict 含 downloader_used='douk'。"""
    def fake_run(cmd, **kw):
        (tmp_path / "123.mp4").write_bytes(b"fake")
        (tmp_path / "123.zh.vtt").write_text("WEBVTT\n...")

        class R:
            returncode = 0
            stdout = b""
            stderr = b""
        return R()

    monkeypatch.setattr("src.extractors.douk_fallback.subprocess.run", fake_run)
    result = download_with_douk(
        video_id="123",
        canonical_url="https://www.douyin.com/video/123",
        out_dir=tmp_path,
        douk_path="/fake/douk.exe",
    )
    assert result["video_path"].exists()
    assert result["downloader_used"] == "douk"


def test_douk_command_not_found(monkeypatch, tmp_path):
    """subprocess.run 抛 FileNotFoundError → DoukDownloadError('douk_unavailable')。"""
    def fake_run(cmd, **kw):
        raise FileNotFoundError("No such file: douk")

    monkeypatch.setattr("src.extractors.douk_fallback.subprocess.run", fake_run)
    with pytest.raises(DoukDownloadError, match="douk_unavailable"):
        download_with_douk(
            video_id="123",
            canonical_url="https://www.douyin.com/video/123",
            out_dir=tmp_path,
            douk_path="/nonexistent/douk.exe",
        )


def test_douk_failed_nonzero(monkeypatch, tmp_path):
    """subprocess returncode != 0 → DoukDownloadError('douk_failed: ...')。"""
    def fake_run(cmd, **kw):
        class R:
            returncode = 1
            stdout = b""
            stderr = b"some douk error"
        return R()

    monkeypatch.setattr("src.extractors.douk_fallback.subprocess.run", fake_run)
    with pytest.raises(DoukDownloadError, match="douk_failed"):
        download_with_douk(
            video_id="123",
            canonical_url="https://www.douyin.com/video/123",
            out_dir=tmp_path,
            douk_path="/fake/douk.exe",
        )


def test_douk_result_dict_fields(monkeypatch, tmp_path):
    """返回 dict 包含 video_path、subtitle_path、downloader_used 三个字段。"""
    def fake_run(cmd, **kw):
        (tmp_path / "456.mp4").write_bytes(b"fake")
        (tmp_path / "456.zh.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nTest")

        class R:
            returncode = 0
            stdout = b""
            stderr = b""
        return R()

    monkeypatch.setattr("src.extractors.douk_fallback.subprocess.run", fake_run)
    result = download_with_douk(
        video_id="456",
        canonical_url="https://www.douyin.com/video/456",
        out_dir=tmp_path,
        douk_path="/fake/douk.exe",
    )
    assert "video_path" in result
    assert "subtitle_path" in result
    assert "downloader_used" in result
    assert result["video_path"].exists()
    assert result["subtitle_path"] is not None
    assert result["subtitle_path"].name == "456.zh.srt"


def test_douk_success_returns_subtitle_source(monkeypatch, tmp_path):
    """DouK 有字幕 → subtitle_source='douyin_native'。"""
    def fake_run(cmd, **kw):
        (tmp_path / "789.mp4").write_bytes(b"fake")
        (tmp_path / "789.zh.vtt").write_text("WEBVTT\n...")

        class R:
            returncode = 0
            stdout = b""
            stderr = b""
        return R()

    monkeypatch.setattr("src.extractors.douk_fallback.subprocess.run", fake_run)
    result = download_with_douk(
        video_id="789",
        canonical_url="https://www.douyin.com/video/789",
        out_dir=tmp_path,
        douk_path="/fake/douk.exe",
    )
    assert result["subtitle_source"] == "douyin_native"


def test_douk_success_no_subtitle_raises(monkeypatch, tmp_path):
    """DouK 只产 mp4 无字幕 → NoSubtitleError('no_subtitle_in_m1')。"""
    def fake_run(cmd, **kw):
        (tmp_path / "789.mp4").write_bytes(b"fake")
        # No subtitle file produced

        class R:
            returncode = 0
            stdout = b""
            stderr = b""
        return R()

    monkeypatch.setattr("src.extractors.douk_fallback.subprocess.run", fake_run)
    with pytest.raises(NoSubtitleError, match="no_subtitle_in_m1"):
        download_with_douk(
            video_id="789",
            canonical_url="https://www.douyin.com/video/789",
            out_dir=tmp_path,
            douk_path="/fake/douk.exe",
        )


def test_douk_returns_none_metadata_fields(monkeypatch, tmp_path):
    """DouK 返回 dict 含 info_dict=None + 5 个元数据占位字段。"""
    def fake_run(cmd, **kw):
        (tmp_path / "000.mp4").write_bytes(b"fake")
        (tmp_path / "000.zh.vtt").write_text("WEBVTT\n...")

        class R:
            returncode = 0
            stdout = b""
            stderr = b""
        return R()

    monkeypatch.setattr("src.extractors.douk_fallback.subprocess.run", fake_run)
    result = download_with_douk(
        video_id="000",
        canonical_url="https://www.douyin.com/video/000",
        out_dir=tmp_path,
        douk_path="/fake/douk.exe",
    )
    assert result["info_dict"] is None
    assert result["title"] is None
    assert result["duration"] is None
    assert result["uploader"] is None
    assert result["uploader_url"] is None
    assert result["thumbnail"] is None
