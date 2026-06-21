"""PlatformExtractor ABC + get_extractor 工厂函数 (M5 Task 1)。

D-M5-1: 统一接口，抖音作为参考实现。
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class PlatformExtractor(ABC):
    """平台 extractor 抽象基类，定义统一接口。"""

    platform: str

    @abstractmethod
    def resolve_url(self, raw_url: str) -> dict:
        """解析 URL，返回 {video_id, canonical_url, platform, ...}。"""

    @abstractmethod
    def download(
        self, video_id: str, canonical_url: str, out_dir: Path, **kwargs
    ) -> dict:
        """下载视频 + 字幕，返回下载结果 dict。"""

    @abstractmethod
    def extract_metadata(self, info_dict: dict) -> dict:
        """从 info_dict 提取元数据。"""

    @abstractmethod
    def classify_subtitle(self, info_dict: dict) -> str:
        """分类字幕来源。"""


# ── 工厂注册表 ──────────────────────────────────────────────────
_REGISTRY: dict[str, type[PlatformExtractor]] = {}


def register_extractor(name: str, cls: type[PlatformExtractor]) -> None:
    """注册平台 extractor 类。"""
    _REGISTRY[name.lower()] = cls


def get_extractor(name: str, config: dict) -> PlatformExtractor:
    """按平台名返回对应 extractor 实例。

    Raises:
        ValueError: 未知平台名。
    """
    key = name.lower()
    if key not in _REGISTRY:
        raise ValueError(f"unknown platform: {name}")
    return _REGISTRY[key](config)
