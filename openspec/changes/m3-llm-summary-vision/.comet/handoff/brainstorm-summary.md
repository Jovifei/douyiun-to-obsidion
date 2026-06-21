# Brainstorm Summary

- Change: m3-llm-summary-vision
- Date: 2026-06-21

## Confirmed Technical Approach

M3 在 M1 字幕路径 + M2 ASR 路径基础上，补 LLM 总结 + 视觉理解。

### LLM 总结（D-M3-1, D-M3-4, D-M3-5）
- mimo-v2.5-pro 走 openclaw MCP 工具 `llm_summarize`（合规方案 A）
- prompt 模板：3-5 要点、中文、按重要性排序
- 字幕 > 8000 字自动截断（前后各 4000 + 中间省略提示）
- 笔记 `## 摘要` 段写入 key_points
- `summary_status=done`，`ai_summary_model="mimo-v2.5-pro"`

### 视觉理解（D-M3-2, D-M3-6）
- 关键帧抽取（ffmpeg scene detect + 均匀采样兜底）
- OCR：PaddleOCR PP-OCRv5（本地 4070S，免费）
- VLM：mimo-v2-omni（走 openclaw MCP 工具，默认 vision.enabled: false）
- 二期：本地 Qwen2.5-VL-7B AWQ-4bit
- 串行铁律：LLM 和 VLM 不并行（4070S 显存限制）

### 启发式分流（D-M3-3）
- 字幕密度 + 场景变化率 → 3 档分流（summary_only / summary_with_vlm / ocr_only）
- 口播类（字幕密度高、场景变化低）→ 纯总结
- PPT/图表类（字幕密度低、场景变化高）→ 总结 + 视觉

## Key Trade-offs and Risks

| 风险 | 缓解 |
|------|------|
| mimo-v2.5-pro 总结质量不稳定 | prompt 模板优化 + 失败时 fallback 纯字幕 |
| PaddleOCR 中文识别率 | 4070S 本地推理，PP-OCRv5 server 级别 |
| 4070S LLM+VLM 并行 OOM | 串行铁律（config 默认 vision.enabled: false）|
| openclaw MCP 工具延迟 | 30s 超时 + 失败时跳过总结 |

## Testing Strategy

- 单元：mock LLM/VLM/OCR client，验证结果字段
- 集成：真实调 mimo-v2.5-pro（用 500 字测试字幕）
- E2E：curl 有字幕视频 → 笔记含 AI 总结；curl PPT 视频 → 笔记含关键帧 OCR + VLM 描述
- 性能：5 条视频串行 ≤ 4 分钟/条

## Spec Patches

None。
