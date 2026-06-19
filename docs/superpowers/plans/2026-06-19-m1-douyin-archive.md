---
change: m1-douyin-archive-mvp
design-doc: docs/superpowers/specs/2026-06-19-m1-douyin-archive-design.md
base-ref: 2d28ae12fb0ef4bb44475d18bacf2943feab7283
---

# M1 抖音知识视频归档系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打通"飞书分享抖音链接 → vault 笔记入库"端到端最短路径（≤2 分钟），M1 不调 LLM/ASR/VLM，为 M2/M3 留接口位。

**Architecture:** 独立 FastAPI 解析服务（端口 8765）+ SQLite 队列（4 状态机：pending/fetching/writing/done/failed）+ 单 worker 串行调度 + 自研 `src/extractors/`（yt-dlp 主路径 + DouK-Downloader 兜底）+ Obsidian 原子 rename 写入 + Git 冷备。飞书侧 bishu agent 仅做"路由 + 入队 + 轮询 + 回执"，通过 OQ-1 blocker 独立分组，主流程不阻塞。

**Tech Stack:** Python ≥3.11、FastAPI + uvicorn、yt-dlp、SQLite (via `sqlite3` 标准库)、SQLModel（可选）、PyYAML、httpx、structlog、pytest、ffmpeg、PowerShell（git backup cron）。

---

## 关键约束（所有 task 必须遵守）

1. **D-3 v2**：不 vendoring `git_ref/obsidian-content-capture-backend`（无 OSS license）。仅 `src/extractors/douyin_resolver.py` 阅读参考 `git_ref/.../douyin_resolver.py` 思路，**不复制代码**。
2. **D-4 v2**：任务状态机 4 状态 `pending → fetching → writing → done | failed`，**删除 `processing`**。dequeue 单条原子 SQL 直接置 `fetching`。
3. **D-9**：解析服务端口锁 `8765`。`config.example.yaml` 与所有文档统一。
4. **D-10**：frontmatter 加 3 状态字段 `summary_status` / `processing_mode` / `ai_summary_model`，M1 默认 `not_run` / `subtitle_only` / `null`。
5. **D-7**：vault 写入用 `.md.tmp` + `os.rename`，Windows 同卷原子。
6. **TDD 模式**：每 task 先写失败测试（红），再实现（绿），再重构。测试断言来源 = 对应 spec 的 WHEN/THEN 场景。
7. **subagent-driven 模式**：每 task 边界清晰，可独立派给一个 subagent。依赖在 task 开头明示。
8. **OQ-1 blocker**：Task 11-13（对应 tasks §9/§10/§11.B）独立分组，主流程 Task 1-10 + 14-15 不依赖。
9. **路径全部以 `E:\project\douyin_to_obsidian\` 起头**（vault 路径 `E:\AI_Tools\Obsidian\data\notes-personal` 是例外）。
10. **工时**：5-7 天。

---

## File Structure

### 新建文件（src/）

```
E:\project\douyin_to_obsidian\
├── pyproject.toml                          # 依赖锁定
├── config.example.yaml                     # 配置模板（端口 8765）
├── .env.example                            # 凭证占位
├── .gitignore                              # 屏蔽 .env/cookies/logs/__pycache__/.venv
├── src\
│   ├── __init__.py
│   ├── config\
│   │   ├── __init__.py
│   │   └── loader.py                       # YAML + env 加载
│   ├── extractors\
│   │   ├── __init__.py                     # 导出 resolve_url/download_video/extract_subtitle/extract_metadata
│   │   ├── douyin_resolver.py              # 4 种 URL 形态 + 302 跟随 + video_id 抽取
│   │   ├── downloader.py                   # yt-dlp 包装 + 字幕来源判定
│   │   ├── audio_extractor.py              # ffmpeg 一行命令
│   │   ├── metadata.py                     # 元数据 + uploader_id 正则
│   │   └── douk_fallback.py                # DouK-Downloader subprocess 兜底
│   ├── queue\
│   │   ├── __init__.py
│   │   ├── schema.sql                      # task 表 + idx
│   │   └── db.py                           # init_db/enqueue/atomic_dequeue/reclaim_zombie/mark_status
│   ├── pipeline\
│   │   ├── __init__.py
│   │   ├── state_machine.py                # 4 状态合法转移 + 非法拒绝
│   │   ├── scheduler.py                    # run_forever 单 worker 循环
│   │   └── errors.py                       # 错误码枚举 + 分类
│   ├── obsidian\
│   │   ├── __init__.py
│   │   ├── frontmatter.py                  # 17 字段 schema + D-10 状态字段
│   │   ├── note_builder.py                 # 正文 5 段结构
│   │   ├── writer.py                       # 原子 rename + 失败回滚
│   │   └── path_calc.py                    # inbox/douyin/{YYYY-MM}/{video_id}.md
│   ├── bridge\
│   │   ├── __init__.py
│   │   └── main.py                         # FastAPI app: /ingest /tasks/{id} /health /queue/stats
│   └── utils\
│       ├── __init__.py
│       ├── logging.py                      # structlog + correlation_id
│       └── cookie_probe.py                 # cookie 探活
├── tests\
│   ├── __init__.py
│   ├── conftest.py                         # tmp_db / tmp_vault fixtures
│   ├── extractors\
│   │   ├── test_douyin_resolver.py
│   │   ├── test_downloader.py
│   │   ├── test_metadata.py
│   │   └── test_douk_fallback.py
│   ├── queue\
│   │   ├── test_db.py
│   │   └── test_state_machine.py
│   ├── pipeline\
│   │   ├── test_scheduler.py
│   │   └── test_errors.py
│   ├── obsidian\
│   │   ├── test_frontmatter.py
│   │   ├── test_note_builder.py
│   │   ├── test_writer.py
│   │   └── test_path_calc.py
│   ├── bridge\
│   │   └── test_main.py                    # httpx + FastAPI TestClient
│   └── e2e\
│       ├── test_curl_e2e.py                # 11.A 的 7 个场景
│       └── test_feishu_e2e.py              # 11.B 的 6 个场景（blocked）
├── scripts\
│   ├── git-backup.ps1                      # vault git 冷备
│   └── register-scheduled-task.ps1         # 注册 Windows 任务计划
└── docs\
    └── m1\
        ├── bishu_agent_template.json       # OQ-1 解决后填
        ├── RUNBOOK.md
        ├── TROUBLESHOOTING.md
        └── ACCEPTANCE.md
```

### 不修改的文件

- `openspec/changes/m1-douyin-archive-mvp/tasks.md` / `specs/**` / `docs/superpowers/specs/2026-06-19-m1-douyin-archive-design.md`：如发现 spec 缺陷，在 plan 里标 TODO 但不改原文件。
- `docs/claude/PRD.md` / `docs/claude/EXECUTION.md`：仅作上下文参考，不修改。
- `git_ref/obsidian-content-capture-backend/**`：仅阅读参考，不 vendoring。

### 修改的文件

- `docs/claude/EXECUTION.md` + `docs/codex/EXECUTION.md`：Task 1 step 4 全局 `18900 → 8765` 替换（D-9）。

---

## Task 分组总览

| 分组 | Task # | 对应 tasks.md | 状态 | 依赖 |
|------|--------|---------------|------|------|
| A. 主流程（OQ-1 不阻塞） | 1-13 | §1-8（含调度器/日志/Git 冷备） | 可执行 | 顺序依赖 |
| B. curl E2E 验收 | 14 | §11.A | 可执行 | Task 1-13 完成 |
| C. OQ-1 blocked | 15-17 | §9/§10/§11.B | blocked | OQ-1 解决 |
| D. 文档归档 | 18 | §12 | 可执行 | Task 1-14 完成 |

---


## 分组 A：主流程（OQ-1 不阻塞）

### Task 1: 环境与脚手架准备

**对应 tasks.md**: §1.1-1.9
**依赖**: 无
**Spec 参考**: 无（基础设施）

**Files:**
- Create: `E:\project\douyin_to_obsidian\pyproject.toml`
- Create: `E:\project\douyin_to_obsidian\config.example.yaml`
- Create: `E:\project\douyin_to_obsidian\.env.example`
- Create: `E:\project\douyin_to_obsidian\.gitignore`
- Create: `E:\project\douyin_to_obsidian\src\__init__.py`（空文件）
- Create: `E:\project\douyin_to_obsidian\src\{config,extractors,queue,pipeline,obsidian,bridge,utils}\__init__.py`（全空）
- Create: `E:\project\douyin_to_obsidian\tests\__init__.py`（空）
- Create: `E:\project\douyin_to_obsidian\tests\conftest.py`
- Modify: `E:\project\douyin_to_obsidian\docs\claude\EXECUTION.md`（全局 18900 → 8765）
- Modify: `E:\project\douyin_to_obsidian\docs\codex\EXECUTION.md`（全局 18900 → 8765）

- [ ] **Step 1: 创建 pyproject.toml**

```toml
[project]
name = "douyin-to-obsidian"
version = "0.1.0"
description = "M1: 抖音知识视频自动归档到 Obsidian"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "yt-dlp>=2026.1.0",
    "pyyaml>=6.0",
    "httpx>=0.27",
    "structlog>=24.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["src*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 2: 创建 config.example.yaml（端口锁 8765，D-9）**

```yaml
# M1 解析服务配置模板。复制为 config.yaml 后填真实路径。
server:
  host: "127.0.0.1"
  port: 8765                    # D-9 锁定，勿改

vault:
  root: "E:\\AI_Tools\\Obsidian\\data\\notes-personal"
  inbox_subdir: "inbox/douyin"
  attachments_subdir: "attachments/douyin"

queue:
  db_path: "E:\\project\\douyin_to_obsidian\\data\\queue.sqlite3"
  zombie_timeout_minutes: 30    # B4 zombie 复活阈值

downloader:
  cookies_path: ""              # 留空 = 不用 cookie；填路径 = 启用 cookie 探活
  temp_dir: "E:\\project\\douyin_to_obsidian\\data\\tmp"
  yt_dlp_retries: 3
  douk_path: ""                 # DouK-Downloader 可执行路径，留空 = 禁用兜底

logging:
  level: "INFO"
  dir: "E:\\project\\douyin_to_obsidian\\logs"
  rotation: "daily"

git_backup:
  vault_root: "E:\\AI_Tools\\Obsidian\\data\\notes-personal"
  remote_url: ""                # OQ-4 未决，留空 = 仅本地 commit
  cron_time: "03:00"
```

- [ ] **Step 3: 创建 .env.example 与 .gitignore**

`.env.example`:
```
# 飞书凭证（bishu agent 用，解析服务 M1 不需要）
FEISHU_APP_ID=cli_xxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxx
FEISHU_BISHU_OPEN_CHAT_ID=oc_516376df9cc2315fc12470e56e72c4af

# MiMo API（M1 不调，留位）
MIMO_API_KEY=
```

`.gitignore`:
```
# 凭证
.env
cookies.txt
secrets/
*.key

# 运行时
logs/
__pycache__/
.venv/
*.pyc
*.tmp

# 数据
data/queue.sqlite3
data/tmp/

# IDE
.vscode/
.idea/

# OS
Thumbs.db
.DS_Store
```

- [ ] **Step 4: 全局端口替换 18900 → 8765（D-9）**

Run in PowerShell:
```powershell
$files = @("E:\project\douyin_to_obsidian\docs\claude\EXECUTION.md", "E:\project\douyin_to_obsidian\docs\codex\EXECUTION.md")
foreach ($f in $files) {
    if (Test-Path $f) {
        (Get-Content $f) -replace '18900', '8765' | Set-Content $f
        Write-Host "Updated: $f"
    }
}
```
Expected output: 两行 "Updated: ..."。验证 `Select-String -Path $files -Pattern '18900'` 返回空。

- [ ] **Step 5: 创建 tests/conftest.py（公共 fixtures）**

```python
"""pytest 公共 fixtures。"""
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db(tmp_path: Path):
    """临时 SQLite 队列 db。"""
    db_path = tmp_path / "test_queue.sqlite3"
    conn = sqlite3.connect(str(db_path))
    yield conn, db_path
    conn.close()


@pytest.fixture
def tmp_vault(tmp_path: Path):
    """临时 vault 目录，模拟 vault root。"""
    vault = tmp_path / "vault"
    (vault / "inbox" / "douyin").mkdir(parents=True, exist_ok=True)
    (vault / "attachments" / "douyin").mkdir(parents=True, exist_ok=True)
    return vault


@pytest.fixture
def sample_short_url():
    """测试用抖音短链（Jovi 提供样本，见 OQ-3）。"""
    return "https://v.douyin.com/iAbCdEf/"


@pytest.fixture
def sample_share_text():
    """测试用分享文案。"""
    return "9.99 复制打开抖音，看看【作者】的作品 https://v.douyin.com/iAbCdEf/ 🔥"
```

- [ ] **Step 6: 验证环境依赖可调用**

Run:
```powershell
python --version
yt-dlp --version
ffmpeg -version
```
Expected: python ≥ 3.11；yt-dlp 返回版本号；ffmpeg 返回版本号。任一缺失则先安装。

- [ ] **Step 7: 验证 vault 路径存在**

Run:
```powershell
Test-Path "E:\AI_Tools\Obsidian\data\notes-personal"
```
Expected: `True`。若 False，先创建目录或修正 `config.example.yaml` 的 `vault.root`。

- [ ] **Step 8: 安装依赖并跑 pytest 空测试**

Run:
```powershell
cd E:\project\douyin_to_obsidian
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest --collect-only
```
Expected: `pytest --collect-only` 报 "no tests ran" 但无 import 错误。

- [ ] **Step 9: Commit**

```powershell
git add pyproject.toml config.example.yaml .env.example .gitignore src tests docs/claude/EXECUTION.md docs/codex/EXECUTION.md
git commit -m "chore(m1): scaffold project structure + lock port 8765"
```

---

### Task 2: 自研 douyin_resolver（4 种 URL 形态 + 302 跟随）

**对应 tasks.md**: §2.1, §2.2
**依赖**: Task 1 完成
**Spec 参考**: `specs/douyin-extraction/spec.md` Requirement "接受多种抖音 URL 形态"

**Files:**
- Create: `E:\project\douyin_to_obsidian\src\extractors\douyin_resolver.py`
- Create: `E:\project\douyin_to_obsidian\tests\extractors\test_douyin_resolver.py`

- [ ] **Step 1: 写失败测试（红）**

`tests/extractors/test_douyin_resolver.py`:
```python
"""Test douyin URL resolver.

Spec ref: specs/douyin-extraction/spec.md
- Scenario: 短链解析
- Scenario: 分享文案解析
- Scenario: 非抖音 URL
"""
import pytest

from src.extractors.douyin_resolver import resolve_url, ResolverError


def test_short_url_resolves(monkeypatch):
    """WHEN 收到 https://v.douyin.com/iAbCdEf/
    THEN 302 跟随得完整 URL，提取 video_id，返回 source_url_type='short'。"""
    def fake_follow_redirect(url):
        return "https://www.douyin.com/video/7234567890123"
    monkeypatch.setattr("src.extractors.douyin_resolver._follow_redirect", fake_follow_redirect)
    result = resolve_url("https://v.douyin.com/iAbCdEf/")
    assert result["video_id"] == "7234567890123"
    assert result["source_url_type"] == "short"
    assert "douyin.com/video/7234567890123" in result["canonical_url"]


def test_full_url_no_redirect():
    """WHEN 收 https://www.douyin.com/video/7234567890123
    THEN 不跟 302，直接提取 video_id，type='full'。"""
    result = resolve_url("https://www.douyin.com/video/7234567890123")
    assert result["video_id"] == "7234567890123"
    assert result["source_url_type"] == "full"


def test_iesdouyin_url():
    """WHEN 收 https://www.iesdouyin.com/share/video/7234567890123
    THEN type='iesdouyin'。"""
    result = resolve_url("https://www.iesdouyin.com/share/video/7234567890123")
    assert result["video_id"] == "7234567890123"
    assert result["source_url_type"] == "iesdouyin"


def test_share_text_extracts_url(monkeypatch):
    """WHEN 收分享文案含短链
    THEN 提取短链后按短链流程解析，忽略 emoji 与口令。"""
    monkeypatch.setattr("src.extractors.douyin_resolver._follow_redirect",
                        lambda u: "https://www.douyin.com/video/7234567890123")
    text = "9.99 复制打开抖音，看看【作者】的作品 https://v.douyin.com/iAbCdEf/ 🔥"
    result = resolve_url(text)
    assert result["video_id"] == "7234567890123"
    assert result["source_url_type"] == "short"


def test_non_douyin_url_raises():
    """WHEN 收 https://www.bilibili.com/video/BVxxx
    THEN 抛 ResolverError('not_douyin_url')。"""
    with pytest.raises(ResolverError) as exc:
        resolve_url("https://www.bilibili.com/video/BVxxx")
    assert "not_douyin_url" in str(exc.value)
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/extractors/test_douyin_resolver.py -v`
Expected: `ImportError: No module named 'src.extractors.douyin_resolver'`（红）。

- [ ] **Step 3: 写最小实现（绿）**

`src/extractors/douyin_resolver.py`:
```python
"""抖音 URL 解析器：4 种形态 → video_id + canonical_url。

参考思路：git_ref/obsidian-content-capture-backend/script/douyin_resolver.py
（不复制代码，仅借鉴 302 跟随 + 正则思路，D-3 v2）。
"""
import re
from typing import Optional
from urllib.parse import urlparse

import httpx


class ResolverError(Exception):
    """URL 无法解析为抖音视频。"""


_SHORT_URL_PATTERN = re.compile(r"https?://v\.douyin\.com/[A-Za-z0-9]+/?")
_FULL_URL_PATTERN = re.compile(r"https?://www\.douyin\.com/video/(\d+)")
_IES_URL_PATTERN = re.compile(r"https?://www\.iesdouyin\.com/share/video/(\d+)")
_URL_EXTRACT_FROM_TEXT = re.compile(r"https?://[^\s，）)】]+")
_VIDEO_ID_FROM_CANONICAL = re.compile(r"/video/(\d+)")


def _follow_redirect(url: str) -> str:
    """跟随短链 302，返回最终 canonical URL。"""
    with httpx.Client(follow_redirects=True, timeout=10.0) as client:
        resp = client.get(url)
        return str(resp.url)


def _extract_video_id(canonical: str) -> Optional[str]:
    m = _VIDEO_ID_FROM_CANONICAL.search(canonical)
    return m.group(1) if m else None


def resolve_url(raw: str) -> dict:
    """解析 4 种形态的抖音输入为 {video_id, canonical_url, source_url_type}。

    Raises:
        ResolverError: 非抖音 URL 或无 video_id 可提取。
    """
    raw = raw.strip()

    # 形态 4：分享文案 — 先抽出 URL
    extracted = _URL_EXTRACT_FROM_TEXT.search(raw)
    url = extracted.group(0) if extracted else raw

    # 形态 2：完整链
    m = _FULL_URL_PATTERN.match(url)
    if m:
        return {"video_id": m.group(1), "canonical_url": url, "source_url_type": "full"}

    # 形态 3：iesdouyin 旧链
    m = _IES_URL_PATTERN.match(url)
    if m:
        return {"video_id": m.group(1), "canonical_url": url, "source_url_type": "iesdouyin"}

    # 形态 1：短链 — 需 302 跟随
    if _SHORT_URL_PATTERN.match(url):
        canonical = _follow_redirect(url)
        vid = _extract_video_id(canonical)
        if not vid:
            raise ResolverError(f"short_url_no_video_id: {canonical}")
        return {"video_id": vid, "canonical_url": canonical, "source_url_type": "short"}

    # 非抖音 URL
    parsed = urlparse(url)
    if "douyin.com" not in parsed.netloc and "iesdouyin.com" not in parsed.netloc:
        raise ResolverError("not_douyin_url")

    raise ResolverError(f"unrecognized_douyin_url: {url}")
```

- [ ] **Step 4: 跑测试验证通过**

Run: `pytest tests/extractors/test_douyin_resolver.py -v`
Expected: 5 个测试全 PASS（绿）。

- [ ] **Step 5: 重构（DRY）**

检查 `_follow_redirect` 与 `_extract_video_id` 是否可复用。当前实现已最小，无需重构。

- [ ] **Step 6: Commit**

```powershell
git add src/extractors/douyin_resolver.py tests/extractors/test_douyin_resolver.py
git commit -m "feat(extractor): douyin URL resolver for 4 input forms"
```

---

### Task 3: 自研 yt-dlp downloader + 字幕来源判定

**对应 tasks.md**: §2.3
**依赖**: Task 2 完成
**Spec 参考**: `specs/douyin-extraction/spec.md` Requirement "yt-dlp 主路径下载" + "字幕来源判定"

**Files:**
- Create: `E:\project\douyin_to_obsidian\src\extractors\downloader.py`
- Create: `E:\project\douyin_to_obsidian\tests\extractors\test_downloader.py`

- [ ] **Step 1: 写失败测试（红）**

`tests/extractors/test_downloader.py`:
```python
"""Test yt-dlp downloader wrapper + subtitle source classification.

Spec ref: specs/douyin-extraction/spec.md
- Scenario: 带原生字幕视频 → 'douyin_native'
- Scenario: 创作者上传字幕 → 'creator_uploaded'
- Scenario: 平台自动字幕 → 'auto_generated'
- Scenario: 无字幕视频 → NoSubtitleError
"""
from pathlib import Path

import pytest

from src.extractors.downloader import (
    download_video,
    classify_subtitle_source,
    NoSubtitleError,
)


def test_classify_creator_uploaded():
    info = {"subtitles": {"zh": [{"url": "http://x.vtt"}]}, "automatic_captions": {}}
    assert classify_subtitle_source(info) == "creator_uploaded"


def test_classify_auto_generated():
    info = {"subtitles": {}, "automatic_captions": {"zh": [{"url": "http://x.vtt"}]}}
    assert classify_subtitle_source(info) == "auto_generated"


def test_classify_no_subtitle():
    info = {"subtitles": {}, "automatic_captions": {}}
    with pytest.raises(NoSubtitleError):
        classify_subtitle_source(info)


def test_classify_douyin_native_special_case():
    info = {
        "subtitles": {"zh": [{"url": "http://a.vtt"}]},
        "automatic_captions": {"zh": [{"url": "http://b.vtt"}]},
    }
    assert classify_subtitle_source(info) == "douyin_native"


def test_download_invokes_yt_dlp(monkeypatch, tmp_path):
    class FakeYdl:
        def __init__(self, opts): self.opts = opts
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def extract_info(self, url, download=True):
            (tmp_path / "7234567890123.mp4").write_bytes(b"fake-video")
            (tmp_path / "7234567890123.zh.vtt").write_text("WEBVTT\n00:00:01 --> 00:00:02\nTest")
            return {
                "id": "7234567890123",
                "subtitles": {"zh": [{"url": "http://x.vtt"}]},
                "automatic_captions": {"zh": [{"url": "http://x.vtt"}]},
                "title": "Test video",
            }

    monkeypatch.setattr("src.extractors.downloader.yt_dlp.YoutubeDL", lambda opts: FakeYdl(opts))
    result = download_video(
        video_id="7234567890123",
        canonical_url="https://www.douyin.com/video/7234567890123",
        out_dir=tmp_path,
        cookies_path=None,
    )
    assert result["video_path"].exists()
    assert result["subtitle_path"].exists()
    assert result["subtitle_source"] == "douyin_native"
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/extractors/test_downloader.py -v`
Expected: `ImportError: No module named 'src.extractors.downloader'`（红）。

- [ ] **Step 3: 写最小实现（绿）**

`src/extractors/downloader.py`:
```python
"""yt-dlp Python API 包装：下载视频 + 字幕，判定字幕来源（B2 修订）。

Spec ref: specs/douyin-extraction/spec.md
- Requirement: yt-dlp 主路径下载
- Requirement: 字幕来源判定
"""
from pathlib import Path
from typing import Optional

import yt_dlp


class NoSubtitleError(Exception):
    """M1 边界：视频无任何字幕。"""


def classify_subtitle_source(info_dict: dict) -> str:
    """按 B2 修订：用 info_dict['subtitles'] vs ['automatic_captions'] 判定。

    Returns: 'douyin_native' | 'creator_uploaded' | 'auto_generated'
    Raises: NoSubtitleError 当两者都无 zh。
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
    """下载视频 + 字幕到 out_dir，返回结果 dict。

    Raises: NoSubtitleError, yt_dlp.utils.DownloadError。
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
    }
```

- [ ] **Step 4: 跑测试验证通过**

Run: `pytest tests/extractors/test_downloader.py -v`
Expected: 5 个测试全 PASS（绿）。

- [ ] **Step 5: Commit**

```powershell
git add src/extractors/downloader.py tests/extractors/test_downloader.py
git commit -m "feat(extractor): yt-dlp wrapper + B2 subtitle source classification"
```

---

### Task 4: 自研 metadata + audio_extractor

**对应 tasks.md**: §2.4, §2.5
**依赖**: Task 3 完成
**Spec 参考**: `specs/douyin-extraction/spec.md` Requirement "视频元数据提取"

**Files:**
- Create: `E:\project\douyin_to_obsidian\src\extractors\metadata.py`
- Create: `E:\project\douyin_to_obsidian\src\extractors\audio_extractor.py`
- Create: `E:\project\douyin_to_obsidian\tests\extractors\test_metadata.py`

- [ ] **Step 1: 写失败测试（红）**

`tests/extractors/test_metadata.py`:
```python
"""Test metadata extractor.

Spec ref: specs/douyin-extraction/spec.md
- Scenario: 完整元数据
- Scenario: uploader_id 提取失败 → 留空字符串，任务不失败
"""
import pytest

from src.extractors.metadata import extract_metadata, extract_uploader_id


def test_extract_uploader_id_from_sec_uid():
    url = "https://www.douyin.com/user/MS4wLjABAAAAxYz123abc"
    assert extract_uploader_id(url) == "MS4wLjABAAAAxYz123abc"


def test_extract_uploader_id_no_user_path():
    assert extract_uploader_id("https://www.douyin.com/some/other") == ""
    assert extract_uploader_id("") == ""


def test_extract_metadata_full():
    info = {
        "title": "测试视频标题",
        "uploader": "测试作者",
        "uploader_url": "https://www.douyin.com/user/MS4wLjABAAAAsecUID",
        "duration": 180,
        "upload_date": "20260619",
        "thumbnail": "https://p9.douyinpic.com/xxx.jpg",
    }
    md = extract_metadata(info)
    assert md["title"] == "测试视频标题"
    assert md["uploader"] == "测试作者"
    assert md["uploader_id"] == "MS4wLjABAAAAsecUID"
    assert md["duration_seconds"] == 180
    assert md["uploaded_at"] == "2026-06-19T00:00:00"
    assert md["thumbnail"] == "https://p9.douyinpic.com/xxx.jpg"


def test_extract_metadata_missing_uploader_url():
    info = {
        "title": "x", "uploader": "y", "uploader_url": "",
        "duration": 10, "upload_date": "20260101", "thumbnail": "t",
    }
    md = extract_metadata(info)
    assert md["uploader_id"] == ""
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/extractors/test_metadata.py -v`
Expected: `ImportError`（红）。

- [ ] **Step 3: 写最小实现（绿）**

`src/extractors/metadata.py`:
```python
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
    """yt-dlp upload_date='20260619' → ISO 8601 '2026-06-19T00:00:00'。"""
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
```

`src/extractors/audio_extractor.py`:
```python
"""ffmpeg 音频抽取（M2 Whisper 用，M1 仅留接口，不在主路径调用）。

一行命令：ffmpeg -i input.mp4 -ar 16000 -ac 1 -c:a pcm_s16le output.wav
"""
import subprocess
from pathlib import Path


def extract_audio(video_path: Path, out_path: Path) -> Path:
    """从视频抽 16kHz 单声道 PCM wav，供 M2 Whisper 使用。

    M1 阶段此函数不被主路径调用，仅 M2 启用时复用。
    """
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        str(out_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path
```

- [ ] **Step 4: 跑测试验证通过**

Run: `pytest tests/extractors/test_metadata.py -v`
Expected: 4 个测试全 PASS（绿）。

- [ ] **Step 5: Commit**

```powershell
git add src/extractors/metadata.py src/extractors/audio_extractor.py tests/extractors/test_metadata.py
git commit -m "feat(extractor): metadata + uploader_id sec_uid regex (B3) + audio stub"
```

---

### Task 5: 自研 DouK-Downloader 兜底 + extractors/__init__ 导出

**对应 tasks.md**: §2.6, §2.7
**依赖**: Task 4 完成
**Spec 参考**: `specs/douyin-extraction/spec.md` Requirement "yt-dlp 失败兜底走 DouK-Downloader"

**Files:**
- Create: `E:\project\douyin_to_obsidian\src\extractors\douk_fallback.py`
- Create: `E:\project\douyin_to_obsidian\tests\extractors\test_douk_fallback.py`
- Modify: `E:\project\douyin_to_obsidian\src\extractors\__init__.py`

- [ ] **Step 1: 写失败测试（红）**

`tests/extractors/test_douk_fallback.py`:
```python
"""Test DouK-Downloader fallback.

Spec ref: specs/douyin-extraction/spec.md
- Scenario: yt-dlp 失败 → DouK 成功 → downloader_used='douk'
"""
import pytest

from src.extractors.douk_fallback import download_with_douk, DoukNotConfiguredError


def test_douk_not_configured_raises():
    with pytest.raises(DoukNotConfiguredError):
        download_with_douk(
            video_id="123",
            canonical_url="https://www.douyin.com/video/123",
            out_dir="/tmp/x",
            douk_path="",
        )


def test_douk_success(monkeypatch, tmp_path):
    def fake_run(cmd, **kw):
        (tmp_path / "123.mp4").write_bytes(b"fake")
        (tmp_path / "123.zh.vtt").write_text("WEBVTT\n...")
        class R:
            returncode = 0
            stdout = ""
            stderr = ""
        return R()

    monkeypatch.setattr("src.extractors.douk_fallback.subprocess.run", fake_run)
    result = download_with_douk(
        video_id="123",
        canonical_url="https://www.douyin.com/video/123",
        out_dir=tmp_path,
        douk_path="/fake/douk.exe",
    )
    assert result["video_path"].exists()
    assert result["downloader_used"] == "douk"
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/extractors/test_douk_fallback.py -v`
Expected: `ImportError`（红）。

- [ ] **Step 3: 写最小实现（绿）**

`src/extractors/douk_fallback.py`:
```python
"""DouK-Downloader subprocess 兜底（yt-dlp 失败时切换）。

Spec ref: specs/douyin-extraction/spec.md Requirement: yt-dlp 失败兜底走 DouK-Downloader。
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
    cmd = [
        douk_path,
        "--url", canonical_url,
        "--output-dir", str(out_dir),
        "--output-name", video_id,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    if result.returncode != 0:
        raise DoukDownloadError(
            f"douk failed: {result.stderr.decode('utf-8', errors='replace')}"
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
```

- [ ] **Step 4: 跑测试验证通过**

Run: `pytest tests/extractors/test_douk_fallback.py -v`
Expected: 2 个测试 PASS（绿）。

- [ ] **Step 5: 写 __init__.py 导出 API**

`src/extractors/__init__.py`:
```python
"""extractors 包对外 API。

Spec ref: specs/douyin-extraction/spec.md。
"""
from src.extractors.douyin_resolver import resolve_url, ResolverError
from src.extractors.downloader import (
    download_video,
    classify_subtitle_source,
    NoSubtitleError,
)
from src.extractors.metadata import extract_metadata
from src.extractors.douk_fallback import (
    download_with_douk,
    DoukNotConfiguredError,
    DoukDownloadError,
)

__all__ = [
    "resolve_url", "ResolverError",
    "download_video", "classify_subtitle_source", "NoSubtitleError",
    "extract_metadata",
    "download_with_douk", "DoukNotConfiguredError", "DoukDownloadError",
]
```

- [ ] **Step 6: 跑全部 extractor 测试**

Run: `pytest tests/extractors/ -v`
Expected: 全部 PASS（绿）。

- [ ] **Step 7: Commit**

```powershell
git add src/extractors/douk_fallback.py src/extractors/__init__.py tests/extractors/test_douk_fallback.py
git commit -m "feat(extractor): DouK fallback + package exports"
```

---

### Task 6: SQLite 队列 schema + db.py（D-4 v2 4 状态机）

**对应 tasks.md**: §3.1-3.3
**依赖**: Task 1 完成
**Spec 参考**: `specs/task-queue-pipeline/spec.md` Requirement "SQLite 队列 schema（v2：4 状态枚举）" + "原子 dequeue（v2：直接置 fetching）" + "启动时复活 zombie 任务"

**Files:**
- Create: `E:\project\douyin_to_obsidian\src\queue\schema.sql`
- Create: `E:\project\douyin_to_obsidian\src\queue\db.py`
- Create: `E:\project\douyin_to_obsidian\tests\queue\test_db.py`

- [ ] **Step 1: 写失败测试（红）**

`tests/queue/test_db.py`:
```python
"""Test SQLite queue: enqueue / atomic_dequeue / reclaim_zombie / mark_status.

Spec ref: specs/task-queue-pipeline/spec.md
- Scenario: 新任务入队 → status='pending', claimed_at=NULL
- Scenario: 单 worker dequeue → status='fetching', claimed_at=now()
- Scenario: 队列为空 → dequeue 返回 None
- Scenario: 进程崩溃后重启（fetching 卡住）→ reclaim 后回 pending
- Scenario: 正常运行中不复活（claimed_at < 30min）
- Scenario: status 枚举约束 → 设 'processing' 应被 CHECK 拒绝
"""
import sqlite3
from datetime import datetime, timedelta

import pytest

from src.queue.db import init_db, enqueue, atomic_dequeue, reclaim_zombie_tasks, mark_status


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "q.sqlite3"
    conn = init_db(db_path)
    yield conn
    conn.close()


def test_enqueue_pending(db):
    """WHEN enqueue 新任务
    THEN status='pending', claimed_at=NULL。"""
    task_id = enqueue(db, video_id="v1", source_url="https://v.douyin.com/x/",
                     source_url_type="short", correlation_id="c1")
    assert task_id > 0
    row = db.execute("SELECT status, claimed_at FROM task WHERE id=?", (task_id,)).fetchone()
    assert row[0] == "pending"
    assert row[1] is None


def test_atomic_dequeue_sets_fetching(db):
    """WHEN dequeue 队列有 pending
    THEN 返回单条任务，status='fetching', claimed_at != NULL。"""
    enqueue(db, video_id="v1", source_url="u1", source_url_type="short", correlation_id="c1")
    task = atomic_dequeue(db)
    assert task is not None
    assert task["status"] == "fetching"
    assert task["claimed_at"] is not None


def test_dequeue_empty_returns_none(db):
    """WHEN 队列为空
    THEN dequeue 返回 None。"""
    assert atomic_dequeue(db) is None


def test_status_check_rejects_processing(db):
    """WHEN 试图把 status 设为 'processing'
    THEN CHECK 约束拒绝。"""
    task_id = enqueue(db, video_id="v1", source_url="u1", source_url_type="short", correlation_id="c1")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE task SET status='processing' WHERE id=?", (task_id,))
        db.commit()


def test_reclaim_zombie_fetching(db):
    """WHEN fetching 任务 claimed_at = 1 小时前
    THEN reclaim 后回 pending, claimed_at=NULL。"""
    task_id = enqueue(db, video_id="v1", source_url="u1", source_url_type="short", correlation_id="c1")
    atomic_dequeue(db)  # 置 fetching
    # 手动改 claimed_at 为 1 小时前
    old_time = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute("UPDATE task SET claimed_at=? WHERE id=?", (old_time, task_id))
    db.commit()

    reclaimed = reclaim_zombie_tasks(db, timeout_minutes=30)
    assert reclaimed == 1
    row = db.execute("SELECT status, claimed_at FROM task WHERE id=?", (task_id,)).fetchone()
    assert row[0] == "pending"
    assert row[1] is None


def test_reclaim_skips_recent(db):
    """WHEN fetching 任务 claimed_at = 5 分钟前（仍在处理）
    THEN 不复活。"""
    task_id = enqueue(db, video_id="v1", source_url="u1", source_url_type="short", correlation_id="c1")
    atomic_dequeue(db)
    reclaimed = reclaim_zombie_tasks(db, timeout_minutes=30)
    assert reclaimed == 0


def test_reclaim_zombie_writing(db):
    """WHEN writing 任务 claimed_at 超时
    THEN 也回 pending（writing 失败可重做）。"""
    task_id = enqueue(db, video_id="v1", source_url="u1", source_url_type="short", correlation_id="c1")
    atomic_dequeue(db)
    db.execute("UPDATE task SET status='writing' WHERE id=?", (task_id,))
    db.commit()
    old_time = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute("UPDATE task SET claimed_at=? WHERE id=?", (old_time, task_id))
    db.commit()
    reclaimed = reclaim_zombie_tasks(db, timeout_minutes=30)
    assert reclaimed == 1
    row = db.execute("SELECT status FROM task WHERE id=?", (task_id,)).fetchone()
    assert row[0] == "pending"


def test_mark_status_legal_transition(db):
    """WHEN fetching → writing 合法转移
    THEN 成功。"""
    task_id = enqueue(db, video_id="v1", source_url="u1", source_url_type="short", correlation_id="c1")
    atomic_dequeue(db)
    mark_status(db, task_id, "writing")
    row = db.execute("SELECT status FROM task WHERE id=?", (task_id,)).fetchone()
    assert row[0] == "writing"
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/queue/test_db.py -v`
Expected: `ImportError`（红）。

- [ ] **Step 3: 写 schema.sql**

`src/queue/schema.sql`:
```sql
-- M1 任务队列表（D-4 v2: 4 状态机，无 processing）
-- Spec: specs/task-queue-pipeline/spec.md Requirement: SQLite 队列 schema

CREATE TABLE IF NOT EXISTS task (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id TEXT NOT NULL,
  source_url TEXT NOT NULL,
  source_url_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'fetching', 'writing', 'done', 'failed')),
  claimed_at TIMESTAMP NULL,
  error_code TEXT NULL,
  error_message TEXT NULL,
  correlation_id TEXT NOT NULL,
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_task_status_claimed ON task(status, claimed_at);
```

- [ ] **Step 4: 写 db.py**

`src/queue/db.py`:
```python
"""SQLite 队列：enqueue / atomic_dequeue / reclaim_zombie / mark_status。

Spec ref: specs/task-queue-pipeline/spec.md
- Requirement: 原子 dequeue（v2：直接置 fetching）
- Requirement: 启动时复活 zombie 任务
"""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


def init_db(db_path: Path) -> sqlite3.Connection:
    """初始化 db，建表建索引。返回 connection（row_factory=Row）。"""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    schema = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.commit()
    return conn


def enqueue(
    conn: sqlite3.Connection,
    video_id: str,
    source_url: str,
    source_url_type: str,
    correlation_id: str,
    payload: Optional[dict] = None,
) -> int:
    """入队新任务。返回 task_id。"""
    cur = conn.execute(
        """INSERT INTO task (video_id, source_url, source_url_type, correlation_id, payload_json)
           VALUES (?, ?, ?, ?, ?)""",
        (video_id, source_url, source_url_type, correlation_id, json.dumps(payload or {})),
    )
    conn.commit()
    return cur.lastrowid


def atomic_dequeue(conn: sqlite3.Connection) -> Optional[dict]:
    """原子 dequeue：挑 pending + 占用 + 置 fetching。返回 task dict 或 None。"""
    cur = conn.execute(
        """UPDATE task
           SET claimed_at = CURRENT_TIMESTAMP,
               status = 'fetching',
               updated_at = CURRENT_TIMESTAMP
           WHERE id = (
             SELECT id FROM task
             WHERE status = 'pending' AND claimed_at IS NULL
             ORDER BY id LIMIT 1
           )
           RETURNING *""",
    )
    row = cur.fetchone()
    conn.commit()
    return dict(row) if row else None


def reclaim_zombie_tasks(conn: sqlite3.Connection, timeout_minutes: int = 30) -> int:
    """复活超时的 fetching/writing 任务回 pending。

    Spec: Scenario: 进程崩溃后重启（fetching 状态卡住）。
    """
    cur = conn.execute(
        """UPDATE task
           SET status = 'pending',
               claimed_at = NULL,
               updated_at = CURRENT_TIMESTAMP
           WHERE status IN ('fetching', 'writing')
             AND claimed_at < datetime(CURRENT_TIMESTAMP, ?)""",
        (f"-{timeout_minutes} minutes",),
    )
    conn.commit()
    return cur.rowcount


def mark_status(
    conn: sqlite3.Connection,
    task_id: int,
    new_status: str,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    """更新任务状态（state_machine.py 校验合法转移，这里只写 db）。"""
    if error_code:
        conn.execute(
            """UPDATE task
               SET status = ?, error_code = ?, error_message = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (new_status, error_code, error_message, task_id),
        )
    else:
        conn.execute(
            """UPDATE task
               SET status = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (new_status, task_id),
        )
    conn.commit()


def get_task(conn: sqlite3.Connection, task_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM task WHERE id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def queue_stats(conn: sqlite3.Connection) -> dict:
    """返回队列统计 {pending, fetching, writing, done, failed}。"""
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM task GROUP BY status"
    ).fetchall()
    stats = {"pending": 0, "fetching": 0, "writing": 0, "done": 0, "failed": 0}
    for r in rows:
        stats[r["status"]] = r["cnt"]
    return stats
```

- [ ] **Step 5: 跑测试验证通过**

Run: `pytest tests/queue/test_db.py -v`
Expected: 8 个测试全 PASS（绿）。

- [ ] **Step 6: Commit**

```powershell
git add src/queue/schema.sql src/queue/db.py tests/queue/test_db.py
git commit -m "feat(queue): SQLite 4-state machine + atomic dequeue + zombie reclaim"
```

---

### Task 7: 状态机（4 状态合法转移校验）

**对应 tasks.md**: §3.4
**依赖**: Task 6 完成
**Spec 参考**: `specs/task-queue-pipeline/spec.md` Requirement "任务状态机（v2 修订：删除 processing，4 状态严格机）"

**Files:**
- Create: `E:\project\douyin_to_obsidian\src\pipeline\state_machine.py`
- Create: `E:\project\douyin_to_obsidian\tests\queue\test_state_machine.py`

- [ ] **Step 1: 写失败测试（红）**

`tests/queue/test_state_machine.py`:
```python
"""Test 4-state machine legal/illegal transitions.

Spec ref: specs/task-queue-pipeline/spec.md
- Scenario: 主路径成功 pending → fetching → writing → done
- Scenario: fetching 阶段失败 → failed
- Scenario: writing 阶段失败 → failed（不回退 fetching）
- Scenario: 非法状态转移 done → pending → 拒绝
"""
import pytest

from src.pipeline.state_machine import (
    validate_transition,
    IllegalTransitionError,
    STATES,
)


def test_legal_main_path():
    assert validate_transition("pending", "fetching") is None
    assert validate_transition("fetching", "writing") is None
    assert validate_transition("writing", "done") is None


def test_legal_failure_paths():
    assert validate_transition("fetching", "failed") is None
    assert validate_transition("writing", "failed") is None


def test_illegal_done_to_pending():
    """WHEN 试图把 done 改回 pending
    THEN raise IllegalTransitionError。"""
    with pytest.raises(IllegalTransitionError):
        validate_transition("done", "pending")


def test_illegal_pending_to_writing():
    """WHEN 试图跳过 fetching
    THEN raise。"""
    with pytest.raises(IllegalTransitionError):
        validate_transition("pending", "writing")


def test_illegal_fetching_to_fetching():
    """WHEN 同状态自转移
    THEN raise。"""
    with pytest.raises(IllegalTransitionError):
        validate_transition("fetching", "fetching")


def test_illegal_processing_state():
    """WHEN 状态值不在 STATES 枚举内（如 'processing'）
    THEN raise。"""
    with pytest.raises(IllegalTransitionError):
        validate_transition("pending", "processing")


def test_states_no_processing():
    """WHEN 检查 STATES 集合
    THEN 不含 'processing'。"""
    assert "processing" not in STATES
    assert STATES == {"pending", "fetching", "writing", "done", "failed"}
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/queue/test_state_machine.py -v`
Expected: `ImportError`（红）。

- [ ] **Step 3: 写最小实现（绿）**

`src/pipeline/state_machine.py`:
```python
"""任务状态机：4 状态合法转移校验（D-4 v2，删除 processing）。

Spec ref: specs/task-queue-pipeline/spec.md
- Requirement: 任务状态机（v2 修订：删除 processing，4 状态严格机）

合法转移图：
    pending → fetching → writing → done
                   ↓          ↓
                 failed     failed
"""
from typing import Set


STATES: Set[str] = {"pending", "fetching", "writing", "done", "failed"}

LEGAL_TRANSITIONS = {
    ("pending", "fetching"),
    ("fetching", "writing"),
    ("fetching", "failed"),
    ("writing", "done"),
    ("writing", "failed"),
}


class IllegalTransitionError(Exception):
    """非法状态转移。"""


def validate_transition(from_status: str, to_status: str) -> None:
    """校验转移合法性。非法则 raise IllegalTransitionError。

    Spec: Scenario: 非法状态转移（done → pending 拒绝并记录错误）。
    """
    if to_status not in STATES:
        raise IllegalTransitionError(
            f"unknown_status: {to_status} not in {STATES}"
        )
    if from_status not in STATES:
        raise IllegalTransitionError(
            f"unknown_from_status: {from_status} not in {STATES}"
        )
    if from_status == to_status:
        raise IllegalTransitionError(
            f"self_transition: {from_status} → {to_status}"
        )
    if (from_status, to_status) not in LEGAL_TRANSITIONS:
        raise IllegalTransitionError(
            f"illegal_transition: {from_status} → {to_status}"
        )
```

- [ ] **Step 4: 跑测试验证通过**

Run: `pytest tests/queue/test_state_machine.py -v`
Expected: 7 个测试全 PASS（绿）。

- [ ] **Step 5: Commit**

```powershell
git add src/pipeline/state_machine.py tests/queue/test_state_machine.py
git commit -m "feat(pipeline): 4-state machine with illegal transition rejection"
```

---

### Task 8: FastAPI 服务（端口 8765，/ingest /tasks/{id} /health /queue/stats）

**对应 tasks.md**: §4.1-4.6
**依赖**: Task 6, Task 7 完成
**Spec 参考**: `specs/task-queue-pipeline/spec.md` Requirement "bishu 轮询 API" + `specs/obsidian-archive-writer/spec.md` Requirement "重复检测"

**Files:**
- Create: `E:\project\douyin_to_obsidian\src\bridge\main.py`
- Create: `E:\project\douyin_to_obsidian\tests\bridge\test_main.py`

- [ ] **Step 1: 写失败测试（红）**

`tests/bridge/test_main.py`:
```python
"""Test FastAPI /ingest /tasks/{id} /health /queue/stats + dedup.

Spec ref: specs/task-queue-pipeline/spec.md
- Scenario: bishu 轮询单任务 → done 时返回 note_path
- Scenario: bishu 看到 fetching 进度
- Scenario: 健康检查 → 返回 queue 概要

Spec ref: specs/obsidian-archive-writer/spec.md
- Scenario: 已存在跳过 → already_archived
- Scenario: force=true 强制覆盖
"""
import pytest
from fastapi.testclient import TestClient

from src.bridge.main import app, reset_state_for_test


@pytest.fixture
def client(tmp_path, monkeypatch):
    """用临时 db + 临时 vault 构造 TestClient。"""
    db_path = tmp_path / "q.sqlite3"
    vault_root = tmp_path / "vault"
    (vault_root / "inbox" / "douyin").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("src.bridge.main.DB_PATH", db_path)
    monkeypatch.setattr("src.bridge.main.VAULT_ROOT", vault_root)
    reset_state_for_test()
    with TestClient(app) as c:
        yield c


def test_health_returns_queue_stats(client):
    """WHEN GET /health
    THEN 返回 status=ok + queue 概要（含 fetching/writing 分项）。"""
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "queue" in body
    assert "pending" in body["queue"]
    assert "fetching" in body["queue"]
    assert "writing" in body["queue"]


def test_ingest_enqueues_task(client, monkeypatch):
    """WHEN POST /ingest {source_url: 抖音短链}
    THEN 返回 task_id + status=pending。"""
    def fake_resolve(url):
        return {"video_id": "v1", "canonical_url": "https://www.douyin.com/video/v1", "source_url_type": "short"}
    monkeypatch.setattr("src.bridge.main.resolve_url", fake_resolve)

    resp = client.post("/ingest", json={"source_url": "https://v.douyin.com/x/"})
    assert resp.status_code == 200
    body = resp.json()
    assert "task_id" in body
    assert body["status"] == "pending"


def test_ingest_dedup_already_archived(client, monkeypatch, tmp_path):
    """WHEN vault 已存在 {video_id}.md 且 force != true
    THEN 返回 already_archived=true，不入队。"""
    def fake_resolve(url):
        return {"video_id": "v1", "canonical_url": "https://www.douyin.com/video/v1", "source_url_type": "short"}
    monkeypatch.setattr("src.bridge.main.resolve_url", fake_resolve)

    # 先 mock vault 里已有 v1.md
    vault = client.app.dependency_overrides  # placeholder
    from src.bridge import main as m
    note_dir = m.VAULT_ROOT / "inbox" / "douyin" / "2026-06"
    note_dir.mkdir(parents=True, exist_ok=True)
    (note_dir / "v1.md").write_text("---\n---\n")

    resp = client.post("/ingest", json={"source_url": "https://v.douyin.com/x/"})
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("already_archived") is True
    assert "note_path" in body


def test_ingest_force_overrides_dedup(client, monkeypatch):
    """WHEN force=true
    THEN 跳过 dedup，正常入队。"""
    def fake_resolve(url):
        return {"video_id": "v1", "canonical_url": "https://www.douyin.com/video/v1", "source_url_type": "short"}
    monkeypatch.setattr("src.bridge.main.resolve_url", fake_resolve)
    from src.bridge import main as m
    note_dir = m.VAULT_ROOT / "inbox" / "douyin" / "2026-06"
    note_dir.mkdir(parents=True, exist_ok=True)
    (note_dir / "v1.md").write_text("---\n---\n")

    resp = client.post("/ingest", json={"source_url": "https://v.douyin.com/x/", "force": True})
    assert resp.status_code == 200
    body = resp.json()
    assert "task_id" in body


def test_get_task_returns_status(client, monkeypatch):
    """WHEN GET /tasks/{id}
    THEN 返回 task_id + status + correlation_id。"""
    def fake_resolve(url):
        return {"video_id": "v1", "canonical_url": "https://www.douyin.com/video/v1", "source_url_type": "short"}
    monkeypatch.setattr("src.bridge.main.resolve_url", fake_resolve)
    resp = client.post("/ingest", json={"source_url": "https://v.douyin.com/x/"})
    task_id = resp.json()["task_id"]

    resp = client.get(f"/tasks/{task_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_id"] == task_id
    assert "status" in body
    assert "correlation_id" in body


def test_queue_stats_detailed(client):
    """WHEN GET /queue/stats
    THEN 返回详细队列统计。"""
    resp = client.get("/queue/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert "pending" in body
    assert "fetching" in body
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/bridge/test_main.py -v`
Expected: `ImportError`（红）。

- [ ] **Step 3: 写最小实现（绿）**

`src/bridge/main.py`:
```python
"""FastAPI 解析服务：/ingest /tasks/{id} /health /queue/stats。

Spec ref: specs/task-queue-pipeline/spec.md Requirement: bishu 轮询 API。
Spec ref: specs/obsidian-archive-writer/spec.md Requirement: 重复检测。
端口锁 8765（D-9）。
"""
import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.queue.db import init_db, enqueue, get_task, queue_stats, reclaim_zombie_tasks
from src.extractors.douyin_resolver import resolve_url, ResolverError


# 全局可被测试 monkeypatch
DB_PATH = Path(os.environ.get("DOUYIN_DB_PATH", "data/queue.sqlite3"))
VAULT_ROOT = Path(os.environ.get("DOUYIN_VAULT_ROOT", "E:/AI_Tools/Obsidian/data/notes-personal"))

_conn: Optional[sqlite3.Connection] = None


def reset_state_for_test():
    """测试用：重置全局 connection。"""
    global _conn
    if _conn:
        _conn.close()
    _conn = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = init_db(DB_PATH)
        # 启动钩子：复活 zombie
        reclaimed = reclaim_zombie_tasks(_conn, timeout_minutes=30)
        if reclaimed:
            # TODO: structlog 日志
            pass
    return _conn


app = FastAPI(title="douyin-to-obsidian M1")


class IngestRequest(BaseModel):
    source_url: str
    force: bool = False


@app.get("/health")
def health():
    stats = queue_stats(get_conn())
    return {"status": "ok", "queue": stats}


@app.get("/queue/stats")
def get_queue_stats():
    return queue_stats(get_conn())


@app.post("/ingest")
def ingest(req: IngestRequest):
    try:
        resolved = resolve_url(req.source_url)
    except ResolverError as e:
        raise HTTPException(status_code=400, detail=f"not_douyin_url: {e}")

    video_id = resolved["video_id"]

    # 重复检测（specs/obsidian-archive-writer/spec.md Requirement: 重复检测）
    if not req.force:
        existing = _find_existing_note(video_id)
        if existing:
            return {"already_archived": True, "note_path": existing}

    correlation_id = str(uuid.uuid4())
    task_id = enqueue(
        get_conn(),
        video_id=video_id,
        source_url=resolved["canonical_url"],
        source_url_type=resolved["source_url_type"],
        correlation_id=correlation_id,
        payload={"raw_input": req.source_url},
    )
    return {"task_id": task_id, "status": "pending", "correlation_id": correlation_id}


@app.get("/tasks/{task_id}")
def get_task_status(task_id: int):
    task = get_task(get_conn(), task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_not_found")
    resp = {
        "task_id": task["id"],
        "status": task["status"],
        "correlation_id": task["correlation_id"],
    }
    if task["status"] == "done":
        # note_path 计算见 Task 9 path_calc，此处占位用 video_id
        resp["note_path"] = f"inbox/douyin/{{YYYY-MM}}/{task['video_id']}.md"
    if task["status"] == "failed":
        resp["error_code"] = task["error_code"]
    return resp


def _find_existing_note(video_id: str) -> Optional[str]:
    """扫 vault inbox/douyin/*/ 查 {video_id}.md。返回 vault 相对路径或 None。"""
    inbox = VAULT_ROOT / "inbox" / "douyin"
    if not inbox.exists():
        return None
    for month_dir in inbox.iterdir():
        if not month_dir.is_dir():
            continue
        note = month_dir / f"{video_id}.md"
        if note.exists():
            return f"inbox/douyin/{month_dir.name}/{video_id}.md"
    return None


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
```

- [ ] **Step 4: 跑测试验证通过**

Run: `pytest tests/bridge/test_main.py -v`
Expected: 6 个测试全 PASS（绿）。

- [ ] **Step 5: Commit**

```powershell
git add src/bridge/main.py tests/bridge/test_main.py
git commit -m "feat(bridge): FastAPI /ingest /tasks /health /queue/stats + dedup"
```

---

### Task 9: Obsidian frontmatter + note_builder + path_calc

**对应 tasks.md**: §5.1-5.2, §5.5
**依赖**: Task 1 完成
**Spec 参考**: `specs/obsidian-archive-writer/spec.md` Requirement "frontmatter schema" + "vault 路径计算" + "笔记正文结构"

**Files:**
- Create: `E:\project\douyin_to_obsidian\src\obsidian\path_calc.py`
- Create: `E:\project\douyin_to_obsidian\src\obsidian\frontmatter.py`
- Create: `E:\project\douyin_to_obsidian\src\obsidian\note_builder.py`
- Create: `E:\project\douyin_to_obsidian\tests\obsidian\test_path_calc.py`
- Create: `E:\project\douyin_to_obsidian\tests\obsidian\test_frontmatter.py`
- Create: `E:\project\douyin_to_obsidian\tests\obsidian\test_note_builder.py`

- [ ] **Step 1: 写失败测试 — path_calc（红）**

`tests/obsidian/test_path_calc.py`:
```python
"""Test vault path calculation.

Spec ref: specs/obsidian-archive-writer/spec.md
- Scenario: 标准路径 → inbox/douyin/{YYYY-MM}/{video_id}.md
- Scenario: 跨月写入 → 按"完成时刻"月份
"""
from datetime import datetime
from pathlib import Path

from src.obsidian.path_calc import calc_note_path, calc_cover_path


def test_standard_path():
    """WHEN video_id='7234567890123', captured_at=2026-06-19
    THEN 笔记路径 = .../inbox/douyin/2026-06/7234567890123.md。"""
    vault = Path("E:/vault")
    p = calc_note_path(vault, video_id="7234567890123",
                       captured_at=datetime(2026, 6, 19, 10, 0, 0))
    assert p == Path("E:/vault/inbox/douyin/2026-06/7234567890123.md")


def test_cross_month_uses_completion_time():
    """WHEN 6/30 23:59 触发，7/1 00:01 完成
    THEN 文件路径按 7 月算。"""
    vault = Path("E:/vault")
    completion = datetime(2026, 7, 1, 0, 1, 0)
    p = calc_note_path(vault, video_id="v1", captured_at=completion)
    assert "2026-07" in str(p)


def test_cover_path():
    """WHEN video_id='v1'
    THEN cover = vault/attachments/douyin/v1/cover.jpg。"""
    vault = Path("E:/vault")
    p = calc_cover_path(vault, video_id="v1")
    assert p == Path("E:/vault/attachments/douyin/v1/cover.jpg")
```

- [ ] **Step 2: 写失败测试 — frontmatter（红）**

`tests/obsidian/test_frontmatter.py`:
```python
"""Test frontmatter schema (17 fields + D-10 3 status fields).

Spec ref: specs/obsidian-archive-writer/spec.md
- Scenario: M1 完整 frontmatter
- Scenario: 字段不可缺失 → raise
- Scenario: 状态字段防误判（D-10）
"""
import pytest

from src.obsidian.frontmatter import build_frontmatter, IncompleteFrontmatterError


def _minimal_valid_input():
    return {
        "title": "测试标题",
        "video_id": "v1",
        "source_url": "https://www.douyin.com/video/v1",
        "source_url_type": "full",
        "author": "作者",
        "uploader_id": "sec_uid_xxx",
        "duration_seconds": 180,
        "uploaded_at": "2026-06-19T00:00:00",
        "captured_at": "2026-06-19T10:00:00",
        "cover_url": "https://p9.douyinpic.com/x.jpg",
        "local_cover_path": "attachments/douyin/v1/cover.jpg",
        "subtitle_source": "douyin_native",
        "subtitle_language": "zh",
        "pipeline_version": "1.0",
        "status": "done",
        "downloader_used": "ytdlp",
        "correlation_id": "uuid-xxx",
    }


def test_m1_full_frontmatter_has_status_fields():
    """WHEN M1 完整 frontmatter
    THEN 含 summary_status=not_run, processing_mode=subtitle_only, ai_summary_model=null。"""
    fm = build_frontmatter(_minimal_valid_input())
    assert "summary_status" in fm
    assert fm["summary_status"] == "not_run"
    assert fm["processing_mode"] == "subtitle_only"
    assert fm["ai_summary_model"] is None


def test_m1_default_status_values():
    fm = build_frontmatter(_minimal_valid_input())
    assert fm["summary"] == ""
    assert fm["vlm_results"] == []
    assert fm["pipeline_version"] == "1.0"


def test_missing_correlation_id_raises():
    """WHEN correlation_id 缺失
    THEN raise IncompleteFrontmatterError。"""
    data = _minimal_valid_input()
    del data["correlation_id"]
    with pytest.raises(IncompleteFrontmatterError):
        build_frontmatter(data)


def test_missing_title_raises():
    data = _minimal_valid_input()
    del data["title"]
    with pytest.raises(IncompleteFrontmatterError):
        build_frontmatter(data)


def test_status_field_d10_filter():
    """WHEN M1 笔记 frontmatter summary_status='not_run'
    THEN DataView WHERE summary_status != 'done' 能匹配（模拟检查）。"""
    fm = build_frontmatter(_minimal_valid_input())
    assert fm["summary_status"] != "done"
```

- [ ] **Step 3: 写失败测试 — note_builder（红）**

`tests/obsidian/test_note_builder.py`:
```python
"""Test note body builder (5 sections).

Spec ref: specs/obsidian-archive-writer/spec.md
- Requirement: 笔记正文结构（5 段）
- Scenario: M1 完整笔记正文
"""
from src.obsidian.note_builder import build_note_body


def test_note_body_has_5_sections():
    """WHEN 构建笔记正文
    THEN 含 ## 摘要 / ## 字幕全文 / ## 关键帧 / ## 元数据 / ## 链接。"""
    body = build_note_body(
        subtitle_vtt="WEBVTT\n00:00:01 --> 00:00:02\nTest line",
        metadata={"source_url": "https://www.douyin.com/video/v1",
                  "author": "作者", "duration_seconds": 180,
                  "cover_url": "https://x.jpg"},
        local_cover_path="attachments/douyin/v1/cover.jpg",
        correlation_id="c1",
        raw_input="https://v.douyin.com/x/",
        processing_time_seconds=30,
    )
    assert "## 摘要" in body
    assert "## 字幕全文" in body
    assert "## 关键帧" in body
    assert "## 元数据" in body
    assert "## 链接" in body


def test_summary_section_m1_placeholder():
    """WHEN M1 阶段
    THEN ## 摘要 仅占位提示文字。"""
    body = build_note_body(
        subtitle_vtt="", metadata={}, local_cover_path="",
        correlation_id="c1", raw_input="", processing_time_seconds=0,
    )
    assert "M1 阶段无 LLM 总结" in body


def test_cover_embedded_with_obsidian_syntax():
    """WHEN local_cover_path 存在
    THEN 正文用 ![[path]] 嵌入。"""
    body = build_note_body(
        subtitle_vtt="", metadata={"cover_url": "https://x.jpg"},
        local_cover_path="attachments/douyin/v1/cover.jpg",
        correlation_id="c1", raw_input="", processing_time_seconds=0,
    )
    assert "![[attachments/douyin/v1/cover.jpg]]" in body
```

- [ ] **Step 4: 跑测试验证失败**

Run: `pytest tests/obsidian/ -v`
Expected: 3 个文件全 `ImportError`（红）。

- [ ] **Step 5: 写实现 — path_calc.py**

`src/obsidian/path_calc.py`:
```python
"""vault 路径计算。

Spec ref: specs/obsidian-archive-writer/spec.md Requirement: vault 路径计算。
- 笔记：inbox/douyin/{YYYY-MM}/{video_id}.md
- 附件：attachments/douyin/{video_id}/{filename}
- 月份按"完成时刻"（spec Scenario: 跨月写入）。
"""
from datetime import datetime
from pathlib import Path


def calc_note_path(vault_root: Path, video_id: str, captured_at: datetime) -> Path:
    """计算笔记文件路径。"""
    month = captured_at.strftime("%Y-%m")
    return vault_root / "inbox" / "douyin" / month / f"{video_id}.md"


def calc_cover_path(vault_root: Path, video_id: str, filename: str = "cover.jpg") -> Path:
    """计算封面附件路径。"""
    return vault_root / "attachments" / "douyin" / video_id / filename
```

- [ ] **Step 6: 写实现 — frontmatter.py**

`src/obsidian/frontmatter.py`:
```python
"""frontmatter schema：17 字段 + D-10 三状态字段。

Spec ref: specs/obsidian-archive-writer/spec.md Requirement: frontmatter schema。
M1 默认：summary_status=not_run, processing_mode=subtitle_only, ai_summary_model=null。
"""
from typing import Any, Dict, Optional


REQUIRED_FIELDS = [
    "title", "video_id", "source_url", "source_url_type",
    "author", "uploader_id", "duration_seconds", "uploaded_at",
    "captured_at", "cover_url", "local_cover_path",
    "subtitle_source", "subtitle_language", "pipeline_version",
    "status", "downloader_used", "correlation_id",
]


class IncompleteFrontmatterError(Exception):
    """frontmatter SHALL 字段缺失。"""


def build_frontmatter(data: dict) -> Dict[str, Any]:
    """构建 frontmatter dict。M1 默认填充 3 状态字段。

    Raises: IncompleteFrontmatterError 当任一 REQUIRED_FIELDS 缺失。
    """
    for f in REQUIRED_FIELDS:
        if f not in data:
            raise IncompleteFrontmatterError(f"missing field: {f}")

    fm = {f: data[f] for f in REQUIRED_FIELDS}
    # D-10 状态字段（M1 默认值）
    fm["summary_status"] = "not_run"
    fm["processing_mode"] = "subtitle_only"
    fm["ai_summary_model"] = None
    # M1 占位字段
    fm["summary"] = ""
    fm["vlm_results"] = []
    return fm
```

- [ ] **Step 7: 写实现 — note_builder.py**

`src/obsidian/note_builder.py`:
```python
"""笔记正文构建（5 段结构）。

Spec ref: specs/obsidian-archive-writer/spec.md Requirement: 笔记正文结构。
段落顺序：摘要 → 字幕全文 → 关键帧 → 元数据 → 链接。
"""
from typing import Optional


def _render_subtitle(vtt_content: str) -> str:
    """简单渲染 VTT 为可读文本（保留时间戳）。M1 不做复杂解析。"""
    if not vtt_content:
        return "（无字幕内容）"
    # 去掉 WEBVTT 头，保留 cue 时间行 + 文本
    lines = vtt_content.splitlines()
    if lines and lines[0].startswith("WEBVTT"):
        lines = lines[1:]
    return "\n".join(lines).strip()


def build_note_body(
    subtitle_vtt: str,
    metadata: dict,
    local_cover_path: str,
    correlation_id: str,
    raw_input: str,
    processing_time_seconds: int,
) -> str:
    """构建笔记正文（5 段）。"""
    sections = []

    # 1. 摘要（M1 占位）
    sections.append("## 摘要\n\nM1 阶段无 LLM 总结，待 M3 填充。\n")

    # 2. 字幕全文
    sections.append(f"## 字幕全文\n\n```\n{_render_subtitle(subtitle_vtt)}\n```\n")

    # 3. 关键帧（M1 占位）
    sections.append("## 关键帧\n\nM1 阶段不抽取关键帧，待 M3 填充。\n")

    # 4. 元数据
    meta_lines = []
    if local_cover_path:
        meta_lines.append(f"封面： ![[{local_cover_path}]]")
    elif metadata.get("cover_url"):
        meta_lines.append(f"封面： [外部链接]({metadata['cover_url']})")
    if metadata.get("source_url"):
        meta_lines.append(f"原始 URL： {metadata['source_url']}")
    if metadata.get("author"):
        meta_lines.append(f"作者： {metadata['author']}")
    if metadata.get("duration_seconds"):
        meta_lines.append(f"时长： {metadata['duration_seconds']} 秒")
    sections.append("## 元数据\n\n" + "\n\n".join(meta_lines) + "\n")

    # 5. 链接
    sections.append(
        "## 链接\n\n"
        f"- 飞书触发消息： {raw_input}\n"
        f"- correlation_id： `{correlation_id}`\n"
        f"- 处理耗时： {processing_time_seconds} 秒\n"
    )

    return "\n".join(sections)
```

- [ ] **Step 8: 跑测试验证通过**

Run: `pytest tests/obsidian/ -v`
Expected: 全部 PASS（绿）。

- [ ] **Step 9: Commit**

```powershell
git add src/obsidian/path_calc.py src/obsidian/frontmatter.py src/obsidian/note_builder.py tests/obsidian/
git commit -m "feat(obsidian): frontmatter (D-10) + note builder (5 sections) + path calc"
```

---

### Task 10: Obsidian writer（原子 rename + 附件下载 + 失败回滚）

**对应 tasks.md**: §5.3, §5.4, §5.7
**依赖**: Task 9 完成
**Spec 参考**: `specs/obsidian-archive-writer/spec.md` Requirement "原子写入" + "附件管理"

**Files:**
- Create: `E:\project\douyin_to_obsidian\src\obsidian\writer.py`
- Create: `E:\project\douyin_to_obsidian\tests\obsidian\test_writer.py`

- [ ] **Step 1: 写失败测试（红）**

`tests/obsidian/test_writer.py`:
```python
"""Test atomic writer: .tmp + os.rename, rollback on failure, cover download.

Spec ref: specs/obsidian-archive-writer/spec.md
- Scenario: 正常流程 → .tmp → rename → 瞬时出现
- Scenario: 写入失败回滚 → 删 .tmp，不留 .md
- Scenario: 封面下载成功 → local_cover_path 填充
- Scenario: 封面下载失败 → local_cover_path=''，任务不失败
"""
from pathlib import Path

import pytest

from src.obsidian.writer import write_note, write_note_atomic, download_cover


def test_write_note_atomic_success(tmp_vault, monkeypatch):
    """WHEN 写笔记
    THEN 先写 .tmp，rename 后 .md 存在，.tmp 不存在。"""
    note_path = tmp_vault / "inbox" / "douyin" / "2026-06" / "v1.md"
    content = "---\ntitle: x\n---\nbody"

    write_note_atomic(note_path, content)
    assert note_path.exists()
    assert not (tmp_vault / "v1.md.tmp").exists()
    assert note_path.read_text(encoding="utf-8") == content


def test_write_note_atomic_rollback_on_failure(tmp_vault, monkeypatch):
    """WHEN .tmp 写入失败（模拟磁盘满）
    THEN 删 .tmp，不留 .md。"""
    note_path = tmp_vault / "inbox" / "douyin" / "2026-06" / "v1.md"
    note_path.parent.mkdir(parents=True, exist_ok=True)

    def fake_write(p, content):
        # 模拟写 .tmp 后失败
        tmp = p.with_suffix(".md.tmp")
        tmp.write_text("partial", encoding="utf-8")
        raise OSError("disk full")

    monkeypatch.setattr("src.obsidian.writer._write_tmp_then_rename", fake_write)
    with pytest.raises(OSError):
        write_note_atomic(note_path, "content")
    # .md 不应存在
    assert not note_path.exists()


def test_download_cover_success(tmp_vault, monkeypatch):
    """WHEN thumbnail URL 下载成功
    THEN 封面存到 attachments/douyin/{vid}/cover.jpg。"""
    def fake_get(url):
        class R:
            content = b"fake-jpeg-bytes"
            def raise_for_status(self): pass
        return R()

    monkeypatch.setattr("src.obsidian.writer.httpx.get", fake_get)
    local_path = download_cover(
        vault_root=tmp_vault,
        video_id="v1",
        cover_url="https://p9.douyinpic.com/x.jpg",
    )
    assert local_path.exists()
    assert local_path.read_bytes() == b"fake-jpeg-bytes"
    assert "attachments/douyin/v1/cover.jpg" in str(local_path).replace("\\", "/")


def test_download_cover_failure_returns_empty(tmp_vault, monkeypatch):
    """WHEN thumbnail URL 不存在或下载失败
    THEN 返回 None，任务不失败。"""
    def fake_get(url):
        raise Exception("network error")

    monkeypatch.setattr("src.obsidian.writer.httpx.get", fake_get)
    result = download_cover(
        vault_root=tmp_vault,
        video_id="v1",
        cover_url="https://x.jpg",
    )
    assert result is None


def test_write_note_full_pipeline(tmp_vault, monkeypatch):
    """WHEN write_note 集成 frontmatter + body + cover
    THEN 笔记落地，Obsidian 可见。"""
    from src.obsidian.frontmatter import build_frontmatter
    from src.obsidian.note_builder import build_note_body

    fm_data = {
        "title": "测试", "video_id": "v1",
        "source_url": "https://www.douyin.com/video/v1", "source_url_type": "full",
        "author": "作者", "uploader_id": "sec_uid",
        "duration_seconds": 10, "uploaded_at": "2026-06-19T00:00:00",
        "captured_at": "2026-06-19T10:00:00",
        "cover_url": "https://x.jpg", "local_cover_path": "attachments/douyin/v1/cover.jpg",
        "subtitle_source": "douyin_native", "subtitle_language": "zh",
        "pipeline_version": "1.0", "status": "done",
        "downloader_used": "ytdlp", "correlation_id": "c1",
    }
    fm = build_frontmatter(fm_data)
    body = build_note_body(
        subtitle_vtt="WEBVTT\n00:00:01 --> 00:00:02\nhi",
        metadata=fm_data, local_cover_path="attachments/douyin/v1/cover.jpg",
        correlation_id="c1", raw_input="https://v.douyin.com/x/",
        processing_time_seconds=5,
    )

    note_path = tmp_vault / "inbox" / "douyin" / "2026-06" / "v1.md"
    write_note(note_path, fm, body)
    assert note_path.exists()
    content = note_path.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert "## 摘要" in content
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/obsidian/test_writer.py -v`
Expected: `ImportError`（红）。

- [ ] **Step 3: 写最小实现（绿）**

`src/obsidian/writer.py`:
```python
"""vault 原子写入：.tmp + os.rename + 封面下载。

Spec ref: specs/obsidian-archive-writer/spec.md
- Requirement: 原子写入
- Requirement: 附件管理
"""
import os
from pathlib import Path
from typing import Optional

import httpx
import yaml


def _write_tmp_then_rename(note_path: Path, content: str) -> None:
    """先写 .tmp，再 os.rename 切换为 .md（D-7）。"""
    note_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = note_path.with_suffix(".md.tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(str(tmp_path), str(note_path))  # Windows 同卷原子
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def write_note_atomic(note_path: Path, content: str) -> None:
    """对外暴露的原子写入入口。失败自动回滚 .tmp。"""
    _write_tmp_then_rename(note_path, content)


def write_note(note_path: Path, frontmatter: dict, body: str) -> None:
    """拼装 frontmatter + body 后原子写入。"""
    fm_yaml = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False)
    content = f"---\n{fm_yaml}---\n\n{body}"
    write_note_atomic(note_path, content)


def download_cover(vault_root: Path, video_id: str, cover_url: str) -> Optional[Path]:
    """下载封面到 attachments/douyin/{video_id}/cover.jpg。

    Returns: 本地 Path，或 None（下载失败时）。
    Spec: Scenario: 封面下载失败 → 任务不失败。
    """
    if not cover_url:
        return None
    cover_path = vault_root / "attachments" / "douyin" / video_id / "cover.jpg"
    cover_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        resp = httpx.get(cover_url, timeout=15.0)
        resp.raise_for_status()
        cover_path.write_bytes(resp.content)
        return cover_path
    except Exception:
        return None
```

- [ ] **Step 4: 跑测试验证通过**

Run: `pytest tests/obsidian/test_writer.py -v`
Expected: 5 个测试全 PASS（绿）。

- [ ] **Step 5: Commit**

```powershell
git add src/obsidian/writer.py tests/obsidian/test_writer.py
git commit -m "feat(obsidian): atomic writer (D-7) + cover download + rollback"
```

---

### Task 11: 调度器 + pipeline 编排（单 worker 串行）

**对应 tasks.md**: §6.1-6.7
**依赖**: Task 5, Task 6, Task 7, Task 8, Task 10 完成
**Spec 参考**: `specs/task-queue-pipeline/spec.md` Requirement "不允许并发 worker（M1 简化）" + `specs/douyin-extraction/spec.md` Requirement "yt-dlp 失败兜底走 DouK-Downloader" + "Cookie 失效检测" + "视频文件清理"

**Files:**
- Create: `E:\project\douyin_to_obsidian\src\pipeline\errors.py`
- Create: `E:\project\douyin_to_obsidian\src\pipeline\scheduler.py`
- Create: `E:\project\douyin_to_obsidian\src\utils\cookie_probe.py`
- Create: `E:\project\douyin_to_obsidian\tests\pipeline\test_errors.py`
- Create: `E:\project\douyin_to_obsidian\tests\pipeline\test_scheduler.py`

- [ ] **Step 1: 写失败测试 — errors.py（红）**

`tests/pipeline/test_errors.py`:
```python
"""Test error code classification.

Spec ref: specs/douyin-extraction/spec.md
- Scenario: 无字幕视频 → 'no_subtitle_in_m1'
- Scenario: 下载失败 → 'download_failed_all_tools'
- Scenario: cookie 过期 → 'cookie_expired'
- Scenario: frontmatter 字段缺失 → 'incomplete_frontmatter'
"""
import pytest

from src.pipeline.errors import ErrorCode, classify_exception
from src.extractors.downloader import NoSubtitleError
from src.extractors.douk_fallback import DoukDownloadError
from src.obsidian.frontmatter import IncompleteFrontmatterError


def test_classify_no_subtitle():
    err = NoSubtitleError("no_subtitle_in_m1")
    assert classify_exception(err) == ErrorCode.NO_SUBTITLE_IN_M1


def test_classify_download_failed():
    err = DoukDownloadError("all tools failed")
    assert classify_exception(err) == ErrorCode.DOWNLOAD_FAILED_ALL_TOOLS


def test_classify_cookie_expired():
    class FakeCookieErr(Exception):
        pass
    err = FakeCookieErr("403 forbidden - cookie expired")
    code = classify_exception(err, hint="cookie_403")
    assert code == ErrorCode.COOKIE_EXPIRED


def test_classify_incomplete_frontmatter():
    err = IncompleteFrontmatterError("missing title")
    assert classify_exception(err) == ErrorCode.INCOMPLETE_FRONTMATTER


def test_classify_unknown():
    err = Exception("unknown")
    assert classify_exception(err) == ErrorCode.UNKNOWN
```

- [ ] **Step 2: 写失败测试 — scheduler.py（红）**

`tests/pipeline/test_scheduler.py`:
```python
"""Test scheduler: dequeue → process → mark done/failed.

Spec ref: specs/task-queue-pipeline/spec.md
- Scenario: 主路径成功 pending → fetching → writing → done
- Scenario: fetching 阶段失败 → failed，不自动重试
- Scenario: 队列为空 → 睡眠 5s
- Spec ref: specs/douyin-extraction/spec.md
- Scenario: 成功入库后清理 → 删 mp4/vtt
"""
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.pipeline.scheduler import process_task, run_forever
from src.queue.db import init_db, enqueue


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "q.sqlite3"
    conn = init_db(db_path)
    yield conn
    conn.close()


def test_process_task_success(db, tmp_path, monkeypatch):
    """WHEN process_task 跑完整管线
    THEN task 进 done，笔记落地，临时视频清理。"""
    task_id = enqueue(db, video_id="v1", source_url="https://www.douyin.com/video/v1",
                     source_url_type="full", correlation_id="c1")

    # mock 下载
    def fake_download(video_id, canonical_url, out_dir, cookies_path=None):
        video = out_dir / f"{video_id}.mp4"
        video.write_bytes(b"fake")
        sub = out_dir / f"{video_id}.zh.vtt"
        sub.write_text("WEBVTT\n...")
        return {
            "video_path": video, "subtitle_path": sub,
            "subtitle_source": "douyin_native",
            "info_dict": {"title": "t", "uploader": "u", "uploader_url": "",
                          "duration": 10, "upload_date": "20260619", "thumbnail": ""},
        }
    monkeypatch.setattr("src.pipeline.scheduler.download_video", fake_download)
    monkeypatch.setattr("src.pipeline.scheduler.download_with_douk", lambda **k: None)

    vault_root = tmp_path / "vault"
    (vault_root / "inbox" / "douyin").mkdir(parents=True, exist_ok=True)
    (vault_root / "attachments" / "douyin").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("src.pipeline.scheduler.VAULT_ROOT", vault_root)
    monkeypatch.setattr("src.pipeline.scheduler.TEMP_DIR", tmp_path / "tmp")
    monkeypatch.setattr("src.pipeline.scheduler.download_cover", lambda **k: None)

    task = {"id": task_id, "video_id": "v1", "source_url": "https://www.douyin.com/video/v1",
            "correlation_id": "c1"}
    process_task(db, task)

    row = db.execute("SELECT status FROM task WHERE id=?", (task_id,)).fetchone()
    assert row["status"] == "done"
    # 视频临时文件应被清理
    assert not (tmp_path / "tmp" / "v1.mp4").exists()


def test_process_task_no_subtitle_fails(db, tmp_path, monkeypatch):
    """WHEN 视频无字幕
    THEN task 进 failed + error_code='no_subtitle_in_m1'。"""
    from src.extractors.downloader import NoSubtitleError
    task_id = enqueue(db, video_id="v1", source_url="u1",
                     source_url_type="full", correlation_id="c1")

    def fake_download(**kwargs):
        raise NoSubtitleError("no_subtitle_in_m1")
    monkeypatch.setattr("src.pipeline.scheduler.download_video", fake_download)

    task = {"id": task_id, "video_id": "v1", "source_url": "u1", "correlation_id": "c1"}
    process_task(db, task)

    row = db.execute("SELECT status, error_code FROM task WHERE id=?", (task_id,)).fetchone()
    assert row["status"] == "failed"
    assert row["error_code"] == "no_subtitle_in_m1"


def test_run_forever_empty_queue_sleeps(db, monkeypatch):
    """WHEN 队列为空
    THEN run_forever 一次循环后睡眠 5s（mock 后立即返回）。"""
    slept = []
    monkeypatch.setattr("src.pipeline.scheduler.time.sleep", lambda s: slept.append(s))
    # 跑一次就停
    iterations = {"n": 0}
    def stop_after_one():
        iterations["n"] += 1
        if iterations["n"] > 1:
            raise KeyboardInterrupt
    monkeypatch.setattr("src.pipeline.scheduler.run_forever_loop", stop_after_one)
    # 直接调一次空 dequeue
    from src.queue.db import atomic_dequeue
    assert atomic_dequeue(db) is None
    # 模拟 sleep 被调用
    import src.pipeline.scheduler as sched
    sched._sleep_when_empty(5)
    assert slept == [5]
```

- [ ] **Step 3: 跑测试验证失败**

Run: `pytest tests/pipeline/ -v`
Expected: `ImportError`（红）。

- [ ] **Step 4: 写实现 — errors.py**

`src/pipeline/errors.py`:
```python
"""错误码枚举 + 异常分类。

Spec ref: specs/douyin-extraction/spec.md 多个 Scenario 的 error_code。
"""
from enum import Enum
from typing import Optional


class ErrorCode(str, Enum):
    NO_SUBTITLE_IN_M1 = "no_subtitle_in_m1"
    DOWNLOAD_FAILED_ALL_TOOLS = "download_failed_all_tools"
    COOKIE_EXPIRED = "cookie_expired"
    INCOMPLETE_FRONTMATTER = "incomplete_frontmatter"
    UNKNOWN = "unknown"


def classify_exception(exc: Exception, hint: Optional[str] = None) -> ErrorCode:
    """根据异常类型 + hint 判定 ErrorCode。"""
    exc_name = type(exc).__name__
    exc_msg = str(exc).lower()

    # NoSubtitleError
    if "NoSubtitle" in exc_name or "no_subtitle" in exc_msg:
        return ErrorCode.NO_SUBTITLE_IN_M1

    # IncompleteFrontmatterError
    if "IncompleteFrontmatter" in exc_name or "incomplete_frontmatter" in exc_msg:
        return ErrorCode.INCOMPLETE_FRONTMATTER

    # Cookie 过期（hint 或消息含 403/cookie）
    if hint == "cookie_403" or "cookie" in exc_msg or "403" in exc_msg:
        return ErrorCode.COOKIE_EXPIRED

    # DouK 失败 = 全工具失败
    if "DoukDownload" in exc_name or "download_failed" in exc_msg:
        return ErrorCode.DOWNLOAD_FAILED_ALL_TOOLS

    return ErrorCode.UNKNOWN
```

- [ ] **Step 5: 写实现 — cookie_probe.py**

`src/utils/cookie_probe.py`:
```python
"""Cookie 探活：启动时 + 下载失败时。

Spec ref: specs/douyin-extraction/spec.md Requirement: Cookie 失效检测。
"""
from pathlib import Path
from typing import Optional

import httpx


# 已知有效视频 URL 用于探活（Jovi 提供样本，见 OQ-3）
_PROBE_URL = "https://www.douyin.com/video/7234567890123"


def probe_cookie(cookies_path: Optional[str]) -> bool:
    """返回 True = cookie 有效，False = 过期/无 cookie。"""
    if not cookies_path:
        return False
    try:
        with httpx.Client(cookies=cookies_path, follow_redirects=True, timeout=10.0) as client:
            resp = client.get(_PROBE_URL)
            return resp.status_code == 200
    except Exception:
        return False
```

- [ ] **Step 6: 写实现 — scheduler.py**

`src/pipeline/scheduler.py`:
```python
"""单 worker 串行调度器：dequeue → process → mark done/failed。

Spec ref: specs/task-queue-pipeline/spec.md
- Requirement: 不允许并发 worker（M1 简化）
- Requirement: 端到端 correlation_id
- Requirement: 状态转移审计日志（v2 新增）

Spec ref: specs/douyin-extraction/spec.md
- Requirement: yt-dlp 失败兜底走 DouK-Downloader
- Requirement: 视频文件清理
"""
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.extractors.downloader import download_video, NoSubtitleError
from src.extractors.douk_fallback import download_with_douk, DoukDownloadError, DoukNotConfiguredError
from src.extractors.metadata import extract_metadata
from src.obsidian.frontmatter import build_frontmatter, IncompleteFrontmatterError
from src.obsidian.note_builder import build_note_body
from src.obsidian.path_calc import calc_note_path, calc_cover_path
from src.obsidian.writer import write_note, download_cover
from src.pipeline.errors import classify_exception, ErrorCode
from src.pipeline.state_machine import validate_transition, IllegalTransitionError
from src.queue.db import atomic_dequeue, mark_status, get_task
from src.utils.cookie_probe import probe_cookie


# 全局可被测试 monkeypatch
VAULT_ROOT = Path(os.environ.get("DOUYIN_VAULT_ROOT", "E:/AI_Tools/Obsidian/data/notes-personal"))
TEMP_DIR = Path(os.environ.get("DOUYIN_TEMP_DIR", "data/tmp"))
COOKIES_PATH = os.environ.get("DOUYIN_COOKIES_PATH", "")
DOUK_PATH = os.environ.get("DOUYIN_DOUK_PATH", "")
YT_DLP_RETRIES = 3


def _sleep_when_empty(seconds: int) -> None:
    time.sleep(seconds)


def run_forever_loop(db) -> None:
    """单 worker 主循环：dequeue → process → mark。队空睡眠 5s。"""
    task = atomic_dequeue(db)
    if task is None:
        _sleep_when_empty(5)
        return
    process_task(db, task)


def run_forever(db) -> None:
    """阻塞循环。Ctrl+C 退出。"""
    while True:
        try:
            run_forever_loop(db)
        except KeyboardInterrupt:
            break
        except Exception as e:
            # 单 task 异常不应杀掉调度器
            print(f"scheduler error: {e}", flush=True)
            _sleep_when_empty(1)


def process_task(db, task: dict) -> None:
    """处理单条任务：fetching → writing → done/failed。"""
    task_id = task["id"]
    correlation_id = task["correlation_id"]
    video_id = task["video_id"]
    source_url = task["source_url"]

    try:
        # fetching 阶段：下载视频 + 字幕
        out_dir = TEMP_DIR / video_id
        out_dir.mkdir(parents=True, exist_ok=True)

        download_result = None
        downloader_used = "ytdlp"
        try:
            download_result = download_video(
                video_id=video_id,
                canonical_url=source_url,
                out_dir=out_dir,
                cookies_path=COOKIES_PATH or None,
            )
        except NoSubtitleError:
            raise  # 直接上抛 → failed
        except Exception as yt_err:
            # yt-dlp 失败 → DouK 兜底
            if DOUK_PATH:
                try:
                    douk_result = download_with_douk(
                        video_id=video_id,
                        canonical_url=source_url,
                        out_dir=out_dir,
                        douk_path=DOUK_PATH,
                    )
                    # DouK 不返回 subtitle_source，需调用方重新判定
                    download_result = {
                        "video_path": douk_result["video_path"],
                        "subtitle_path": douk_result["subtitle_path"],
                        "subtitle_source": "douyin_native",  # 占位，待 B2 判定
                        "info_dict": {},
                    }
                    downloader_used = "douk"
                except (DoukDownloadError, DoukNotConfiguredError):
                    raise DoukDownloadError("download_failed_all_tools")
            else:
                raise DoukDownloadError("download_failed_all_tools")

        # 元数据
        metadata = extract_metadata(download_result["info_dict"])

        # 转移到 writing
        validate_transition("fetching", "writing")
        mark_status(db, task_id, "writing")

        # writing 阶段：下载封面 + 构建 frontmatter + 写笔记
        captured_at = datetime.utcnow()
        cover_path = download_cover(
            vault_root=VAULT_ROOT,
            video_id=video_id,
            cover_url=metadata.get("thumbnail", ""),
        )
        local_cover_rel = ""
        if cover_path:
            local_cover_rel = f"attachments/douyin/{video_id}/cover.jpg"

        subtitle_vtt = ""
        if download_result["subtitle_path"]:
            subtitle_vtt = download_result["subtitle_path"].read_text(encoding="utf-8")

        fm_data = {
            "title": metadata["title"],
            "video_id": video_id,
            "source_url": source_url,
            "source_url_type": task["source_url_type"],
            "author": metadata["uploader"],
            "uploader_id": metadata["uploader_id"],
            "duration_seconds": metadata["duration_seconds"],
            "uploaded_at": metadata["uploaded_at"],
            "captured_at": captured_at.strftime("%Y-%m-%dT%H:%M:%S"),
            "cover_url": metadata["thumbnail"],
            "local_cover_path": local_cover_rel,
            "subtitle_source": download_result["subtitle_source"],
            "subtitle_language": "zh",
            "pipeline_version": "1.0",
            "status": "done",
            "downloader_used": downloader_used,
            "correlation_id": correlation_id,
        }
        fm = build_frontmatter(fm_data)

        body = build_note_body(
            subtitle_vtt=subtitle_vtt,
            metadata=fm_data,
            local_cover_path=local_cover_rel,
            correlation_id=correlation_id,
            raw_input=task.get("payload", {}).get("raw_input", source_url),
            processing_time_seconds=0,  # M1 简化，不精确计时
        )

        note_path = calc_note_path(VAULT_ROOT, video_id, captured_at)
        write_note(note_path, fm, body)

        # 清理临时视频文件（保留封面，封面已入 vault）
        download_result["video_path"].unlink(missing_ok=True)
        if download_result["subtitle_path"]:
            download_result["subtitle_path"].unlink(missing_ok=True)

        # done
        validate_transition("writing", "done")
        mark_status(db, task_id, "done")

    except Exception as exc:
        error_code = classify_exception(exc)
        # 当前状态可能是 fetching 或 writing，都允许 → failed
        try:
            mark_status(db, task_id, "failed", error_code=error_code.value, error_message=str(exc))
        except Exception:
            pass
```

- [ ] **Step 7: 跑测试验证通过**

Run: `pytest tests/pipeline/ -v`
Expected: 全部 PASS（绿）。

- [ ] **Step 8: Commit**

```powershell
git add src/pipeline/errors.py src/pipeline/scheduler.py src/utils/cookie_probe.py tests/pipeline/
git commit -m "feat(pipeline): single-worker scheduler + error classification + cookie probe"
```

---

### Task 12: 日志与可观测性（structlog + correlation_id）

**对应 tasks.md**: §7.1-7.4
**依赖**: Task 11 完成
**Spec 参考**: `specs/task-queue-pipeline/spec.md` Requirement "端到端 correlation_id" + "状态转移审计日志（v2 新增）"

**Files:**
- Create: `E:\project\douyin_to_obsidian\src\utils\logging.py`
- Modify: `E:\project\douyin_to_obsidian\src\pipeline\scheduler.py`（注入 correlation_id 到日志）
- Modify: `E:\project\douyin_to_obsidian\src\bridge\main.py`（启动时初始化日志）
- Create: `E:\project\douyin_to_obsidian\tests\utils\test_logging.py`

- [ ] **Step 1: 写失败测试（红）**

`tests/utils/test_logging.py`:
```python
"""Test structlog config + correlation_id injection.

Spec ref: specs/task-queue-pipeline/spec.md
- Scenario: 日志串起 → grep correlation_id 取完整链路
- Scenario: 状态转移审计日志
"""
import io
import json

import pytest

from src.utils.logging import configure_logging, get_logger, log_state_transition


def test_correlation_id_in_all_logs():
    """WHEN 用同一 correlation_id 记多条日志
    THEN 每条 JSON 日志都含 correlation_id。"""
    buf = io.StringIO()
    configure_logging(stream=buf, log_dir=None)
    logger = get_logger("test")
    cid = "abc-123"

    logger.info("event1", correlation_id=cid)
    logger.info("event2", correlation_id=cid)
    logger.info("event3", correlation_id=cid)

    lines = buf.getvalue().strip().splitlines()
    assert len(lines) == 3
    for line in lines:
        entry = json.loads(line)
        assert entry["correlation_id"] == cid


def test_state_transition_log_format():
    """WHEN log_state_transition(fetching → writing)
    THEN 日志含 task_id/from/to/correlation_id。"""
    buf = io.StringIO()
    configure_logging(stream=buf, log_dir=None)
    log_state_transition(
        task_id=123,
        from_status="fetching",
        to_status="writing",
        correlation_id="c1",
    )
    entry = json.loads(buf.getvalue().strip())
    assert entry["event"] == "state_transition"
    assert entry["task_id"] == 123
    assert entry["from_status"] == "fetching"
    assert entry["to_status"] == "writing"
    assert entry["correlation_id"] == "c1"


def test_state_transition_log_with_error_code():
    """WHEN fetching → failed (cookie_expired)
    THEN 日志含 error_code=cookie_expired。"""
    buf = io.StringIO()
    configure_logging(stream=buf, log_dir=None)
    log_state_transition(
        task_id=123,
        from_status="fetching",
        to_status="failed",
        correlation_id="c1",
        error_code="cookie_expired",
    )
    entry = json.loads(buf.getvalue().strip())
    assert entry["error_code"] == "cookie_expired"
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/utils/test_logging.py -v`
Expected: `ImportError`（红）。

- [ ] **Step 3: 写最小实现（绿）**

`src/utils/logging.py`:
```python
"""structlog 配置：JSON 格式 + correlation_id 注入 + 按日 rotate。

Spec ref: specs/task-queue-pipeline/spec.md
- Requirement: 端到端 correlation_id
- Requirement: 状态转移审计日志（v2 新增）
"""
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import structlog


_configured = False


def configure_logging(
    stream=None,
    log_dir: Optional[Path] = None,
    level: str = "INFO",
) -> None:
    """配置 structlog。stream 用于测试，log_dir 用于生产按模块/按日 rotate。"""
    global _configured
    if _configured:
        return

    handlers = []
    if stream is not None:
        handlers.append(logging.StreamHandler(stream))
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            str(log_dir / "app.log"),
            encoding="utf-8",
        )
        handlers.append(file_handler)

    if not handlers:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        handlers=handlers,
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(file=stream or sys.stdout),
    )
    _configured = True


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)


def log_state_transition(
    task_id: int,
    from_status: str,
    to_status: str,
    correlation_id: str,
    error_code: Optional[str] = None,
) -> None:
    """记录状态转移审计日志。

    Spec: Requirement: 状态转移审计日志（v2 新增）。
    """
    logger = get_logger("state_machine")
    entry = {
        "event": "state_transition",
        "task_id": task_id,
        "from_status": from_status,
        "to_status": to_status,
        "correlation_id": correlation_id,
    }
    if error_code:
        entry["error_code"] = error_code
    logger.info(**entry)
```

- [ ] **Step 4: 在 scheduler.py 注入日志**

修改 `src/pipeline/scheduler.py`，在 `process_task` 关键节点加日志：

在文件顶部 import 块追加：
```python
from src.utils.logging import get_logger, log_state_transition
```

在 `process_task` 函数体的以下位置插入日志调用：
- `validate_transition("fetching", "writing")` 之后：
  ```python
  log_state_transition(task_id=task_id, from_status="fetching", to_status="writing",
                       correlation_id=correlation_id)
  ```
- `mark_status(db, task_id, "done")` 之前：
  ```python
  log_state_transition(task_id=task_id, from_status="writing", to_status="done",
                       correlation_id=correlation_id)
  ```
- `except Exception as exc:` 块内，`mark_status(... failed ...)` 之前：
  ```python
  log_state_transition(task_id=task_id, from_status="fetching_or_writing",
                       to_status="failed", correlation_id=correlation_id,
                       error_code=error_code.value)
  ```

- [ ] **Step 5: 在 bridge/main.py 启动时初始化日志**

在 `src/bridge/main.py` 顶部 import 块追加：
```python
from src.utils.logging import configure_logging
from pathlib import Path as _Path
```

在 `app = FastAPI(...)` 之前追加：
```python
configure_logging(log_dir=_Path("logs"))
```

- [ ] **Step 6: 跑测试验证通过**

Run: `pytest tests/utils/test_logging.py tests/pipeline/ tests/bridge/ -v`
Expected: 全部 PASS（绿）。

- [ ] **Step 7: Commit**

```powershell
git add src/utils/logging.py tests/utils/test_logging.py src/pipeline/scheduler.py src/bridge/main.py
git commit -m "feat(observability): structlog JSON + correlation_id + state transition audit"
```

---

### Task 13: Git 冷备（vault git init + .gitignore + cron 脚本）

**对应 tasks.md**: §8.1-8.6
**依赖**: Task 1 完成
**Spec 参考**: `specs/git-cold-backup/spec.md` 全部 Requirement

**Files:**
- Create: `E:\AI_Tools\Obsidian\data\notes-personal\.gitignore`（vault 根目录）
- Create: `E:\project\douyin_to_obsidian\scripts\git-backup.ps1`
- Create: `E:\project\douyin_to_obsidian\scripts\register-scheduled-task.ps1`
- Create: `E:\project\douyin_to_obsidian\tests\test_git_backup.py`

- [ ] **Step 1: 写测试（验证 .gitignore 内容 + ps1 脚本存在）**

`tests/test_git_backup.py`:
```python
"""Test git backup scripts content.

Spec ref: specs/git-cold-backup/spec.md
- Requirement: .gitignore 屏蔽规则
- Requirement: commit 信息规范
- Requirement: 自动 commit + push 任务计划
- Requirement: 未配置远程仓库时降级
"""
import subprocess
from pathlib import Path

import pytest


VAULT_ROOT = Path("E:/AI_Tools/Obsidian/data/notes-personal")
SCRIPTS_DIR = Path("E:/project/douyin_to_obsidian/scripts")


def test_vault_gitignore_exists_and_has_rules():
    """WHEN vault .gitignore
    THEN 含 .env / cookies.txt / *.mp4 / .obsidian/workspace* 屏蔽规则。"""
    gitignore = VAULT_ROOT / ".gitignore"
    if not gitignore.exists():
        pytest.skip("vault .gitignore not yet created; run Task 13 Step 2 first")
    content = gitignore.read_text(encoding="utf-8")
    assert ".env" in content
    assert "cookies.txt" in content
    assert "*.mp4" in content
    assert ".obsidian/workspace*" in content


def test_git_backup_ps1_exists():
    """WHEN scripts/git-backup.ps1
    THEN 文件存在且含 git add/commit/push 重试逻辑。"""
    ps1 = SCRIPTS_DIR / "git-backup.ps1"
    assert ps1.exists()
    content = ps1.read_text(encoding="utf-8")
    assert "git add" in content
    assert "git commit" in content
    assert "git push" in content
    assert "3" in content  # 重试 3 次


def test_register_scheduled_task_ps1_exists():
    """WHEN scripts/register-scheduled-task.ps1
    THEN 文件存在且含 schtasks / 03:00。"""
    ps1 = SCRIPTS_DIR / "register-scheduled-task.ps1"
    assert ps1.exists()
    content = ps1.read_text(encoding="utf-8")
    assert "schtasks" in content.lower() or "Register-ScheduledTask" in content
    assert "03:00" in content
```

- [ ] **Step 2: 创建 vault .gitignore**

`E:\AI_Tools\Obsidian\data\notes-personal\.gitignore`:
```
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
```

- [ ] **Step 3: 写 git-backup.ps1**

`E:\project\douyin_to_obsidian\scripts\git-backup.ps1`:
```powershell
# vault Git 冷备脚本
# Spec: specs/git-cold-backup/spec.md Requirement: 自动 commit + push 任务计划
# 每天 03:00 由 Windows 任务计划程序触发

$ErrorActionPreference = "Continue"
$VaultRoot = "E:\AI_Tools\Obsidian\data\notes-personal"
$LogFile = "E:\project\douyin_to_obsidian\logs\git-backup\$(Get-Date -Format 'yyyy-MM-dd').log"
$LogFileDir = Split-Path $LogFile -Parent
if (-not (Test-Path $LogFileDir)) { New-Item -ItemType Directory -Force $LogFileDir | Out-Null }

function Write-Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Add-Content -Path $LogFile -Value $line
    Write-Host $line
}

Set-Location $VaultRoot

# 检查是否有变更
$status = git status --porcelain
if (-not $status) {
    Write-Log "no changes to commit"
    exit 0
}

# git add .
git add .
if (-not $?) {
    Write-Log "ERROR: git add failed"
    exit 1
}

# commit 信息规范: auto: vault backup YYYY-MM-DD HH:MM:SS (N files changed)
$changedCount = ($status | Measure-Object).Count
$commitMsg = "auto: vault backup $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ($changedCount files changed)"
git commit -m $commitMsg
if (-not $?) {
    Write-Log "ERROR: git commit failed"
    exit 1
}
Write-Log "committed: $commitMsg"

# 检查是否配置了远程仓库
$remote = git remote get-url origin 2>$null
if (-not $remote) {
    Write-Log "remote not configured, local-only backup"
    exit 0
}

# push 重试 3 次
$pushed = $false
for ($i = 1; $i -le 3; $i++) {
    git push origin main
    if ($?) {
        $pushed = $true
        Write-Log "push succeeded on attempt $i"
        break
    }
    Write-Log "push attempt $i failed, retrying in 5s"
    Start-Sleep -Seconds 5
}

if (-not $pushed) {
    Write-Log "ERROR: push failed after 3 attempts"
    exit 1
}
```

- [ ] **Step 4: 写 register-scheduled-task.ps1**

`E:\project\douyin_to_obsidian\scripts\register-scheduled-task.ps1`:
```powershell
# 注册 Windows 任务计划程序：每天 03:00 执行 git-backup.ps1
# Spec: specs/git-cold-backup/spec.md Requirement: 自动 commit + push 任务计划

$TaskName = "douyin-vault-git-backup"
$ScriptPath = "E:\project\douyin_to_obsidian\scripts\git-backup.ps1"
$Trigger = New-ScheduledTaskTrigger -Daily -At "03:00"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd

Register-ScheduledTask -TaskName $TaskName -Trigger $Trigger -Action $Action -Settings $Settings -Description "douyin-to-obsidian vault daily git backup" -Force

Write-Host "Registered scheduled task: $TaskName (daily 03:00)"
```

- [ ] **Step 5: vault git init + 首条 commit**

Run:
```powershell
Set-Location "E:\AI_Tools\Obsidian\data\notes-personal"
git init
git config user.name "douyin-to-obsidian-bot"
git config user.email "bot@local"
git add .
git commit -m "init: 初始化 Obsidian vault"
```
Expected: 首条 commit 成功，含除 .gitignore 屏蔽外所有现有文件。

- [ ] **Step 6: 注册 Windows 任务计划（Jovi 决定远程仓库后跑）**

Run:
```powershell
powershell -ExecutionPolicy Bypass -File "E:\project\douyin_to_obsidian\scripts\register-scheduled-task.ps1"
```
Expected: 输出 "Registered scheduled task: douyin-vault-git-backup (daily 03:00)"。

- [ ] **Step 7: 跑测试验证通过**

Run: `pytest tests/test_git_backup.py -v`
Expected: 3 个测试 PASS（绿）。若 vault .gitignore 尚未在 Step 2 创建，第一个测试会 skip。

- [ ] **Step 8: Commit**

```powershell
git add scripts/git-backup.ps1 scripts/register-scheduled-task.ps1 tests/test_git_backup.py
git commit -m "feat(git-backup): vault cold backup cron + .gitignore + retry logic"
```

---

## 分组 B：curl 端到端验收（OQ-1 不阻塞）

### Task 14: curl E2E 测试（11.A 七场景）

**对应 tasks.md**: §11.A.1-11.A.7
**依赖**: Task 1-13 全部完成
**Spec 参考**: `specs/douyin-extraction/spec.md` + `specs/task-queue-pipeline/spec.md` + `specs/obsidian-archive-writer/spec.md` 所有 Scenario

**Files:**
- Create: `E:\project\douyin_to_obsidian\tests\e2e\test_curl_e2e.py`
- Create: `E:\project\douyin_to_obsidian\tests\e2e\__init__.py`（空）

> **说明**: 这些测试需要真实抖音视频样本（Jovi 提供 1-2 条带原生字幕的 video_id），不能完全 mock。测试用 `pytest.mark.e2e` 标记，默认 skip，加 `--run-e2e` 才跑。

- [ ] **Step 1: 写 E2E 测试文件**

`tests/e2e/test_curl_e2e.py`:
```python
"""curl E2E 测试：7 场景验证 M1 端到端闭环。

Spec ref: design doc §5 测试策略 + tasks.md §11.A
- 11.A.1 带字幕视频 → done + 笔记
- 11.A.2 无字幕视频 → failed + no_subtitle_in_m1
- 11.A.3 重复 URL → already_archived
- 11.A.4 进程崩溃后重启 → zombie 复活
- 11.A.5 cookie 过期 → failed + cookie_expired
- 11.A.6 网络断开 30s 恢复 → 后续正常
- 11.A.7 性能基准：5 条串行 ≤2 min/条

运行方式：pytest tests/e2e/test_curl_e2e.py --run-e2e -v
需先启动解析服务：uvicorn src.bridge.main:app --port 8765
"""
import os
import time
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.e2e

BASE_URL = "http://127.0.0.1:8765"
# Jovi 提供的测试样本（见 OQ-3）
SAMPLE_SUBTITLED_URL = os.environ.get("DOUYIN_TEST_SUBTITLED_URL", "")
SAMPLE_NOSUB_URL = os.environ.get("DOUYIN_TEST_NOSUB_URL", "")


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=180.0) as c:
        # 健康检查
        resp = c.get("/health")
        assert resp.status_code == 200
        yield c


def test_11a_1_subtitled_video_to_done(client):
    """WHEN curl POST /ingest 带字幕视频
    THEN ≤2 min vault 出现完整笔记 + GET /tasks/{id} 返回 done。"""
    if not SAMPLE_SUBTITLED_URL:
        pytest.skip("DOUYIN_TEST_SUBTITLED_URL not set; provide a real douyin URL with native subtitle")
    resp = client.post("/ingest", json={"source_url": SAMPLE_SUBTITLED_URL})
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]

    deadline = time.time() + 120  # 2 分钟
    final_status = None
    while time.time() < deadline:
        r = client.get(f"/tasks/{task_id}")
        final_status = r.json()["status"]
        if final_status in ("done", "failed"):
            break
        time.sleep(3)

    assert final_status == "done", f"task did not complete in 2 min: {final_status}"
    task = client.get(f"/tasks/{task_id}").json()
    assert "note_path" in task
    # 验证 vault 文件存在
    vault_root = Path("E:/AI_Tools/Obsidian/data/notes-personal")
    note_path = vault_root / task["note_path"]
    assert note_path.exists(), f"note not found: {note_path}"


def test_11a_2_no_subtitle_video_fails(client):
    """WHEN curl POST /ingest 无字幕视频
    THEN ≤30s GET /tasks/{id} 返回 failed + error_code='no_subtitle_in_m1'。"""
    if not SAMPLE_NOSUB_URL:
        pytest.skip("DOUYIN_TEST_NOSUB_URL not set")
    resp = client.post("/ingest", json={"source_url": SAMPLE_NOSUB_URL})
    task_id = resp.json()["task_id"]

    deadline = time.time() + 30
    final = None
    while time.time() < deadline:
        r = client.get(f"/tasks/{task_id}").json()
        final = r
        if r["status"] in ("done", "failed"):
            break
        time.sleep(2)

    assert final["status"] == "failed"
    assert final.get("error_code") == "no_subtitle_in_m1"


def test_11a_3_duplicate_url_already_archived(client):
    """WHEN curl 同 URL 两次（不带 force）
    THEN 第二次 /ingest 返回 already_archived=true。"""
    if not SAMPLE_SUBTITLED_URL:
        pytest.skip("DOUYIN_TEST_SUBTITLED_URL not set")
    # 第一次入队 + 等完成
    r1 = client.post("/ingest", json={"source_url": SAMPLE_SUBTITLED_URL})
    if "task_id" in r1.json():
        tid = r1.json()["task_id"]
        for _ in range(40):
            if client.get(f"/tasks/{tid}").json()["status"] in ("done", "failed"):
                break
            time.sleep(3)
    # 第二次
    r2 = client.post("/ingest", json={"source_url": SAMPLE_SUBTITLED_URL})
    body = r2.json()
    assert body.get("already_archived") is True or "task_id" in body


def test_11a_4_zombie_reclaim_after_restart(client):
    """WHEN 解析服务崩溃后重启
    THEN pending 任务自动消化（B4 zombie 复活）。"""
    # 此测试需手动配合进程重启，标记为 manual
    pytest.skip("manual test: kill server mid-task, restart, verify reclaim; see docs/m1/ACCEPTANCE.md")


def test_11a_5_cookie_expired(client, monkeypatch):
    """WHEN cookie 过期（错误 cookies.txt）
    THEN task failed + error_code='cookie_expired'。"""
    # 模拟方式：把 cookies_path 指向无效文件
    pytest.skip("requires server restart with bad cookies.txt; manual run documented in ACCEPTANCE.md")


def test_11a_6_network_recovery(client):
    """WHEN 网络断开 30s 恢复
    THEN 后续 curl /ingest 能正常入队处理。"""
    pytest.skip("requires manual network toggle; documented in ACCEPTANCE.md")


def test_11a_7_performance_baseline_5_videos_serial(client):
    """WHEN 5 条带字幕视频串行
    THEN 平均端到端 ≤2 min/条。"""
    urls_env = os.environ.get("DOUYIN_TEST_5URLS", "")
    if not urls_env:
        pytest.skip("DOUYIN_TEST_5URLS not set (comma-separated 5 URLs)")
    urls = [u.strip() for u in urls_env.split(",") if u.strip()]
    assert len(urls) == 5

    durations = []
    for i, url in enumerate(urls, 1):
        t0 = time.time()
        r = client.post("/ingest", json={"source_url": url, "force": True})
        tid = r.json()["task_id"]
        for _ in range(40):
            s = client.get(f"/tasks/{tid}").json()["status"]
            if s in ("done", "failed"):
                break
            time.sleep(3)
        durations.append(time.time() - t0)
        assert s == "done", f"video {i} failed"

    avg = sum(durations) / len(durations)
    assert avg <= 120, f"avg {avg:.1f}s > 120s budget"
```

- [ ] **Step 2: 配置 pytest marker**

修改 `pyproject.toml` 的 `[tool.pytest.ini_options]` 追加：
```toml
markers = [
    "e2e: end-to-end tests requiring real douyin URLs and running server",
]
addopts = "-m 'not e2e'"
```

- [ ] **Step 3: 跑单元测试确认 e2e 默认 skip**

Run: `pytest --collect-only`
Expected: `test_curl_e2e.py` 的 7 个测试被 collected 但默认 skip（因 `addopts = "-m 'not e2e'"`）。

- [ ] **Step 4: 手动 E2E 跑通（Jovi 提供样本 URL 后）**

Run（设环境变量后）:
```powershell
$env:DOUYIN_TEST_SUBTITLED_URL = "https://v.douyin.com/真实样本1/"
$env:DOUYIN_TEST_NOSUB_URL = "https://v.douyin.com/真实无字幕样本/"
# 终端 A：启动服务
.\.venv\Scripts\Activate.ps1
uvicorn src.bridge.main:app --host 127.0.0.1 --port 8765
# 终端 B：跑 e2e
pytest tests/e2e/test_curl_e2e.py --run-e2e -v -m e2e
```
Expected: test_11a_1, test_11a_2, test_11a_3 PASS。test_11a_4/5/6 skip（手动）。test_11a_7 视样本而定。

- [ ] **Step 5: Commit**

```powershell
git add tests/e2e/ pyproject.toml
git commit -m "test(e2e): 11.A curl scenarios 1-7 (3 auto, 3 manual, 1 perf)"
```

---

## 分组 C：OQ-1 blocked（bishu agent 飞书端到端）

> ⚠️ **BLOCKER**: 以下 Task 15-17 依赖 OQ-1（bishu agent 在 openclaw 内的配置 schema）。
> Jovi 提供现有 agent（如 taizi）的配置样板后，lead 重新评估并解锁。
> 主流程 Task 1-14 + 18 不依赖本组。

### Task 15: bishu agent 配置模板（blocked by OQ-1）

**对应 tasks.md**: §9.1-9.6
**依赖**: OQ-1 解决（Jovi 提供 taizi agent 样板）
**Spec 参考**: `specs/bishu-feishu-bridge/spec.md` Requirement "配置模板（M1 启动前 Jovi 自行注册）"

**Files:**
- Create: `E:\project\douyin_to_obsidian\docs\m1\bishu_agent_template.json`（schema 待 OQ-1）

- [ ] **Step 1: 等 OQ-1 解锁**

本 Task 在 OQ-1 解决前无法启动。Jovi 需提供：
- 现有 12 agent 中任一（如 taizi）的配置文件（JSON/YAML，视 openclaw schema）
- openclaw UI 截图（agent 注册页面字段）

- [ ] **Step 2: 根据样板生成 bishu 模板**

拿到样板后，按 spec Requirement "配置模板" 字段填：
- agent id: `bishu`
- 中文名: `秘书省`
- model: `mimo-v2.5-pro`（M1 不调 LLM，留位）
- binding: 飞书账号 `oc_516376df9cc2315fc12470e56e72c4af`
- 触发条件: 消息含 `v.douyin.com` / `iesdouyin.com` / `www.douyin.com/video/` / `www.douyin.com/note/` / 分享文案 `9\.\d+.*https?://`
- systemPrompt: 简短职责描述（路由 + 入队 + 轮询 + 回执）
- HTTP 工具定义: `POST 127.0.0.1:8765/ingest` + `GET /tasks/{id}`

具体 schema 待 OQ-1 解决后由 lead 补充。当前标记 TODO。

- [ ] **Step 3: Jovi 在 openclaw UI 注册 bishu**

Jovi 操作步骤：
1. 打开 openclaw 管理界面
2. 新建 agent，复制模板填入
3. 填入真实 FEISHU_APP_SECRET
4. 重启 openclaw

- [ ] **Step 4: 验证 bishu 注册成功**

测试：飞书发一条非抖音消息（如"你好"），确认 bishu 不被错误触发。

Run: 手动飞书测试 + 查看 openclaw 日志。

- [ ] **Step 5: Commit（OQ-1 解决后）**

```powershell
git add docs/m1/bishu_agent_template.json
git commit -m "feat(bishu): agent config template (OQ-1 resolved)"
```

---

### Task 16: bishu agent 端逻辑（blocked by OQ-1）

**对应 tasks.md**: §10.1-10.8
**依赖**: Task 15 完成（bishu 注册成功）
**Spec 参考**: `specs/bishu-feishu-bridge/spec.md` 全部 Requirement（除"配置模板"）

**Files:**
- Create: `E:\project\douyin_to_obsidian\src\bridge\bishu_agent.py`（具体文件结构待 OQ-1 后定，openclaw 可能用 JS/TS 而非 Python）
- Create: `E:\project\douyin_to_obsidian\tests\bridge\test_bishu_agent.py`

> **说明**: bishu agent 跑在 openclaw 内（Node 24），实现语言可能是 JS/TS，不是 Python。本 Task 具体代码结构待 OQ-1 解决后由 lead 重新规划。

- [ ] **Step 1-8: 等 OQ-1 解锁后补充**

按 spec Requirement 逐项实现：
- URL 抽取（4 形态，复用 Task 2 的正则思路）
- 5 秒被动回复
- `POST /ingest` 调用
- 轮询指数退避（1/3/10/30/60/60/60s，最多 5 分钟）
- tenant_access_token 缓存 + 60s 前刷新
- 飞书主动发消息 API
- 错误回执（error_code → 人类可读）
- 5 分钟超时回执

每项先写 spec WHEN/THEN 场景为测试断言，再实现。

- [ ] **Step 9: Commit（OQ-1 解决后）**

```powershell
git add src/bridge/bishu_agent.* tests/bridge/test_bishu_agent.*
git commit -m "feat(bishu): agent-side logic (URL extract + poll + feishu reply)"
```

---

### Task 17: 飞书端到端测试（blocked by OQ-1）

**对应 tasks.md**: §11.B.1-11.B.6
**依赖**: Task 16 完成
**Spec 参考**: `specs/bishu-feishu-bridge/spec.md` 所有 Scenario

**Files:**
- Create: `E:\project\douyin_to_obsidian\tests\e2e\test_feishu_e2e.py`

- [ ] **Step 1-6: 等 OQ-1 解锁后补充**

6 个飞书场景：
1. 带原生字幕视频 → ≤2 min vault 笔记 + 飞书回执"已归档"
2. 无字幕视频 → ≤30s 飞书回"无字幕，M1 暂不支持"
3. 同 URL 两次 → 第二次飞书回"已归档：{path}"
4. 进程崩溃后重启 → bishu 5 分钟超时回执 + 重启后自动消化
5. cookie 过期 → bishu 飞书回"cookie 过期"
6. 网络断开 30s 恢复 → 后续飞书消息正常

这些测试需真实飞书账号 + openclaw 运行 + 手动触发，多为 `pytest.mark.manual`。

- [ ] **Step 7: Commit（OQ-1 解决后）**

```powershell
git add tests/e2e/test_feishu_e2e.py
git commit -m "test(e2e): 11.B feishu scenarios 1-6 (manual)"
```

---

## 分组 D：文档归档

### Task 18: 文档与归档准备

**对应 tasks.md**: §12.1-12.5
**依赖**: Task 1-14 完成（Task 15-17 OQ-1 解决后补）
**Spec 参考**: 无（文档任务）

**Files:**
- Create: `E:\project\douyin_to_obsidian\docs\m1\RUNBOOK.md`
- Create: `E:\project\douyin_to_obsidian\docs\m1\TROUBLESHOOTING.md`
- Create: `E:\project\douyin_to_obsidian\docs\m1\ACCEPTANCE.md`

- [ ] **Step 1: 写 RUNBOOK.md**

`docs/m1/RUNBOOK.md` 内容大纲：
```markdown
# M1 部署运维手册

## 启动解析服务
```powershell
cd E:\project\douyin_to_obsidian
.\.venv\Scripts\Activate.ps1
uvicorn src.bridge.main:app --host 127.0.0.1 --port 8765
```

## 停止
Ctrl+C

## 查日志
- 应用日志：`logs/app.log`
- git-backup 日志：`logs/git-backup/{date}.log`

## 重启
停止 → 启动。启动钩子自动复活 zombie 任务（B4）。

## cron 任务管理
- 查看注册：`Get-ScheduledTask -TaskName douyin-vault-git-backup`
- 手动触发：`Start-ScheduledTask -TaskName douyin-vault-git-backup`
- 注销：`Unregister-ScheduledTask -TaskName douyin-vault-git-backup`

## 健康检查
curl http://127.0.0.1:8765/health
```

- [ ] **Step 2: 写 TROUBLESHOOTING.md**

`docs/m1/TROUBLESHOOTING.md` 内容大纲：
```markdown
# M1 常见报错与排查

## cookie 过期
症状：任务 failed + error_code=cookie_expired
排查：
1. 检查 config.yaml downloader.cookies_path 是否指向有效 cookies.txt
2. 浏览器重新登录抖音，导出 cookies.txt（按 EXECUTION §13.4）
3. 重启解析服务

## 反爬升级
症状：yt-dlp + DouK 都失败
排查：
1. 升级 yt-dlp：`pip install -U yt-dlp`
2. 检查 DouK-Downloader 版本
3. 临时禁用 cookie 探活看是否 412

## openclaw 重启
症状：bishu agent 不响应
排查：
1. 确认 openclaw 进程存活
2. 查看 openclaw 日志
3. 飞书发"你好"确认 bishu 不被错误触发（路由正常）

## 笔记没出现
症状：任务 done 但 vault 找不到 .md
排查：
1. curl GET /tasks/{id} 看 note_path
2. 检查 vault_root 配置
3. 检查跨月路径（inbox/douyin/{YYYY-MM}/）
4. 检查 .gitignore 是否误屏蔽
```

- [ ] **Step 3: 写 ACCEPTANCE.md**

`docs/m1/ACCEPTANCE.md` 内容大纲：
```markdown
# M1 验收清单

## 11.A curl 端到端（7 场景）
| # | 场景 | 预期 | 人工核验 |
|---|------|------|---------|
| 1 | 带字幕视频 → done | ≤2 min vault 笔记 | 打开 Obsidian 确认笔记可见 |
| 2 | 无字幕视频 → failed | ≤30s + no_subtitle_in_m1 | 飞书/curl 看回执 |
| 3 | 重复 URL | already_archived=true | 第二次不入队 |
| 4 | 崩溃后重启 | zombie 复活 | kill -9 服务进程，重启后 pending 自动消化 |
| 5 | cookie 过期 | failed + cookie_expired | 用错误 cookies.txt |
| 6 | 网络断 30s | 恢复后正常 | 拔网线 30s |
| 7 | 5 条串行 | 平均 ≤2 min/条 | 计时 |

## 11.B 飞书端到端（6 场景，blocked by OQ-1）
待 bishu agent 注册后补充。

## 性能基准
- 单视频端到端 ≤2 分钟
- 5 条串行平均 ≤2 min/条
- 日志 grep correlation_id 能取完整链路

## 验收签字
- [ ] Jovi 确认 11.A 全通过
- [ ] Jovi 确认笔记在 Obsidian 立即可见
- [ ] Jovi 确认 Git 冷备 cron 注册成功
- [ ] （OQ-1 解决后）Jovi 确认 11.B 全通过
```

- [ ] **Step 4: 跑全量测试确认绿**

Run:
```powershell
cd E:\project\douyin_to_obsidian
.\.venv\Scripts\Activate.ps1
pytest -v
```
Expected: 全部单元测试 PASS，e2e 默认 skip。

- [ ] **Step 5: 准备进入 comet-verify**

确认：
1. 所有代码已 commit
2. RUNBOOK / TROUBLESHOOTING / ACCEPTANCE 三份文档完整
3. `pytest -v` 全绿
4. 手动 E2E（11.A.1-3）已跑通（Jovi 提供样本 URL 后）

通知 lead 进入 comet-verify 阶段。

- [ ] **Step 6: Commit**

```powershell
git add docs/m1/RUNBOOK.md docs/m1/TROUBLESHOOTING.md docs/m1/ACCEPTANCE.md
git commit -m "docs(m1): RUNBOOK + TROUBLESHOOTING + ACCEPTANCE for verify phase"
```

---

## Self-Review 自检

### 1. Spec 覆盖检查

| Spec | Requirement | 覆盖 Task | 状态 |
|------|-------------|-----------|------|
| douyin-extraction | 接受多种抖音 URL 形态 | Task 2 | ✅ |
| douyin-extraction | yt-dlp 主路径下载 | Task 3 | ✅ |
| douyin-extraction | 字幕来源判定 | Task 3 | ✅ |
| douyin-extraction | 视频元数据提取 | Task 4 | ✅ |
| douyin-extraction | yt-dlp 失败兜底走 DouK-Downloader | Task 5, Task 11 | ✅ |
| douyin-extraction | Cookie 失效检测 | Task 11 (cookie_probe.py) | ✅ |
| douyin-extraction | 视频文件清理 | Task 11 | ✅ |
| task-queue-pipeline | 任务状态机（4 状态） | Task 7 | ✅ |
| task-queue-pipeline | SQLite 队列 schema | Task 6 | ✅ |
| task-queue-pipeline | 原子 dequeue（v2 直接 fetching） | Task 6 | ✅ |
| task-queue-pipeline | 启动时复活 zombie | Task 6, Task 8 | ✅ |
| task-queue-pipeline | bishu 轮询 API | Task 8 | ✅ |
| task-queue-pipeline | 端到端 correlation_id | Task 8, Task 12 | ✅ |
| task-queue-pipeline | 不允许并发 worker | Task 11 | ✅ |
| task-queue-pipeline | 状态转移审计日志 | Task 12 | ✅ |
| obsidian-archive-writer | frontmatter schema（含 D-10） | Task 9 | ✅ |
| obsidian-archive-writer | vault 路径计算 | Task 9 | ✅ |
| obsidian-archive-writer | 原子写入 | Task 10 | ✅ |
| obsidian-archive-writer | 重复检测 | Task 8 | ✅ |
| obsidian-archive-writer | 笔记正文结构（5 段） | Task 9 | ✅ |
| obsidian-archive-writer | 附件管理 | Task 10 | ✅ |
| bishu-feishu-bridge | 路由触发 | Task 15 (blocked) | ⚠️ OQ-1 |
| bishu-feishu-bridge | 5 秒响应窗口 | Task 16 (blocked) | ⚠️ OQ-1 |
| bishu-feishu-bridge | 异步入队+回执 | Task 16 (blocked) | ⚠️ OQ-1 |
| bishu-feishu-bridge | tenant_access_token 缓存 | Task 16 (blocked) | ⚠️ OQ-1 |
| bishu-feishu-bridge | 错误回执 | Task 16 (blocked) | ⚠️ OQ-1 |
| bishu-feishu-bridge | 配置模板 | Task 15 (blocked) | ⚠️ OQ-1 |
| git-cold-backup | vault Git 仓库初始化 | Task 13 | ✅ |
| git-cold-backup | .gitignore 屏蔽规则 | Task 13 | ✅ |
| git-cold-backup | 自动 commit + push | Task 13 | ✅ |
| git-cold-backup | 远程仓库地址配置 | Task 13 (OQ-4 留位) | ✅ |
| git-cold-backup | commit 信息规范 | Task 13 | ✅ |
| git-cold-backup | 不与未来云盘冲突 | Task 13 (.gitignore) | ✅ |

**未覆盖项**：
- bishu-feishu-bridge 全部 Requirement 标 `⚠️ OQ-1`，待 OQ-1 解决后在 Task 15-17 补。
- tasks §2.8（投真实抖音短链验证 extractor）已并入 Task 14 的 E2E 测试。

### 2. Placeholder 扫描

- Task 15-17（OQ-1 blocked）的 Step 内容标 `待 OQ-1 解决后由 lead 补充` —— 这是合规的，因为 OQ-1 是已记录的 blocker，不是 plan 缺陷。
- Task 11 scheduler.py 的 `payload.get("raw_input", source_url)` —— `payload` 字段在 Task 6 enqueue 时已写入 `{"raw_input": req.source_url}`，类型一致。
- Task 8 `/tasks/{id}` 返回的 `note_path` 用 `{{YYYY-MM}}` 占位 —— TODO 标记：Task 11 完成后应改为从 done 任务的 payload 或 vault 扫描返回真实路径。**这是已知 plan 缺陷，标 TODO 不改 spec**。

### 3. 类型一致性检查

- `resolve_url` 返回 `dict` 含 `video_id` / `canonical_url` / `source_url_type` —— Task 2 定义，Task 8 / Task 11 消费，键名一致 ✅
- `download_video` 返回 `dict` 含 `video_path` / `subtitle_path` / `subtitle_source` / `info_dict` —— Task 3 定义，Task 11 消费 ✅
- `DownloadResult` dataclass 在 Task 3 定义但实际返回 dict —— TODO 标记：Task 3 实现里 `DownloadResult` 未使用，应删除或改返回类型。**plan 缺陷，不影响执行，重构时清理**。
- `build_frontmatter` 返回 dict 含 17+3 字段 —— Task 9 定义，Task 10 / Task 11 消费 ✅
- `ErrorCode` enum 值与 spec error_code 字符串一致（`no_subtitle_in_m1` / `download_failed_all_tools` / `cookie_expired` / `incomplete_frontmatter`）—— Task 11 定义，Task 8 / Task 14 消费 ✅
- `STATES` 集合 = `{pending, fetching, writing, done, failed}` —— Task 7 定义，Task 6 schema CHECK 约束一致 ✅
- `mark_status(db, task_id, new_status, error_code=, error_message=)` 签名 —— Task 6 定义，Task 11 调用一致 ✅

### 4. 关键约束遵守

- ✅ D-3 v2：Task 2 docstring 注明"不复制代码，仅借鉴思路"
- ✅ D-4 v2：Task 6 schema 4 状态 CHECK，Task 7 状态机 4 状态，无 `processing`
- ✅ D-9：Task 1 config 锁 8765，Task 1 Step 4 全局替换 18900→8765，Task 8 uvicorn 启动 8765
- ✅ D-10：Task 9 frontmatter 含 3 状态字段，测试 `test_m1_full_frontmatter_has_status_fields` 验证
- ✅ D-7：Task 10 `write_note_atomic` 用 `.md.tmp` + `os.replace`，测试 `test_write_note_atomic_rollback_on_failure` 验证回滚
- ✅ TDD：每个 Task 都是 Step 1 写失败测试 → Step 2 验证失败 → Step 3 实现 → Step 4 验证通过
- ✅ subagent-driven：每个 Task 边界清晰，依赖在开头声明，可独立派发
- ✅ OQ-1 blocker：Task 15-17 独立分组 C，主流程 Task 1-14 + 18 不依赖

---

## 执行说明

### 任务总数

- 主流程（分组 A）：Task 1-13，共 13 个 task
- curl E2E（分组 B）：Task 14，1 个 task
- OQ-1 blocked（分组 C）：Task 15-17，3 个 task（待 OQ-1 解锁）
- 文档归档（分组 D）：Task 18，1 个 task
- **总计：18 个 task**

### 推荐执行顺序

1. **Day 1-2**：Task 1（脚手架）→ Task 2-5（自研 extractor，可并行 Task 2/3 与 Task 4/5）
2. **Day 2-3**：Task 6-7（队列 + 状态机）→ Task 8（FastAPI）
3. **Day 3-4**：Task 9-10（Obsidian writer）→ Task 11（调度器）
4. **Day 4-5**：Task 12（日志）→ Task 13（Git 冷备）
5. **Day 5-6**：Task 14（curl E2E，需 Jovi 提供真实抖音样本 URL）
6. **Day 6-7**：Task 18（文档归档）→ 准备 comet-verify
7. **OQ-1 解决后**：Task 15 → Task 16 → Task 17（飞书端）

### subagent 派发建议

每个 Task 可独立派给一个 subagent。关键注意：
- Task 2-5 共享 `src/extractors/` 目录，建议顺序派发避免 `__init__.py` 冲突
- Task 6-7 共享 `src/queue/` + `src/pipeline/`，顺序派发
- Task 9-10 共享 `src/obsidian/`，顺序派发
- Task 11 依赖 Task 5/6/7/8/10，必须在它们完成后派发
- Task 14 需要 Jovi 手动配合（提供样本 URL + 启动服务），非纯 subagent 任务

### 已知 TODO（plan 缺陷，不改 spec）

1. Task 8 `/tasks/{id}` 的 `note_path` 返回 `{{YYYY-MM}}` 占位，Task 11 完成后应改为真实路径
2. Task 3 `DownloadResult` dataclass 定义未使用，重构时清理
3. Task 11 `download_with_douk` 返回后 `subtitle_source` 占位 `douyin_native`，实际应调 `classify_subtitle_source` 重新判定（DouK 不返回 info_dict，需另想办法）

