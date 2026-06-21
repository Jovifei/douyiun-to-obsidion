# Brainstorm Summary

- Change: m2-asr-fallback
- Date: 2026-06-21

## Confirmed Technical Approach

M2 在 M1 基础上加 ASR 兜底：yt-dlp 抓不到字幕时，自动下载视频 → ffmpeg 抽 16kHz 音频 → ASR 转写 → 用转写文字替代字幕写入笔记。

**一期**：mimo-v2.5-asr API（走 openclaw MCP 工具层，合规方案 A）。零本地装机成本。
**二期**：本地 faster-whisper + Belle-whisper-large-v3-turbo-zh（4070S 12G）。零 API 成本，离线可用。

ASR 统一接口：`ASRResult(text, segments, source, confidence)`，一期/二期可热切换（config.yaml `asr.provider`）。

调度器改造：fetching 阶段加 ASR 分支（有字幕→字幕路径，无字幕→ASR 路径，ASR 失败→failed）。

## Key Trade-offs and Risks

| 风险 | 缓解 |
|------|------|
| mimo-asr 准确率未知 | 上线后 A/B 测试记录 CER |
| openclaw 工具层无 asr_transcribe | 需在 mcp_server.py 注册新工具 |
| 本地 Whisper cuDNN 踩坑 | T3 调研已记录配对表 |
| 4070S 显存 Whisper+OCR+VLM 并行 | 串行铁律（PRD §5.3） |

## Testing Strategy

- 单元测试：mock ASRClient，验证 ASRResult
- 集成测试：真实调 mimo-asr（5 秒测试音频）
- E2E：curl 提交无字幕视频 → 2 分钟内 vault 出笔记
- 性能：4070S 30 秒音频 < 5 秒

## Spec Patches

None — specs 已在 open 阶段完整创建。
