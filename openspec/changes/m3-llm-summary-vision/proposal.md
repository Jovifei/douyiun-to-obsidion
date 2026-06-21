## Why

M1/M2 只产出"裸字幕笔记"（frontmatter + 字幕全文 + 封面）。用户需要笔记含 **AI 总结**（3-5 个要点）和**视觉理解**（PPT/图表类视频的画面内容提取）。这大幅提升 Obsidian vault 的知识检索效率。

## What Changes

- **LLM 总结**：调度器 writing 阶段调 LLM 生成 3-5 要点总结，写入 `## 摘要` 段 + `summary` frontmatter 字段
  - 一期：mimo-v2.5-pro 走 openclaw 工具层（合规方案 A，DECISIONS A15）
  - 二期：本地 Qwen2.5-72B（如未来有足够显存）
- **视觉理解**：PPT/图表/操作演示类视频自动抽关键帧 + OCR + VLM 理解画面
  - 一期：mimo-v2-omni（走 openclaw 工具层）
  - 二期：本地 Qwen2.5-VL-7B AWQ-4bit（4070S 12G，串行铁律）
- **启发式分流**：自动判断视频类型（口播类 → 只总结字幕；PPT 类 → 字幕 + 关键帧 OCR + VLM）
- **frontmatter 字段填充**：`summary_status`/`processing_mode`/`ai_summary_model` 从占位改为实际值

## Capabilities

### New Capabilities

- `llm-summarizer`: LLM 总结模块。接收字幕全文 + 视频元数据，返回 3-5 要点总结文本。一期 mimo-v2.5-pro（走 openclaw 工具层），二期本地 Qwen。
- `video-vision`: 视觉理解模块。接收视频文件，抽取关键帧 → OCR → VLM → 返回画面描述文本。一期 mimo-v2-omni，二期本地 Qwen2.5-VL-7B。
- `heuristic-router`: 启发式分流模块。根据字幕内容 + 视频时长 + 场景变化频率判断视频类型，决定走"纯字幕总结"还是"字幕 + 视觉理解"路径。

### Modified Capabilities

- `task-queue-pipeline`: 调度器 writing 阶段加 LLM 总结分支 + 视觉理解分支
- `obsidian-archive-writer`: 笔记正文 `## 摘要` 段从占位改为实际总结内容；`## 关键帧` 段从占位改为 VLM 描述

## Impact

- 修改 `src/pipeline/scheduler.py`（writing 阶段加 LLM + VLM 分支）
- 新增 `src/llm/summarizer.py`（LLM 总结模块）
- 新增 `src/vision/`（视觉理解模块：关键帧抽取 + OCR + VLM）
- 修改 `src/obsidian/note_builder.py`（摘要段从占位改为实际内容）
- 修改 `src/bridge/mcp_server.py`（新增 mimo_vlm MCP 工具）
- 修改 `config.yaml`（加 llm/vision 配置块）
