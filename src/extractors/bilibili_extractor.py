"""Bilibili extractor 占位 — Task 2 实现。"""
from pathlib import Path

from src.extractors.platform import PlatformExtractor, register_extractor


class BilibiliExtractor(PlatformExtractor):
    """Bilibili 平台 extractor 占位类。"""

    platform = "bilibili"

    def __init__(self, config: dict):
        self.config = config

    def resolve_url(self, raw_url: str) -> dict:
        raise NotImplementedError("bilibili resolve_url: Task 2")

    def download(
        self, video_id: str, canonical_url: str, out_dir: Path, **kwargs
    ) -> dict:
        raise NotImplementedError("bilibili download: Task 2")

    def extract_metadata(self, info_dict: dict) -> dict:
        raise NotImplementedError("bilibili extract_metadata: Task 2")

    def classify_subtitle(self, info_dict: dict) -> str:
        raise NotImplementedError("bilibili classify_subtitle: Task 2")


register_extractor("bilibili", BilibiliExtractor)
