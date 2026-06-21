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
