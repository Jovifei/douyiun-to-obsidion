"""Task 13: Git 冷备 — TDD 测试。"""
import subprocess
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 1. vault git init
# ---------------------------------------------------------------------------

def test_vault_git_init_creates_repo(tmp_vault: Path):
    """vault 目录执行 git init 后 .git 子目录存在。"""
    from src.utils.git_backup import init_vault_git

    init_vault_git(tmp_vault)

    git_dir = tmp_vault / ".git"
    assert git_dir.exists(), ".git directory should exist after init"
    assert (git_dir / "HEAD").is_file(), ".git/HEAD should exist"


# ---------------------------------------------------------------------------
# 2. .gitignore 屏蔽 secrets
# ---------------------------------------------------------------------------

def test_gitignore_excludes_secrets(tmp_vault: Path):
    """.gitignore 含 .env / cookies.txt / secrets/。"""
    from src.utils.git_backup import ensure_gitignore

    ensure_gitignore(tmp_vault)

    content = (tmp_vault / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in content
    assert "cookies.txt" in content
    assert "secrets/" in content


# ---------------------------------------------------------------------------
# 3. .gitignore 屏蔽 workspace
# ---------------------------------------------------------------------------

def test_gitignore_excludes_workspace(tmp_vault: Path):
    """.gitignore 含 .obsidian/workspace*。"""
    from src.utils.git_backup import ensure_gitignore

    ensure_gitignore(tmp_vault)

    content = (tmp_vault / ".gitignore").read_text(encoding="utf-8")
    assert ".obsidian/workspace" in content


# ---------------------------------------------------------------------------
# 4. .gitignore 屏蔽大附件
# ---------------------------------------------------------------------------

def test_gitignore_excludes_large_attachments(tmp_vault: Path):
    """.gitignore 含 *.mp4 / *.webm。"""
    from src.utils.git_backup import ensure_gitignore

    ensure_gitignore(tmp_vault)

    content = (tmp_vault / ".gitignore").read_text(encoding="utf-8")
    assert ".mp4" in content
    assert ".webm" in content


# ---------------------------------------------------------------------------
# 5. .gitignore 不屏蔽 .md 文件
# ---------------------------------------------------------------------------

def test_gitignore_allows_md_files(tmp_vault: Path):
    """.md 文件不被 gitignore 排除（即 .md 不在 ignore 模式中）。"""
    from src.utils.git_backup import ensure_gitignore

    ensure_gitignore(tmp_vault)

    content = (tmp_vault / ".gitignore").read_text(encoding="utf-8")
    # 确保没有 "*.md" 排除规则
    lines = [l.strip() for l in content.splitlines() if l.strip() and not l.strip().startswith("#")]
    for line in lines:
        assert "*.md" not in line, f"gitignore should not exclude .md files, found: {line}"


# ---------------------------------------------------------------------------
# 6. auto commit script 存在
# ---------------------------------------------------------------------------

def test_auto_commit_script_exists():
    """scripts/git-backup.ps1 文件存在。"""
    from pathlib import Path as _P
    script = _P(__file__).resolve().parents[2] / "scripts" / "git-backup.ps1"
    assert script.exists(), f"Expected script at {script}"


# ---------------------------------------------------------------------------
# 7. auto commit script 含 git push
# ---------------------------------------------------------------------------

def test_auto_commit_script_has_push():
    """scripts/git-backup.ps1 包含 git push 指令。"""
    from pathlib import Path as _P
    script = _P(__file__).resolve().parents[2] / "scripts" / "git-backup.ps1"
    content = script.read_text(encoding="utf-8")
    assert "git push" in content, "Script should contain git push command"
