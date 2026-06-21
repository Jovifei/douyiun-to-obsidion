## Context

M1-M4 链路稳定。M5 扩展支持 3 个新平台 + 批量处理。D-3 串行铁律仍适用（GPU 资源约束）。

## Goals / Non-Goals

**Goals**：
1. Bilibili + 小红书 + YouTube 支持（均可选，默认抖音）
2. 平台通用 extractor 接口，抖音作为实现参考
3. 批量 URL 入队（飞书多条消息一次性处理）
4. platform 字段贯穿 scheduler → extractor → frontmatter

**Non-Goals**：
- 不做 TikTok 国际版、快手
- 不做多视频并行下载（仍串行）
- 不做自动订阅/定时抓取

## Decisions

### D-M5-1: 平台通用 extractor 接口

```python
class PlatformExtractor(ABC):
    @abstractmethod
    def resolve_url(self, raw_url: str) -> dict  # {video_id, canonical_url, platform}
    @abstractmethod
    def download(self, video_id, canonical_url, out_dir) -> dict  # {video_path, subtitle_path, ...}
    @abstractmethod
    def extract_metadata(self, info_dict) -> dict
    @abstractmethod
    def classify_subtitle(self, info_dict) -> str
```

抖音/B站/小红书/YouTube 各自实现。yt-dlp 作为共享下载后端（90% 代码复用）。

### D-M5-2: 批量 URL 解析

飞书消息里可能包含多条 URL（一次转发 10 条）。提取所有 URL，每条独立入队独立回调，互不影响。

### D-M5-3: platform 字段贯穿

frontmatter 新增 `platform: douyin | bilibili | xiaohongshu | youtube`，vault 路径不变（仍 `inbox/douyin/...`，M6+ 考虑按平台分目录）。

## Risks

| Risk | 缓解 |
|------|------|
| 小红书 yt-dlp 支持不稳定 | 专用 downloader 兜底 |
| B站字幕格式不同 | yt-dlp 统一 SRT/VTT 转换 |
| 批量处理 scheduler 阻塞 | 每条独立任务，不会互相阻塞 |
