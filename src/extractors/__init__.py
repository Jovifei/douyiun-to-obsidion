"""extractors 包对外 API。

Spec ref: specs/douyin-extraction/spec.md。
M5: PlatformExtractor ABC + get_extractor 工厂。
"""
from .douyin_resolver import resolve_url, ResolverError
from .downloader import (
    download_video,
    download_video_only,
    classify_subtitle_source,
    NoSubtitleError,
)
from .metadata import extract_metadata
from .audio_extractor import extract_audio, AudioExtractionError
from .douk_fallback import (
    download_with_douk,
    DoukNotConfiguredError,
    DoukDownloadError,
)

# M5: 导入 extractor 模块触发 register_extractor 注册
from .platform import PlatformExtractor, get_extractor  # noqa: F401
from .douyin_extractor import DouyinExtractor  # noqa: F401
from .bilibili_extractor import BilibiliExtractor  # noqa: F401
from .xiaohongshu_extractor import XiaohongshuExtractor  # noqa: F401
from .youtube_extractor import YouTubeExtractor  # noqa: F401

__all__ = [
    "resolve_url", "ResolverError",
    "download_video", "download_video_only", "classify_subtitle_source", "NoSubtitleError",
    "extract_metadata",
    "extract_audio", "AudioExtractionError",
    "download_with_douk", "DoukNotConfiguredError", "DoukDownloadError",
    # M5
    "PlatformExtractor", "get_extractor",
    "DouyinExtractor", "BilibiliExtractor", "XiaohongshuExtractor", "YouTubeExtractor",
]
