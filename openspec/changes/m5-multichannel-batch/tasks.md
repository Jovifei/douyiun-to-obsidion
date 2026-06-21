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
