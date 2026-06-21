"""Test YouTubeExtractor — PlatformExtractor 实现 (M5 Task 4)。

YouTube URL 解析 + yt-dlp 下载 + 多语言字幕选择。
"""
import pytest

from src.extractors.youtube_extractor import YouTubeExtractor
from src.extractors.platform import PlatformExtractor, get_extractor
from src.extractors.douyin_resolver import ResolverError


class TestYouTubeExtractorABC:
    """验证 YouTubeExtractor 实现 PlatformExtractor ABC。"""

    def test_inherits_platform_extractor(self):
        assert issubclass(YouTubeExtractor, PlatformExtractor)

    def test_platform_attribute(self):
        ext = YouTubeExtractor({})
        assert ext.platform == "youtube"

    def test_registered_in_get_extractor(self):
        ext = get_extractor("youtube", {})
        assert isinstance(ext, YouTubeExtractor)
        assert isinstance(ext, PlatformExtractor)


class TestResolveUrl:
    """resolve_url URL 解析测试。"""

    def setup_method(self):
        self.ext = YouTubeExtractor({})

    def test_watch_url_full(self):
        """完整 watch URL → video_id + canonical_url + platform。"""
        result = self.ext.resolve_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert result["video_id"] == "dQw4w9WgXcQ"
        assert result["canonical_url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert result["platform"] == "youtube"

    def test_watch_url_with_extra_params(self):
        """watch URL 带额外参数 → 正常解析。"""
        result = self.ext.resolve_url(
            "https://www.youtube.com/watch?v=abc123&t=30s&list=PLxxx"
        )
        assert result["video_id"] == "abc123"
        assert result["platform"] == "youtube"

    def test_short_url_youtu_be(self):
        """youtu.be 短链 → 跟随 302 → 解析 video_id。"""
        import src.extractors.youtube_extractor as mod

        original_follow = mod._follow_redirect

        def fake_follow(url):
            return "https://www.youtube.com/watch?v=xyz789"

        mod._follow_redirect = fake_follow
        try:
            result = self.ext.resolve_url("https://youtu.be/xyz789")
            assert result["video_id"] == "xyz789"
            assert result["canonical_url"] == "https://www.youtube.com/watch?v=xyz789"
            assert result["platform"] == "youtube"
        finally:
            mod._follow_redirect = original_follow

    def test_short_url_no_video_id(self):
        """短链跟随后无法提取 video_id → ResolverError。"""
        import src.extractors.youtube_extractor as mod

        original_follow = mod._follow_redirect

        def fake_follow(url):
            return "https://www.youtube.com/"

        mod._follow_redirect = fake_follow
        try:
            with pytest.raises(ResolverError, match="short_url_no_video_id"):
                self.ext.resolve_url("https://youtu.be/abc123")
        finally:
            mod._follow_redirect = original_follow

    def test_non_youtube_url_raises(self):
        """非 YouTube URL → ResolverError。"""
        with pytest.raises(ResolverError, match="not_youtube_url"):
            self.ext.resolve_url("https://www.bilibili.com/video/BVxxx")

    def test_douyin_url_raises(self):
        """抖音 URL → ResolverError。"""
        with pytest.raises(ResolverError, match="not_youtube_url"):
            self.ext.resolve_url("https://www.douyin.com/video/123456")

    def test_url_with_whitespace(self):
        """URL 前后有空格 → 正常解析。"""
        result = self.ext.resolve_url("  https://www.youtube.com/watch?v=abc123  ")
        assert result["video_id"] == "abc123"


class TestDownload:
    """download 委托 yt-dlp 下载 YouTube 视频。"""

    def test_download_delegates_to_yt_dlp(self, monkeypatch, tmp_path):
        """download 调用 yt-dlp 下载视频+字幕，返回标准结果 dict。"""
        called_with = {}

        class FakeYdl:
            def __init__(self, opts):
                self.opts = opts

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def extract_info(self, url, download=True):
                called_with["url"] = url
                called_with["opts"] = self.opts
                (tmp_path / "dQw4w9WgXcQ.mp4").write_bytes(b"fake-video")
                (tmp_path / "dQw4w9WgXcQ.zh.vtt").write_text(
                    "WEBVTT\n00:00:01 --> 00:00:02\nTest"
                )
                return {
                    "id": "dQw4w9WgXcQ",
                    "subtitles": {"zh": [{"url": "http://x.vtt"}]},
                    "automatic_captions": {"zh": [{"url": "http://x.vtt"}]},
                    "title": "Test YouTube video",
                    "duration": 200,
                    "uploader": "TestChannel",
                    "uploader_url": "https://www.youtube.com/@test",
                    "thumbnail": "http://thumb.jpg",
                }

        monkeypatch.setattr(
            "src.extractors.youtube_extractor.yt_dlp.YoutubeDL",
            lambda opts: FakeYdl(opts),
        )
        extractor = YouTubeExtractor({})
        result = extractor.download(
            "dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            tmp_path,
        )
        assert called_with["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert result["video_path"].exists()
        assert result["subtitle_source"] == "douyin_native"
        assert result["downloader_used"] == "yt-dlp"

    def test_download_configures_zh_subtitle_priority(self, monkeypatch, tmp_path):
        """download 配置 subtitleslangs 优先 zh + zh-Hans + zh-CN。"""
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
                (tmp_path / "X.mp4").write_bytes(b"fake-video")
                return {
                    "id": "X",
                    "subtitles": {},
                    "automatic_captions": {
                        "en": [{"url": "http://en.vtt"}],
                        "zh": [{"url": "http://zh.vtt"}],
                    },
                    "title": "Test",
                }

        monkeypatch.setattr(
            "src.extractors.youtube_extractor.yt_dlp.YoutubeDL",
            lambda opts: FakeYdl(opts),
        )
        extractor = YouTubeExtractor({})
        extractor.download("X", "https://www.youtube.com/watch?v=X", tmp_path)
        assert captured_opts is not None
        assert "zh" in captured_opts["subtitleslangs"]
        assert "zh-Hans" in captured_opts["subtitleslangs"]
        assert "zh-CN" in captured_opts["subtitleslangs"]

    def test_download_with_cookies(self, monkeypatch, tmp_path):
        """cookies_path 传递到 yt-dlp opts。"""
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
                (tmp_path / "X.mp4").write_bytes(b"fake-video")
                return {
                    "id": "X",
                    "subtitles": {"zh": [{"url": "http://x.vtt"}]},
                    "automatic_captions": {},
                    "title": "Test",
                }

        monkeypatch.setattr(
            "src.extractors.youtube_extractor.yt_dlp.YoutubeDL",
            lambda opts: FakeYdl(opts),
        )
        extractor = YouTubeExtractor({"downloader": {"cookies_path": "cookies.txt"}})
        extractor.download("X", "https://www.youtube.com/watch?v=X", tmp_path)
        assert captured_opts["cookiefile"] == "cookies.txt"


class TestClassifySubtitle:
    """classify_subtitle 复用 classify_subtitle_source。"""

    def test_creator_uploaded(self):
        """subtitles 有 zh → creator_uploaded。"""
        ext = YouTubeExtractor({})
        info = {
            "subtitles": {"zh": [{"url": "http://x.vtt"}]},
            "automatic_captions": {},
        }
        assert ext.classify_subtitle(info) == "creator_uploaded"

    def test_auto_generated(self):
        """automatic_captions 有 zh → auto_generated。"""
        ext = YouTubeExtractor({})
        info = {
            "subtitles": {},
            "automatic_captions": {"zh": [{"url": "http://x.vtt"}]},
        }
        assert ext.classify_subtitle(info) == "auto_generated"

    def test_no_subtitle_raises(self):
        """无字幕 → NoSubtitleError。"""
        from src.extractors.downloader import NoSubtitleError

        ext = YouTubeExtractor({})
        info = {"subtitles": {}, "automatic_captions": {}}
        with pytest.raises(NoSubtitleError):
            ext.classify_subtitle(info)


class TestMultiLanguageSubtitle:
    """多语言字幕选择：优先 zh，否则第一个可用。"""

    def test_download_selects_zh_over_other_langs(self, monkeypatch, tmp_path):
        """info_dict 有 en + zh 自动字幕 → 下载时 subtitleslangs 优先 zh。"""
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
                (tmp_path / "X.mp4").write_bytes(b"fake-video")
                return {
                    "id": "X",
                    "subtitles": {},
                    "automatic_captions": {
                        "en": [{"url": "http://en.vtt"}],
                        "zh": [{"url": "http://zh.vtt"}],
                    },
                    "title": "Test",
                }

        monkeypatch.setattr(
            "src.extractors.youtube_extractor.yt_dlp.YoutubeDL",
            lambda opts: FakeYdl(opts),
        )
        ext = YouTubeExtractor({})
        result = ext.download("X", "https://www.youtube.com/watch?v=X", tmp_path)
        # subtitleslangs 配置优先 zh
        assert captured_opts["subtitleslangs"][0] == "zh"
        assert result["video_path"].exists()
