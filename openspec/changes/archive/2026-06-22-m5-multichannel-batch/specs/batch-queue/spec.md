## ADDED Requirements

### Requirement: 批量 URL 入队

系统 SHALL 从飞书消息中提取所有 URL，每条独立入队。

#### Scenario: 一条消息含 3 条抖音链接

- **WHEN** 飞书消息含 3 条不同抖音 URL
- **THEN** 入队 3 条独立任务，每条独立回调

#### Scenario: 混合平台链接

- **WHEN** 飞书消息含抖音 + Bilibili 混合链接
- **THEN** 每条 URL 路由到对应平台 extractor，独立入队

#### Scenario: 消息无有效 URL

- **WHEN** 飞书消息不含任何有效 URL
- **THEN** 回复"未识别到视频链接，请检查格式"
