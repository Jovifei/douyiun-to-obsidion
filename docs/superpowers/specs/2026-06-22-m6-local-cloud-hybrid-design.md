---
comet_change: m6-local-cloud-hybrid
role: technical-design
canonical_spec: openspec
---

# M6 本地+云端全兼容 + 语义选帧 — 技术设计文档

> 日期：2026-06-22
> 目标：让系统同时支持本地推理和云端 API，config.yaml 一键切换，开箱即用，适合开源发布。

## Context

M1-M5 已稳定（391 tests, 5 平台支持）。v4.1 方案提出"mimo 语义选帧 + 本地 Ollama VLM"两个核心升级。Jovi 要求**同时兼容本地和云端**，适合开源发布——不同用户有不同硬件/预算。

## 目标用户画像

| 用户类型 | 硬件 | API | 默认配置 |
|---------|------|-----|---------|
| 混合用户（典型） | 4070S/4060 | mimo/智谱/DeepSeek | ASR 本地 + VLM 本地 + LLM 云端 |
| 纯本地用户 | 4070S | 无 | ASR 本地 + VLM 本地 + LLM 本地 Ollama |
| 纯云端用户 | 无 GPU | mimo/智谱/DeepSeek | ASR 云端 + VLM 云端 + LLM 云端 |

默认配置覆盖混合用户（最常见），其他两类改 1-2 行 config 即可。

## 架构决策

### D-M6-1: LLM 统一抽象层

**替换**当前 `src/llm/mimo_summarizer.py`（硬编码 mimo API）为 `src/llm/client.py`（OpenAI-compatible 抽象）。

```python
class LLMClient(ABC):
    def chat(self, messages: list[dict], model: str | None = None) -> str
    def chat_json(self, messages: list[dict], model: str | None = None) -> dict

class OpenAICompatibleLLM(LLMClient):
    """覆盖 mimo / DeepSeek / 智谱 / 本地 Ollama 等任何 OpenAI-compatible 端点。"""
    def __init__(self, base_url: str, api_key: str, default_model: str): ...

class OllamaLocalLLM(LLMClient):
    """本地 Ollama（零 API 成本），直接走 python-ollama SDK。"""
    def __init__(self, model: str = "qwen2.5:7b", base_url: str = "http://localhost:11434"): ...

def get_llm_client(config: dict) -> LLMClient:
    """根据 config.llm.provider 返回对应实例。"""
```

**config.yaml**：
```yaml
llm:
  provider: openai_compatible        # openai_compatible | ollama_local
  openai_compatible:
    base_url: "https://token-plan-cn.xiaomimimo.com/v1"
    model: "mimo-v2.5-pro"
    api_key_env: "LLM_API_KEY"
  ollama_local:
    model: "qwen2.5:7b"
    base_url: "http://localhost:11434"
```

纯本地用户：`llm.provider: ollama_local`。
纯云端用户：`llm.provider: openai_compatible` + 换 base_url/model。

### D-M6-2: VLM 统一抽象层

扩展 `src/vision/vlm_client.py`，当前只有 `describe_image()`（直连 mimo-v2-omni）。新增：

```python
class VLMClient(ABC):
    def describe_image(self, image_path: Path, prompt: str) -> str

class OllamaVLMClient(VLMClient):
    """本地 Ollama VLM（零 API 成本）。"""
    def __init__(self, model: str = "qwen2.5-vl:7b", base_url: str = "http://localhost:11434"): ...

class CloudVLMClient(VLMClient):
    """云端 VLM（mimo-v2-omni / Qwen-VL / 任何 OpenAI-compatible vision 端点）。"""
    def __init__(self, base_url: str, api_key: str, model: str): ...

def get_vlm_client(config: dict) -> VLMClient:
    """根据 config.vision.provider 返回对应实例。"""
```

**config.yaml**：
```yaml
vision:
  enabled: true
  provider: ollama                    # ollama | cloud_api
  ollama:
    model: "qwen2.5-vl:7b"
    base_url: "http://localhost:11434"
  cloud_api:
    base_url: "https://token-plan-cn.xiaomimimo.com/v1"
    model: "mimo-v2-omni"
    api_key_env: "VLM_API_KEY"
```

### D-M6-3: ASR 双轨保留（已有，无新设计）

M2 已实现 `asr.provider: whisper_local | mimo_asr`。无需改动，config 保持原样。

### D-M6-4: 语义选帧（核心新能力）

新增 `src/vision/semantic_frame_selector.py`：

```python
def select_semantic_frames(
    asr_segments: list[dict],
    llm_client: LLMClient,
    max_frames: int = 15,
) -> list[dict]:
    """
    调 LLM 从 ASR segments 识别关键时间点。

    Prompt: "这里是视频的带时间戳转写文本。请识别 3-{max_frames} 个知识重点时刻，
    返回 JSON: [{\"time_sec\": 30, \"reason\": \"讲师展示代码示例\"}, ...]"

    回退链：
    1. LLM 返回 ≥ 3 帧 → 使用语义帧
    2. LLM 返回 < 3 帧 或 API 失败 → fallback 到 ASR segments 直接抽帧
    3. 无 ASR segments → 均匀采样（每 10 秒）
    """
```

**config.yaml**：
```yaml
frame_selection:
  provider: semantic                  # semantic | asr_segments | interval
  semantic:
    llm_ref: openai_compatible       # 复用 LLM 配置（不重复写 base_url/key）
    max_frames: 15
    fallback: asr_segments           # LLM 不可用时回退
  interval:
    seconds: 10
```

### D-M6-5: Scheduler 适配

`src/pipeline/scheduler.py` 改动最小化：
- `_run_asr_fallback()` 调 `get_llm_client(config)` 替代 `get_summarizer(config)`
- `_run_vision()` 调 `get_vlm_client(config)` 替代直接 `describe_image()`
- `_select_frames()` 调 `select_semantic_frames()` 替代 `extract_keyframes_by_segments()`
- `config.frame_selection.provider` 决定选帧策略

## 测试策略

- LLMClient：mock OpenAI-compatible 端点，验证 chat/chat_json
- OllamaLLMClient：mock ollama SDK，验证本地调用路径
- VLMClient：mock httpx.post，验证 Ollama/Cloud 两条路径
- 语义选帧：mock LLM 返回关键时间点 → 验证 ffmpeg 抽帧对应时间戳
- 回退链：LLM 超时 → fallback ASR segments → 验证不崩溃
- 配置驱动：改 config.yaml 一行 → 验证切换到对应 provider

## Spec Patches

新增 2 份 delta spec：`llm-client` + `semantic-frame-selector`。
