"""Test PlatformExtractor ABC + get_extractor factory (M5 Task 1).

Spec ref: openspec/changes/m1-douyin-archive-mvp/
D-M5-1: 统一接口，抖音作为参考实现
"""
import pytest

from src.extractors.platform import PlatformExtractor, get_extractor


class TestPlatformExtractorABC:
    """PlatformExtractor 是抽象基类，定义统一平台接口。"""

    def test_is_abstract_class(self):
        """PlatformExtractor 不能直接实例化。"""
        with pytest.raises(TypeError):
            PlatformExtractor()

    def test_has_resolve_url_method(self):
        """ABC 定义 resolve_url 抽象方法。"""
        assert hasattr(PlatformExtractor, "resolve_url")
        # 抽象方法在类上存在
        assert callable(getattr(PlatformExtractor, "resolve_url", None))

    def test_has_download_method(self):
        """ABC 定义 download 抽象方法。"""
        assert hasattr(PlatformExtractor, "download")

    def test_has_extract_metadata_method(self):
        """ABC 定义 extract_metadata 抽象方法。"""
        assert hasattr(PlatformExtractor, "extract_metadata")

    def test_has_classify_subtitle_method(self):
        """ABC 定义 classify_subtitle 抽象方法。"""
        assert hasattr(PlatformExtractor, "classify_subtitle")


class TestGetExtractorFactory:
    """get_extractor 工厂函数按平台名返回对应 extractor。"""

    def test_douyin_returns_douyin_extractor(self):
        """get_extractor('douyin', config) 返回 DouyinExtractor 实例。"""
        from src.extractors.douyin_extractor import DouyinExtractor

        config = {"downloader": {"cookies_path": ""}}
        extractor = get_extractor("douyin", config)
        assert isinstance(extractor, DouyinExtractor)
        assert isinstance(extractor, PlatformExtractor)

    def test_bilibili_returns_bilibili_extractor(self):
        """get_extractor('bilibili', config) 返回 BilibiliExtractor 占位。"""
        from src.extractors.bilibili_extractor import BilibiliExtractor

        config = {}
        extractor = get_extractor("bilibili", config)
        assert isinstance(extractor, BilibiliExtractor)
        assert isinstance(extractor, PlatformExtractor)

    def test_unknown_platform_raises_valueerror(self):
        """get_extractor('unknown', config) 抛 ValueError。"""
        config = {}
        with pytest.raises(ValueError, match="unknown"):
            get_extractor("unknown", config)

    def test_case_insensitive(self):
        """平台名大小写不敏感。"""
        config = {"downloader": {"cookies_path": ""}}
        extractor = get_extractor("Douyin", config)
        assert isinstance(extractor, PlatformExtractor)


class TestDouyinExtractorInterface:
    """DouyinExtractor 实现 PlatformExtractor 接口。"""

    @pytest.fixture
    def extractor(self):
        from src.extractors.douyin_extractor import DouyinExtractor

        config = {"downloader": {"cookies_path": ""}}
        return DouyinExtractor(config)

    def test_platform_field(self, extractor):
        """DouyinExtractor.platform == 'douyin'。"""
        assert extractor.platform == "douyin"

    def test_resolve_url_returns_dict_with_required_fields(self, extractor, monkeypatch):
        """resolve_url 返回 dict 含 video_id, canonical_url, platform。"""
        monkeypatch.setattr(
            "src.extractors.douyin_resolver.resolve_url",
            lambda url: {
                "video_id": "123456",
                "canonical_url": "https://www.douyin.com/video/123456",
                "source_url_type": "full",
            },
        )
        result = extractor.resolve_url("https://www.douyin.com/video/123456")
        assert "video_id" in result
        assert "canonical_url" in result
        assert "platform" in result
        assert result["platform"] == "douyin"

    def test_download_delegates_to_downloader(self, extractor, monkeypatch):
        """download 委托给 downloader.download_video。"""
        called_with = {}

        def fake_download(video_id, canonical_url, out_dir, cookies_path=None):
            called_with["video_id"] = video_id
            return {"video_path": "/tmp/test.mp4", "subtitle_source": "douyin_native"}

        monkeypatch.setattr(
            "src.extractors.douyin_extractor._download_video", fake_download
        )
        from pathlib import Path

        result = extractor.download("123456", "https://www.douyin.com/video/123456", Path("/tmp"))
        assert called_with["video_id"] == "123456"
        assert result["subtitle_source"] == "douyin_native"

    def test_extract_metadata_delegates(self, extractor, monkeypatch):
        """extract_metadata 委托给 metadata.extract_metadata。"""
        monkeypatch.setattr(
            "src.extractors.metadata.extract_metadata",
            lambda info: {"title": "test", "uploader": "user"},
        )
        result = extractor.extract_metadata({"title": "test"})
        assert result["title"] == "test"

    def test_classify_subtitle_delegates(self, extractor, monkeypatch):
        """classify_subtitle 委托给 downloader.classify_subtitle_source。"""
        monkeypatch.setattr(
            "src.extractors.douyin_extractor._classify_subtitle",
            lambda info: "douyin_native",
        )
        result = extractor.classify_subtitle({"subtitles": {"zh": []}})
        assert result == "douyin_native"
