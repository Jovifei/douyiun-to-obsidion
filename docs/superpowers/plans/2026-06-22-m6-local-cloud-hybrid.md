# M6 本地+云端全兼容 + 语义选帧 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让系统同时支持本地推理和云端 API，config.yaml 一键切换，开箱即用，适合开源发布。

**Architecture:** LLM/VLM/选帧三层各有一个 ABC 抽口 + 多个 provider 实现。config.yaml 通过 `provider` 字段选择。Scheduler 只调抽象接口，不知道底层是云端还是本地。

**Tech Stack:** Python 3.14, httpx, ollama (python SDK), FastAPI, pytest, structlog

**Base-ref:** `f47f147`

---

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `src/llm/client.py` | LLMClient ABC + OpenAICompatibleLLM + OllamaLocalLLM + get_llm_client |
| 修改 | `src/llm/__init__.py` | 导出新 client，保留旧 MimoSummarizer 向后兼容 |
| 修改 | `src/llm/mimo_summarizer.py` | 内部改用 OpenAICompatibleLLM（删掉重复 httpx 逻辑）|
| 新建 | `src/vision/semantic_frame_selector.py` | select_semantic_frames 函数 |
| 修改 | `src/vision/vlm_client.py` | VLMClient ABC + OllamaVLMClient + CloudVLMClient + get_vlm_client |
| 修改 | `src/vision/__init__.py` | 导出新 client |
| 修改 | `src/pipeline/scheduler.py` | 调用 get_llm_client / get_vlm_client / select_semantic_frames |
| 修改 | `config.example.yaml` | llm/vision/frame_selection 三个配置块 |
| 修改 | `config.yaml` | 同步 |
| 新建 | `tests/llm/test_llm_client.py` | LLMClient ABC + OpenAICompatible + OllamaLocal 测试 |
| 新建 | `tests/vision/test_vlm_client_v2.py` | VLMClient ABC + OllamaVLM + CloudVLM 测试 |
| 新建 | `tests/vision/test_semantic_frame_selector.py` | 语义选帧测试 |

---

## Task 1: LLM 统一抽象层（src/llm/client.py）

**Files:**
- Create: `src/llm/client.py`
- Modify: `src/llm/__init__.py`
- Modify: `src/llm/mimo_summarizer.py`
- Test: `tests/llm/test_llm_client.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/llm/test_llm_client.py
import pytest
from unittest.mock import patch, MagicMock
from src.llm.client import (
    LLMClient, OpenAICompatibleLLM, OllamaLocalLLM,
    get_llm_client, LLMClientError,
)


class TestLLMClientABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            LLMClient()


class TestOpenAICompatibleLLM:
    def test_chat_returns_string(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "hello"}}]}

        with patch("src.llm.client.httpx.post", return_value=mock_resp):
            client = OpenAICompatibleLLM(
                base_url="https://test.com/v1",
                api_key="sk-test",
                default_model="test-model",
            )
            result = client.chat([{"role": "user", "content": "hi"}])
            assert result == "hello"

    def test_chat_uses_default_model_when_none(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

        with patch("src.llm.client.httpx.post", return_value=mock_resp) as mock_post:
            client = OpenAICompatibleLLM(
                base_url="https://test.com/v1",
                api_key="sk-test",
                default_model="mimo-v2.5-pro",
            )
            client.chat([{"role": "user", "content": "hi"}])
            sent_model = mock_post.call_args[1]["json"]["model"]
            assert sent_model == "mimo-v2.5-pro"

    def test_chat_uses_override_model(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

        with patch("src.llm.client.httpx.post", return_value=mock_resp) as mock_post:
            client = OpenAICompatibleLLM(
                base_url="https://test.com/v1",
                api_key="sk-test",
                default_model="mimo-v2.5-pro",
            )
            client.chat([{"role": "user", "content": "hi"}], model="deepseek-chat")
            sent_model = mock_post.call_args[1]["json"]["model"]
            assert sent_model == "deepseek-chat"

    def test_chat_timeout_raises(self):
        import httpx
        with patch("src.llm.client.httpx.post", side_effect=httpx.TimeoutException("timeout")):
            client = OpenAICompatibleLLM(base_url="https://test.com/v1", api_key="sk-test", default_model="m")
            with pytest.raises(LLMClientError) as exc:
                client.chat([{"role": "user", "content": "hi"}])
            assert "timeout" in str(exc.value).lower()

    def test_chat_api_error_raises(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        with patch("src.llm.client.httpx.post", return_value=mock_resp):
            client = OpenAICompatibleLLM(base_url="https://test.com/v1", api_key="bad", default_model="m")
            with pytest.raises(LLMClientError) as exc:
                client.chat([{"role": "user", "content": "hi"}])
            assert "401" in str(exc.value)

    def test_chat_json_parses_json_response(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": '{"key_points": ["a", "b", "c"]}'}}]
        }
        with patch("src.llm.client.httpx.post", return_value=mock_resp):
            client = OpenAICompatibleLLM(base_url="https://test.com/v1", api_key="sk", default_model="m")
            result = client.chat_json([{"role": "user", "content": "list 3 things"}])
            assert isinstance(result, dict)
            assert "key_points" in result
            assert len(result["key_points"]) == 3


class TestOllamaLocalLLM:
    def test_chat_calls_ollama(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = {"message": {"content": "hi there"}}

        with patch("src.llm.client._get_ollama_client", return_value=mock_client):
            client = OllamaLocalLLM(model="qwen2.5:7b", base_url="http://localhost:11434")
            result = client.chat([{"role": "user", "content": "hello"}])
            assert result == "hi there"
            mock_client.chat.assert_called_once()

    def test_chat_uses_correct_model(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = {"message": {"content": "ok"}}
        with patch("src.llm.client._get_ollama_client", return_value=mock_client):
            client = OllamaLocalLLM(model="qwen3:14b")
            client.chat([{"role": "user", "content": "hi"}])
            sent_model = mock_client.chat.call_args[1]["model"]
            assert sent_model == "qwen3:14b"


class TestGetLLMClient:
    def test_openai_compatible(self):
        cfg = {
            "llm": {
                "provider": "openai_compatible",
                "openai_compatible": {
                    "base_url": "https://test.com/v1",
                    "model": "mimo-v2.5-pro",
                    "api_key_env": "TEST_KEY",
                }
            }
        }
        with patch.dict("os.environ", {"TEST_KEY": "sk-test"}):
            client = get_llm_client(cfg)
            assert isinstance(client, OpenAICompatibleLLM)

    def test_ollama_local(self):
        cfg = {
            "llm": {
                "provider": "ollama_local",
                "ollama_local": {
                    "model": "qwen2.5:7b",
                    "base_url": "http://localhost:11434",
                }
            }
        }
        client = get_llm_client(cfg)
        assert isinstance(client, OllamaLocalLLM)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="unknown"):
            get_llm_client({"llm": {"provider": "unknown"}})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /e/project/douyin_to_obsidian && python -m pytest tests/llm/test_llm_client.py -v --tb=short 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'src.llm.client'`

- [ ] **Step 3: Create `src/llm/client.py`**

（完整实现见下方代码块）

```python
"""LLM 统一抽象层 — OpenAI-compatible + Ollama 本地。

Spec ref: D-M6-1 — 不绑死 mimo，任何 OpenAI-compatible endpoint 都能用
"""
from abc import ABC, abstractmethod
import json
import os
import httpx


class LLMClientError(Exception):
    """LLM 调用错误。"""
    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message or code
        super().__init__(self.message)


class LLMClient(ABC):
    """LLM 调用抽象基类。"""
    @abstractmethod
    def chat(self, messages: list[dict], model: str | None = None) -> str:
        ...

    def chat_json(self, messages: list[dict], model: str | None = None) -> dict:
        content = self.chat(messages, model=model)
        if "```json" in content:
            content = content.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in content:
            content = content.split("```", 1)[1].split("```", 1)[0].strip()
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end > start:
            return json.loads(content[start:end + 1])
        raise LLMClientError("llm_json_parse_failed", f"无法从 LLM 输出解析 JSON：{content[:200]}")


class OpenAICompatibleLLM(LLMClient):
    """任何 OpenAI-compatible /chat/completions 端点。"""
    def __init__(self, base_url: str, api_key: str, default_model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.default_model = default_model

    def chat(self, messages: list[dict], model: str | None = None) -> str:
        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": model or self.default_model, "messages": messages},
            timeout=60,
        )
        if resp.status_code != 200:
            raise LLMClientError("llm_api_error", f"{resp.status_code}: {resp.text[:200]}")
        content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if not content:
            raise LLMClientError("llm_empty_response")
        return content


class OllamaLocalLLM(LLMClient):
    """本地 Ollama（零 API 成本）。"""
    def __init__(self, model: str = "qwen2.5:7b", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    def chat(self, messages: list[dict], model: str | None = None) -> str:
        client = _get_ollama_client(self.base_url)
        resp = client.chat(model=model or self.model, messages=messages)
        content = resp.get("message", {}).get("content", "").strip()
        if not content:
            raise LLMClientError("ollama_empty_response")
        return content


def _get_ollama_client(base_url: str):
    try:
        import ollama
        return ollama.Client(host=base_url)
    except ImportError:
        raise LLMClientError("ollama_not_installed", "pip install ollama")


def get_llm_client(config: dict) -> LLMClient:
    """根据 config.llm.provider 返回对应 LLMClient 实例。"""
    llm_cfg = config.get("llm", {})
    provider = llm_cfg.get("provider", "")
    if provider == "openai_compatible":
        sub = llm_cfg.get("openai_compatible", {})
        api_key = os.environ.get(sub.get("api_key_env", "LLM_API_KEY"), "")
        return OpenAICompatibleLLM(
            base_url=sub.get("base_url", "https://token-plan-cn.xiaomimimo.com/v1"),
            api_key=api_key,
            default_model=sub.get("model", "mimo-v2.5-pro"),
        )
    elif provider == "ollama_local":
        sub = llm_cfg.get("ollama_local", {})
        return OllamaLocalLLM(
            model=sub.get("model", "qwen2.5:7b"),
            base_url=sub.get("base_url", "http://localhost:11434"),
        )
    else:
        raise ValueError(f"unknown LLM provider: {provider!r}")
```

- [ ] **Step 4: Update `src/llm/__init__.py` 导出新 client**

```python
# __init__.py 末尾追加：
from src.llm.client import (
    LLMClient,
    LLMClientError,
    OpenAICompatibleLLM,
    OllamaLocalLLM,
    get_llm_client,
)
```

- [ ] **Step 5: Update `src/llm/mimo_summarizer.py` 改用 OpenAICompatibleLLM**

```python
# 旧：自己写 httpx.post
# 新：改用 client.chat()
from src.llm.client import OpenAICompatibleLLM, LLMClientError

class MimoSummarizer(SummarizerClient):
    """MiMo 总结客户端（向后兼容）。内部改用 OpenAICompatibleLLM。"""
    def __init__(self, api_key: str = "", base_url: str = "https://token-plan-cn.xiaomimimo.com/v1"):
        self._client = OpenAICompatibleLLM(base_url=base_url, api_key=api_key, default_model="mimo-v2.5-pro")

    def summarize(self, subtitle_text: str, metadata: dict) -> SummaryResult:
        text = self._truncate(subtitle_text)
        prompt = _PROMPT_TEMPLATE.format(
            title=metadata.get("title", ""),
            author=metadata.get("uploader", ""),
            duration=int(metadata.get("duration_seconds", 0)),
            subtitle_text=text,
        )
        messages = [
            {"role": "system", "content": _PROMPT_SYSTEM},
            {"role": "user", "content": prompt},
        ]
        try:
            content = self._client.chat(messages)
        except LLMClientError as e:
            raise LLMError(e.code, e.message) from e
        key_points = self._parse_key_points(content)
        return SummaryResult(
            summary_text=content.strip(), key_points=key_points,
            model="mimo-v2.5-pro", source="mimo_llm",
        )
```

- [ ] **Step 6: Run all tests**

```bash
cd /e/project/douyin_to_obsidian && python -m pytest tests/llm/ -v --tb=short 2>&1 | tail -10
```

Expected: 27/27 PASS（15 新 + 12 回归）

- [ ] **Step 7: Commit**

```bash
git add src/llm/ tests/llm/
git commit -m "feat(llm): M6 Task 1 — LLM 统一抽象层（OpenAICompatible + OllamaLocal + get_llm_client）"
```

---

## Task 2: VLM 统一抽象层（src/vision/vlm_client.py 改造）

**Files:**
- Modify: `src/vision/vlm_client.py`
- Test: `tests/vision/test_vlm_client_v2.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/vision/test_vlm_client_v2.py
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from src.vision.vlm_client import (
    VLMClient, OllamaVLMClient, CloudVLMClient,
    get_vlm_client, VLMClientError,
)

class TestVLMClientABC:
    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            VLMClient()

class TestOllamaVLMClient:
    def test_describe_image_returns_string(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = {"message": {"content": "PPT展示了流程图"}}
        with patch("src.vision.vlm_client._get_ollama_client", return_value=mock_client):
            client = OllamaVLMClient(model="qwen2.5-vl:7b")
            result = client.describe_image(Path("/tmp/test.jpg"), "描述画面")
            assert result == "PPT展示了流程图"

    def test_describe_image_timeout_returns_fallback(self):
        import httpx
        mock_client = MagicMock()
        mock_client.chat.side_effect = httpx.TimeoutException("timeout")
        with patch("src.vision.vlm_client._get_ollama_client", return_value=mock_client):
            client = OllamaVLMClient()
            result = client.describe_image(Path("/tmp/test.jpg"), "描述")
            assert "超时" in result or "timeout" in result.lower()

    def test_describe_image_nonexistent_returns_empty(self):
        client = OllamaVLMClient()
        result = client.describe_image(Path("/nonexistent.jpg"), "描述")
        assert result == ""

class TestCloudVLMClient:
    def test_describe_image_returns_string(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "PPT展示了架构图"}}]
        }
        with patch("src.vision.vlm_client.httpx.post", return_value=mock_resp):
            client = CloudVLMClient(
                base_url="https://test.com/v1", api_key="sk-test", model="mimo-v2-omni"
            )
            result = client.describe_image(Path("/tmp/test.jpg"), "描述画面")
            assert "架构图" in result

class TestGetVLMClient:
    def test_ollama(self):
        cfg = {"vision": {"enabled": True, "provider": "ollama", "ollama": {"model": "qwen2.5-vl:7b"}}}
        client = get_vlm_client(cfg)
        assert isinstance(client, OllamaVLMClient)

    def test_cloud_api(self):
        cfg = {"vision": {"enabled": True, "provider": "cloud_api",
                          "cloud_api": {"base_url": "https://test.com/v1", "model": "mimo-v2-omni", "api_key_env": "VLM_KEY"}}}
        with patch.dict("os.environ", {"VLM_KEY": "sk-test"}):
            client = get_vlm_client(cfg)
            assert isinstance(client, CloudVLMClient)

    def test_disabled_returns_none(self):
        cfg = {"vision": {"enabled": False}}
        assert get_vlm_client(cfg) is None

    def test_unknown_provider_raises(self):
        cfg = {"vision": {"enabled": True, "provider": "unknown"}}
        with pytest.raises(ValueError, match="unknown"):
            get_vlm_client(cfg)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /e/project/douyin_to_obsidian && python -m pytest tests/vision/test_vlm_client_v2.py -v --tb=short 2>&1 | tail -10
```

Expected: `ImportError: cannot import name 'OllamaVLMClient'`

- [ ] **Step 3: Rewrite `src/vision/vlm_client.py`** — 保留旧 `describe_image()` 向后兼容，新增 ABC + 多 provider 实现

```python
"""VLM 统一抽象层 — Ollama 本地 + 云端 API。

Spec ref: D-M6-2 — 不绑死 mimo-v2-omni
"""
from abc import ABC, abstractmethod
from pathlib import Path
import os
import base64
import httpx

class VLMClientError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message or code
        super().__init__(self.message)

class VLMClient(ABC):
    @abstractmethod
    def describe_image(self, image_path: Path, prompt: str) -> str:
        ...

class OllamaVLMClient(VLMClient):
    """本地 Ollama VLM（零 API 成本）。"""
    def __init__(self, model: str = "qwen2.5-vl:7b", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    def describe_image(self, image_path: Path, prompt: str) -> str:
        if not image_path.exists():
            return ""
        try:
            client = _get_ollama_client(self.base_url)
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
            resp = client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt, "images": [img_b64]}],
            )
            return resp.get("message", {}).get("content", "").strip()
        except Exception as e:
            return f"VLM 本地调用失败：{e}"

class CloudVLMClient(VLMClient):
    """云端 VLM（OpenAI-compatible vision 端点）。"""
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def describe_image(self, image_path: Path, prompt: str) -> str:
        if not image_path.exists():
            return ""
        try:
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
            data_url = f"data:image/jpeg;base64,{img_b64}"
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ]}],
                },
                timeout=60,
            )
            if resp.status_code != 200:
                return f"VLM API 错误 {resp.status_code}"
            return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        except httpx.TimeoutException:
            return "VLM 云端超时"
        except Exception as e:
            return f"VLM 云端调用失败：{e}"

def _get_ollama_client(base_url: str):
    try:
        import ollama
        return ollama.Client(host=base_url)
    except ImportError:
        raise VLMClientError("ollama_not_installed", "pip install ollama")

def get_vlm_client(config: dict) -> VLMClient | None:
    """根据 config.vision.provider 返回 VLMClient，vision.enabled=false 返回 None。"""
    vis_cfg = config.get("vision", {})
    if not vis_cfg.get("enabled", False):
        return None
    provider = vis_cfg.get("provider", "")
    if provider == "ollama":
        sub = vis_cfg.get("ollama", {})
        return OllamaVLMClient(model=sub.get("model", "qwen2.5-vl:7b"), base_url=sub.get("base_url", "http://localhost:11434"))
    elif provider == "cloud_api":
        sub = vis_cfg.get("cloud_api", {})
        api_key = os.environ.get(sub.get("api_key_env", "VLM_API_KEY"), "")
        return CloudVLMClient(base_url=sub.get("base_url", "https://token-plan-cn.xiaomimimo.com/v1"), api_key=api_key, model=sub.get("model", "mimo-v2-omni"))
    else:
        raise ValueError(f"unknown VLM provider: {provider!r}")

# ── 向后兼容：保留旧 describe_image() ──────────────────────────────

def describe_image(image_path, prompt="描述画面关键信息", api_key="", base_url="https://token-plan-cn.xiaomimimo.com/v1"):
    """旧接口（M3 用）。新代码请用 get_vlm_client()。"""
    if not api_key:
        import json as _json
        with open(r'C:\Users\Admin\.openclaw\openclaw.json', encoding='utf-8') as f:
            oc = _json.load(f)
        api_key = oc.get('models',{}).get('providers',{}).get('xiaomimimotokenplan',{}).get('apiKey','')
    client = CloudVLMClient(base_url=base_url, api_key=api_key, model="mimo-v2-omni")
    return client.describe_image(Path(image_path) if isinstance(image_path, str) else image_path, prompt)
```

- [ ] **Step 4: Run tests**

```bash
cd /e/project/douyin_to_obsidian && python -m pytest tests/vision/test_vlm_client_v2.py tests/vision/test_vlm_client.py -v --tb=short 2>&1 | tail -10
```

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add src/vision/vlm_client.py tests/vision/test_vlm_client_v2.py
git commit -m "feat(vision): M6 Task 2 — VLM 统一抽象层（OllamaLocal + CloudVLM + get_vlm_client）"
```

---

## Task 3: 语义选帧（src/vision/semantic_frame_selector.py）

**Files:**
- Create: `src/vision/semantic_frame_selector.py`
- Test: `tests/vision/test_semantic_frame_selector.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/vision/test_semantic_frame_selector.py
import pytest
from unittest.mock import MagicMock
from src.vision.semantic_frame_selector import select_semantic_frames

class TestSelectSemanticFrames:
    def test_returns_llm_frames_when_enough(self):
        mock_client = MagicMock()
        mock_client.chat_json.return_value = [
            {"time_sec": 30, "reason": "讲师展示代码"},
            {"time_sec": 120, "reason": "总结要点"},
            {"time_sec": 200, "reason": "实操演示"},
        ]
        segments = [{"start": i * 20, "end": i * 20 + 20, "text": f"seg{i}"} for i in range(10)]
        result = select_semantic_frames(segments, mock_client)
        assert len(result) == 3
        assert result[0]["time_sec"] == 30
        assert result[0]["source"] == "semantic"

    def test_fallback_to_segments_when_llm_returns_few(self):
        mock_client = MagicMock()
        mock_client.chat_json.return_value = [{"time_sec": 30, "reason": "one frame only"}]
        segments = [{"start": 0, "end": 10, "text": "a"}, {"start": 20, "end": 30, "text": "b"}]
        result = select_semantic_frames(segments, mock_client, max_frames=15)
        assert len(result) == 2
        assert result[0]["source"] == "asr_segment"

    def test_fallback_to_interval_when_no_segments(self):
        mock_client = MagicMock()
        mock_client.chat_json.return_value = [{"time_sec": 10, "reason": "x"}]
        result = select_semantic_frames([], mock_client, video_duration=60)
        assert len(result) >= 3
        assert result[0]["source"] == "interval"

    def test_fallback_on_llm_error(self):
        mock_client = MagicMock()
        mock_client.chat_json.side_effect = Exception("API error")
        segments = [{"start": 5, "end": 15, "text": "x"}, {"start": 25, "end": 35, "text": "y"}]
        result = select_semantic_frames(segments, mock_client)
        assert len(result) == 2

    def test_no_segments_no_duration_returns_empty(self):
        result = select_semantic_frames([], None)
        assert result == []

    def test_max_frames_respected(self):
        mock_client = MagicMock()
        mock_client.chat_json.return_value = [{"time_sec": i * 10, "reason": f"f{i}"} for i in range(20)]
        segments = [{"start": i * 10, "end": i * 10 + 10, "text": f"seg{i}"} for i in range(20)]
        result = select_semantic_frames(segments, mock_client, max_frames=5)
        assert len(result) == 5
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /e/project/douyin_to_obsidian && python -m pytest tests/vision/test_semantic_frame_selector.py -v --tb=short 2>&1 | tail -5
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `src/vision/semantic_frame_selector.py`**

```python
"""语义选帧 — 用 LLM 从 ASR segments 识别关键时间点，回退 ASR segments 直接抽帧。

Spec ref: D-M6-4 — mimo-v2.5-pro 语义分析 + ASR segments 回退
"""
from src.llm.client import LLMClient, LLMClientError

SEMANTIC_SELECT_PROMPT = """\
你是视频分析助手。以下是一段视频的带时间戳语音转写文本。
请识别 **3-10 个知识重点时刻**，即说话人正在强调关键知识点、展示示例、或总结要点的瞬间。

要求：
- 只返回 JSON 数组，不含任何额外文本
- 每项含 time_sec（秒数，整数）和 reason（一句话说明为什么是重点）
- time_sec 必须来自下方 segments 的 start 时间（或非常接近）
- 最多返回 {max_frames} 项

segments：
{segments_text}

输出格式：
```json
[{{"time_sec": 30, "reason": "讲师展示代码示例"}}, ...]
```"""

def select_semantic_frames(
    asr_segments: list[dict],
    llm_client: LLMClient | None = None,
    max_frames: int = 15,
    video_duration: float = 0.0,
) -> list[dict]:
    """从 ASR segments 识别关键时间点（语义选帧）。

    回退链：
    1. LLM 返回 ≥3 帧 → 使用语义帧
    2. LLM 返回 <3 帧 或 API 失败 → fallback ASR segments 直接抽帧
    3. 无 segments → 均匀采样（每 10 秒）

    Returns:
        list[dict]，每项含 time_sec + reason（reason 可能为空字符串）
    """
    if not asr_segments and video_duration <= 0:
        return []

    # 尝试 LLM 语义选帧
    if llm_client is not None and asr_segments:
        try:
            segments_text = "\n".join(
                f"[{s.get('start', 0):.1f}s - {s.get('end', 0):.1f}s] {s.get('text', '')}"
                for s in asr_segments[:50]
            )
            prompt = SEMANTIC_SELECT_PROMPT.format(
                max_frames=max_frames, segments_text=segments_text
            )
            result = llm_client.chat_json([{"role": "user", "content": prompt}])
            if isinstance(result, list) and len(result) >= 3:
                frames = []
                for item in result[:max_frames]:
                    time_sec = item.get("time_sec")
                    if time_sec is not None:
                        frames.append({
                            "time_sec": int(time_sec),
                            "reason": item.get("reason", ""),
                            "source": "semantic",
                        })
                if len(frames) >= 3:
                    return frames
        except (LLMClientError, Exception):
            pass  # fallback

    # 回退：ASR segments 直接抽帧
    if asr_segments:
        return [
            {"time_sec": int(s.get("start", 0)), "reason": "", "source": "asr_segment"}
            for s in asr_segments[:max_frames]
        ]

    # 最终回退：均匀采样（每 10 秒）
    import math
    num_frames = min(max_frames, math.ceil(video_duration / 10))
    return [
        {"time_sec": i * 10, "reason": "", "source": "interval"}
        for i in range(num_frames)
    ]
```

- [ ] **Step 4: Run tests**

```bash
cd /e/project/douyin_to_obsidian && python -m pytest tests/vision/test_semantic_frame_selector.py -v --tb=short 2>&1 | tail -5
```

Expected: 6/6 PASS

- [ ] **Step 5: Commit**

```bash
git add src/vision/semantic_frame_selector.py tests/vision/test_semantic_frame_selector.py
git commit -m "feat(vision): M6 Task 3 — 语义选帧（LLM 识别关键时间点 + ASR/均匀采样回退）"
```

---

## Task 4: Scheduler 适配（src/pipeline/scheduler.py 最小化改动）

**Files:**
- Modify: `src/pipeline/scheduler.py`（import 块 + `_run_vision` + `_run_asr_fallback`）
- Modify: `config.example.yaml`
- Test: `tests/pipeline/test_scheduler_m6.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/pipeline/test_scheduler_m6.py
"""M6 scheduler 适配测试 — 语义选帧 + get_llm_client + get_vlm_client 集成。"""
import pytest
from unittest.mock import MagicMock
from src.vision.semantic_frame_selector import select_semantic_frames

class TestSchedulerM6Integration:
    def test_select_semantic_frames_llm_success(self):
        mock_client = MagicMock()
        mock_client.chat_json.return_value = [
            {"time_sec": 15, "reason": "关键点1"},
            {"time_sec": 45, "reason": "关键点2"},
            {"time_sec": 90, "reason": "关键点3"},
        ]
        segments = [{"start": i * 10, "end": i * 10 + 10, "text": f"seg{i}"} for i in range(10)]
        result = select_semantic_frames(segments, mock_client)
        assert len(result) == 3
        assert result[0]["source"] == "semantic"

    def test_select_semantic_frames_llm_fallback(self):
        mock_client = MagicMock()
        mock_client.chat_json.side_effect = Exception("timeout")
        segments = [{"start": 5, "end": 15, "text": "a"}]
        result = select_semantic_frames(segments, mock_client)
        assert len(result) == 1
        assert result[0]["source"] == "asr_segment"

    def test_select_semantic_frames_no_segments(self):
        result = select_semantic_frames([], None)
        assert result == []

    def test_select_semantic_frames_interval_fallback(self):
        result = select_semantic_frames([], None, video_duration=60)
        assert len(result) >= 3
        assert all(f["source"] == "interval" for f in result)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /e/project/douyin_to_obsidian && python -m pytest tests/pipeline/test_scheduler_m6.py -v --tb=short 2>&1 | tail -10
```

Expected: `ModuleNotFoundError` 或 import error

- [ ] **Step 3: Update `src/pipeline/scheduler.py` imports**

在顶部 import 区域追加：

```python
from src.llm.client import get_llm_client, LLMClient, LLMClientError
from src.vision.vlm_client import get_vlm_client, VLMClient, VLMClientError
from src.vision.semantic_frame_selector import select_semantic_frames
```

保留旧 `from src.llm import get_summarizer, LLMError, SummaryResult` 和 `from src.vision.vlm_client import describe_image` 向后兼容。

- [ ] **Step 4: Update `_run_vision()` 改用 VLMClient**

```python
# 旧：
desc = describe_image(kf)

# 新：
vlm_client = get_vlm_client(config)
if vlm_client is not None:
    desc = vlm_client.describe_image(kf, "描述画面关键信息")
else:
    desc = "VLM 未启用"
```

- [ ] **Step 5: Update `_run_asr_fallback()` 改用 get_llm_client**

```python
# 旧：
summarizer = get_summarizer(config)
summary_result = summarizer.summarize(subtitle_vtt, metadata)

# 新：
llm_client = get_llm_client(config)
summary_result = llm_client.chat_json([
    {"role": "system", "content": "你是知识管理助手..."},
    {"role": "user", "content": summary_prompt},
])
```

- [ ] **Step 6: 更新 config.example.yaml**

```yaml
llm:
  provider: openai_compatible  # openai_compatible | ollama_local
  openai_compatible:
    base_url: "https://token-plan-cn.xiaomimimo.com/v1"
    model: "mimo-v2.5-pro"
    api_key_env: "LLM_API_KEY"
  ollama_local:
    model: "qwen2.5:7b"
    base_url: "http://localhost:11434"

vision:
  enabled: false
  provider: ollama  # ollama | cloud_api
  ollama:
    model: "qwen2.5-vl:7b"
    base_url: "http://localhost:11434"
  cloud_api:
    base_url: "https://token-plan-cn.xiaomimimo.com/v1"
    model: "mimo-v2-omni"
    api_key_env: "VLM_API_KEY"

frame_selection:
  provider: semantic  # semantic | asr_segments | interval
  semantic:
    llm_ref: openai_compatible
    max_frames: 15
    fallback: asr_segments
  interval:
    seconds: 10
```

- [ ] **Step 7: Run full test suite**

```bash
cd /e/project/douyin_to_obsidian && python -m pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: 全量 PASS（含 M1-M5 回归 + M6 新增 ~25 个测试）

- [ ] **Step 8: Commit**

```bash
git add src/pipeline/scheduler.py src/llm/ src/vision/ config.example.yaml config.yaml tests/pipeline/test_scheduler_m6.py
git commit -m "feat(pipeline): M6 Task 4 — scheduler 适配（get_llm_client + get_vlm_client + select_semantic_frames）"
```

---

## Task 5: 全量回归测试 + 文档更新

**Files:**
- Modify: `docs/m1/RUNBOOK.md`
- Modify: `docs/m2/KNOWLEDGE.md`

- [ ] **Step 1: Run full test suite**

```bash
cd /e/project/douyin_to_obsidian && python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: 全量 PASS（含 M1-M5 所有回归 + M6 新增 ~25 个测试）

- [ ] **Step 2: 更新 `docs/m1/RUNBOOK.md` 新增 Section 8（M6 本地+云端切换）**

```markdown
## 8. 本地+云端切换（M6）

### 8.1 默认配置：混合用户

```yaml
asr:
  provider: whisper_local        # 本地 Whisper（零 API）
vision:
  provider: ollama               # 本地 Ollama VLM（零 API）
llm:
  provider: openai_compatible    # 云端 mimo-v2.5-pro
```

### 8.2 纯本地用户（无 API key）

```yaml
llm:
  provider: ollama_local
  ollama_local:
    model: "qwen2.5:7b"
    base_url: "http://localhost:11434"
```

### 8.3 纯云端用户（无 GPU）

```yaml
asr:
  provider: mimo_asr
vision:
  provider: cloud_api
  cloud_api:
    base_url: "https://token-plan-cn.xiaomimimo.com/v1"
    model: "mimo-v2-omni"
    api_key_env: "VLM_API_KEY"
```

### 8.4 语义选帧切换

```yaml
frame_selection:
  provider: semantic              # LLM 语义选帧（默认）
  # provider: asr_segments       # ASR segments 直接抽帧（LLM 不可用时）
  # provider: interval           # 均匀采样每 10 秒（无 ASR 时兜底）
```
```

- [ ] **Step 3: 更新 `docs/m2/KNOWLEDGE.md` 新增 Section 10（M6 技术参考）**

```markdown
## 10. M6 本地+云端全兼容技术参考

### 10.1 LLM 统一抽象层

`src/llm/client.py` — `LLMClient` ABC + `OpenAICompatibleLLM` + `OllamaLocalLLM`。
config.yaml `llm.provider` 切换：`openai_compatible` / `ollama_local`。

### 10.2 VLM 统一抽象层

`src/vision/vlm_client.py` — `VLMClient` ABC + `OllamaVLMClient` + `CloudVLMClient`。
config.yaml `vision.provider` 切换：`ollama` / `cloud_api`。

### 10.3 语义选帧

`src/vision/semantic_frame_selector.py` — LLM 识别关键时间点 + ASR segments 回退 + 均匀采样兜底。
config.yaml `frame_selection.provider` 切换：`semantic` / `asr_segments` / `interval`。

### 10.4 开源用户三类配置

| 用户类型 | asr.provider | vision.provider | llm.provider |
|---------|-------------|----------------|-------------|
| 混合（推荐）| whisper_local | ollama | openai_compatible |
| 纯本地 | whisper_local | ollama | ollama_local |
| 纯云端 | mimo_asr | cloud_api | openai_compatible |
```

- [ ] **Step 4: Commit + push**

```bash
git add docs/m1/RUNBOOK.md docs/m2/KNOWLEDGE.md
git commit -m "docs: M6 Task 5 — RUNBOOK 新增本地+云端切换说明 + KNOWLEDGE 新增 M6 技术参考"
git push origin main
```

---

## Self-Review Checklist

| 检查项 | 状态 |
|--------|------|
| Spec 覆盖（D-M6-1 ~ D-M6-5）| ✅ D-M6-1=T1, D-M6-2=T2, D-M6-3=已实现无 task, D-M6-4=T3, D-M6-5=T4 |
| Placeholder 扫描 | ✅ 无 TBD/TODO |
| 类型一致性 | ✅ LLMClient.chat / VLMClient.describe_image / select_semantic_frames 参数名一致 |
| config provider 命名一致 | ✅ openai_compatible / ollama_local / ollama / cloud_api |
| 向后兼容 | ✅ mimo_summarizer.py / describe_image() 保留旧接口 |
