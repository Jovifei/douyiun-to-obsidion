---
comet_change: m3-llm-summary-vision
role: technical-design
canonical_spec: openspec
---

# M3 LLM 总结 + 视觉理解 — 技术设计文档

> 日期：2026-06-21
> 上游：`openspec/changes/m3-llm-summary-vision/`（proposal + design + tasks + 4 specs）

## Context

M1 字幕路径 + M2 ASR 路径已通，笔记有完整字幕/转写文字。M3 补 AI 总结 + 视觉理解，让笔记有"摘要"和"画面内容"。

## 决策

### D-M3-1: LLM 总结走 openclaw MCP（合规方案 A）

MiMo token-plan 合规约束。通过 openclaw MCP 工具 `llm_summarize` 调 mimo-v2.5-pro。

### D-M3-2: 视觉理解分层架构

```
视频 → 关键帧（ffmpeg scene detect）→ OCR（PaddleOCR PP-OCRv5 本地）→ VLM（mimo-v2-omni / 本地 Qwen2.5-VL）
```

OCR 本地免费（4070S ~2GB 显存），VLM 默认禁用（config `vision.enabled: false`）。

### D-M3-3: 启发式分流

字幕密度 + 场景变化率 → 3 档：summary_only / summary_with_vlm / ocr_only。

### D-M3-4: LLM prompt 模板

3-5 要点、中文、按重要性排序、字幕 > 8000 字自动截断。

### D-M3-5: frontmatter 字段更新

`summary_status=done/failed`、`ai_summary_model`、`processing_mode` 从占位改为实际值。

### D-M3-6: 串行铁律

4070S 12G：LLM 和 VLM 不并行。config 默认 `vision.enabled: false`。

## 测试策略

- 单元：mock LLM/VLM/OCR，验证结果
- 集成：真实调 mimo-v2.5-pro（500 字字幕）
- E2E：有字幕视频 → AI 总结；PPT 视频 → 关键帧 OCR + VLM
- 性能：5 条 ≤ 4 分钟/条

## Spec Patches

None。
