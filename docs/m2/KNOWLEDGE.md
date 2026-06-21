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
