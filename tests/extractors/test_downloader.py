"""Test yt-dlp downloader wrapper + subtitle source classification.

Spec ref: specs/douyin-extraction/spec.md
- Scenario: 带原生字幕视频 → 'douyin_native'
- Scenario: 创作者上传字幕 → 'creator_uploaded'
- Scenario: 平台自动字幕 → 'auto_generated'
- Scenario: 无字幕视频 → NoSubtitleError
"""
import pytest

from src.extractors.downloader import (
    download_video,
    classify_subtitle_source,
    NoSubtitleError,
)


def test_classify_creator_uploaded():
    info = {"subtitles": {"zh": [{"url": "http://x.vtt"}]}, "automatic_captions": {}}
    assert classify_subtitle_source(info) == "creator_uploaded"


def test_classify_auto_generated():
    info = {"subtitles": {}, "automatic_captions": {"zh": [{"url": "http://x.vtt"}]}}
    assert classify_subtitle_source(info) == "auto_generated"


def test_classify_no_subtitle():
    info = {"subtitles": {}, "automatic_captions": {}}
    with pytest.raises(NoSubtitleError):
        classify_subtitle_source(info)


def test_classify_douyin_native_special_case():
    info = {
        "subtitles": {"zh": [{"url": "http://a.vtt"}]},
        "automatic_captions": {"zh": [{"url": "http://b.vtt"}]},
    }
    assert classify_subtitle_source(info) == "douyin_native"


def test_download_invokes_yt_dlp(monkeypatch, tmp_path):
    class FakeYdl:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def extract_info(self, url, download=True):
            (tmp_path / "7234567890123.mp4").write_bytes(b"fake-video")
            (tmp_path / "7234567890123.zh.vtt").write_text(
                "WEBVTT\n00:00:01 --> 00:00:02\nTest"
            )
            return {
                "id": "7234567890123",
                "subtitles": {"zh": [{"url": "http://x.vtt"}]},
                "automatic_captions": {"zh": [{"url": "http://x.vtt"}]},
                "title": "Test video",
            }

    monkeypatch.setattr(
        "src.extractors.downloader.yt_dlp.YoutubeDL", lambda opts: FakeYdl(opts)
    )
    result = download_video(
        video_id="7234567890123",
        canonical_url="https://www.douyin.com/video/7234567890123",
        out_dir=tmp_path,
        cookies_path=None,
    )
    assert result["video_path"].exists()
    assert result["subtitle_path"].exists()
    assert result["subtitle_source"] == "douyin_native"


def test_cookies_path_passed_to_ydl_opts(monkeypatch, tmp_path):
    """(c) cookies_path is transparently set as ydl_opts['cookiefile']."""
    captured_opts = None

    class FakeYdl:
        def __init__(self, opts):
            nonlocal captured_opts
            captured_opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def extract_info(self, url, download=True):
            (tmp_path / "7234567890123.mp4").write_bytes(b"fake-video")
            return {
                "id": "7234567890123",
                "subtitles": {"zh": [{"url": "http://x.vtt"}]},
                "automatic_captions": {"zh": [{"url": "http://x.vtt"}]},
                "title": "Test video",
            }

    monkeypatch.setattr(
        "src.extractors.downloader.yt_dlp.YoutubeDL", lambda opts: FakeYdl(opts)
    )
    _result = download_video(
        video_id="7234567890123",
        canonical_url="https://www.douyin.com/video/7234567890123",
        out_dir=tmp_path,
        cookies_path="cookies.txt",
    )
    assert captured_opts is not None
    assert captured_opts["cookiefile"] == "cookies.txt"


def test_subtitle_path_zh_srt(monkeypatch, tmp_path):
    """(d) When yt-dlp writes .srt, subtitle_path resolves to the .zh.srt file."""

    class FakeYdl:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def extract_info(self, url, download=True):
            (tmp_path / "7234567890123.mp4").write_bytes(b"fake-video")
            (tmp_path / "7234567890123.zh.srt").write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nTest"
            )
            return {
                "id": "7234567890123",
                "subtitles": {"zh": [{"url": "http://x.srt"}]},
                "automatic_captions": {},
                "title": "Test video",
            }

    monkeypatch.setattr(
        "src.extractors.downloader.yt_dlp.YoutubeDL", lambda opts: FakeYdl(opts)
    )
    result = download_video(
        video_id="7234567890123",
        canonical_url="https://www.douyin.com/video/7234567890123",
        out_dir=tmp_path,
    )
    assert result["subtitle_path"] is not None
    assert result["subtitle_path"].name == "7234567890123.zh.srt"


def test_classify_subtitle_source_none_defense():
    """(e) classify_subtitle_source with None values uses or {} defense and raises NoSubtitleError."""
    info = {"subtitles": None, "automatic_captions": None}
    with pytest.raises(NoSubtitleError, match="no_subtitle_in_m1"):
        classify_subtitle_source(info)
