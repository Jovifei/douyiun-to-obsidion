"""DouK-Downloader subprocess 兜底（yt-dlp 失败时切换）。

Spec ref: specs/douyin-extraction/spec.md
Requirement: yt-dlp 失败兜底走 DouK-Downloader。
"""
import subprocess
from pathlib import Path


class DoukNotConfiguredError(Exception):
    """douk_path 未配置。"""


class DoukDownloadError(Exception):
    """DouK-Downloader subprocess 失败。"""


def download_with_douk(
    video_id: str,
    canonical_url: str,
    out_dir: Path,
    douk_path: str,
) -> dict:
    """调 DouK-Downloader 下载视频 + 字幕。

    Returns: {video_path, subtitle_path, downloader_used='douk'}
    Raises: DoukNotConfiguredError, DoukDownloadError。
    """
    if not douk_path:
        raise DoukNotConfiguredError("douk_path empty")

    out_dir.mkdir(parents=True, exist_ok=True)

    # DouK CLI 参数模板（如实际 DouK CLI 参数不同需调整）：
    #   douk --url <url> --output-dir <out_dir> --output-name <video_id>
    cmd = [
        douk_path,
        "--url", canonical_url,
        "--output-dir", str(out_dir),
        "--output-name", video_id,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=300)
    except FileNotFoundError:
        raise DoukDownloadError("douk_unavailable")

    if result.returncode != 0:
        raise DoukDownloadError(
            f"douk_failed: {result.stderr.decode('utf-8', errors='replace')}"
        )

    video_path = out_dir / f"{video_id}.mp4"
    if not video_path.exists():
        raise DoukDownloadError(f"douk did not produce {video_path}")

    subtitle_path = None
    for ext in (".zh.vtt", ".zh.srt"):
        p = out_dir / f"{video_id}{ext}"
        if p.exists():
            subtitle_path = p
            break

    return {
        "video_path": video_path,
        "subtitle_path": subtitle_path,
        "downloader_used": "douk",
    }
