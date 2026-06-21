"""批量 URL 提取 — 从飞书消息中提取所有支持平台的 URL。

Spec ref: openspec/changes/m5-multichannel-batch/specs/batch-url/spec.md
D-M5-2: 飞书消息含多条 URL 时全部入队，每条独立处理。
"""
import re


# 已识别平台的 URL 模式（域名匹配）
_SUPPORTED_PLATFORM_PATTERNS = [
    re.compile(r"https?://(?:www\.)?douyin\.com/"),
    re.compile(r"https?://v\.douyin\.com/"),
    re.compile(r"https?://(?:www\.)?iesdouyin\.com/"),
    re.compile(r"https?://(?:www\.)?bilibili\.com/"),
    re.compile(r"https?://b23\.tv/"),
    re.compile(r"https?://(?:www\.)?xiaohongshu\.com/"),
    re.compile(r"https?://xhslink\.com/"),
    re.compile(r"https?://(?:www\.)?youtube\.com/"),
    re.compile(r"https?://youtu\.be/"),
]

# 通用 URL 提取正则（贪婪匹配到空白/中文标点）
_URL_PATTERN = re.compile(r"https?://[^\s，）)】】【​]+")


def _is_supported_platform(url: str) -> bool:
    """检查 URL 是否属于已识别平台。"""
    return any(p.match(url) for p in _SUPPORTED_PLATFORM_PATTERNS)


def extract_all_urls(text: str) -> list[str]:
    """从文本中提取所有支持平台的 URL，去重并保持顺序。

    Args:
        text: 飞书消息文本，可能含 emoji、口令、多条 URL。

    Returns:
        去重后的支持平台 URL 列表，保持首次出现顺序。
    """
    raw_urls = _URL_PATTERN.findall(text)
    seen: set[str] = set()
    result: list[str] = []

    for url in raw_urls:
        # 去除末尾标点
        url = url.rstrip(".,;:!?。，；：！？）】")
        if url not in seen and _is_supported_platform(url):
            seen.add(url)
            result.append(url)

    return result
