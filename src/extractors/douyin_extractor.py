"""抖音 extractor — PlatformExtractor 参考实现 (M5 Task 1)。

代理现有 douyin_resolver / downloader / metadata 函数。
"""
from pathlib import Path

from src.extractors.platform import PlatformExtractor, register_extractor
from src.extractors.douyin_resolver import resolve_url as _resolve_url
from src.extractors.downloader import download_video as _download_video
from src.extractors.metadata import extract_metadata as _extract_metadata
from src.extractors.downloader import classify_subtitle_source as _classify_subtitle


class DouyinExtractor(PlatformExtractor):
    """抖音平台 extractor，继承 PlatformExtractor ABC。"""

    platform = "douyin"

    def __init__(self, config: dict):
        self.config = config

    def resolve_url(self, raw_url: str) -> dict:
        result = _resolve_url(raw_url)
        result["platform"] = self.platform
        return result

    def download(
        self, video_id: str, canonical_url: str, out_dir: Path, **kwargs
    ) -> dict:
        cookies_path = (
            self.config.get("downloader", {}).get("cookies_path") or None
        )
        return _download_video(
            video_id=video_id,
            canonical_url=canonical_url,
            out_dir=out_dir,
            cookies_path=cookies_path,
        )

    def extract_metadata(self, info_dict: dict) -> dict:
        return _extract_metadata(info_dict)

    def classify_subtitle(self, info_dict: dict) -> str:
        return _classify_subtitle(info_dict)


register_extractor("douyin", DouyinExtractor)
