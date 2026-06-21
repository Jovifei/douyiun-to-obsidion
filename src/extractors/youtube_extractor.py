"""YouTube extractor — PlatformExtractor 实现 (M5 Task 4)。

复用 yt-dlp 下载 + douyin_resolver 的 302 跟随逻辑。
Spec ref: openspec/changes/m5-multichannel-batch/specs/youtube-extractor/spec.md
"""
import re
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp

from src.extractors.platform import PlatformExtractor, register_extractor
from src.extractors.douyin_resolver import ResolverError, _follow_redirect
from src.extractors.downloader import classify_subtitle_source as _classify_subtitle
from src.extractors.metadata import extract_metadata as _extract_metadata

# URL patterns
_WATCH_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?youtube\.com/watch\?"
)
_SHORT_URL_PATTERN = re.compile(r"https?://youtu\.be/([A-Za-z0-9_-]+)")
_VIDEO_ID_PARAM = re.compile(r"[?&]v=([A-Za-z0-9_-]+)")


def _extract_video_id(url: str) -> str | None:
    """从 YouTube URL 提取 video_id（v= 参数后的值）。"""
    m = _VIDEO_ID_PARAM.search(url)
    return m.group(1) if m else None


class YouTubeExtractor(PlatformExtractor):
    """YouTube 平台 extractor，继承 PlatformExtractor ABC。"""

    platform = "youtube"

    def __init__(self, config: dict):
        self.config = config

    def resolve_url(self, raw_url: str) -> dict:
        """解析 YouTube URL，返回 {video_id, canonical_url, platform}。

        Raises:
            ResolverError: 非 YouTube URL 或无法提取 video_id。
        """
        raw = raw_url.strip()

        # 完整链: https://www.youtube.com/watch?v=xxx
        if _WATCH_URL_PATTERN.match(raw):
            vid = _extract_video_id(raw)
            if vid:
                return {
                    "video_id": vid,
                    "canonical_url": raw,
                    "platform": self.platform,
                }

        # 短链: https://youtu.be/xxx
        sm = _SHORT_URL_PATTERN.match(raw)
        if sm:
            canonical = _follow_redirect(raw)
            vid = _extract_video_id(canonical)
            if not vid:
                raise ResolverError(f"short_url_no_video_id: {canonical}")
            return {
                "video_id": vid,
                "canonical_url": canonical,
                "platform": self.platform,
            }

        # 非 YouTube URL
        parsed = urlparse(raw)
        if "youtube.com" not in parsed.netloc and "youtu.be" not in parsed.netloc:
            raise ResolverError("not_youtube_url")

        # YouTube 域名但路径不匹配
        raise ResolverError(f"unrecognized_youtube_url: {raw}")

    def download(
        self, video_id: str, canonical_url: str, out_dir: Path, **kwargs
    ) -> dict:
        """下载 YouTube 视频 + 字幕，返回标准结果 dict。

        subtitleslangs 优先 zh, zh-Hans, zh-CN。
        """
        cookies_path = (
            self.config.get("downloader", {}).get("cookies_path") or None
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        outtmpl = str(out_dir / f"{video_id}.%(ext)s")

        ydl_opts = {
            "outtmpl": outtmpl,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["zh", "zh-Hans", "zh-CN"],
            "subtitlesformat": "vtt/srt",
            "quiet": True,
            "no_warnings": True,
            "retries": 3,
        }
        if cookies_path:
            ydl_opts["cookiefile"] = cookies_path

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(canonical_url, download=True)

        subtitle_source = _classify_subtitle(info)

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
        for ext in (".zh.vtt", ".zh.srt", ".zh-Hans.vtt", ".zh-Hans.srt",
                     ".zh-CN.vtt", ".zh-CN.srt"):
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
        """分类字幕来源，复用 classify_subtitle_source。"""
        return _classify_subtitle(info_dict)


register_extractor("youtube", YouTubeExtractor)
