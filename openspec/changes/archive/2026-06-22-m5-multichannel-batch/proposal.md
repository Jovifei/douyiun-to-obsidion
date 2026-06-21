## Why

当前系统只支持抖音单视频。Jovi 看 Bilibili、小红书也有知识类内容；同时飞书发链接是单条手动触发，批量场景（一次性转发 10 条抖音链接）时要排队等。

## What Changes

- **多平台 URL 识别**：Bilibili（b23.tv / bilibili.com/video）、小红书（xhslink.com / xiaohongshu.com）、YouTube（youtu.be / youtube.com/watch）作为可选扩展，不阻塞 M1 抖音核心链路
- **平台通用 extractor**：重构 `src/extractors/` 统一接口，抖音/B站/小红书/YouTube 各自实现，共享 yt-dlp 下载层 + ASR/LLM/VLM 后处理
- **批量处理**：飞书消息含多条 URL 时全部入队，每条独立处理、独立回调
- **平台调度器升级**：scheduler 处理 `platform=douyin/bilibili/xiaohongshu/youtube` 字段，不同平台走不同 extractor + 字幕策略

## Capabilities

### New Capabilities
- `bilibili-extractor`: Bilibili 视频下载 + 字幕（yt-dlp 支持 Bilibili auto-caption）
- `xiaohongshu-extractor`: 小红书笔记/视频下载（需 yt-dlp 小红书扩展或专用 downloader）
- `youtube-extractor`: YouTube 视频下载 + 字幕（yt-dlp 原生支持）
- `batch-queue`: 飞书消息含多 URL 时批量入队处理

### Modified Capabilities
- `douyin-extraction`: 重构为 `platform-extractor` 通用接口，抖音作为默认实现
- `task-queue-pipeline`: scheduler 支持 platform 字段，根据 URL 路由到对应 extractor
- `bishu-feishu-bridge`: 飞书消息解析支持多 URL 提取

## Non-Goals
- 不做 TikTok/快手/YouTube Shorts
- 不做多视频同时下载并行（仍串行，D-3 串行铁律）
- 不做自动订阅/定时抓取
- 不做视频二次编辑/剪辑
