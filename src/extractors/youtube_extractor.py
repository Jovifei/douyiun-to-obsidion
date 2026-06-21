"""YouTube extractor 占位 — Task 4 实现。"""
from pathlib import Path

from src.extractors.platform import PlatformExtractor, register_extractor


class YouTubeExtractor(PlatformExtractor):
    """YouTube 平台 extractor 占位类。"""

    platform = "youtube"

    def __init__(self, config: dict):
        self.config = config

    def resolve_url(self, raw_url: str) -> dict:
        raise NotImplementedError("youtube resolve_url: Task 4")

    def download(
        self, video_id: str, canonical_url: str, out_dir: Path, **kwargs
    ) -> dict:
        raise NotImplementedError("youtube download: Task 4")

    def extract_metadata(self, info_dict: dict) -> dict:
        raise NotImplementedError("youtube extract_metadata: Task 4")

    def classify_subtitle(self, info_dict: dict) -> str:
        raise NotImplementedError("youtube classify_subtitle: Task 4")


register_extractor("youtube", YouTubeExtractor)
