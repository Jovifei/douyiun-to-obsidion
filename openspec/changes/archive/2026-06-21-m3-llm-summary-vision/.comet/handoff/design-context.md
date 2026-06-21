# Comet Design Handoff

- Change: m3-llm-summary-vision
- Phase: design
- Mode: compact
- Context hash: c01de7187ad551cab93555bc1ff31f92c40e798bb574558a275c7806359ece36

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/m3-llm-summary-vision/proposal.md

- Source: openspec/changes/m3-llm-summary-vision/proposal.md
- Lines: 1-36
- SHA256: 98bf1c73aff9cac9acd939b936284d44e434440b43c55b870521c0359472e5b7

```md
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
```

## openspec/changes/m3-llm-summary-vision/design.md

- Source: openspec/changes/m3-llm-summary-vision/design.md
- Lines: 1-86
- SHA256: 63ba514317f95f5d7b6cabd21d9dd2b0cf4f4d6930a371d341d2767fb9dbd5de

[TRUNCATED]

```md
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

```

Full source: openspec/changes/m3-llm-summary-vision/design.md

## openspec/changes/m3-llm-summary-vision/tasks.md

- Source: openspec/changes/m3-llm-summary-vision/tasks.md
- Lines: 1-84
- SHA256: cc88ac1917f96e73ea05b5d51c8c4740fdb99cb2695336169a984888ff726c8e

[TRUNCATED]

```md
# M3 实施任务清单

> Change: `m3-llm-summary-vision`
> Workflow: full (spec-driven)
> 总工时估算: **7-10 天**（LLM 总结 ~2 天，视觉理解 ~4 天，启发式分流 ~1 天，集成测试 ~2 天）
> 依赖：M1 + M2 完成

## 1. LLM 总结接口设计（0.5 天）

- [ ] 1.1 创建 `src/llm/__init__.py`，定义 `SummaryResult` dataclass（summary_text / key_points / model / source / confidence）
- [ ] 1.2 定义 `SummarizerClient` 抽象基类：`summarize(subtitle_text: str, metadata: dict) -> SummaryResult`
- [ ] 1.3 定义 `get_summarizer(config) -> SummarizerClient` 工厂函数
- [ ] 1.4 单元测试：mock SummarizerClient，验证 SummaryResult 字段

## 2. mimo-v2.5-pro 总结客户端（一期）（1 天）

- [ ] 2.1 创建 `src/llm/mimo_summarizer.py`：`MimoSummarizer` 实现 `SummarizerClient`
- [ ] 2.2 实现 `summarize(subtitle_text, metadata)`：构造 prompt → 调 mimo-v2.5-pro API → 解析返回
- [ ] 2.3 prompt 模板实现：按 D-M3-4 格式，3-5 要点、中文、按重要性排序
- [ ] 2.4 实现 prompt 超长截断：字幕 > 8000 字时截取前后各 4000 字 + 中间摘要提示
- [ ] 2.5 错误处理：API 超时 / 返回空 / 格式不对 → ASRError("llm_failed")，上层调度器跳过总结
- [ ] 2.6 openclaw MCP 工具注册：`src/bridge/mcp_server.py` 新增 `llm_summarize` 工具
- [ ] 2.7 单元测试：mock API 调用，验证 SummaryResult

## 3. 视觉理解 — 关键帧抽取（1 天）

- [ ] 3.1 创建 `src/vision/keyframe_extractor.py`：从视频文件抽取关键帧图片
- [ ] 3.2 实现 ffmpeg scene detect：`ffmpeg -vf "select='gt(scene,0.4)'" -vsync vframe`
- [ ] 3.3 实现按时间均匀采样（scene detect 帧太少时兜底，每 10 秒一帧）
- [ ] 3.4 实现关键帧输出到 `tmp_dir/{video_id}_keyframes/`
- [ ] 3.5 单元测试：mock ffmpeg，验证关键帧路径列表

## 4. 视觉理解 — OCR（0.5 天）

- [ ] 4.1 创建 `src/vision/ocr_client.py`：调 PaddleOCR PP-OCRv5
- [ ] 4.2 实现 `extract_text_from_image(image_path: Path) -> str`
- [ ] 4.3 错误处理：OCR 失败 / 模型未装 → 返回空字符串，不阻塞
- [ ] 4.4 单元测试：mock PaddleOCR，验证中文文字提取

## 5. 视觉理解 — VLM（1.5 天）

- [ ] 5.1 创建 `src/vision/vlm_client.py`：VLM 理解模块
- [ ] 5.2 一期：`MimoVLMClient` 调 mimo-v2-omni（走 openclaw MCP 工具）
- [ ] 5.3 二期：`LocalVLMClient` 调本地 Qwen2.5-VL-7B AWQ-4bit（默认关闭）
- [ ] 5.4 VLM prompt 设计："这是一段抖音知识视频的关键帧，请描述画面中的关键信息"
- [ ] 5.5 实现逐帧推理 + 聚合描述
- [ ] 5.6 openclaw MCP 工具注册：`mimo_vlm` 工具
- [ ] 5.7 单元测试：mock API，验证 VLM 描述文本

## 6. 启发式分流（1 天）

- [ ] 6.1 创建 `src/vision/heuristic_router.py`：视频类型判断
- [ ] 6.2 实现 `classify_video(subtitle_text, video_duration, keyframe_count) -> str`
- [ ] 6.3 返回值：`"summary_only"` / `"summary_with_vlm"` / `"ocr_only"`
- [ ] 6.4 实现字幕密度计算：字幕字数 / 视频时长
- [ ] 6.5 单元测试：mock 数据验证 3 种分流路径

## 7. 调度器集成（1.5 天）

- [ ] 7.1 修改 `src/pipeline/scheduler.py` writing 阶段：加 LLM 总结分支
- [ ] 7.2 修改 `src/obsidian/note_builder.py`：`## 摘要` 段从占位改为实际总结内容
- [ ] 7.3 修改 frontmatter：`summary_status` 从 `not_run` 改为 `done`（LLM 成功时）
- [ ] 7.4 修改 frontmatter：`ai_summary_model` 记录实际使用的模型名
- [ ] 7.5 视觉理解集成（`config.yaml vision.enabled: true` 时触发）：
  - 关键帧抽取 → OCR → VLM → 写入 `## 关键帧` 段
- [ ] 7.6 修改 `processing_mode`：根据实际路径更新（`subtitle_only` / `subtitle_vlm` / `full`）
- [ ] 7.7 串行铁律：LLM 和 VLM 不并行，用锁或队列串行执行
- [ ] 7.8 单元测试：mock LLM/VLM，验证笔记正文含总结 + 关键帧描述

## 8. 配置更新（0.5 天）

- [ ] 8.1 更新 `config.example.yaml`：新增 `llm` 配置块（provider/mimo/api_key/base_url）和 `vision` 配置块（enabled/ocr_model/vlm_model）
- [ ] 8.2 更新 `config.yaml`：默认 `vision.enabled: false`
- [ ] 8.3 更新 `docs/m1/RUNBOOK.md`：新增 LLM 总结和视觉理解的启停说明

## 9. 端到端测试 + 文档（1 天）

- [ ] 9.1 测试场景 1：curl 提交有字幕视频 → 笔记含 AI 总结（3-5 要点）
- [ ] 9.2 测试场景 2：curl 提交无字幕视频 → ASR 转写 + LLM 总结
- [ ] 9.3 测试场景 3：curl 提交 PPT 类视频（`vision.enabled: true`）→ 笔记含关键帧 OCR + VLM 描述
```

Full source: openspec/changes/m3-llm-summary-vision/tasks.md

## openspec/changes/m3-llm-summary-vision/specs/llm-summarizer/spec.md

- Source: openspec/changes/m3-llm-summary-vision/specs/llm-summarizer/spec.md
- Lines: 1-34
- SHA256: b39324df7a93fd97a5743aabb7d243b433c596186c3e7e4fbc41540f138102f2

```md
## ADDED Requirements

### Requirement: LLM 总结生成

系统 SHALL 通过 openclaw MCP 工具 `llm_summarize` 调用 mimo-v2.5-pro，接收字幕全文 + 元数据，返回 3-5 要点总结。

#### Scenario: 正常总结

- **WHEN** 传入 500 字以上的字幕文本 + 视频标题
- **THEN** 返回 SummaryResult（summary_text=总结全文, key_points=[3-5条], model="mimo-v2.5-pro", confidence≥0.8）

#### Scenario: 字幕太短

- **WHEN** 字幕 < 50 字
- **THEN** 返回 SummaryResult（summary_text="字幕内容过短，无法提炼要点", key_points=[], confidence=0.5）

#### Scenario: API 超时

- **WHEN** openclaw MCP 调用超时 30 秒
- **THEN** 抛 LLMError("llm_timeout")，上层调度器跳过总结，笔记仍含字幕

#### Scenario: prompt 超长截断

- **WHEN** 字幕 > 8000 字
- **THEN** 自动截取前后各 4000 字 + 中间省略提示，确保不超 token 限制

### Requirement: openclaw MCP 工具注册

`src/bridge/mcp_server.py` SHALL 暴露 `llm_summarize` 工具，内部调 mimo-v2.5-pro API。

#### Scenario: 工具可调用

- **WHEN** openclaw agent 调用 `llm_summarize(subtitle_text="...", metadata={...})`
- **THEN** 返回 JSON 含 summary_text / key_points / model / confidence
```

## openspec/changes/m3-llm-summary-vision/specs/obsidian-archive-writer/spec.md

- Source: openspec/changes/m3-llm-summary-vision/specs/obsidian-archive-writer/spec.md
- Lines: 1-31
- SHA256: a627d4b824bc35772e119768003d92035e32c1360528e51692ec352b274b95c8

```md
## MODIFIED Requirements

### Requirement: 笔记正文摘要段更新（M3 修改）

**原行为**：`## 摘要` 段写"M1 阶段无 LLM 总结，待 M3 填充"
**新行为**：LLM 成功时写入 3-5 要点总结；失败时写"LLM 总结失败：{原因}"

#### Scenario: LLM 总结成功

- **WHEN** SummaryResult.summary_text 非空
- **THEN** `## 摘要` 段写入 key_points（3-5 条），每条一句话

#### Scenario: LLM 总结失败

- **WHEN** LLM 调用失败
- **THEN** `## 摘要` 段写"LLM 总结失败：{error}，请稍后重试"

### Requirement: 笔记正文关键帧段更新（M3 修改）

**原行为**：`## 关键帧` 段写"M1 阶段不抽取关键帧"
**新行为**：VLM 成功时写入画面描述；禁用时写"视觉理解已禁用"

#### Scenario: VLM 理解成功

- **WHEN** VLMResult.descriptions 非空
- **THEN** `## 关键帧` 段逐帧写入描述（`### 帧 N: {description}`）

#### Scenario: VLM 禁用

- **WHEN** config.yaml `vision.enabled: false`
- **THEN** `## 关键帧` 段写"视觉理解已禁用（config.yaml vision.enabled=false）"
```

## openspec/changes/m3-llm-summary-vision/specs/task-queue-pipeline/spec.md

- Source: openspec/changes/m3-llm-summary-vision/specs/task-queue-pipeline/spec.md
- Lines: 1-31
- SHA256: a3c72ee143633e871b3e811704e83dca8bc0bb4d96136e0f44bcee6b540bb18e

```md
## MODIFIED Requirements

### Requirement: 调度器 writing 阶段加 LLM 总结 + 视觉理解（M3 修改）

**原行为**：writing 阶段直接写笔记，`## 摘要` 段为占位文字
**新行为**：writing 阶段先调 LLM 总结 → 写入摘要段；如 vision.enabled 则额外走关键帧 OCR + VLM

#### Scenario: LLM 总结成功

- **WHEN** writing 阶段 + LLM 调用成功
- **THEN** `## 摘要` 段写入 3-5 要点，`summary_status=done`，`ai_summary_model="mimo-v2.5-pro"`

#### Scenario: LLM 总结失败

- **WHEN** LLM 超时/失败
- **THEN** `## 摘要` 段保留占位文字，`summary_status=failed`，笔记仍正常入库

#### Scenario: 视觉理解触发（vision.enabled=true）

- **WHEN** 启发式判断走 summary_with_vlm + vision.enabled=true
- **THEN** 关键帧 → OCR → VLM → `## 关键帧` 段写入描述，`processing_mode="subtitle_vlm"`

#### Scenario: 视觉理解禁用（默认）

- **WHEN** config.yaml `vision.enabled: false`
- **THEN** 跳过视觉理解，`processing_mode="subtitle_only"`，`## 关键帧` 段写"视觉理解已禁用"

#### Scenario: LLM + VLM 串行（铁律）

- **WHEN** 同时需要 LLM 和 VLM
- **THEN** 先跑 LLM，完成后再跑 VLM，不并行（4070S 显存限制）
```

## openspec/changes/m3-llm-summary-vision/specs/video-vision/spec.md

- Source: openspec/changes/m3-llm-summary-vision/specs/video-vision/spec.md
- Lines: 1-67
- SHA256: 7ff8dd6eeac2514229664a09030b0947f5101816746d77321a8d6f43b4514940

```md
## ADDED Requirements

### Requirement: 关键帧抽取

系统 SHALL 从视频文件抽取关键帧图片，供 OCR 和 VLM 使用。

#### Scenario: scene detect 抽取

- **WHEN** 视频含 PPT 切换/图表变化（场景变化率 > 0.4）
- **THEN** 抽取 N 张关键帧到 `tmp_dir/{video_id}_keyframes/`

#### Scenario: 兜底均匀采样

- **WHEN** scene detect 抽到的帧 < 3 张
- **THEN** 每 10 秒补抽 1 帧，最多 30 帧

### Requirement: OCR 文字提取

系统 SHALL 用 PaddleOCR PP-OCRv5 从关键帧图片提取中文文字。

#### Scenario: 正常 OCR

- **WHEN** 传入含中文文字的 PPT 截图
- **THEN** 返回识别文字字符串（中文准确率 > 95%）

#### Scenario: OCR 失败

- **WHEN** 模型未装 / 图片模糊
- **THEN** 返回空字符串，不阻塞后续流程

### Requirement: VLM 视觉理解

系统 SHALL 通过 openclaw MCP 工具 `mimo_vlm` 调用 mimo-v2-omni，接收关键帧图片，返回画面描述。

#### Scenario: 正常 VLM

- **WHEN** 传入 PPT 关键帧图片
- **THEN** 返回描述文本（"PPT展示了XXX流程图"）

#### Scenario: VLM 禁用

- **WHEN** config.yaml `vision.enabled: false`
- **THEN** 跳过 VLM，笔记关键帧段写"视觉理解已禁用"

#### Scenario: VLM 超时

- **WHEN** API 超时 30 秒
- **THEN** 返回"VLM 超时，画面内容未提取"，不阻塞笔记生成

### Requirement: 启发式分流

系统 SHALL 根据字幕内容 + 视频特征判断视频类型，决定处理路径。

#### Scenario: 口播类视频（summary_only）

- **WHEN** 字幕密度 > 0.5 字/秒 且 场景变化率 < 0.3
- **THEN** 只走 LLM 总结，不走 VLM

#### Scenario: PPT/图表类视频（summary_with_vlm）

- **WHEN** 字幕密度 < 0.3 字/秒 且 场景变化率 > 0.5
- **THEN** 走 LLM 总结 + 关键帧 OCR + VLM

#### Scenario: 混合类视频（summary_with_vlm）

- **WHEN** 字幕密度介于 0.3-0.5 之间
- **THEN** 走 LLM 总结 + 关键帧 OCR + VLM（保守策略）
```

