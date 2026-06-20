"""
M1 Task 1: 项目脚手架测试

测试 pyproject.toml、目录骨架、config 模板、.env 模板、.gitignore 等基础设施。
"""

import os
from pathlib import Path

import pytest
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ── helpers ──────────────────────────────────────────────────────────

def _abs(*parts: str) -> Path:
    return PROJECT_ROOT.joinpath(*parts)


def _read_text(*parts: str) -> str:
    return _abs(*parts).read_text(encoding="utf-8")


# ── pyproject.toml ───────────────────────────────────────────────────

class TestPyprojectToml:
    """Step 1.1: pyproject.toml 存在且含必要依赖"""

    REQUIRED_DEPS = [
        "fastapi",
        "uvicorn",
        "yt-dlp",
        "sqlmodel",
        "pyyaml",
        "httpx",
        "structlog",
    ]

    def test_exists(self):
        assert _abs("pyproject.toml").is_file(), "pyproject.toml 不存在"

    def test_has_required_deps(self):
        data = tomllib.loads(_read_text("pyproject.toml"))
        deps: list[str] = []
        # Standard: [project] dependencies
        if "project" in data:
            deps.extend(data["project"].get("dependencies", []))
        # Fallback: [tool.poetry.dependencies]
        if "tool" in data and "poetry" in data["tool"]:
            deps.extend(data["tool"]["poetry"].get("dependencies", {}).keys())

        dep_text = " ".join(deps).lower()
        for req in self.REQUIRED_DEPS:
            assert req.lower() in dep_text, f"pyproject.toml 缺少依赖: {req}"


# ── 目录骨架 ──────────────────────────────────────────────────────────

class TestDirectorySkeleton:
    """Step 1.1: src 子包、tests、scripts、docs/m1 目录存在"""

    SRC_PACKAGES = [
        "extractors",
        "obsidian",
        "bridge",
        "queue",
        "pipeline",
        "config",
        "utils",
    ]

    @pytest.mark.parametrize("pkg", SRC_PACKAGES)
    def test_src_package_init_exists(self, pkg: str):
        init = _abs("src", pkg, "__init__.py")
        assert init.is_file(), f"src/{pkg}/__init__.py 不存在"

    def test_tests_init_exists(self):
        assert _abs("tests", "__init__.py").is_file(), "tests/__init__.py 不存在"

    def test_scripts_dir_exists(self):
        assert _abs("scripts").is_dir(), "scripts/ 目录不存在"

    def test_docs_m1_dir_exists(self):
        assert _abs("docs", "m1").is_dir(), "docs/m1/ 目录不存在"


# ── config.example.yaml ──────────────────────────────────────────────

class TestConfigExample:
    """Step 1.1: config.example.yaml 存在且含 port: 8765"""

    def test_exists(self):
        assert _abs("config.example.yaml").is_file(), "config.example.yaml 不存在"

    def test_contains_port_8765(self):
        text = _read_text("config.example.yaml")
        assert "8765" in text, "config.example.yaml 中未找到 port 8765"


# ── .env.example ─────────────────────────────────────────────────────

class TestEnvExample:
    """Step 1.1: .env.example 存在且含飞书/MIMO 占位"""

    REQUIRED_KEYS = [
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "MIMO_API_KEY",
    ]

    def test_exists(self):
        assert _abs(".env.example").is_file(), ".env.example 不存在"

    @pytest.mark.parametrize("key", REQUIRED_KEYS)
    def test_contains_key_placeholder(self, key: str):
        text = _read_text(".env.example")
        assert key in text, f".env.example 缺少 {key} 占位"


# ── .gitignore ───────────────────────────────────────────────────────

class TestGitignore:
    """Step 1.1: .gitignore 存在且含必要屏蔽规则"""

    REQUIRED_PATTERNS = [
        ".env",
        "cookies.txt",
        "logs/",
        "__pycache__/",
    ]

    def test_exists(self):
        assert _abs(".gitignore").is_file(), ".gitignore 不存在"

    @pytest.mark.parametrize("pattern", REQUIRED_PATTERNS)
    def test_contains_pattern(self, pattern: str):
        text = _read_text(".gitignore")
        assert pattern in text, f".gitignore 缺少屏蔽规则: {pattern}"
