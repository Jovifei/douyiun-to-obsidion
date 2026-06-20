"""Git 冷备工具 — vault 初始化 + .gitignore 管理。"""
import subprocess
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# .gitignore 内容，按 specs/git-cold-backup 规范
_GITIGNORE_CONTENT = """\
# Obsidian 运行时
.obsidian/workspace*
.obsidian/cache/
.obsidian/plugins/*/data.json
.trash/

# 同步冲突
.sync-conflict-*
*.tmp

# 凭证（绝不能进版本控制）
.env
cookies.txt
secrets/
*.key

# 大附件（>50MB 不进 Git，由 Syncthing/iCloud 处理）
attachments/**/*.mp4
attachments/**/*.webm
attachments/**/full-video.*
"""


def init_vault_git(vault_root: Path) -> None:
    """在 vault 目录执行 git init + 配置默认 user + 首条 commit。"""
    vault_root.mkdir(parents=True, exist_ok=True)

    # git init
    subprocess.run(
        ["git", "init"],
        cwd=str(vault_root),
        check=True,
        capture_output=True,
    )
    logger.info("git_init_done", path=str(vault_root))

    # 配置默认 user（首次需要）
    for key, val in [("user.name", "Jovi"), ("user.email", "jovi@douyin-archive.local")]:
        subprocess.run(
            ["git", "config", key, val],
            cwd=str(vault_root),
            check=True,
            capture_output=True,
        )

    # 写入 .gitignore
    ensure_gitignore(vault_root)

    # 首条 commit
    subprocess.run(["git", "add", "."], cwd=str(vault_root), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init: 初始化 Obsidian vault"],
        cwd=str(vault_root),
        check=True,
        capture_output=True,
    )
    logger.info("vault_init_commit_done", path=str(vault_root))


def ensure_gitignore(vault_root: Path) -> None:
    """确保 vault_root/.gitignore 存在且内容正确。"""
    gitignore = vault_root / ".gitignore"
    gitignore.write_text(_GITIGNORE_CONTENT, encoding="utf-8")
    logger.info("gitignore_written", path=str(gitignore))
