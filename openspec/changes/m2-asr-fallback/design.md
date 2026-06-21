## Context

M1 已跑通"字幕有 → 写笔记"的完整链路。M2 补"字幕无 → ASR 转写 → 写笔记"的兜底路径。

**关键约束**：
- MiMo token-plan 套餐合规（DECISIONS A15）：ASR 调用必须走 openclaw 工具层（方案 A）
- 4070S 12G 显存预算：本地 Whisper 必须串行，不能与 OCR/VLM 并行（PRD §5.3）
- M2 不涉及 LLM 总结（那是 M3）

## Goals / Non-Goals

**Goals**：
1. 无字幕视频自动 ASR 转写，写入 Obsidian 笔记
2. 一期用 mimo-v2.5-asr API（走 openclaw 工具层）
3. 二期用本地 faster-whisper + Belle turbo（零 API 成本）
4. ASR 统一接口：一期/二期可热切换
5. 技术参考文档归纳

**Non-Goals**：
- 不做 LLM 总结（M3）
- 不做关键帧 OCR/VLM（M3）
- 不做 iOS/Android 同步（M4）
- 不做实时流式 ASR

## Decisions

### D-M2-1: ASR 走 openclaw 工具层（合规方案 A）

MiMo token-plan 禁止自动化后端直调。ASR 调用通过 openclaw MCP 工具 `asr_transcribe(audio_path)` 完成，openclaw 内部打 mimo-v2.5-asr API。

### D-M2-2: ASR 统一接口

```python
class ASRResult:
    text: str           # 完整转写文本
    segments: list[dict]  # [{start, end, text}, ...]
    source: str         # "mimo_asr" | "whisper_local"
    confidence: float   # 0-1
```

一期实现 `MimoASRClient`，二期实现 `WhisperLocalClient`，都返回 `ASRResult`。config.yaml 切换：

```yaml
asr:
  provider: mimo  # 或 whisper_local
  mimo:
    model: mimo-v2.5-asr
  whisper:
    model: Belle-whisper-large-v3-turbo-zh
    device: cuda
    compute_type: int8_float16
```

### D-M2-3: 调度器 fetching 阶段加 ASR 分支

```
fetching:
  yt-dlp 下载视频 + 抓字幕
    ├─ 有字幕 → subtitle_source = douyin_native → writing
    └─ 无字幕 → ffmpeg 抽 16kHz wav → ASR 转写
        ├─ mimo-asr 成功 → subtitle_source = mimo_asr → writing
        └─ mimo-asr 失败 → 降级 whisper_local（如已装）
            ├─ whisper 成功 → subtitle_source = whisper_local → writing
            └─ 都失败 → failed(asr_failed)
```

### D-M2-4: 一期 mimo-asr 走 openclaw MCP 工具

openclaw 注册新 MCP 工具 `asr_transcribe`，由 `src/bridge/mcp_server.py` 暴露。解析服务调用 MCP 工具而非直连 API。

### D-M2-5: 二期本地 Whisper 装机但默认关闭

config.yaml `asr.provider: mimo`（默认）。二期装好 faster-whisper + Belle 后改 `asr.provider: whisper_local` 即可切换，零代码改动。

### D-M2-6: 技术参考文档

`docs/m2/KNOWLEDGE.md` 归纳：
- 视频下载地址（yt-dlp 参数、cookie 配置）
- ASR 模型调用步骤（mimo-asr API 格式、faster-whisper Python API）
- 安装地址（cuDNN、ctranslate2、Belle 模型 HuggingFace 链接）
- cuDNN 9 vs 8 配对表（T3 调研核心结论）

## Risks

| Risk | 缓解 |
|------|------|
| mimo-asr 准确率未知 | M2 上线后 A/B 测试，记录 CER |
| openclaw 工具层无 asr_transcribe | 需要注册，类似 mcp_server.py |
| 本地 Whisper 装机踩坑 cuDNN | T3 调研已记录配对表，照做 |
| ASR 转写结果与字幕质量差异 | 两种来源都记录到 frontmatter `subtitle_source`，用户可判断 |
