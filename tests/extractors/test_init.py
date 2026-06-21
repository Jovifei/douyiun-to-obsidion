"""Test extractors package __init__ exports.

Spec ref: specs/douyin-extraction/spec.md
"""
from src.extractors import __all__ as extractors_all


def test_import_resolve_url():
    """resolve_url 可从 src.extractors 导入。"""
    from src.extractors import resolve_url
    assert callable(resolve_url)


def test_import_download_video():
    """download_video 可从 src.extractors 导入。"""
    from src.extractors import download_video
    assert callable(download_video)


def test_all_exports():
    """__all__ 包含所有公共 API 符号。"""
    expected = {
        "resolve_url", "ResolverError",
        "download_video", "download_video_only", "classify_subtitle_source", "NoSubtitleError",
        "extract_metadata",
        "extract_audio", "AudioExtractionError",
        "download_with_douk", "DoukNotConfiguredError", "DoukDownloadError",
        # M5
        "PlatformExtractor", "get_extractor",
        "DouyinExtractor", "BilibiliExtractor", "XiaohongshuExtractor", "YouTubeExtractor",
    }
    assert set(extractors_all) == expected
