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
