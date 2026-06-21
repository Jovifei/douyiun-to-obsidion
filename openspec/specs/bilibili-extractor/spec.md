## ADDED Requirements

### Requirement: Bilibili 视频下载

系统 SHALL 通过 yt-dlp 下载 Bilibili 视频 + 字幕。

#### Scenario: Bilibili 视频带字幕

- **WHEN** 传入 `https://www.bilibili.com/video/BVxxx` + 视频含自动字幕
- **THEN** 返回 dict 含 `video_path`、`subtitle_path`、`platform="bilibili"`

#### Scenario: b23.tv 短链

- **WHEN** 传入 `https://b23.tv/xxx`
- **THEN** 302 跟随到完整 Bilibili URL，再下载

#### Scenario: 无字幕 Bilibili 视频

- **WHEN** 传入无字幕 Bilibili 视频
- **THEN** 抛 `NoSubtitleError("no_subtitle_in_m1")`，走 ASR 路径
