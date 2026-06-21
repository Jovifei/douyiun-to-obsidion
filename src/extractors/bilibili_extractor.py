"""Bilibili extractor — PlatformExtractor 实现 (M5 Task 2)。

复用 yt-dlp 下载 + douyin_resolver 的 302 跟随逻辑。
Spec ref: openspec/changes/m5-multichannel-batch/specs/bilibili-extractor/spec.md
"""
import re
from pathlib import Path
from urllib.parse import urlparse

from src.extractors.platform import PlatformExtractor, register_extractor
from src.extractors.douyin_resolver import ResolverError, _follow_redirect
from src.extractors.downloader import download_video as _download_video
from src.extractors.downloader import classify_subtitle_source as _classify_subtitle

_FULL_URL_PATTERN = re.compile(r"https?://www\.bilibili\.com/video/(BV[A-Za-z0-9]+)")
_SHORT_URL_PATTERN = re.compile(r"https?://b23\.tv/[A-Za-z0-9]+")
_VIDEO_ID_FROM_CANONICAL = re.compile(r"/video/(BV[A-Za-z0-9]+)")


def _extract_video_id(canonical: str) -> str | None:
    m = _VIDEO_ID_FROM_CANONICAL.search(canonical)
    return m.group(1) if m else None


class BilibiliExtractor(PlatformExtractor):
    """Bilibili 平台 extractor，继承 PlatformExtractor ABC。"""

    platform = "bilibili"

    def __init__(self, config: dict):
        self.config = config

    def resolve_url(self, raw_url: str) -> dict:
        raw = raw_url.strip()

        # 完整链: https://www.bilibili.com/video/BVxxx
        m = _FULL_URL_PATTERN.match(raw)
        if m:
            return {
                "video_id": m.group(1),
                "canonical_url": raw,
                "platform": self.platform,
            }

        # 短链: https://b23.tv/xxx
        if _SHORT_URL_PATTERN.match(raw):
            canonical = _follow_redirect(raw)
            vid = _extract_video_id(canonical)
            if not vid:
                raise ResolverError(f"bilibili_short_url_no_video_id: {canonical}")
            return {
                "video_id": vid,
                "canonical_url": canonical,
                "platform": self.platform,
            }

        # 非 Bilibili URL
        parsed = urlparse(raw)
        if "bilibili.com" not in parsed.netloc and "b23.tv" not in parsed.netloc:
            raise ResolverError("not_bilibili_url")

        raise ResolverError(f"unrecognized_bilibili_url: {raw}")

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
        from src.extractors.metadata import extract_metadata as _extract_metadata

        return _extract_metadata(info_dict)

    def classify_subtitle(self, info_dict: dict) -> str:
        return _classify_subtitle(info_dict)


register_extractor("bilibili", BilibiliExtractor)
