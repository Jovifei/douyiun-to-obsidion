"""Test XiaohongshuExtractor — PlatformExtractor 实现 (M5 Task 3)。

小红书 URL 解析 + yt-dlp/requests 双层下载策略。
"""
import pytest

from src.extractors.xiaohongshu_extractor import XiaohongshuExtractor
from src.extractors.platform import PlatformExtractor
from src.extractors.douyin_resolver import ResolverError


class TestXiaohongshuExtractorInterface:
    """验证 XiaohongshuExtractor 实现 PlatformExtractor ABC。"""

    def test_inherits_platform_extractor(self):
        assert issubclass(XiaohongshuExtractor, PlatformExtractor)

    def test_platform_attribute(self):
        ext = XiaohongshuExtractor({})
        assert ext.platform == "xiaohongshu"

    def test_registered_in_get_extractor(self):
        from src.extractors.platform import get_extractor
        ext = get_extractor("xiaohongshu", {})
        assert isinstance(ext, XiaohongshuExtractor)


class TestResolveUrl:
    """resolve_url URL 解析测试。"""

    def setup_method(self):
        self.ext = XiaohongshuExtractor({})

    def test_explore_url_full(self):
        """完整 explore URL → video_id + canonical_url + platform。"""
        result = self.ext.resolve_url("https://www.xiaohongshu.com/explore/6789abcdef")
        assert result["video_id"] == "6789abcdef"
        assert result["canonical_url"] == "https://www.xiaohongshu.com/explore/6789abcdef"
        assert result["platform"] == "xiaohongshu"

    def test_explore_url_with_query_params(self):
        """explore URL 带查询参数 → 正常解析。"""
        result = self.ext.resolve_url(
            "https://www.xiaohongshu.com/explore/6789abcdef?xsec_token=abc"
        )
        assert result["video_id"] == "6789abcdef"
        assert result["platform"] == "xiaohongshu"

    def test_short_link_xhslink(self):
        """xhslink.com 短链 → 跟随 302 → 解析 video_id。"""
        import src.extractors.xiaohongshu_extractor as mod

        original_follow = mod._follow_redirect

        def fake_follow(url):
            return "https://www.xiaohongshu.com/explore/abc123xyz"

        mod._follow_redirect = fake_follow
        try:
            result = self.ext.resolve_url("https://xhslink.com/abc123")
            assert result["video_id"] == "abc123xyz"
            assert result["canonical_url"] == "https://www.xiaohongshu.com/explore/abc123xyz"
            assert result["platform"] == "xiaohongshu"
        finally:
            mod._follow_redirect = original_follow

    def test_not_xiaohongshu_url_raises(self):
        """非小红书 URL → ResolverError。"""
        with pytest.raises(ResolverError, match="not_xiaohongshu"):
            self.ext.resolve_url("https://www.youtube.com/watch?v=abc")

    def test_douyin_url_raises(self):
        """抖音 URL → ResolverError。"""
        with pytest.raises(ResolverError, match="not_xiaohongshu"):
            self.ext.resolve_url("https://www.douyin.com/video/123456")

    def test_unrecognized_xiaohongshu_url(self):
        """小红书域名但路径不匹配 → ResolverError。"""
        with pytest.raises(ResolverError, match="unrecognized_xiaohongshu"):
            self.ext.resolve_url("https://www.xiaohongshu.com/user/profile/123")

    def test_short_link_no_video_id(self):
        """短链跟随后无法提取 video_id → ResolverError。"""
        import src.extractors.xiaohongshu_extractor as mod

        original_follow = mod._follow_redirect

        def fake_follow(url):
            return "https://www.xiaohongshu.com/something-else"

        mod._follow_redirect = fake_follow
        try:
            with pytest.raises(ResolverError, match="short_url_no_video_id"):
                self.ext.resolve_url("https://xhslink.com/abc123")
        finally:
            mod._follow_redirect = original_follow

    def test_url_with_whitespace(self):
        """URL 前后有空格 → 正常解析。"""
        result = self.ext.resolve_url("  https://www.xiaohongshu.com/explore/xyz789  ")
        assert result["video_id"] == "xyz789"


class TestDownload:
    """download 双层策略测试。"""

    def setup_method(self):
        self.ext = XiaohongshuExtractor({})

    def test_ytdlp_success(self, monkeypatch, tmp_path):
        """yt-dlp 成功 → downloader_used='yt-dlp'。"""
        import src.extractors.xiaohongshu_extractor as mod

        class FakeYdl:
            def __init__(self, opts):
                self.opts = opts

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def extract_info(self, url, download=True):
                (tmp_path / "abc123.mp4").write_bytes(b"fake-video")
                (tmp_path / "abc123.zh.vtt").write_text(
                    "WEBVTT\n00:00:01 --> 00:00:02\nTest"
                )
                return {
                    "id": "abc123",
                    "subtitles": {"zh": [{"url": "http://x.vtt"}]},
                    "automatic_captions": {"zh": [{"url": "http://x.vtt"}]},
                    "title": "Test Xiaohongshu video",
                    "duration": 60,
                    "uploader": "TestUser",
                    "uploader_url": "https://www.xiaohongshu.com/user/profile/123",
                    "thumbnail": "http://thumb.jpg",
                }

        monkeypatch.setattr(
            "src.extractors.xiaohongshu_extractor.yt_dlp.YoutubeDL",
            lambda opts: FakeYdl(opts),
        )
        result = self.ext.download(
            video_id="abc123",
            canonical_url="https://www.xiaohongshu.com/explore/abc123",
            out_dir=tmp_path,
        )
        assert result["video_path"].exists()
        assert result["subtitle_path"].exists()
        assert result["downloader_used"] == "yt-dlp"
        assert result["subtitle_source"] == "douyin_native"

    def test_ytdlp_fails_fallback_to_requests(self, monkeypatch, tmp_path):
        """yt-dlp 失败 → fallback requests → downloader_used='requests'。"""
        import src.extractors.xiaohongshu_extractor as mod

        class FakeYdlFail:
            def __init__(self, opts):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def extract_info(self, url, download=True):
                raise Exception("yt-dlp not supported for xiaohongshu")

        monkeypatch.setattr(
            "src.extractors.xiaohongshu_extractor.yt_dlp.YoutubeDL",
            lambda opts: FakeYdlFail(opts),
        )

        def fake_requests_download(url, out_dir, video_id):
            (out_dir / f"{video_id}.mp4").write_bytes(b"fake-video")
            return {
                "video_path": out_dir / f"{video_id}.mp4",
                "subtitle_path": None,
            }

        monkeypatch.setattr(
            "src.extractors.xiaohongshu_extractor._download_via_requests",
            fake_requests_download,
        )
        result = self.ext.download(
            video_id="abc123",
            canonical_url="https://www.xiaohongshu.com/explore/abc123",
            out_dir=tmp_path,
        )
        assert result["video_path"].exists()
        assert result["downloader_used"] == "requests"
        assert result["subtitle_source"] is None

    def test_both_fail_raises(self, monkeypatch, tmp_path):
        """yt-dlp + requests 都失败 → 抛异常。"""
        import src.extractors.xiaohongshu_extractor as mod

        class FakeYdlFail:
            def __init__(self, opts):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def extract_info(self, url, download=True):
                raise Exception("yt-dlp failed")

        def fake_requests_fail(url, out_dir, video_id):
            raise Exception("requests fallback failed")

        monkeypatch.setattr(
            "src.extractors.xiaohongshu_extractor.yt_dlp.YoutubeDL",
            lambda opts: FakeYdlFail(opts),
        )
        monkeypatch.setattr(
            "src.extractors.xiaohongshu_extractor._download_via_requests",
            fake_requests_fail,
        )
        with pytest.raises(Exception, match="requests fallback failed"):
            self.ext.download(
                video_id="abc123",
                canonical_url="https://www.xiaohongshu.com/explore/abc123",
                out_dir=tmp_path,
            )


class TestExtractMetadata:
    """extract_metadata 测试。"""

    def test_extract_metadata_from_info_dict(self):
        ext = XiaohongshuExtractor({})
        info = {
            "title": "Test Note",
            "uploader": "Author",
            "uploader_url": "https://www.xiaohongshu.com/user/profile/uid123",
            "duration": 120,
            "upload_date": "20260615",
            "thumbnail": "http://thumb.jpg",
        }
        meta = ext.extract_metadata(info)
        assert meta["title"] == "Test Note"
        assert meta["uploader"] == "Author"
        assert meta["duration_seconds"] == 120


class TestClassifySubtitle:
    """classify_subtitle 测试。"""

    def test_classify_subtitle_with_subs(self):
        ext = XiaohongshuExtractor({})
        info = {
            "subtitles": {"zh": [{"url": "http://x.vtt"}]},
            "automatic_captions": {},
        }
        assert ext.classify_subtitle(info) == "creator_uploaded"

    def test_classify_subtitle_auto(self):
        ext = XiaohongshuExtractor({})
        info = {
            "subtitles": {},
            "automatic_captions": {"zh": [{"url": "http://x.vtt"}]},
        }
        assert ext.classify_subtitle(info) == "auto_generated"

    def test_classify_subtitle_none(self):
        """无字幕 → ASR 路径（M2 复用），返回 'auto_generated' 或 None。"""
        from src.extractors.downloader import NoSubtitleError

        ext = XiaohongshuExtractor({})
        info = {"subtitles": {}, "automatic_captions": {}}
        with pytest.raises(NoSubtitleError):
            ext.classify_subtitle(info)
