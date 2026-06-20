"""抖音 URL 解析器：4 种形态 → video_id + canonical_url。

参考思路：git_ref/obsidian-content-capture-backend/script/douyin_resolver.py
（不复制代码，仅借鉴 302 跟随 + 正则思路，D-3 v2）。
"""
import re
from typing import Optional
from urllib.parse import urlparse

import httpx


class ResolverError(Exception):
    """URL 无法解析为抖音视频。"""


_SHORT_URL_PATTERN = re.compile(r"https?://v\.douyin\.com/[A-Za-z0-9]+/?")
_FULL_URL_PATTERN = re.compile(r"https?://www\.douyin\.com/video/(\d+)")
_IES_URL_PATTERN = re.compile(
    r"https?://www\.iesdouyin\.com/share/video/(\d+)"
)
_URL_EXTRACT_FROM_TEXT = re.compile(r"https?://[^\s，）)】]+")
_VIDEO_ID_FROM_CANONICAL = re.compile(r"/video/(\d+)")


def _follow_redirect(url: str) -> str:
    """跟随短链 302，返回最终 canonical URL。"""
    try:
        with httpx.Client(
            follow_redirects=True, timeout=10.0, max_redirects=5
        ) as client:
            resp = client.get(url)
            return str(resp.url)
    except httpx.RequestError as e:
        raise ResolverError(f"redirect_failed: {e}") from e


def _extract_video_id(canonical: str) -> Optional[str]:
    m = _VIDEO_ID_FROM_CANONICAL.search(canonical)
    return m.group(1) if m else None


def resolve_url(raw: str) -> dict:
    """解析 4 种形态的抖音输入为 {video_id, canonical_url, source_url_type}。

    Raises:
        ResolverError: 非抖音 URL 或无 video_id 可提取。
    """
    raw = raw.strip()

    # 形态 4：分享文案 — 先抽出 URL
    extracted = _URL_EXTRACT_FROM_TEXT.search(raw)
    url = extracted.group(0) if extracted else raw

    # 形态 2：完整链
    m = _FULL_URL_PATTERN.match(url)
    if m:
        return {
            "video_id": m.group(1),
            "canonical_url": url,
            "source_url_type": "full",
        }

    # 形态 3：iesdouyin 旧链
    m = _IES_URL_PATTERN.match(url)
    if m:
        return {
            "video_id": m.group(1),
            "canonical_url": url,
            "source_url_type": "iesdouyin",
        }

    # 形态 1：短链 — 需 302 跟随
    if _SHORT_URL_PATTERN.match(url):
        canonical = _follow_redirect(url)
        vid = _extract_video_id(canonical)
        if not vid:
            raise ResolverError(f"short_url_no_video_id: {canonical}")
        return {
            "video_id": vid,
            "canonical_url": canonical,
            "source_url_type": "short",
        }

    # 非抖音 URL
    parsed = urlparse(url)
    if "douyin.com" not in parsed.netloc and "iesdouyin.com" not in parsed.netloc:
        raise ResolverError("not_douyin_url")

    raise ResolverError(f"unrecognized_douyin_url: {url}")
