"""Cookie HTTP 探活 — probe_cookie() + probe_and_rotate() 函数。

Spec ref: tasks.md §12 — 日志与可观测性
启动时用已知抖音 URL 做 HTTP 探活（不只是文件存在检查）。
M4: 新增 probe_and_rotate() — cookie 过期检测 + 自动轮转。
"""
import shutil
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


def probe_and_rotate(cookies_path: str, backup_dir: str) -> bool:
    """探测 cookies 有效性，过期时自动从备份目录轮转。

    流程：
    1. 用 probe_cookie() 探测当前 cookies
    2. 若有效 → 返回 True，不轮换
    3. 若过期 → 在 backup_dir 中找 cookies_backup_*.txt，按修改时间降序
       逐个探测，找到第一个有效的则替换主 cookies 文件，返回 True
    4. 全部过期或无备份 → 返回 False

    Args:
        cookies_path: 主 cookies 文件路径
        backup_dir: 备份目录路径

    Returns:
        True 如果当前生效的 cookies 有效，False 如果全部过期
    """
    # 1. 先探测当前 cookies
    if probe_cookie(cookies_path):
        return True

    # 2. 当前 cookies 无效，检查备份目录
    backup_path = Path(backup_dir)
    if not backup_path.exists():
        return False

    # 3. 按修改时间降序排列备份文件（最新在前）
    backup_files = sorted(
        backup_path.glob("cookies_backup_*.txt"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    # 4. 逐个探测备份，找到第一个有效的
    for backup_file in backup_files:
        if probe_cookie(str(backup_file)):
            shutil.copy2(backup_file, cookies_path)
            return True

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
