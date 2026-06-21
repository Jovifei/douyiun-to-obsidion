## ADDED Requirements

### Requirement: mimo-v2.5-asr 转写

系统 SHALL 通过 openclaw MCP 工具 `asr_transcribe` 调用 mimo-v2.5-asr API，接收音频文件路径，返回转写结果。

#### Scenario: 正常转写

- **WHEN** 传入 30 秒中文音频文件
- **THEN** 返回 ASRResult（text=转写全文, segments=[{start,end,text}], source="mimo_asr", confidence≥0.8）

#### Scenario: 音频太短

- **WHEN** 传入 <1 秒音频
- **THEN** 抛 ASRError("audio_too_short")

#### Scenario: API 超时

- **WHEN** openclaw MCP 调用超时 30 秒
- **THEN** 抛 ASRError("asr_timeout")，上层调度器捕获

### Requirement: openclaw MCP 工具注册

`src/bridge/mcp_server.py` SHALL 暴露 `asr_transcribe` 工具，内部调 mimo-v2.5-asr API。

#### Scenario: 工具可调用

- **WHEN** openclaw agent 调用 `asr_transcribe(audio_path="/tmp/test.wav")`
- **THEN** 返回 JSON 含 text / segments / source / confidence 字段
