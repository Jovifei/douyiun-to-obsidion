# Comet Design Handoff

- Change: m5-multichannel-batch
- Phase: design
- Mode: compact
- Context hash: 2cf8942171d4fa6812a293c3eb1555eb08ead1aab9e1ca8b2e194b49107254af

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/m5-multichannel-batch/proposal.md

- Source: openspec/changes/m5-multichannel-batch/proposal.md
- Lines: 1-29
- SHA256: 9376a3cc46cbde17a813ffab47e479dfe3f22e7a561514a1b01a0e75162e6659

```md
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
```

## openspec/changes/m5-multichannel-batch/design.md

- Source: openspec/changes/m5-multichannel-batch/design.md
- Lines: 1-50
- SHA256: 35469c2fc0ee22aee4f74001c76431c2ffd142ef9b9d4653cc26833bfa028c14

```md
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
```

## openspec/changes/m5-multichannel-batch/tasks.md

- Source: openspec/changes/m5-multichannel-batch/tasks.md
- Lines: 1-52
- SHA256: 0991a40274759e67a5bee9f3510fd59041e0952d00a624b7818d9b60235e22a5

```md
# M5 实施任务清单

> Change: `m5-multichannel-batch`
> Workflow: full (spec-driven)
> 总工时估算: **10-12 天**
> 依赖：M1-M4 完成

## 1. 平台通用 extractor 接口设计（1 天）

- [ ] 1.1 定义 `PlatformExtractor` ABC（resolve_url / download / extract_metadata / classify_subtitle）
- [ ] 1.2 定义 `get_extractor(platform, config) -> PlatformExtractor` 工厂函数
- [ ] 1.3 重构 `src/extractors/douyin_resolver.py` + `downloader.py` 实现 PlatformExtractor 接口（保持现有行为）
- [ ] 1.4 单元测试：mock 各平台 extractor，验证工厂路由

## 2. Bilibili 支持（2 天）

- [ ] 2.1 创建 `src/extractors/bilibili/`：resolve_url + download + metadata + classify_subtitle
- [ ] 2.2 yt-dlp Bilibili 支持验证（b23.tv 短链 302 跟随、自动字幕）
- [ ] 2.3 Bilibili 字幕格式处理（yt-dlp 统一 VTT 转换）
- [ ] 2.4 单元测试：mock yt-dlp，验证 Bilibili URL 解析 + 字幕判定
- [ ] 2.5 E2E：curl 提交 Bilibili 视频 → 笔记入 Obsidian vault

## 3. 小红书支持（2 天）

- [ ] 3.1 创建 `src/extractors/xiaohongshu/`：resolve_url + download + metadata
- [ ] 3.2 yt-dlp 小红书扩展验证（xhslink.com 短链）
- [ ] 3.3 若 yt-dlp 不支持：专用 downloader（requests + 从小红书 web 抓取）
- [ ] 3.4 小红书笔记无字幕时走 ASR 路径（M2 复用）
- [ ] 3.5 单元测试：mock yt-dlp，验证小红书 URL 解析
- [ ] 3.6 E2E：curl 提交小红书链接 → 笔记入 Obsidian vault

## 4. YouTube 支持（1.5 天）

- [ ] 4.1 创建 `src/extractors/youtube/`：resolve_url + download + metadata
- [ ] 4.2 yt-dlp YouTube 支持验证（youtu.be 短链、自动字幕、多语言字幕选择）
- [ ] 4.3 YouTube 字幕格式处理（yt-dlp 统一 VTT 转换）
- [ ] 4.4 单元测试：mock yt-dlp，验证 YouTube URL 解析
- [ ] 4.5 E2E：curl 提交 YouTube 视频 → 笔记入 Obsidian vault

## 5. 批量 URL 处理（1 天）

- [ ] 5.1 修改 `src/extractors/douyin_resolver.py`：`extract_all_urls(text) -> list[str]`（从飞书消息提取所有 URL）
- [ ] 5.2 修改 scheduler：收到批量 URL 时每条独立入队
- [ ] 5.3 单元测试：一条飞书消息含 3 条抖音链接 → 入队 3 条独立任务
- [ ] 5.4 E2E：飞书发含多 URL 消息 → 每条独立归档

## 6. 集成测试 + 文档（1.5 天）

- [ ] 6.1 全量回归测试（M1-M4 场景不受影响）
- [ ] 6.2 更新 `docs/m2/KNOWLEDGE.md`：新增多平台支持说明
- [ ] 6.3 更新 `config.example.yaml`：新增 `platforms` 配置块
- [ ] 6.4 性能基准：10 条混合平台视频串行处理 ≤ 30 分钟
```

## openspec/changes/m5-multichannel-batch/specs/batch-queue/spec.md

- Source: openspec/changes/m5-multichannel-batch/specs/batch-queue/spec.md
- Lines: 1-20
- SHA256: 86c1c1a0d77f8a03f973e6b905516f23f7718409c2d0ed4d01374336af0bf8ce

```md
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
```

## openspec/changes/m5-multichannel-batch/specs/bilibili-extractor/spec.md

- Source: openspec/changes/m5-multichannel-batch/specs/bilibili-extractor/spec.md
- Lines: 1-20
- SHA256: 02031becb558a2e587c12a2e4e26fd91067f557a178da333227fd68c85511075

```md
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
```

## openspec/changes/m5-multichannel-batch/specs/platform-extractor/spec.md

- Source: openspec/changes/m5-multichannel-batch/specs/platform-extractor/spec.md
- Lines: 1-20
- SHA256: b3856e09d5faeb8a0099596238357e1f5fbfcd85b0213e35e3b79aa7c0880b48

```md
## ADDED Requirements

### Requirement: 平台通用 extractor 接口

系统 SHALL 定义 `PlatformExtractor` ABC，所有平台 extractor 实现统一接口。

#### Scenario: 抖音 extractor 实现 PlatformExtractor

- **WHEN** 调用 `resolve_url("https://v.douyin.com/xxx/")`
- **THEN** 返回 dict 含 `video_id`、`canonical_url`、`platform="douyin"`

#### Scenario: Bilibili extractor 实现 PlatformExtractor

- **WHEN** 调用 `resolve_url("https://b23.tv/xxx")`
- **THEN** 返回 dict 含 `video_id`、`canonical_url`、`platform="bilibili"`

#### Scenario: 工厂路由

- **WHEN** 调用 `get_extractor("douyin", config)`
- **THEN** 返回 DouyinExtractor 实例（PlatformExtractor 子类）
```

## openspec/changes/m5-multichannel-batch/specs/xiaohongshu-extractor/spec.md

- Source: openspec/changes/m5-multichannel-batch/specs/xiaohongshu-extractor/spec.md
- Lines: 1-20
- SHA256: deb0fd8d3335abf4e77869482e4bcaa812e221803d16ed9637a09e5979a288e2

```md
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
```

## openspec/changes/m5-multichannel-batch/specs/youtube-extractor/spec.md

- Source: openspec/changes/m5-multichannel-batch/specs/youtube-extractor/spec.md
- Lines: 1-20
- SHA256: 8babb2a0dfb51bb13d5704c95908ef3d4f3a2b956a586d258fb9324d6c182ecb

```md
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
```

