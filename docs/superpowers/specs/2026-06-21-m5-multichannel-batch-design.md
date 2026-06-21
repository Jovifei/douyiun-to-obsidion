---
comet_change: m5-multichannel-batch
role: technical-design
canonical_spec: openspec
archived-with: 2026-06-22-m5-multichannel-batch
status: final
---

# M5 多平台扩展 + 批量处理 — 技术设计文档

> 日期：2026-06-21

## 决策

### D-M5-1: 平台通用 extractor 接口

```python
class PlatformExtractor(ABC):
    def resolve_url(self, raw_url: str) -> dict   # {video_id, canonical_url, platform}
    def download(self, ...) -> dict                # {video_path, subtitle_path, ...}
    def extract_metadata(self, info_dict) -> dict
    def classify_subtitle(self, info_dict) -> str
```

抖音作为默认实现，yt-dlp 作为共享下载后端。

### D-M5-2: 批量 URL 解析

飞书消息可能含多条 URL，每条独立入队。

### D-M5-3: platform 字段

frontmatter 新增 `platform`，vault 路径暂不变。

## 测试策略

- 平台 extractor 单元测试：mock yt-dlp
- 批量 URL 测试：mock 飞书消息
- 回归测试：M1-M4 场景不受影响
