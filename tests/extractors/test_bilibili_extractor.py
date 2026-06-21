"""Test BilibiliExtractor — PlatformExtractor implementation (M5 Task 2).

Spec ref: openspec/changes/m5-multichannel-batch/specs/bilibili-extractor/spec.md
D-M5-1: 统一接口，Bilibili 作为第二平台实现。
"""
import pytest

from src.extractors.platform import PlatformExtractor, get_extractor
from src.extractors.bilibili_extractor import BilibiliExtractor


class TestBilibiliExtractorABC:
    """BilibiliExtractor 继承 PlatformExtractor ABC。"""

    def test_is_platform_extractor_subclass(self):
        """BilibiliExtractor 是 PlatformExtractor 子类。"""
        assert issubclass(BilibiliExtractor, PlatformExtractor)

    def test_platform_field(self):
        """BilibiliExtractor.platform == 'bilibili'。"""
        extractor = BilibiliExtractor({})
        assert extractor.platform == "bilibili"

    def test_factory_returns_bilibili_extractor(self):
        """get_extractor('bilibili', config) 返回 BilibiliExtractor 实例。"""
        extractor = get_extractor("bilibili", {})
        assert isinstance(extractor, BilibiliExtractor)
        assert isinstance(extractor, PlatformExtractor)


class TestResolveUrl:
    """resolve_url 解析 Bilibili URL。"""

    def test_full_url_resolves(self):
        """WHEN 传入 https://www.bilibili.com/video/BV1xx411c7mD
        THEN 返回 {video_id, canonical_url, platform='bilibili'}。"""
        extractor = BilibiliExtractor({})
        result = extractor.resolve_url("https://www.bilibili.com/video/BV1xx411c7mD")
        assert result["video_id"] == "BV1xx411c7mD"
        assert "bilibili.com/video/BV1xx411c7mD" in result["canonical_url"]
        assert result["platform"] == "bilibili"

    def test_short_url_follows_redirect(self, monkeypatch):
        """WHEN 传入 https://b23.tv/xxx
        THEN 302 跟随到完整 Bilibili URL，返回正确结果。"""
        monkeypatch.setattr(
            "src.extractors.bilibili_extractor._follow_redirect",
            lambda url: "https://www.bilibili.com/video/BV1xx411c7mD",
        )
        extractor = BilibiliExtractor({})
        result = extractor.resolve_url("https://b23.tv/abc123")
        assert result["video_id"] == "BV1xx411c7mD"
        assert result["platform"] == "bilibili"

    def test_non_bilibili_url_raises_resolver_error(self):
        """WHEN 传入非 Bilibili URL
        THEN 抛 ResolverError。"""
        from src.extractors.bilibili_extractor import ResolverError

        extractor = BilibiliExtractor({})
        with pytest.raises(ResolverError):
            extractor.resolve_url("https://www.douyin.com/video/123456")

    def test_no_video_id_in_resolved_raises(self, monkeypatch):
        """WHEN 302 跟随后 URL 中无 video_id
        THEN 抛 ResolverError。"""
        from src.extractors.bilibili_extractor import ResolverError

        monkeypatch.setattr(
            "src.extractors.bilibili_extractor._follow_redirect",
            lambda url: "https://www.bilibili.com/",
        )
        extractor = BilibiliExtractor({})
        with pytest.raises(ResolverError):
            extractor.resolve_url("https://b23.tv/abc123")


class TestDownload:
    """download 委托 yt-dlp 下载 Bilibili 视频。"""

    def test_download_delegates_to_yt_dlp(self, monkeypatch, tmp_path):
        """download 调用 yt-dlp 下载视频+字幕，返回标准结果 dict。"""
        from pathlib import Path

        called_with = {}

        def fake_download(video_id, canonical_url, out_dir, cookies_path=None):
            called_with["video_id"] = video_id
            (out_dir / f"{video_id}.mp4").write_bytes(b"fake-video")
            return {
                "video_path": out_dir / f"{video_id}.mp4",
                "subtitle_path": None,
                "subtitle_source": "auto_generated",
                "downloader_used": "yt-dlp",
                "info_dict": {"title": "Test"},
                "title": "Test",
            }

        monkeypatch.setattr(
            "src.extractors.bilibili_extractor._download_video", fake_download
        )
        extractor = BilibiliExtractor({})
        result = extractor.download(
            "BV1xx411c7mD",
            "https://www.bilibili.com/video/BV1xx411c7mD",
            tmp_path,
        )
        assert called_with["video_id"] == "BV1xx411c7mD"
        assert result["subtitle_source"] == "auto_generated"
        assert result["video_path"].exists()


class TestClassifySubtitle:
    """classify_subtitle 复用 classify_subtitle_source (B2 修订)。"""

    def test_creator_uploaded(self):
        """subtitles 有 zh → creator_uploaded。"""
        extractor = BilibiliExtractor({})
        info = {
            "subtitles": {"zh": [{"url": "http://x.vtt"}]},
            "automatic_captions": {},
        }
        assert extractor.classify_subtitle(info) == "creator_uploaded"

    def test_auto_generated(self):
        """automatic_captions 有 zh → auto_generated。"""
        extractor = BilibiliExtractor({})
        info = {
            "subtitles": {},
            "automatic_captions": {"zh": [{"url": "http://x.vtt"}]},
        }
        assert extractor.classify_subtitle(info) == "auto_generated"

    def test_no_subtitle_raises(self):
        """无字幕 → NoSubtitleError。"""
        from src.extractors.downloader import NoSubtitleError

        extractor = BilibiliExtractor({})
        info = {"subtitles": {}, "automatic_captions": {}}
        with pytest.raises(NoSubtitleError):
            extractor.classify_subtitle(info)
