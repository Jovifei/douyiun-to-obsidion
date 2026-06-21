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
