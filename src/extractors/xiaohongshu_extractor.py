"""小红书 extractor — PlatformExtractor 实现 (M5 Task 3)。

双层策略：yt-dlp 优先，requests 兜底。
Spec ref: openspec/changes/m5-multichannel-batch/specs/xiaohongshu-extractor/spec.md
"""
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
import yt_dlp

from src.extractors.platform import PlatformExtractor, register_extractor
from src.extractors.douyin_resolver import ResolverError, _follow_redirect
from src.extractors.downloader import (
    classify_subtitle_source,
    NoSubtitleError,
)
from src.extractors.metadata import extract_metadata as _extract_metadata

# URL patterns
_FULL_URL_PATTERN = re.compile(
    r"https?://www\.xiaohongshu\.com/explore/([A-Za-z0-9]+)"
)
_SHORT_URL_PATTERN = re.compile(r"https?://xhslink\.com/[A-Za-z0-9]+")
_VIDEO_ID_FROM_CANONICAL = re.compile(r"/explore/([A-Za-z0-9]+)")


def _extract_video_id(canonical: str) -> Optional[str]:
    m = _VIDEO_ID_FROM_CANONICAL.search(canonical)
    return m.group(1) if m else None


def _download_via_requests(
    url: str, out_dir: Path, video_id: str
) -> dict:
    """Fallback: 用 httpx 从小红书 web 页面抓取视频内容。

    小红书反爬强，此方法尽力而为。
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.xiaohongshu.com/",
    }

    with httpx.Client(follow_redirects=True, timeout=30.0, headers=headers) as client:
        resp = client.get(url)
        resp.raise_for_status()
        html = resp.text

    # 尝试从页面提取视频 URL（小红书视频通常在 SSR 数据中）
    import json

    video_url = None
    # 尝试匹配 __INITIAL_STATE__ 中的视频 URL
    state_match = re.search(
        r"window\.__INITIAL_STATE__\s*=\s*({.+?})\s*</script>",
        html,
        re.DOTALL,
    )
    if state_match:
        try:
            # 小红书 SSR 数据中可能有未转义的 undefined，替换掉
            raw = state_match.group(1).replace("undefined", "null")
            state = json.loads(raw)
            # 从 note 数据中提取视频 URL
            note_data = state.get("note", {}).get("noteDetailMap", {})
            for note_id, note_info in note_data.items():
                note = note_info.get("note", {})
                video = note.get("video", {})
                if video:
                    video_url = video.get("url") or video.get("consumer", {}).get(
                        "originVideoKey"
                    )
                    if video_url and not video_url.startswith("http"):
                        video_url = f"https://sns-video-bd.xhscdn.com/{video_url}"
                    break
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    if not video_url:
        raise RuntimeError(
            f"requests fallback: 无法从页面提取视频 URL ({url})"
        )

    # 下载视频文件
    video_path = out_dir / f"{video_id}.mp4"
    with httpx.Client(timeout=120.0, headers=headers) as client:
        with client.stream("GET", video_url) as resp:
            resp.raise_for_status()
            with open(video_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)

    return {
        "video_path": video_path,
        "subtitle_path": None,
    }


class XiaohongshuExtractor(PlatformExtractor):
    """小红书平台 extractor，继承 PlatformExtractor ABC。

    双层策略：yt-dlp 优先，requests 兜底。
    """

    platform = "xiaohongshu"

    def __init__(self, config: dict):
        self.config = config

    def resolve_url(self, raw_url: str) -> dict:
        """解析小红书 URL，返回 {video_id, canonical_url, platform}。

        Raises:
            ResolverError: 非小红书 URL 或无法提取 video_id。
        """
        raw = raw_url.strip()

        # 完整链: https://www.xiaohongshu.com/explore/xxx
        m = _FULL_URL_PATTERN.match(raw)
        if m:
            return {
                "video_id": m.group(1),
                "canonical_url": raw,
                "platform": self.platform,
            }

        # 短链: https://xhslink.com/xxx
        if _SHORT_URL_PATTERN.match(raw):
            canonical = _follow_redirect(raw)
            vid = _extract_video_id(canonical)
            if not vid:
                raise ResolverError(f"short_url_no_video_id: {canonical}")
            return {
                "video_id": vid,
                "canonical_url": canonical,
                "platform": self.platform,
            }

        # 非小红书 URL
        parsed = urlparse(raw)
        if "xiaohongshu.com" not in parsed.netloc and "xhslink.com" not in parsed.netloc:
            raise ResolverError("not_xiaohongshu_url")

        raise ResolverError(f"unrecognized_xiaohongshu_url: {raw}")

    def download(
        self, video_id: str, canonical_url: str, out_dir: Path, **kwargs
    ) -> dict:
        """下载视频 + 字幕，yt-dlp 优先，失败则 requests 兜底。

        Returns: {video_path, subtitle_path, subtitle_source, downloader_used, ...}
        """
        cookies_path = (
            self.config.get("downloader", {}).get("cookies_path") or None
        )

        # 策略 1: yt-dlp
        try:
            return self._download_ytdlp(
                video_id, canonical_url, out_dir, cookies_path
            )
        except Exception:
            pass

        # 策略 2: requests 兜底
        fallback_result = _download_via_requests(canonical_url, out_dir, video_id)
        return {
            "video_path": fallback_result["video_path"],
            "subtitle_path": None,
            "subtitle_source": None,
            "downloader_used": "requests",
            "info_dict": None,
            "title": None,
            "duration": None,
            "uploader": None,
            "uploader_url": None,
            "thumbnail": None,
        }

    def _download_ytdlp(
        self,
        video_id: str,
        canonical_url: str,
        out_dir: Path,
        cookies_path: Optional[str],
    ) -> dict:
        """yt-dlp 下载路径。"""
        out_dir.mkdir(parents=True, exist_ok=True)
        outtmpl = str(out_dir / f"{video_id}.%(ext)s")

        ydl_opts = {
            "outtmpl": outtmpl,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["zh"],
            "subtitlesformat": "vtt/srt",
            "quiet": True,
            "no_warnings": True,
            "retries": 3,
        }
        if cookies_path:
            ydl_opts["cookiefile"] = cookies_path

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(canonical_url, download=True)

        subtitle_source = classify_subtitle_source(info)

        video_path = out_dir / f"{video_id}.mp4"
        if not video_path.exists():
            candidates = list(out_dir.glob(f"{video_id}.*"))
            video_candidates = [
                p for p in candidates if p.suffix in (".mp4", ".webm")
            ]
            if not video_candidates:
                raise FileNotFoundError(f"video file not found for {video_id}")
            video_path = video_candidates[0]

        subtitle_path = None
        for ext in (".zh.vtt", ".zh.srt"):
            p = out_dir / f"{video_id}{ext}"
            if p.exists():
                subtitle_path = p
                break

        return {
            "video_path": video_path,
            "subtitle_path": subtitle_path,
            "subtitle_source": subtitle_source,
            "downloader_used": "yt-dlp",
            "info_dict": info,
            "title": info.get("title"),
            "duration": info.get("duration"),
            "uploader": info.get("uploader"),
            "uploader_url": info.get("uploader_url"),
            "thumbnail": info.get("thumbnail"),
        }

    def extract_metadata(self, info_dict: dict) -> dict:
        """从 info_dict 提取元数据。"""
        return _extract_metadata(info_dict)

    def classify_subtitle(self, info_dict: dict) -> str:
        """分类字幕来源。"""
        return classify_subtitle_source(info_dict)


register_extractor("xiaohongshu", XiaohongshuExtractor)
