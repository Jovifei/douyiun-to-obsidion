"""抖音视频元数据提取（B3 修订：uploader_id 从 uploader_url 正则抽 sec_uid）。

Spec ref: specs/douyin-extraction/spec.md Requirement: 视频元数据提取。
"""
import re
from datetime import datetime

_SEC_UID_PATTERN = re.compile(r"/user/([A-Za-z0-9_\-]+)")


def extract_uploader_id(uploader_url: str) -> str:
    """从 uploader_url 提取 sec_uid。失败返回空字符串，不抛错。"""
    if not uploader_url:
        return ""
    m = _SEC_UID_PATTERN.search(uploader_url)
    return m.group(1) if m else ""


def _format_upload_date(yyyymmdd: str) -> str:
    """yt-dlp upload_date='20260619' -> ISO 8601 '2026-06-19T00:00:00'。"""
    if not yyyymmdd or len(yyyymmdd) != 8:
        return ""
    try:
        dt = datetime.strptime(yyyymmdd, "%Y%m%d")
        return dt.strftime("%Y-%m-%dT00:00:00")
    except ValueError:
        return ""


def extract_metadata(info_dict: dict) -> dict:
    """从 yt-dlp info_dict 提取 frontmatter 所需元数据。"""
    return {
        "title": info_dict.get("title", ""),
        "uploader": info_dict.get("uploader", ""),
        "uploader_id": extract_uploader_id(info_dict.get("uploader_url", "")),
        "duration_seconds": int(info_dict.get("duration", 0) or 0),
        "uploaded_at": _format_upload_date(info_dict.get("upload_date", "")),
        "thumbnail": info_dict.get("thumbnail", ""),
    }
