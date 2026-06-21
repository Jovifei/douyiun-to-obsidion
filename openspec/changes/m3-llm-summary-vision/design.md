## Context

M1 字幕路径 + M2 ASR 路径已通。M3 补 LLM 总结 + 视觉理解。4070S 12G 显存预算：LLM/VLM 必须串行，OCR 可与 LLM 并行。

## Goals / Non-Goals

**Goals**：
1. LLM 总结：3-5 要点，写入笔记 `## 摘要` + frontmatter `summary`
2. 视觉理解：PPT/图表类视频关键帧 OCR + VLM 描述
3. 启发式分流：自动判断视频类型，避免浪费 token
4. frontmatter 状态字段更新：summary_status / processing_mode / ai_summary_model
5. 一期走 openclaw 工具层（合规方案 A），二期本地模型

**Non-Goals**：
- 不做视频搜索/推荐
- 不做多模态 LLM 直接理解整段视频
- 不做用户自定义 prompt 模板
- 不做多语言支持（M3 仅中文）

## Decisions

### D-M3-1: LLM 总结走 openclaw 工具层（合规方案 A）

MiMo token-plan 合规约束。通过 openclaw MCP 工具 `llm_summarize` 调 mimo-v2.5-pro，不直连 API。

### D-M3-2: 视觉理解分层架构

```
视频文件 → 关键帧抽取（ffmpeg/PySceneDetect）
  → OCR 层（PaddleOCR PP-OCRv5，本地 4070S）
  → VLM 层（mimo-v2-omni API / 本地 Qwen2.5-VL-7B）
  → 聚合描述文本
```

三层独立：OCR 本地（免费）、VLM 可选云端/本地。启发式判断视频类型决定是否走 VLM。

### D-M3-3: 启发式分流

```python
def should_run_vlm(subtitle_text, video_duration, scene_change_rate):
    # 口播类（字幕密度高、场景变化低）→ 只总结字幕
    if subtitle_density > 0.5 and scene_change_rate < 0.3:
        return "summary_only"
    # PPT/图表类（字幕密度低、场景变化高）→ 字幕 + 关键帧
    if subtitle_density < 0.3 and scene_change_rate > 0.5:
        return "summary_with_vlm"
    # 混合类
    return "summary_with_vlm"
```

### D-M3-4: LLM 总结 prompt 模板

```
你是知识笔记助手。根据以下抖音视频的字幕内容，提炼 3-5 个核心要点。

要求：
- 每个要点一句话，不超过 30 字
- 按重要性排序
- 用中文
- 不要加序号外的格式

字幕内容：
{subtitle_text}
```

### D-M3-5: frontmatter 字段更新

- `summary_status: "done"`（从 `not_run` 改）
- `ai_summary_model: "mimo-v2.5-pro"`（记录用的哪个模型）
- `processing_mode` 根据实际走的路径更新

### D-M3-6: 串行铁律（显存预算）

4070S 12G 不能同时跑 LLM + VLM + OCR：
- 字幕路径：LLM 单独（~8GB 显存）
- 视觉路径：OCR + VLM 串行（OCR ~2GB，VLM ~8GB）
- M3 默认只走 LLM 总结，VLM 按需触发（`config.yaml vision.enabled: false`）

## Risks

| Risk | 缓解 |
|------|------|
| mimo-v2.5-pro 总结质量不稳定 | prompt 模板优化 + 失败时 fallback 到纯字幕 |
| mimo-v2-omni VLM 对中文图表理解弱 | OCR 先提取文字，VLM 只做语义理解 |
| openclaw 工具层延迟高 | LLM 调用设 30s 超时，超时跳过总结 |
| 本地 VLM 显存 OOM | config.yaml 默认 vision.enabled: false |
