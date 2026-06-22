# M2 KNOWLEDGE — 抖音视频下载与 ASR 转写技术参考

## 1. 视频下载（yt-dlp）

### 1.1 关键 yt-dlp 参数

| 参数 | 用途 | 示例 |
|------|------|------|
| `--write-subs` | 下载已有字幕 | `yt-dlp --write-subs` |
| `--write-auto-sub` | 下载自动生成字幕 | `yt-dlp --write-auto-sub --sub-langs zh` |
| `--sub-langs` | 指定字幕语言 | `--sub-langs zh,en` |
| `--sub-format` | 字幕格式 | `--sub-format vtt/srt` |
| `--socket-timeout` | 连接超时（秒） | `--socket-timeout 30` |
| `--retries` | 下载重试次数 | `--retries 3` |
| `-o` | 输出模板 | `-o "%(id)s.%(ext)s"` |
| `--cookies` | Cookie 文件 | `--cookies cookies.txt` |

### 1.2 Cookie 配置

抖音反爬依赖 Cookie 验证登录态。Cookie 文件格式为 Netscape 格式（`cookies.txt`）。

获取方式：
1. Chrome 登录抖音 → F12 → Application → Cookies
2. 使用 `yt-dlp --cookies-from-browser chrome` 自动提取（推荐）
3. 或使用 EditThisCookie 等扩展导出为 Netscape 格式

Cookie 有效期约 7-30 天，过期后需重新获取。

### 1.3 抖音反爬现状（2026-06）

- 未登录状态：视频下载成功率约 70%，部分视频被限流
- 登录状态（有效 Cookie）：成功率 >95%
- 短链 `v.douyin.com` 需 302 跟随解析为长链
- 视频 ID 格式：纯数字（如 `7387567890123456789`）
- 部分视频字幕仅自动字幕（auto_generated），部分有人工字幕（douyin_native）
- 无字幕视频需走 ASR 路径

## 2. ASR 模型调用

### 2.1 MiMo ASR API（mimo-v2.5-asr）

通过 openclaw MCP 工具 `asr_transcribe` 调用。

**调用方式：**
```python
# 通过 subprocess 调用 openclaw CLI
subprocess.run(
    ["openclaw", "tool", "call", "asr_transcribe",
     "--audio-path", str(audio_path)],
    capture_output=True, text=True, timeout=30,
)
```

**返回格式：**
```json
{
  "text": "转写的完整文本",
  "segments": [
    {"start": 0.0, "end": 2.5, "text": "片段文本"}
  ],
  "source": "mimo_asr",
  "confidence": 0.95
}
```

**前置条件：**
- `MIMO_API_KEY` 环境变量
- openclaw MCP 服务运行中

### 2.2 faster-whisper 本地调用（Belle 模型）

```python
from faster_whisper import WhisperModel

model = WhisperModel(
    "Belle/Belle-whisper-large-v3-turbo-zh",
    device="cuda",
    compute_type="int8_float16",
)

segments, info = model.transcribe(
    audio_path,
    language="zh",
    vad_filter=True,
)

for seg in segments:
    print(f"[{seg.start:.1f}s -> {seg.end:.1f}s] {seg.text}")
```

**关键参数：**
- `language="zh"` — 强制中文，避免语言检测开销
- `vad_filter=True` — 启用 VAD 静音过滤，提升速度
- `compute_type="int8_float16"` — INT8 量化 + FP16 计算，平衡速度与精度

## 3. 安装地址

### 3.1 cuDNN 9.x

- 下载：https://developer.nvidia.com/cudnn-downloads
- 选择 CUDA 12.x 对应版本
- 安装后验证：`python -c "import torch; print(torch.backends.cudnn.version())"`

### 3.2 ctranslate2

```bash
pip install ctranslate2>=4.5.0
```

faster-whisper 依赖 ctranslate2 作为推理后端。

### 3.3 Belle 模型

- HuggingFace：https://huggingface.co/Belle/Belle-whisper-large-v3-turbo-zh
- 大小：约 3GB（int8_float16 量化后）
- 首次运行自动下载到 HuggingFace 缓存目录

## 4. cuDNN 配对表

| ctranslate2 版本 | 要求 cuDNN 版本 | 说明 |
|-----------------|----------------|------|
| >= 4.5 | cuDNN 9.x | 新版，推荐 |
| < 4.5 | cuDNN 8.x | 旧版 |

检查当前版本：
```bash
pip show ctranslate2 | grep Version
python -c "import torch; print(torch.backends.cudnn.version())"
```

## 5. 性能基准（RTX 4070 SUPER）

| 模型 | 速度 | 显存占用 | CER | 备注 |
|------|------|---------|-----|------|
| mimo-v2.5-asr（云端） | ~1x 实时 | N/A（云端） | ~3% | 依赖网络，延迟 2-5s |
| Belle-whisper-large-v3-turbo-zh（int8_float16） | ~8x 实时 | ~2.5GB | ~4% | 本地推理，10 分钟音频约 75s |
| Belle-whisper-large-v3-turbo-zh（int8） | ~6x 实时 | ~2.0GB | ~5% | 显存更省，精度略降 |

**说明：**
- "速度"指处理 1 分钟音频所需时间（N x 实时 = 处理 1 分钟需 60/N 秒）
- CER（字错率）基于内部测试集估算，实际因视频而异
- 4070S 显存 12GB，int8_float16 可同时处理单任务，无需担心 OOM
- 首次加载模型需 3-5 秒（模型缓存到 GPU 后续秒级启动）

## 6. LLM 总结（M3）

### 6.1 Prompt 模板（D-M3-4 格式）

```
请根据以下视频字幕文本生成结构化总结。

要求：
1. 提炼 3-5 个核心要点，按重要性排序
2. 使用中文输出
3. 每个要点简洁明了，一句话概括

字幕文本：
{subtitle_text}

请以 JSON 格式输出：
{"key_points": ["要点1", "要点2", "要点3"]}
```

**截断策略**：字幕超过 8000 字时，保留前后各 4000 字，中间用 `...` 连接。

**解析降级**：
1. 优先 JSON 解析 `{"key_points": [...]}`
2. 支持 ```json 代码块包裹
3. 降级为 `- ` 开头的文本列表
4. 最终降级：按句号分割

### 6.2 API 调用参数

| 参数 | 值 | 说明 |
|------|-----|------|
| model | mimo-v2.5-pro | MiMo 旗舰模型 |
| timeout | 30s | 单次请求超时 |
| messages | `[{"role": "user", "content": prompt}]` | chat/completions 格式 |

### 6.3 SummaryResult 数据结构

```python
@dataclass
class SummaryResult:
    summary_text: str        # 完整总结文本
    key_points: list[str]    # 3-5 个核心要点
    model: str               # 模型名称
    source: str              # 数据源（mimo_llm）
    confidence: float        # 置信度（当前未使用）
```

## 7. 视觉理解（M3）

### 7.1 VLM 选型对比

| 维度 | mimo-v2-omni（云端） | 本地 Qwen2.5-VL-7B |
|------|---------------------|---------------------|
| 推理延迟 | 2-5s/帧（含网络） | 3-8s/帧（4070S） |
| 显存占用 | 0（云端） | ~8GB（7B 参数） |
| 图像理解 | 优秀（多模态训练） | 良好（开源基座） |
| OCR 能力 | 一般 | 一般（需专用 OCR） |
| 可用性 | 需 API key + 网络 | 离线可用 |
| 成本 | 按 token 计费 | 仅电费 |
| 推荐场景 | 网络稳定 + 低延迟需求 | 隐私敏感 + 离线环境 |

**当前选择**：mimo-v2-omni（云端），后续可切换本地 Qwen2.5-VL-7B。

### 7.2 关键帧提取

- 基于 ffmpeg 场景检测：`-vf "select=gt(scene\,0.4)"`
- `scene_threshold` 默认 0.4，可配置
- `keyframe_max` 默认 30，防止过多帧导致显存溢出
- 输出格式：JPEG，存入 `{video_id}_keyframes/` 临时目录

### 7.3 启发式分流（RoutingDecision）

| 决策 | 条件 | 处理路径 |
|------|------|---------|
| SUMMARY_ONLY | 口播类（字幕密度高 + 场景变化低） | 只跑 LLM 总结 |
| SUMMARY_WITH_VLM | PPT/图表类（字幕密度低 + 场景变化高） | LLM + OCR + VLM |
| OCR_ONLY | 纯画面无语音 | 仅 OCR |

**阈值**：
- 字幕密度高：>= 0.5 字/秒
- 字幕密度低：<= 0.3 字/秒
- 场景变化低：<= 0.3
- 场景变化高：>= 0.5

## 8. 4070S 显存预算表

| 模型 | 显存占用 | 说明 |
|------|---------|------|
| LLM（mimo-v2.5-pro） | ~0（云端） | API 调用，不占本地显存 |
| OCR（PaddleOCR） | ~2GB | 本地推理 |
| VLM（Qwen2.5-VL-7B） | ~8GB | 本地推理（如启用） |
| ASR（Belle-whisper） | ~2.5GB | 本地推理（int8_float16） |

**串行铁律**：LLM → VLM 必须串行执行，不能并行。原因：
1. VLM ~8GB + ASR ~2.5GB = ~10.5GB，接近 12GB 上限
2. 并行可能导致 OOM
3. LLM 为云端调用不占本地显存，可与 ASR 并行（但当前实现为串行）

**推荐配置**：
- 默认：LLM（云端）+ ASR（本地）→ 总显存 ~2.5GB
- 进阶：LLM + ASR + VLM（串行）→ 峰值显存 ~10.5GB
- 极限：LLM + ASR + VLM + OCR（串行）→ 峰值显存 ~12.5GB（需关闭其他 GPU 应用）

## 9. M4 健壮性技术参考

### 9.1 Cookie 轮转算法

`probe_and_rotate(cookies_path, backup_dir)` 实现 cookie 过期自动恢复：

```
输入: 主 cookies 路径, 备份目录
流程:
  1. probe_cookie(主cookies) → 有效? → return True
  2. 遍历 backup_dir/cookies_backup_*.txt（按 mtime 降序）
  3. probe_cookie(备份文件) → 有效? → shutil.copy2(备份, 主) → return True
  4. 全部无效 → return False
```

**probe_cookie() 实现**：
- 解析 Netscape 格式 `cookies.txt`（tab 分隔：domain, flag, path, secure, expiry, name, value）
- 用 `httpx.Client.get(test_url, cookies=...)` 做 HTTP 探活
- 返回 `200 <= status < 300` 则有效

**备份文件命名约定**：`cookies_backup_YYYYMMDD.txt`，按文件修改时间排序（最新优先）。

### 9.2 退避序列设计原理

退避序列 `[0, 5, 30, 120, 600]` 秒，设计考量：

| 退避 | 设计意图 |
|------|---------|
| 0s   | 首次重试立即执行（可能是瞬时故障） |
| 5s   | 短暂等待，应对瞬时限流 |
| 30s  | 中等等待，应对服务端临时过载 |
| 120s | 长等待，应对较长时间的服务中断 |
| 600s | 最长等待（10分钟），应对严重故障 |

**不可重试错误列表**（优先级高于可重试）：
```python
_NON_RETRYABLE_MESSAGE_PATTERNS = [
    "404", "403", "not found", "forbidden",
]
```

**可重试错误列表**：
```python
_RETRYABLE_MESSAGE_PATTERNS = [
    "network timeout", "connection reset", "connection refused",
    "connection aborted", "temporarily unavailable",
    "service unavailable", "503", "502", "429", "timed out", "timeout",
]
```

**判断逻辑**：`is_retryable(error)` 按优先级：异常类型 → 不可重试模式 → 可重试模式 → 默认 False。

### 9.3 飞书 Incoming Webhook 格式

飞书机器人 webhook 使用 interactive card 格式：

```json
{
  "msg_type": "interactive",
  "card": {
    "header": {
      "title": {"tag": "plain_text", "content": "告警标题"}
    },
    "elements": [
      {"tag": "markdown", "content": "告警内容（支持 markdown）"}
    ]
  }
}
```

**发送方式**：`httpx.post(webhook_url, json=payload, timeout=10.0)`

**去重机制**：内存缓存 `_alert_cache: dict[str, float]`，`is_alert_duplicate(alert_key, cooldown_minutes=30)` 检查同一 key 是否在冷却期内。

**告警失败处理**：所有异常被捕获，返回 False，不阻塞主流程。

## 10. M5 多平台支持

### 10.1 PlatformExtractor ABC

统一接口，所有平台 extractor 继承 `PlatformExtractor`：

```python
class PlatformExtractor(ABC):
    platform: str
    def resolve_url(self, raw_url: str) -> dict    # {video_id, canonical_url, platform}
    def download(self, video_id, canonical_url, out_dir, **kwargs) -> dict
    def extract_metadata(self, info_dict) -> dict
    def classify_subtitle(self, info_dict) -> str
```

工厂注册表：`register_extractor(name, cls)` → `get_extractor(name, config)` 实例化。

### 10.2 已支持平台

| 平台 | 域名 | 短链 | extractor |
|------|------|------|-----------|
| 抖音 | douyin.com, iesdouyin.com | v.douyin.com | DouyinExtractor |
| Bilibili | bilibili.com | b23.tv | BilibiliExtractor |
| 小红书 | xiaohongshu.com | xhslink.com | XiaohongshuExtractor |
| YouTube | youtube.com | youtu.be | YouTubeExtractor |

### 10.3 批量 URL 提取

`extract_all_urls(text: str) -> list[str]` 从飞书消息提取所有支持平台 URL。

- 正则匹配 `https?://[^\s]+`
- 过滤：只保留已识别平台 URL
- 去重 + 保持首次出现顺序

### 10.4 平台下载策略

| 平台 | 主路径 | 兜底 |
|------|--------|------|
| 抖音 | yt-dlp | DouK-Downloader |
| Bilibili | yt-dlp | 无 |
| 小红书 | yt-dlp | requests 兜底 |
| YouTube | yt-dlp | 无 |

### 10.5 小红书双层策略

小红书反爬较强，采用双层策略：
1. **yt-dlp 优先**：标准下载路径
2. **requests 兜底**：从页面 SSR 数据提取视频 URL，直接下载

失败时自动降级到 requests 路径。

## 11. M6 技术参考

### 11.1 LLM 统一抽象层架构

```
src/llm/
  __init__.py          # SummarizerClient ABC + get_summarizer 工厂（M3 向后兼容）
  client.py            # LLMClient ABC + OpenAICompatibleLLM + OllamaLocalLLM + get_llm_client 工厂
  mimo_summarizer.py   # MimoSummarizer（旧 M3 实现，保留）
```

**双层接口**：
| 接口 | 用途 | 方法 |
|------|------|------|
| `SummarizerClient` | M3 字幕总结 | `summarize(text, metadata) -> SummaryResult` |
| `LLMClient` | M6 通用 LLM 调用 | `chat(messages) -> str` / `chat_json(messages) -> dict` |

**工厂路由**：
- `get_summarizer(config)` → 按 `llm.provider` 路由（mimo/local）
- `get_llm_client(config)` → 按 `llm.provider` 路由（openai_compatible/ollama_local）

### 11.2 VLM 统一抽象层架构

```
src/vision/
  vlm_client.py              # VLMClient ABC + OllamaVLMClient + CloudVLMClient + get_vlm_client 工厂
  semantic_frame_selector.py  # select_semantic_frames（语义选帧）
  heuristic_router.py         # classify_video（启发式分流）
  keyframe_extractor.py       # extract_keyframes（ffmpeg 场景检测）
  ocr_client.py               # extract_text_from_image（PaddleOCR）
```

**VLMClient 接口**：
```python
class VLMClient(ABC):
    def describe_image(self, image_path: Path, prompt: str) -> str: ...
```

**工厂路由**：
- `get_vlm_client(config)` → 按 `vision.provider` 路由（ollama/cloud_api）
- `vision.enabled=false` → 返回 None

### 11.3 语义选帧回退链

```
select_semantic_frames(asr_segments, llm_client, max_frames, video_duration)
  │
  ├─ LLM 可用 + segments 非空 → LLM 语义分析（chat_json）
  │   ├─ 返回 >=3 帧 → source="semantic" ✓
  │   └─ 返回 <3 帧 / 异常 → fallback ↓
  │
  ├─ segments 非空 → ASR segments 直接抽帧
  │   └─ source="asr_segment" ✓
  │
  └─ 无 segments + video_duration > 0 → 均匀采样（每 10 秒）
      └─ source="interval" ✓
```

**prompt 模板**（`SEMANTIC_SELECT_PROMPT`）：
- 输入：ASR segments 带时间戳文本
- 输出：JSON 数组 `[{"time_sec": N, "reason": "..."}]`
- 模型：引用 `llm_ref` 指定的 LLM provider

### 11.4 开源用户三类配置对照表

| 维度 | 默认混合 | 纯本地 | 纯云端 |
|------|---------|--------|--------|
| **LLM** | openai_compatible（云端） | ollama_local（qwen2.5:7b） | openai_compatible（云端） |
| **ASR** | whisper_local（本地 GPU） | whisper_local（本地 GPU） | mimo（云端） |
| **VLM** | ollama（本地，按需启用） | ollama（qwen2.5-vl:7b） | cloud_api（mimo-v2-omni） |
| **选帧** | semantic（LLM 分析） | semantic（本地 LLM） | semantic（云端 LLM） |
| **GPU 需求** | 4070S（ASR ~2.5GB） | 4070S+（ASR+VLM ~10.5GB） | 无 |
| **API 成本** | LLM 按 token 计费 | 零 | LLM+ASR+VLM 按 token 计费 |
| **网络依赖** | LLM 需网络 | 无 | 全部需网络 |
| **推荐场景** | 日常使用 | 隐私敏感/离线 | 无 GPU 环境 |
