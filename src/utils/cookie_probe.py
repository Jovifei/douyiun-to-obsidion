"""Cookie HTTP 探活 — probe_cookie() 函数。

Spec ref: tasks.md §12 — 日志与可观测性
启动时用已知抖音 URL 做 HTTP 探活（不只是文件存在检查）。
"""
from pathlib import Path

import httpx


def probe_cookie(cookies_path: str, test_url: str = "https://v.douyin.com/test/") -> bool:
    """用 cookies 文件对 test_url 做 HTTP 探活。

    Args:
        cookies_path: cookies 文件路径
        test_url: 测试 URL（默认抖音短链）

    Returns:
        True 如果返回 2xx，False 如果 401/403 或文件不存在/异常
    """
    cookie_file = Path(cookies_path)
    if not cookie_file.exists():
        return False

    try:
        # 读取 Netscape 格式 cookies.txt，解析为 httpx cookies dict
        cookies = _parse_cookie_file(cookie_file)
        with httpx.Client() as client:
            response = client.get(
                test_url,
                cookies=cookies,
                follow_redirects=True,
                timeout=10.0,
            )
            return 200 <= response.status_code < 300
    except Exception:
        return False


def _parse_cookie_file(cookie_file: Path) -> dict[str, str]:
    """解析 Netscape 格式 cookies.txt 为 dict。

    格式: domain  flag  path  secure  expiry  name  value
    """
    cookies = {}
    try:
        with open(cookie_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    name = parts[5]
                    value = parts[6]
                    cookies[name] = value
    except Exception:
        pass
    return cookies
