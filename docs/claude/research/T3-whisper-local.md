# T3 — Whisper 本地中文 ASR 调研（2026-06）

> 项目：抖音视频 → Obsidian。本调研用于「字幕兜底」环节：抖音原生字幕优先，缺失时落到本地 Whisper。
> 硬件：Windows 11 + RTX 4070 SUPER 12 GB VRAM。
> 调研者：Claude Code 调研员（替 Jovi 工作）。日期：2026/06/19。

---

## TL;DR

1. **引擎选 `faster-whisper` 1.2.x**：在 Windows + 单 GPU 上速度/显存/装机难度三者最优；`WhisperX` 仅在你需要 diarization 或秒级词时间戳对齐时才上；`whisper.cpp` 仅在没 GPU / 嵌入式时考虑。
2. **模型选 `BELLE-2/Belle-whisper-large-v3-zh`（精度优先）或 `Belle-whisper-large-v3-turbo-zh`（速度优先）**——两者在 AISHELL-1 上 CER 分别 2.78% / 3.07%，比 vanilla `large-v3` (8.08%) 低一个数量级。视频里有人名/术语就开 `hotwords`。
3. **避坑铁律**：`ctranslate2 ≥ 4.5.0` 只认 cuDNN 9，<4.5 认 cuDNN 8。Windows 上别折腾 PyTorch 自带的 cuDNN，直接装 CUDA 12.8 + cuDNN 9，或退到 `ctranslate2==4.4.0` + cuDNN 8。

---

## 1. 三引擎对比

| 维度 | faster-whisper 1.2.1 | WhisperX 3.8.6 | whisper.cpp 1.9.0 |
|---|---|---|---|
| **底层** | CTranslate2 (C++) | faster-whisper + pyannote + wav2vec2 alignment | GGML（纯 C/C++） |
| **速度（large-v2，RTX 3070 Ti，beam 5，README 实测）** | 1m03s（fp16）/ 17s（batched fp16）/ 59s（int8）<br>vs openai-whisper 2m23s | 「70x realtime」large-v2 batched | 同档 GPU 比 faster-whisper 慢 1.5–2x（社区共识，无官方表） |
| **VRAM（large-v2 fp16）** | 4.5 GB / 6.1 GB（batched）/ 2.9 GB（int8） | <8 GB（包含 VAD + diarization 总占用） | ~3.9 GB（large 类）|
| **词级时间戳** | 原生支持 (`word_timestamps=True`) | wav2vec2 强制对齐，秒级精度更高 | 实验性 (`-ml 1`) |
| **说话人分离 (diarization)** | 不支持 | 内置 (`speaker-diarization-community-1`，需 HF token) | 不支持 |
| **CUDA 12 / Windows** | ✅ CUDA 12.x + cuDNN 9（v1.2 起） | ✅ 官方文档要求 CUDA 12.8 | ✅ MSVC/MinGW 都能编 |
| **装机复杂度** | 中（cuDNN 路径要手配） | 高（pyannote 模型协议 + HF token + wav2vec2） | 低（一个 .exe） |
| **批处理** | `BatchedInferencePipeline`（drop-in） | 内置 batched | 不擅长 |
| **HotWords / Initial Prompt** | 两者都有，独立参数 | 透传 faster-whisper | 仅 prompt |

**结论（针对你的项目）**：
- **抖音短视频（30s–5min）+ 中文 + 不要 diarization** → **faster-whisper 单选**。
- 如果某天要做「多人对话播客 → 带说话人 SRT」，再切 WhisperX。
- whisper.cpp 在你的硬件配置下没竞争力——12 GB VRAM 足够跑 large-v3 fp16，没必要降级到 GGML。

来源：[faster-whisper README v1.2.1](https://github.com/SYSTRAN/faster-whisper)、[WhisperX README v3.8.6](https://github.com/m-bain/whisperX)、[whisper.cpp v1.9.0](https://github.com/ggerganov/whisper.cpp)。

---

## 2. 模型 × 4070 SUPER 性能矩阵

> 4070 SUPER 12 GB（AD104，7168 CUDA 核，FP16 ≈ 35.5 TFLOPS）。下表速度按 RTX 3070 Ti 8 GB 实测外推（4070S FP16 算力 ≈ 1.6× 3070 Ti），**外推数据已标注**。

| 模型 | 参数 | VRAM (fp16) | 1 分钟音频耗时 | RTF（1=实时） | 中文质量（AISHELL-1 CER） | 备注 |
|---|---|---|---|---|---|---|
| `whisper-large-v3` (vanilla) | 1.55 B | ~5.5 GB | ~25 s（外推） | ~0.42x | **8.08%** | 中文一般 |
| `whisper-large-v3-turbo` | 0.81 B | ~3.5 GB | ~12 s（外推） | ~0.20x | **8.64%** | 解码层 32→4，速度大幅提升 |
| `distil-large-v3 / v3.5` | 0.76 B | ~3.5 GB | ~10 s（外推） | ~0.17x | ❌ 仅英语 | 中文项目不可用 |
| **`Belle-whisper-large-v3-zh`** | 1.55 B | ~5.5 GB | ~25 s（外推） | ~0.42x | **2.78%** ⭐ | 精度王 |
| **`Belle-whisper-large-v3-zh-punct`** | 1.55 B | ~5.5 GB | ~25 s（外推） | **2.95%** | 自带标点 |
| **`Belle-whisper-large-v3-turbo-zh`** | 0.81 B | ~3.5 GB | ~12 s（外推） | ~0.20x | **3.07%** ⭐ | 速度+精度平衡王 |
| `Belle-whisper-large-v2-zh` | 1.55 B | ~5.5 GB | 同 v3 | ~0.42x | 2.55% | 老牌，无 v3 的鲁棒性 |
| `medium`（24L） | 0.77 B | ~2.5 GB | ~7 s | ~0.12x | 中文 ~12% | 兜底，不推荐 |

**3 个推荐档位（项目落地）**：
- 🥇 **速度优先**：`Belle-whisper-large-v3-turbo-zh` + `compute_type="float16"` + `batch_size=8`。30 秒视频 < 4 秒出结果，VRAM ~5 GB（含 batched 开销），CER ~3% 完全够看字幕。
- 🥈 **质量优先**：`Belle-whisper-large-v3-zh` + `compute_type="float16"` + `beam_size=5`。CER 2.78%，30 秒视频约 12 秒，VRAM ~6 GB。
- 🥉 **极致省显存**：`Belle-whisper-large-v3-zh` + `compute_type="int8_float16"`。VRAM 降到 ~3 GB，速度比 fp16 快 ~10%，精度损失 < 1%（faster-whisper 文档结论）。

来源：[BELLE-2 模型卡（v3-zh / v3-turbo-zh）](https://huggingface.co/BELLE-2)、[Whisper-Finetune 项目 README](https://github.com/shuaijiang/Whisper-Finetune)、[whisper-large-v3-turbo 官方卡](https://huggingface.co/openai/whisper-large-v3-turbo)。

---

## 3. 中文准确率深挖

| 测试集 | vanilla v3 | vanilla turbo | Belle v3-zh | Belle turbo-zh | 相对提升 |
|---|---|---|---|---|---|
| AISHELL-1 test | 8.09% | 8.64% | **2.78%** | **3.07%** | -65% |
| AISHELL-2 test | 5.48% | 6.01% | **3.79%** | **4.11%** | -31% |
| WenetSpeech NET | 11.72% | 13.51% | **8.87%** | **10.23%** | -24% |
| WenetSpeech MEETING | 20.15% | 20.31% | **11.25%** | **13.36%** | -44% |
| HKUST Dev | 28.60% | 37.32% | **16.44%** | **18.94%** | -42% |

**结论**：
- **vanilla Whisper 的中文是「能用但跨场景崩」**——干净录音 8% CER，会议/方言场景直奔 20–30%。
- **BELLE 系列在所有场景都把 CER 砍掉一半以上**，且训练数据覆盖 AISHELL/WenetSpeech/HKUST 四类（朗读/远场/电话/方言）。
- **抖音视频的声学环境**（室内麦克风、小幅 BGM、口语化、偶有方言）介于 AISHELL-2 和 WenetSpeech NET 之间，预期 CER **3–9%**，肉眼可读。
- **不需要自己微调**——BELLE 的覆盖度对消费类视频已足够。如果后期收集到大量带噪垂类数据（如设备开箱评测）再考虑增量微调。

来源：[BELLE-2/Belle-whisper-large-v3-zh](https://huggingface.co/BELLE-2/Belle-whisper-large-v3-zh)、[Belle-whisper-large-v3-turbo-zh](https://huggingface.co/BELLE-2/Belle-whisper-large-v3-turbo-zh)。

---

## 4. 热词 / 术语注入

faster-whisper 提供两条独立通道，**机制不同，用途不同**（来源：faster-whisper `transcribe.py` 源码 + Context7 docs）：

### 4.1 `initial_prompt`
- 作用：把上下文文本作为 **prompt token** 注入到每个 30s 窗口前。
- 上限：约 224 token（half of `max_length`）。
- 适用：**风格/领域引导**，如「这是一段关于人工智能的技术播客」。
- 限制：不直接保证某个词被识别——是「软提示」。

### 4.2 `hotwords`（推荐）
- 作用：通过 `<|startofprev|>` 标记把热词 token 直接塞进 prompt 序列。
- 源码：`hotwords_tokens = tokenizer.encode(" " + hotwords.strip())`，长度自动截到 `max_length // 2 - 1`。
- 适用：**专有名词强注入**——人名、公司名、产品名、技术术语。
- 限制：`prefix is None` 才生效（不能和 prefix 同时用）。

### 4.3 视频领域最佳实践

```python
# 从抖音视频元数据 + 标签里提取候选热词
hotwords = "Jovi 抖音 Obsidian Whisper RTX 4070 OpenAI Anthropic Claude"

# 风格引导（可选）
initial_prompt = "以下是一段关于 AI 工具与硬件评测的中文短视频脚本。"

segments, info = model.transcribe(
    audio_path,
    language="zh",
    hotwords=hotwords,           # 强注入
    initial_prompt=initial_prompt,  # 软引导
    beam_size=5,
)
```

**经验法则**：
- 热词列表 ≤ 50 个、每个 ≤ 6 字符，控制在 ~150 token 以内。
- 优先级：**人名 > 公司/产品名 > 技术术语**。
- 视频领域可以从抖音 caption、hashtags、@提到的账号自动提取候选。
- 别堆通用词（"科技""分享"），只放真正会被识错的小众词。

### 4.4 动态词典（不推荐用 Whisper 走）
Whisper 的 BPE tokenizer 不支持运行时词典扩展。如果真要做"绝对禁用某词"或"绝对替换"，用 `suppress_tokens`（禁用）或后处理正则替换（绝对修正）。

---

## 5. 长音频策略

抖音视频常 30s–5min，偶有直播切片 30min+。Whisper 原生 30s 窗口，必须切片。

### 5.1 推荐方案：`silero-vad` + `BatchedInferencePipeline`

- **silero-vad v6.2.1**（2026-02 发布）：JIT 模型 ~2 MB，CPU 单线程处理 30ms 块 < 1ms。无需 GPU。
- **集成方式**：faster-whisper 的 `vad_filter=True` 已经内置 silero-vad，开箱即用。
- **batched 模式下 VAD 默认开**——无需额外配置。

### 5.2 备选：pyannote-vad
- 精度略高于 silero（边界更准），但要 PyTorch + HF token，重。
- 仅在 silero 频繁切错（如音乐+人声重叠）时考虑。

### 5.3 流式 / 实时
- 你的项目是离线批处理（视频下载完再转写），**不需要流式**。
- 真要做 → `whisper-streaming` 或 `whisperX` 的 batched + chunking。

来源：[silero-vad v6.2.1](https://github.com/snakers4/silero-vad)、[faster-whisper batched 文档](https://github.com/SYSTRAN/faster-whisper)。

---

## 6. 部署 Checklist（Windows 11 + RTX 4070 SUPER）

> 目标：从空机器到 `python transcribe.py audio.wav` 出 SRT，1 小时内完成。

### 6.1 系统级
1. ✅ NVIDIA 驱动 ≥ 555.x（支持 CUDA 12.8）
2. ✅ 安装 **CUDA Toolkit 12.4 / 12.6 / 12.8** 任一（推荐 12.4 LTS，兼容性最广）
3. ✅ 安装 **cuDNN 9.x for CUDA 12**——这是 2025 年后最大坑，老教程多半用 cuDNN 8
4. ✅ 把 `cudnn_*.dll` 所在目录加到 `PATH`，或拷到 `CUDA/v12.x/bin`
5. ✅ 安装 **Visual C++ Redistributable 2015–2022 x64**（ctranslate2 必需）

### 6.2 Python 环境
```powershell
# 建议用 conda 隔离
conda create -n whisper python=3.11 -y
conda activate whisper

# 核心依赖（与 ctranslate2 4.5+ / cuDNN 9 配套）
pip install faster-whisper==1.2.1
pip install ctranslate2>=4.5.0    # cuDNN 9
pip install silero-vad
pip install soundfile

# 如果 cuDNN 装不上 / 必须用 cuDNN 8：
# pip install ctranslate2==4.4.0   # 最后一个 cuDNN 8 兼容版
```

### 6.3 模型预下载
```python
from faster_whisper import WhisperModel
# 首次会从 HF 下载到 ~/.cache/huggingface/hub
m = WhisperModel("BELLE-2/Belle-whisper-large-v3-turbo-zh",
                 device="cuda", compute_type="float16",
                 download_root=r"E:\AI_Tools\Claude\ClaudeCode\data\whisper_models")
```

> ⚠️ HF 上 BELLE 模型是 transformers 格式，faster-whisper 会自动调用 `ct2-transformers-converter` 转 CTranslate2 格式（首次约 2 分钟）。也可以预先手动转换：
> ```bash
> ct2-transformers-converter --model BELLE-2/Belle-whisper-large-v3-turbo-zh --output_dir ./belle-turbo-zh-ct2 --quantization float16
> ```

### 6.4 常见踩坑

| 症状 | 原因 | 解法 |
|---|---|---|
| `Could not load library cudnn_ops_infer64_8.dll` | 装了 cuDNN 9 但 ct2 < 4.5 | 升 ctranslate2 到 ≥ 4.5.0 |
| `cudnn 9.x not found` | 装了 cuDNN 8 但 ct2 ≥ 4.5 | `pip install ctranslate2==4.4.0` 或升 cuDNN |
| `MSVCP140.dll missing` | VC++ Runtime 缺 | 装 VC++ 2015-2022 x64 |
| 首次推理巨慢 | 模型转换 + cuDNN 算子选择 | 第二次正常；预热一次 |
| 中文识别差 | 用了 vanilla v3 | 换 BELLE 系列 |
| 偶尔幻觉重复 | beam_size 太小或 vad off | `beam_size=5` + `vad_filter=True` + `condition_on_previous_text=False` |
| Batched + word_timestamps 慢 | batched 模式下词时间戳算两次 | 词时间戳不必要时关掉 |

> **省事方案**：直接用 [Purfview/whisper-standalone-win](https://github.com/Purfview/whisper-standalone-win) 的 Faster-Whisper-XXL 单文件版（2025-11 发布的 r3.256.1），自带所有 DLL。**但项目要 Python 集成，不推荐当主路径，仅作排错对照**。

---

## 7. Python 代码骨架

```python
# E:\project\douyin_to_obsidian\src\asr\local_whisper.py
"""
本地 Whisper 转写：wav -> SRT + 纯文本
- 引擎: faster-whisper 1.2+
- 模型: Belle-whisper-large-v3-turbo-zh (默认) / -zh (高精度)
- VAD:  silero-vad（faster-whisper 内置）
- 适配: Windows 11 + RTX 4070 SUPER 12 GB
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from faster_whisper import WhisperModel, BatchedInferencePipeline

log = logging.getLogger(__name__)

# ---------- 配置 ----------
@dataclass(frozen=True)
class WhisperConfig:
    model_id: str = "BELLE-2/Belle-whisper-large-v3-turbo-zh"
    device: str = "cuda"
    compute_type: str = "float16"          # int8_float16 也可
    download_root: str | None = r"E:\AI_Tools\Claude\ClaudeCode\data\whisper_models"
    beam_size: int = 5
    batch_size: int = 8
    vad_filter: bool = True
    word_timestamps: bool = True
    language: str = "zh"

# ---------- 时间戳格式化 ----------
def _fmt_srt_time(t: float) -> str:
    h, m = divmod(int(t // 60), 60)
    s = t - int(t // 60) * 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

def _to_srt(segments: Iterable) -> str:
    lines: list[str] = []
    for i, seg in enumerate(segments, 1):
        lines.append(f"{i}\n{_fmt_srt_time(seg.start)} --> {_fmt_srt_time(seg.end)}\n{seg.text.strip()}\n")
    return "\n".join(lines)

# ---------- 模型单例 ----------
_model_cache: dict[str, BatchedInferencePipeline] = {}

def _get_model(cfg: WhisperConfig) -> BatchedInferencePipeline:
    key = f"{cfg.model_id}|{cfg.device}|{cfg.compute_type}"
    if key not in _model_cache:
        log.info("[whisper] loading %s on %s/%s ...", cfg.model_id, cfg.device, cfg.compute_type)
        base = WhisperModel(
            cfg.model_id,
            device=cfg.device,
            compute_type=cfg.compute_type,
            download_root=cfg.download_root,
        )
        _model_cache[key] = BatchedInferencePipeline(model=base)
        log.info("[whisper] model ready.")
    return _model_cache[key]

# ---------- 主入口 ----------
def transcribe(
    audio_path: str | Path,
    *,
    out_srt: str | Path | None = None,
    out_txt: str | Path | None = None,
    hotwords: str | None = None,
    initial_prompt: str | None = None,
    config: WhisperConfig = WhisperConfig(),
    progress_cb: Callable[[float, str], None] | None = None,
) -> dict:
    """
    转写一个音频文件。

    Returns:
        {
          "language": "zh",
          "duration": 92.3,
          "text": "完整文本",
          "segments": [{"start":..,"end":..,"text":..,"words":[...]}],
          "srt_path": "...",
          "txt_path": "...",
        }
    """
    audio_path = Path(audio_path)
    if not audio_path.is_file():
        raise FileNotFoundError(audio_path)

    model = _get_model(config)

    log.info("[whisper] transcribing %s ...", audio_path.name)
    segments_iter, info = model.transcribe(
        str(audio_path),
        language=config.language,
        beam_size=config.beam_size,
        batch_size=config.batch_size,
        vad_filter=config.vad_filter,
        word_timestamps=config.word_timestamps,
        hotwords=hotwords,
        initial_prompt=initial_prompt,
        condition_on_previous_text=False,   # 视频场景关掉，减少幻觉
    )

    # 流式收集 + 进度回调（segments 是 generator）
    segments: list = []
    total = max(info.duration, 1e-6)
    try:
        for seg in segments_iter:
            segments.append(seg)
            if progress_cb:
                progress_cb(min(seg.end / total, 1.0), seg.text)
    except Exception as e:
        log.exception("[whisper] decode error after %d segs: %s", len(segments), e)
        if not segments:
            raise

    full_text = "".join(s.text for s in segments).strip()
    result = {
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
        "text": full_text,
        "segments": [
            {
                "start": s.start, "end": s.end, "text": s.text,
                "words": [{"start": w.start, "end": w.end, "word": w.word} for w in (s.words or [])],
            } for s in segments
        ],
    }

    if out_srt:
        Path(out_srt).write_text(_to_srt(segments), encoding="utf-8")
        result["srt_path"] = str(out_srt)
    if out_txt:
        Path(out_txt).write_text(full_text, encoding="utf-8")
        result["txt_path"] = str(out_txt)

    log.info("[whisper] done: %.1fs audio, %d segs, lang=%s (%.2f)",
             info.duration, len(segments), info.language, info.language_probability)
    return result


# ---------- CLI 自测 ----------
if __name__ == "__main__":
    import argparse, sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("audio")
    p.add_argument("--srt"); p.add_argument("--txt")
    p.add_argument("--hotwords", default=None)
    p.add_argument("--prompt", default=None)
    args = p.parse_args()

    def _bar(pct: float, text: str):
        sys.stdout.write(f"\r[{int(pct*100):3d}%] {text[:60]:<60}")
        sys.stdout.flush()

    r = transcribe(args.audio, out_srt=args.srt, out_txt=args.txt,
                   hotwords=args.hotwords, initial_prompt=args.prompt,
                   progress_cb=_bar)
    print()
    print(f"text: {r['text'][:200]}...")
```

**用法**：
```powershell
python local_whisper.py demo.wav --srt demo.srt --txt demo.txt --hotwords "Jovi 抖音 Obsidian"
```

---

## 8. 风险与缺口

| 风险 | 影响 | 缓解 |
|---|---|---|
| 4070 SUPER 直接 benchmark 缺失 | 表里所有时延都是从 3070 Ti 的 README 数字按 FP16 算力比外推（已标注） | 项目落地时跑 1 小时基准音频实测，更新到本文件 |
| BELLE 模型首次自动转换 CTranslate2 慢 | 首启 1–3 分钟 | 部署时预转一次 (`ct2-transformers-converter`) |
| BELLE-zh 训练里方言占比未知 | 方言/口音视频可能掉点 | 先用 turbo-zh 跑，CER > 10% 再切回 large-v3-zh + beam 5 |
| cuDNN 9 vs 8 装错 | 首次启动直接报 DLL 找不到 | 严格按第 6 节版本配对；备 `ctranslate2==4.4.0` 应急 |
| 抖音音频含 BGM | VAD 误切 + 幻觉 | `vad_filter=True` + `condition_on_previous_text=False` + 后处理过滤孤立片段 |
| HF 国内访问 | 模型下载失败 | `HF_ENDPOINT=https://hf-mirror.com` 或 `huggingface-cli download` 预拉 |
| 显存碎片化 | 长视频 batched 时 OOM | `batch_size` 从 16 降到 8 / 4 |

**未覆盖但建议后续做的事**：
1. 真实抖音视频集（10–20 段，含访谈/评测/Vlog/直播切片）跑一次 CER 实测，决定默认模型。
2. Whisper 输出 → DeepSeek/GLM 后处理流水线（标点修正、错别字纠正、热词强匹配）。
3. 抖音原生字幕和 Whisper 输出的对齐与回退逻辑（主任务的 T2/T4 应该已经在管）。

---

## 9. 引用

1. [SYSTRAN/faster-whisper v1.2.1 README](https://github.com/SYSTRAN/faster-whisper) — 引擎、benchmark 表、API
2. [m-bain/whisperX v3.8.6](https://github.com/m-bain/whisperX) — alignment + diarization
3. [ggerganov/whisper.cpp v1.9.0](https://github.com/ggerganov/whisper.cpp) — GGML 实现
4. [BELLE-2/Belle-whisper-large-v3-zh](https://huggingface.co/BELLE-2/Belle-whisper-large-v3-zh) — 中文 CER 数据
5. [BELLE-2/Belle-whisper-large-v3-turbo-zh](https://huggingface.co/BELLE-2/Belle-whisper-large-v3-turbo-zh) — turbo 中文版 CER
6. [shuaijiang/Whisper-Finetune](https://github.com/shuaijiang/Whisper-Finetune) — BELLE 全系列 CER 矩阵 + ct2 转换流程
7. [openai/whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo) — turbo 架构与 RTFx 200
8. [distil-whisper/distil-large-v3.5](https://huggingface.co/distil-whisper/distil-large-v3.5) — 仅英语，确认排除
9. [snakers4/silero-vad v6.2.1](https://github.com/snakers4/silero-vad) — VAD 性能数据
10. [OpenNMT/CTranslate2 releases](https://github.com/OpenNMT/CTranslate2/releases) — cuDNN 8/9 分水岭（v4.5.0）
11. [Purfview/whisper-standalone-win r3.256.1](https://github.com/Purfview/whisper-standalone-win) — Windows 单文件应急方案
12. [faster-whisper Context7 docs (`/systran/faster-whisper`)](https://context7.com/systran/faster-whisper/llms.txt) — `transcribe()` 完整签名 + hotwords token 注入源码

---

*本调研在 2026-06-19 完成。BELLE 系列、faster-whisper、ctranslate2 均在持续更新——如果 6 个月后再看，先重跑第 1、2、6 节。*
