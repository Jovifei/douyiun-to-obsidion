"""extractors 包对外 API。

Spec ref: specs/douyin-extraction/spec.md。
"""
from .douyin_resolver import resolve_url, ResolverError
from .downloader import (
    download_video,
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

__all__ = [
    "resolve_url", "ResolverError",
    "download_video", "classify_subtitle_source", "NoSubtitleError",
    "extract_metadata",
    "extract_audio", "AudioExtractionError",
    "download_with_douk", "DoukNotConfiguredError", "DoukDownloadError",
]
