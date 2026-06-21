"""小红书 extractor 占位 — Task 3 实现。"""
from pathlib import Path

from src.extractors.platform import PlatformExtractor, register_extractor


class XiaohongshuExtractor(PlatformExtractor):
    """小红书平台 extractor 占位类。"""

    platform = "xiaohongshu"

    def __init__(self, config: dict):
        self.config = config

    def resolve_url(self, raw_url: str) -> dict:
        raise NotImplementedError("xiaohongshu resolve_url: Task 3")

    def download(
        self, video_id: str, canonical_url: str, out_dir: Path, **kwargs
    ) -> dict:
        raise NotImplementedError("xiaohongshu download: Task 3")

    def extract_metadata(self, info_dict: dict) -> dict:
        raise NotImplementedError("xiaohongshu extract_metadata: Task 3")

    def classify_subtitle(self, info_dict: dict) -> str:
        raise NotImplementedError("xiaohongshu classify_subtitle: Task 3")


register_extractor("xiaohongshu", XiaohongshuExtractor)
