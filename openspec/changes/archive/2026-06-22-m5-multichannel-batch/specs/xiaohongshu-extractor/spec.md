## ADDED Requirements

### Requirement: 小红书笔记/视频下载

系统 SHALL 支持小红书分享链接的下载（视频/图文笔记）。

#### Scenario: 小红书视频

- **WHEN** 传入 `https://www.xiaohongshu.com/explore/xxx`
- **THEN** 下载视频 + 字幕（若 yt-dlp 支持），或专用 downloader 兜底

#### Scenario: xhslink.com 短链

- **WHEN** 传入 `https://xhslink.com/xxx`
- **THEN** 跟随到完整 URL，再下载

#### Scenario: 小红书图文笔记

- **WHEN** 传入图文笔记链接（非视频）
- **THEN** 提取图片 + 文字描述，写入笔记（不走 ASR 路径）
