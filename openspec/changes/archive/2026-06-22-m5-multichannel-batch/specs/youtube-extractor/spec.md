## ADDED Requirements

### Requirement: YouTube 视频下载

系统 SHALL 通过 yt-dlp 下载 YouTube 视频 + 多语言字幕。

#### Scenario: YouTube 视频带字幕

- **WHEN** 传入 `https://www.youtube.com/watch?v=xxx` + 视频含字幕
- **THEN** 返回 dict 含 `video_path`、`subtitle_path`、`platform="youtube"`

#### Scenario: youtu.be 短链

- **WHEN** 传入 `https://youtu.be/xxx`
- **THEN** 跟随到完整 URL，再下载

#### Scenario: 多语言字幕选择

- **WHEN** 视频含多语言字幕（zh、en 等）
- **THEN** 优先选 `zh`，否则选第一个可用字幕
