"""yt-dlp Python API wrapper: download video + subtitles, classify subtitle source (B2 revision).

Spec ref: specs/douyin-extraction/spec.md
- Requirement: yt-dlp main download path
- Requirement: subtitle source classification
"""
from pathlib import Path
from typing import Optional

import yt_dlp


class NoSubtitleError(Exception):
    """M1 boundary: video has no subtitles."""


def classify_subtitle_source(info_dict: dict) -> str:
    """B2 revision: use info_dict['subtitles'] vs ['automatic_captions'] to classify.

    Returns: 'douyin_native' | 'creator_uploaded' | 'auto_generated'
    Raises: NoSubtitleError when neither has zh subtitles.
    """
    subs = info_dict.get("subtitles", {}) or {}
    auto = info_dict.get("automatic_captions", {}) or {}
    has_sub_zh = "zh" in subs
    has_auto_zh = "zh" in auto

    if has_sub_zh and has_auto_zh:
        return "douyin_native"
    if has_sub_zh:
        return "creator_uploaded"
    if has_auto_zh:
        return "auto_generated"
    raise NoSubtitleError("no_subtitle_in_m1")


def download_video(
    video_id: str,
    canonical_url: str,
    out_dir: Path,
    cookies_path: Optional[str] = None,
) -> dict:
    """Download video + subtitles to out_dir, return result dict.

    Raises: NoSubtitleError, yt_dlp.utils.DownloadError.
    """
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
        video_candidates = [p for p in candidates if p.suffix in (".mp4", ".webm")]
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
        "info_dict": info,
        "title": info.get("title"),
        "duration": info.get("duration"),
        "uploader": info.get("uploader"),
        "uploader_url": info.get("uploader_url"),
        "thumbnail": info.get("thumbnail"),
    }
