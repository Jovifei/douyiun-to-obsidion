"""
M1 Task 1: 项目脚手架测试

测试 pyproject.toml、目录骨架、config 模板、.env 模板、.gitignore、conftest 等基础设施。
"""

import ast
import os
from pathlib import Path

import pytest
import tomllib
import yaml


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

    def test_src_init_exists(self):
        """M1 fix: src/__init__.py must exist."""
        assert _abs("src", "__init__.py").is_file(), "src/__init__.py 不存在"


# ── config.example.yaml ──────────────────────────────────────────────

class TestConfigExample:
    """Step 1.1: config.example.yaml 存在且含 port: 8765 和 6 个顶层 section"""

    REQUIRED_SECTIONS = [
        "server",
        "vault",
        "queue",
        "downloader",
        "logging",
        "git_backup",
    ]

    def test_exists(self):
        assert _abs("config.example.yaml").is_file(), "config.example.yaml 不存在"

    def test_contains_port_8765(self):
        text = _read_text("config.example.yaml")
        assert "8765" in text, "config.example.yaml 中未找到 port 8765"

    def test_has_all_six_sections(self):
        """M3 fix: config must have 6 top-level sections per plan Step 2."""
        data = yaml.safe_load(_read_text("config.example.yaml"))
        for section in self.REQUIRED_SECTIONS:
            assert section in data, f"config.example.yaml 缺少 section: {section}"


# ── .env.example ─────────────────────────────────────────────────────

class TestEnvExample:
    """Step 1.1: .env.example 存在且含飞书/MIMO 占位"""

    REQUIRED_KEYS = [
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "FEISHU_BISHU_OPEN_CHAT_ID",
        "MIMO_API_KEY",
    ]

    def test_exists(self):
        assert _abs(".env.example").is_file(), ".env.example 不存在"

    @pytest.mark.parametrize("key", REQUIRED_KEYS)
    def test_contains_key_placeholder(self, key: str):
        text = _read_text(".env.example")
        assert key in text, f".env.example 缺少 {key} 占位"


# ── tests/conftest.py ──────────────────────────────────────────────────

class TestConftest:
    """M2 fix: tests/conftest.py 存在且含 4 个 fixtures"""

    REQUIRED_FIXTURES = [
        "tmp_db",
        "tmp_vault",
        "sample_short_url",
        "sample_share_text",
    ]

    def test_exists(self):
        assert _abs("tests", "conftest.py").is_file(), "tests/conftest.py 不存在"

    def test_has_all_four_fixtures(self):
        source = _read_text("tests", "conftest.py")
        tree = ast.parse(source)
        fixture_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for dec in node.decorator_list:
                    # @pytest.fixture (no parens) -> ast.Attribute
                    # @pytest.fixture() (with parens) -> ast.Call
                    if isinstance(dec, ast.Attribute) and dec.attr == "fixture":
                        fixture_names.add(node.name)
                    elif (
                        isinstance(dec, ast.Call)
                        and isinstance(dec.func, ast.Attribute)
                        and dec.func.attr == "fixture"
                    ):
                        fixture_names.add(node.name)
        for name in self.REQUIRED_FIXTURES:
            assert name in fixture_names, f"conftest.py 缺少 fixture: {name}"


# ── pyproject.toml sections ────────────────────────────────────────────

class TestPyprojectSections:
    """M5 fix: pyproject.toml 含 [build-system] + [tool.setuptools.packages.find] + pythonpath"""

    def test_has_build_system_section(self):
        data = tomllib.loads(_read_text("pyproject.toml"))
        assert "build-system" in data, "pyproject.toml 缺少 [build-system]"

    def test_has_setuptools_packages_find(self):
        data = tomllib.loads(_read_text("pyproject.toml"))
        tool = data.get("tool", {})
        setuptools = tool.get("setuptools", {})
        assert "packages" in setuptools, (
            "pyproject.toml 缺少 [tool.setuptools.packages.find]"
        )
        assert "find" in setuptools.get("packages", {}), (
            "pyproject.toml 缺少 [tool.setuptools.packages.find]"
        )

    def test_pytest_pythonpath_is_set(self):
        """plan Step 1 requires pythonpath = ['.'] under [tool.pytest.ini_options]"""
        data = tomllib.loads(_read_text("pyproject.toml"))
        pytest_opts = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
        assert "pythonpath" in pytest_opts, (
            "pyproject.toml [tool.pytest.ini_options] 缺少 pythonpath"
        )

    def test_no_readme_reference(self):
        """E1 fix: pyproject.toml 不应引用不存在的 README.md"""
        text = _read_text("pyproject.toml")
        assert 'readme = "README.md"' not in text, (
            "pyproject.toml 不应引用不存在的 README.md"
        )


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
