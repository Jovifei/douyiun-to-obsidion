---
comet_change: m2-asr-fallback
role: technical-design
canonical_spec: openspec
---

# M2 ASR 兜底 — 技术设计文档

> 日期：2026-06-21
> 上游：`openspec/changes/m2-asr-fallback/`（proposal + design + tasks + 4 specs）

## Context

M1 只支持有抖音原生字幕的视频（~70-80%）。无字幕视频直接 `failed(no_subtitle_in_m1)`。M2 补 ASR 兜底：无字幕时自动转写，写入笔记。

## 决策

### D-M2-1: ASR 走 openclaw 工具层（合规方案 A）

MiMo token-plan 禁止自动化后端直调。ASR 调用通过 openclaw MCP 工具 `asr_transcribe(audio_path)` 完成。

### D-M2-2: ASR 统一接口

```python
@dataclass
class ASRResult:
    text: str
    segments: list[dict]  # [{start, end, text}]
    source: str           # "mimo_asr" | "whisper_local"
    confidence: float
```

一期 `MimoASRClient`，二期 `WhisperLocalClient`，都返回 `ASRResult`。config.yaml 切换 `asr.provider`。

### D-M2-3: 调度器 fetching 阶段加 ASR 分支

```
yt-dlp 下载 + 抓字幕
  ├─ 有字幕 → subtitle_source=douyin_native → writing（M1 不变）
  └─ 无字幕 → ffmpeg 抽 16kHz wav → ASR
      ├─ mimo-asr 成功 → subtitle_source=mimo_asr → writing
      └─ mimo-asr 失败 → 降级 whisper_local
          ├─ 成功 → subtitle_source=whisper_local → writing
          └─ 都失败 → failed(asr_failed)
```

### D-M2-4: mimo-asr 走 openclaw MCP

`src/bridge/mcp_server.py` 新增 `asr_transcribe` 工具。解析服务调 MCP 工具而非直连 API。

### D-M2-5: 本地 Whisper 装机但默认关闭

config.yaml `asr.provider: mimo`（默认）。装好 faster-whisper + Belle 后改 `whisper_local` 即切换。

### D-M2-6: 技术参考文档

`docs/m2/KNOWLEDGE.md` 归纳：视频下载地址、ASR 模型调用、安装地址、cuDNN 配对表、性能基准。

## 测试策略

| 层 | 方法 |
|----|------|
| 单元 | mock ASRClient，验证 ASRResult 字段 |
| 集成 | 真实调 mimo-asr（5 秒测试音频） |
| E2E | curl 无字幕视频 → 2 分钟内 vault 出笔记 |
| 性能 | 4070S 30 秒音频 < 5 秒 |

## Spec Patches

None。
