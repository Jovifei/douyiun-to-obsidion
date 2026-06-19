# 抖音知识视频自动归档到 Obsidian — 产品需求文档（PRD）

> 版本：v1.1  日期：2026-06-19  作者：产品架构师（替 Jovi 整理）
> 调研依据：T2 抖音抓取 / T3 本地 Whisper / T4 飞书+openclaw / T5 Obsidian 写入 / T6 多模态视觉 / WEB_RESEARCH_2026-06-19
> 文档定位：把"做什么 / 为什么这么做 / 怎么验收"讲清楚；不写实施步骤（留给 EXECUTION.md）。

---

## 1. 背景与目标

### 1.1 一句话定位

**openclaw 之后的智能解析与 Obsidian 入库管线**——补齐"飞书 bot → openclaw → ??? → Obsidian"链路里那个 `???`。

### 1.2 现状链路

```mermaid
graph LR
  A[手机抖音 App] -->|复制分享| B[飞书 私聊机器人]
  B -->|im.message.receive_v1| C[飞书事件中台]
  C -->|WebSocket 长连接| D[openclaw Gateway<br/>127.0.0.1:3000]
  D -.->|本项目要补的部分| E[抖音解析服务]
  E -.->|md + 媒体文件| F[Obsidian Vault]
  F -->|Git 冷备 / Syncthing / iCloud or OneDrive| G[多端]

  style E fill:#ffe4b5,stroke:#d2691e,stroke-width:2px
  style D fill:#e6f3ff
```

**已有**：手机抖音 → 飞书自建机器人 → openclaw（Node 24，本地服务，飞书走 WS）。
**缺口**：openclaw 收到包含抖音 URL 的消息后，**没有解析视频内容并写入 Obsidian** 的下游链路。

### 1.3 项目目标

| 类型 | 目标 | 衡量指标 |
|---|---|---|
| 功能 | 分享抖音知识视频后，自动产出结构化 Obsidian 笔记 | 端到端成功率 ≥ 90%（30 天滚动） |
| 体验 | 用户行为只剩"复制 → 粘贴到飞书 bot" | 主路径手动操作 ≤ 1 步 |
| 性能 | 短视频（≤3 min）端到端延迟 ≤ 2 min；长视频（≤30 min）≤ 10 min | 90 分位延迟达标 |
| 质量 | 中文字幕可读（CER ≤ 8%）；PPT/图表能转成 Markdown 可检索内容 | 抽 20 条样本人工核验 |
| 隐私 | 全链路本地优先；云端只做兜底 | 默认配置无云端调用 |

### 1.4 非目标（Out of Scope）

| 不做 | 理由 |
|---|---|
| 飞书自建机器人申请、App ID/Secret 获取 | Jovi 已完成，不在本项目范围 |
| openclaw 自身能力（频道适配、消息路由、skill 框架） | 上游平台，本项目只做下游 skill |
| 抖音平台政策合规审查 | 个人留存使用，不商用、不分发 |
| 抖音账号主页批量抓取、合集订阅 | MVP 不做；需要 a_bogus，工作量超预算（见 T2 §4） |
| iOS 端 Syncthing | 平台限制；iOS 走 Obsidian Sync / iCloud / Working Copy，Syncthing 仅作为 Android/PC 候选 |
| 飞书群消息、富文本 post 类型支持 | MVP 仅支持私聊 text 消息；post/share 留 P2 |
| 视频内容版权审查、原创性判定 | 不在产品职责内 |
| 实时直播切片转写 | 仅离线短视频；直播场景延迟模型完全不同 |

<!-- v2 修订 2026-06-19: 整合 GLM PRD §1.2 Obsidian 角色澄清（详见 GLM_REVIEW.md §1.3） -->

### 1.5 Obsidian 在链路中的角色澄清

> 本节回应 Jovi 早期反复出现的问题："Obsidian 能解析视频内容吗？"——明确划定 Obsidian 与解析服务的职责边界。

**结论**：**Obsidian 不解析视频内容，它只展示**——解析由外部链路完成，最终落 markdown 文件，Obsidian 通过文件系统监听自动刷新。

| 角色 | 职责 | 不做什么 |
|---|---|---|
| 飞书 bot + openclaw | 入口、URL 抽取、调度触发 | 不做下载、不做转写、不做 LLM 调用 |
| 解析服务（本项目，FastAPI 常驻） | 抓取（yt-dlp / DouK）、字幕/Whisper、OCR/VLM、LLM 总结、frontmatter 拼装、Markdown 写入 | 不解析飞书事件、不渲染 markdown、不做笔记检索 |
| Obsidian（GUI） | 文件系统监听、Markdown 渲染、双链/标签/DataView 仪表盘、人工编辑 | 不解析视频、不调用任何 AI、不参与本项目 pipeline |
| Syncthing / iCloud / Git | 跨设备同步与冷备 | 不做内容变换 |

**架构含义**：

1. **解析服务直接写文件系统**（`vault/inbox/douyin/YYYY-MM/{aweme_id}.md`），不依赖 Obsidian Local REST API、不依赖 obsidian-mcp 插件。零网络调用、零认证开销，CI/无 GUI 环境也能跑。
2. **Obsidian 通过 chokidar 文件系统监听**自动感知新文件（≤2 秒），不需要任何 hook / 插件参与。
3. **Obsidian 是消费者而非生产者**——本项目所有 AI 能力（Whisper、OCR、VLM、LLM）都在解析服务里，与 Obsidian 进程完全解耦。Obsidian 关闭时 pipeline 仍可正常入库，下次开 Obsidian 即看到新笔记。
4. **DataView 是查询层，不是写入层**——`dashboards/douyin_inbox.md` 在 Obsidian 内部跑 Dataview 查询，本项目不参与。

**反常识但很重要**：本项目可以**完全在没有 Obsidian 客户端**的机器上跑（比如服务器端 headless 部署），写出来的 markdown 任何编辑器都能读，Obsidian 只是其中一种用户体验最佳的客户端。这一架构选择源自 T5 §A 主方案"文件系统直写"，对应 PRD §6 schema 设计目标。

### 1.6 Obsidian 同步结论

> 本节回答 Jovi 的问题："Obsidian 目前支持云同步吗？手机+PC 怎么同步？"

**结论**：Obsidian 官方有付费 **Obsidian Sync**，支持 Windows、macOS、Linux、iOS、Android，并提供端到端加密、版本历史和选择性同步。它是最省心的官方方案，但不是本项目 M1 的强依赖。

本项目同步层按阶段处理：

| 阶段 | 同步策略 | 说明 |
|---|---|---|
| M1 | PC 本地 vault + Git 冷备 | 先打通"飞书链接 → PC 解析 → 写入 Obsidian vault"，不让同步阻塞解析链路 |
| M2 | Syncthing（Android/PC 可选） | 如果手机端是 Android，可用 Syncthing-Fork；如果只是 PC 阅读，继续 Git 冷备即可 |
| M3/M4 | iCloud / OneDrive / Obsidian Sync 评估 | 如果手机端是 iOS，优先 Obsidian Sync 或 iCloud；OneDrive 适合 Windows/macOS，但移动端限制更多 |

**关键约束**：同一个 vault 不要同时由 Syncthing、iCloud、OneDrive、Obsidian Sync 多方并发双向写。同步通道只能有一个主通道，Git 作为冷备，其他云盘只能做镜像/只读分发，否则冲突文件会快速污染 vault。

<!-- v1.1 修订 2026-06-19: 根据 Obsidian 官方同步帮助页与 Jovi 当前回答，将 F8 从 Android-only Syncthing 改为分阶段同步策略。详见 WEB_RESEARCH_2026-06-19.md。 -->

---

## 2. 用户故事

> 用户：Jovi（个人用户，资深开发者，独立使用）。

### US-1（P0）主路径：带原生字幕的知识视频

**作为** 刷抖音的我，
**当我** 看到一个有原生字幕的知识类口播视频并把链接转发给飞书机器人时，
**我希望** 几分钟内 Obsidian 的 `inbox/douyin/YYYY-MM/` 里出现一篇结构化笔记，包含标题、作者、字幕全文、AI 摘要、封面。

**验收标准**：
- [ ] 飞书消息发出后 ≤ 2 分钟，笔记出现在 vault
- [ ] frontmatter 完整（见 §6 schema）
- [ ] `subtitle_source = douyin_native`，跳过了 Whisper
- [ ] 飞书机器人回写"已入库"线程消息，附笔记本地路径

### US-2（P0）兜底：无原生字幕视频

**作为** 用户，
**当我** 分享的视频抖音没给字幕（纯 BGM 解说、方言、UP 主关闭字幕）时，
**我希望** 系统自动用本地 Whisper 转写音频并产出笔记，不打断主流程。

**验收标准**：
- [ ] 检测到无 SRT 时自动 fallback 到 Whisper
- [ ] 5 分钟内（≤3 min 视频）完成 Whisper 转写并写入笔记
- [ ] frontmatter `subtitle_source = whisper_belle_v3_turbo_zh`，附置信度
- [ ] CER 实测 ≤ 8%（AISHELL-2/WenetSpeech NET 量级，见 T3 §3）

### US-3（P1）PPT/图表类视频

**作为** 学习硬件/AI 的我，
**当我** 分享一个 PPT 讲解类视频（场景切换密集、画面文字多）时，
**我希望** 笔记里不只有字幕，还有关键帧 OCR 文字 + VLM 对图表的描述。

**验收标准**：
- [ ] 启发式分流（见 T6 §E）正确识别 `subtitle_plus_ocr` / `full` 模式
- [ ] 关键帧抽取每分钟 5–25 张（PPT 切换敏感）
- [ ] OCR 文本块按时间戳嵌入笔记正文
- [ ] 图表/手写帧调用 VLM 产出 ≤ 200 字描述
- [ ] LLM 融合后字幕 + OCR + VLM 不重复啰嗦

### US-4（P0）离线消息追赶

**作为** 把电脑关机睡觉的我，
**当我** 半夜在手机上分享了 5 条视频、第二天开机时，
**我希望** 5 条消息按时间顺序排队处理，全部成功入库，飞书有进度回执。

**验收标准**：
- [ ] 离线期间飞书消息由 openclaw 持久化（依赖 openclaw 内置能力）
- [ ] 开机后 30 秒内开始排队处理，先进先出
- [ ] 每条消息独立可重试，单条失败不阻塞队列
- [ ] 处理完成后飞书回写"批量处理完成 X/Y"

### US-5（P1）失败重试与降级

**作为** 用户，
**当** 抖音 cookie 过期 / 视频被删 / Whisper 模型加载失败 / 显存不足 时，
**我希望** 系统不沉默崩溃，而是给出明确状态并允许我手动重试。

**验收标准**：
- [ ] 失败原因分类（INVALID_URL / URL_EXPIRED / COOKIE_STALE / RATE_LIMITED / GPU_OOM / PARSE_FAILED）
- [ ] 飞书回写带 emoji + 错误码 + 简明建议
- [ ] 笔记仍创建，frontmatter `status = failed`、`error` 字段填充
- [ ] 重试通道：在飞书发"重试 <video_id>"或机器人提供按钮（P2）

### US-6（P2）多端阅读与整理

**作为** 通勤/外出的我，
**当我** 在手机端 Obsidian 或云盘同步目录里打开 vault 时，
**我希望** 看到与 PC 同步的笔记，能快速从 inbox 移动到 knowledge/ 归档。

**验收标准**：
- [ ] M1：PC 端 Git 冷备任务可正常 commit/push，生成的 Markdown 不依赖手机端同步即可阅读
- [ ] Android 分支：Syncthing-Fork 在 PC ↔ Android 间增量同步 ≤ 30 秒（≤5MB 笔记）
- [ ] iOS 分支：Obsidian Sync / iCloud / Working Copy 三选一完成验证，不与 Syncthing 双主混用
- [ ] 大附件（mp4 原文件）不进主同步通道，frontmatter 只存 URL 或本机路径
- [ ] 手动整理后 DataView 仪表盘自动从 inbox 待办移除该笔记

---

## 3. 范围 In / Out / TBD

| 状态 | 项 | 理由 |
|---|---|---|
| **In** | 飞书私聊 text 消息中的抖音 URL 解析 | 主路径，覆盖 80%+ 场景 |
| **In** | 单视频 / 图集（gallery）/ 实况图（live photo） | T2 调研已确认 DouK-Downloader 兼容 |
| **In** | yt-dlp 主路径 + DouK 备路径 | 双工具防单点故障（T2 §3） |
| **In** | 抖音原生字幕优先，Whisper 兜底 | 命中时省 90% 算力（T2 §2） |
| **In** | 关键帧抽取 + PaddleOCR + Qwen2.5-VL（启发式分流） | T6 §E 推荐链路 |
| **In** | LLM 总结（本地 Qwen 优先，MiMo/GLM 等 OpenAI-compatible 云端可切） | 笔记可读性核心 |
| **In** | Obsidian 文件系统直写 + frontmatter schema | T5 §A 主方案 |
| **In** | Git 冷备 + Android/PC Syncthing 候选 + iOS 云同步候选 | 官方同步资料 + T5 §C 推荐组合 |
| **In** | 状态机 + 重试 + 离线队列 | 可靠性基础 |
| **In** | 凭证管理（cookies、tokens、HF mirror） | 安全基础 |
| **Out** | 飞书群消息、post 富文本、share_chat | MVP 不做，URL 抽取留接口 |
| **Out** | 抖音用户主页批量、合集订阅 | 需 a_bogus，超预算 |
| **Out** | iOS 端原生 Syncthing 支持 | 平台无方案 |
| **Out** | 实时流式转写、直播切片 | 离线批处理就够 |
| **Out** | 多用户、多 vault、权限隔离 | 个人单用户项目 |
| **TBD** | Bilibili / 小红书 / YouTube 适配 | 架构留扩展点，M5 之后再考虑 |
| **TBD** | 笔记自动分类到 `knowledge/<topic>/` | 涉及 LLM 分类策略，M3 后讨论 |
| **TBD** | iCloud / OneDrive / Obsidian Sync 候选叠加 | M3/M4 评估；不得与 Syncthing 双主混用 |
| **TBD** | 飞书机器人交互按钮（重试、删除） | 取决于 openclaw 是否支持 card |

---

## 4. 功能需求（按模块）

> 与调研报告对齐拆 10 个模块。每个模块给：功能描述 / 优先级 / 验收标准 / 依赖。

### F1 URL 接入与去重

| 维度 | 内容 |
|---|---|
| 描述 | 从 openclaw 收到的飞书消息 payload 中提取抖音 URL，跟 302 还原为 `www.douyin.com/video/{aweme_id}`，用 `aweme_id` 做幂等键去重 |
| 选型理由 | T2 §1 给出 5 种 URL 形态 + 实战正则；T4 §B.2 明确 `message_id` 是飞书侧幂等键，结合 `aweme_id` 做双层去重最稳 |
| 优先级 | P0 |
| 验收标准 | • 5 种 URL 形态全部识别<br>• 短链 302 跟随成功率 ≥ 99%（30 天滚动）<br>• 同一 `aweme_id` 重复分享 24h 内不重复处理，飞书回写"已存在，路径 xxx"<br>• 抽取失败时返回 `INVALID_URL`，不消耗下游算力 |
| 依赖 | openclaw skill 注入消息事件、F10（配置） |

### F2 视频抓取

| 维度 | 内容 |
|---|---|
| 描述 | 用 yt-dlp 主、DouK-Downloader 备，下载视频文件 + info.json + 自带字幕（若有） |
| 选型理由 | T2 §3 横评：yt-dlp 活跃度最高、自带 auto_caption；DouK 覆盖图集/实况图。两者形成 douyin.com/video 与 short-link/note/gallery 的互补 |
| 优先级 | P0 |
| 验收标准 | • 单视频下载成功率 ≥ 95%（cookie 有效时）<br>• 失败自动降级到 DouK<br>• 视频文件存到 `E:\Claude_allow\Download\douyin\{aweme_id}\`<br>• 自带字幕命中时直接输出 SRT，跳过 F4<br>• cookie 过期时返回 `COOKIE_STALE`，飞书提示用户重新登录浏览器 |
| 依赖 | F10（cookie 管理）、yt-dlp ≥ 2026.06、DouK ≥ 14.x |

### F3 字幕优先抽取

| 维度 | 内容 |
|---|---|
| 描述 | yt-dlp `--write-auto-subs --write-subs --sub-langs all --convert-subs srt`；优先 `auto_caption`，其次创作者上传字幕（`cla_info.caption_infos`） |
| 选型理由 | T2 §2 实测：知识类口播视频抖音 95%+ 有 auto_caption。命中时整条 Whisper 链路省掉 |
| 优先级 | P0 |
| 验收标准 | • SRT 输出符合标准格式（pysrt 可读）<br>• 命中率 ≥ 80%（知识类视频 30 天滚动）<br>• `subtitle_source = douyin_native_auto` 或 `douyin_native_creator`<br>• 多语言字幕优先选 `zh-CN > zh > en` |
| 依赖 | F2 |

### F4 Whisper 兜底转写

| 维度 | 内容 |
|---|---|
| 描述 | F3 未命中时：ffmpeg 抽 16 kHz mono wav → faster-whisper（Belle-whisper-large-v3-turbo-zh）→ SRT |
| 选型理由 | T3 §1/§2 横评：faster-whisper + Belle turbo-zh 在 4070S 上速度/精度/装机难度三者最优。CER 3.07%（AISHELL-1），中文场景碾压 vanilla |
| 优先级 | P0 |
| 验收标准 | • 默认模型 `BELLE-2/Belle-whisper-large-v3-turbo-zh`，可配置切到精度版<br>• 3 分钟视频 ≤ 60 秒完成转写（含 VAD）<br>• `vad_filter=True`、`condition_on_previous_text=False`<br>• 支持热词注入（从抖音 caption/hashtags 抽取候选）<br>• 显存峰值 ≤ 8 GB（含 batched 开销）<br>• `subtitle_confidence` 字段填充 |
| 依赖 | F2 输出 wav、CUDA 12.x + cuDNN 9 + ctranslate2 ≥ 4.5.0 |

### F5 关键帧抽取与视觉理解

| 维度 | 内容 |
|---|---|
| 描述 | PySceneDetect ContentDetector(t=27, min_scene_len=15) 抽帧 → 启发式分流 → PaddleOCR PP-OCRv5 server + Qwen2.5-VL-7B-Instruct AWQ |
| 选型理由 | T6 §A/§B/§C 推荐链路；4070S 12G 串行运行刚好；启发式（scene_density / ocr_char_density）避免无脑跑 VLM 浪费算力 |
| 优先级 | P1 |
| 验收标准 | • 4 种模式正确分流：subtitle_only / subtitle_plus_ocr / full / full_with_llm_fuse<br>• PPT 类视频每分钟抽 5–25 帧<br>• PP-OCRv5 中文识别准确率 ≥ 90%（印刷体）<br>• VLM 单帧 prompt 输出 ≤ 200 字<br>• 关键帧存到 `attachments/douyin/{aweme_id}/kf_NNN.jpg`<br>• 处理 5 分钟视频额外耗时 ≤ 5 分钟 |
| 依赖 | F2 视频文件、F4 字幕（用于 ocr_char_density 计算）、4070S 12G |

### F6 LLM 内容总结

| 维度 | 内容 |
|---|---|
| 描述 | 把字幕 + OCR + VLM 描述喂给 LLM，产出 frontmatter 中的 `ai_summary_short`、`ai_keywords` 和正文中的 H2 分节结构 |
| 选型理由 | 笔记可读性核心。本地 Qwen2.5-7B-Instruct 满足 90% 场景；云端通过 OpenAI-compatible 抽象接 MiMo / GLM / Qwen / DeepSeek 等，不把业务代码绑死在某一家 |
| 优先级 | P1 |
| 验收标准 | • 默认本地 Qwen，配置项可切 MiMo/GLM 等云端<br>• 单次调用 token ≤ 8K（避免上下文溢出和成本失控）<br>• 输出符合 §E LLM 融合 prompt 格式<br>• 失败时降级：跳过总结，仅保留字幕 + OCR 原文<br>• API token 不入 Git（F10） |
| 依赖 | F3/F4 字幕、F5 OCR/VLM、F10 凭证 |

### F7 Obsidian 笔记生成与写入

| 维度 | 内容 |
|---|---|
| 描述 | 按 §6 schema 生成 markdown，原子写入（先 `.tmp` 再 rename）到 `vault/inbox/douyin/YYYY-MM/{aweme_id}.md`；附件写到 `vault/attachments/douyin/{aweme_id}/` |
| 选型理由 | T5 §A 推荐"直接文件系统写入 + DataView 视图层"主方案：零依赖、CI 友好、Syncthing 配合天然 |
| 优先级 | P0 |
| 验收标准 | • frontmatter 字段完整、ISO 8601 时间戳、`tags` YAML list 语法<br>• 同 `aweme_id` 重复写入触发 `if exists: append section`，不覆盖<br>• 文件名稳定为 `{aweme_id}.md`，不含中文/特殊字符<br>• Obsidian 桌面端 ≤ 2 秒索引到新笔记（依赖文件系统通知）<br>• 提供 DataView 仪表盘 `dashboards/douyin_inbox.md`，列出 `status=ready AND tags contains "inbox"` |
| 依赖 | F1/F3/F4/F5/F6 输出、vault 路径配置 |

### F8 同步层

| 维度 | 内容 |
|---|---|
| 描述 | M1 先做 PC 本地 vault + Git 冷备；Android/PC 可启用 Syncthing；iOS 走 Obsidian Sync / iCloud / Working Copy 候选；OneDrive 仅作 Windows/macOS 候选 |
| 选型理由 | Obsidian 官方同步资料明确：Obsidian Sync 最省心；Syncthing 适合 PC/Android/局域网；iOS 推荐 Obsidian Sync 或 iCloud；Git 适合版本历史但需要自动化 push/pull |
| 优先级 | P0（PC 本地 + Git 冷备）、P1（Android/PC Syncthing）、P2（iCloud/OneDrive/Obsidian Sync 评估） |
| 验收标准 | • `.stignore` 排除 workspace*.json、cache、graph.json、sync-conflict-* (T5 §C.1)<br>• `.gitignore` 排除 mp4/webm 大附件（T5 §C.2）<br>• PC 端 cron 每日或每小时 commit + push，commit 信息含批次摘要<br>• Android 分支：PC ↔ Android 同步延迟 ≤ 30 秒（≤5MB）<br>• iOS 分支：Obsidian Sync/iCloud/Working Copy 选一条验证，不与 Syncthing 双主混用<br>• `sync-conflict-*` 文件每周扫描提示，不自动合并<br>• `attachments/raw_video/` 不进任何同步通道 |
| 依赖 | 私有 Git 仓；Android 分支依赖 Syncthing-Fork；iOS 分支依赖 Obsidian Sync/iCloud/Working Copy |

### F9 状态机与重试

| 维度 | 内容 |
|---|---|
| 描述 | 笔记 frontmatter 的 `status` 字段驱动状态机：`pending → fetching → transcribing → vlm → writing → done` 或 `failed`。失败可重试，进度可观测 |
| 选型理由 | T5 §B `status` 字段已设计；T4 §C 错误码与重试约定。状态写在 frontmatter 是因为 DataView 能直接 query，不需要单独 DB |
| 优先级 | P0 |
| 验收标准 | • 6 种状态转换合法（不能跳过）<br>• 每次状态变更都更新 `frontmatter.processed_at`<br>• failed 状态填 `error.code` + `error.message`<br>• 单条任务失败 ≤ 3 次重试，指数退避（1s/8s/60s）<br>• DataView 仪表盘按状态分组显示<br>• 进程崩溃后重启可从最近 status 续跑（断点续传） |
| 依赖 | F7（frontmatter 写入）、所有上游模块 |

### F10 配置与凭证管理

| 维度 | 内容 |
|---|---|
| 描述 | 集中管理 cookies（抖音）、tokens（MiMo/GLM/HF 等）、路径（vault、download、模型缓存）、模型名、热词字典 |
| 选型理由 | 凭证不进 Git 是基本盘；路径从 Jovi 全局策略读（`E:\Claude_allow\Download\`、`E:\AI_Tools\...\whisper_models`） |
| 优先级 | P0 |
| 验收标准 | • 配置文件分层：`config/default.yaml`（入库）+ `config/local.yaml`（不入库，含凭证）<br>• 启动时校验 cookie 新鲜度（请求一次低成本接口）<br>• cookie 过期时自动尝试 `cookiesfrombrowser`，失败再报警<br>• HF_ENDPOINT 默认设 `https://hf-mirror.com`，避免国内拉模型超时<br>• 提供 `--validate-config` 命令，启动前预检 |
| 依赖 | 文件系统 |

---

## 5. 非功能需求

### 5.1 端到端延迟

| 视频长度 | 字幕命中 | 字幕未命中（含 Whisper） | 含 VLM 处理（PPT 类） |
|---|---|---|---|
| ≤ 1 min | ≤ 60 s | ≤ 90 s | ≤ 3 min |
| ≤ 3 min | ≤ 90 s | ≤ 2 min | ≤ 5 min |
| ≤ 10 min | ≤ 3 min | ≤ 5 min | ≤ 10 min |
| ≤ 30 min | ≤ 8 min | ≤ 10 min | ≤ 15 min |

90 分位达标即可（受网络/抖音 CDN 抖动影响）。

### 5.2 可靠性

- **离线消息追赶**：开机后 30 秒内开始处理积压消息（依赖 openclaw 内置持久化能力）。
- **进程崩溃恢复**：`status` 断点续传，最多损失当前任务一阶段进度。
- **单条任务隔离**：一个视频失败不影响队列中其他任务。
- **重试**：网络/限频类错误自动指数退避；解析逻辑错误一次性失败，等用户手动重试。

### 5.3 资源预算（4070S 12 GB）

| 模块 | 显存峰值 | 占用策略 |
|---|---|---|
| Whisper Belle turbo-zh fp16 | ~5 GB | F4 运行时独占 |
| PaddleOCR PP-OCRv5 server | ~3 GB | F5 运行时独占 |
| Qwen2.5-VL-7B AWQ-4bit | ~6.5 GB | F5 VLM 阶段独占 |
| 本地 LLM 总结（Qwen2.5-7B-Instruct AWQ） | ~6 GB | F6 运行时独占 |

**铁律**：Whisper / OCR / VLM / LLM **串行执行**，禁止并行。一次只加载一个模型，处理完释放。

### 5.4 隐私

- cookies / tokens 全部放 `config/local.yaml`，进 `.gitignore`。
- 默认本地处理；云端调用必须显式 opt-in（配置项 `cloud_llm: enabled`）。
- 抖音视频含说话人脸，送云端前**必须**裁剪为关键帧元素（不含人物）或模糊化（T6 §风险 #4）。
- 日志中脱敏：cookie / token 字段一律打码为 `***`。

### 5.5 可观测性

- 日志路径：`E:\AI_Tools\Claude\ClaudeCode\logs\douyin_pipeline\YYYY-MM-DD.log`
- 关键事件埋点（结构化 JSON）：
  - `task.received` `task.url_extracted` `task.fetched` `task.subtitle_resolved`（含 source）
  - `task.whisper_done`（含 RTF、CER 估算）`task.vlm_done`（含帧数、token）
  - `task.note_written` `task.failed`（含错误码、堆栈）
- DataView 仪表盘 `dashboards/douyin_stats.md`：按周/作者/topic 统计。
- 飞书回写状态：每个任务至少 2 条线程消息（"已收到处理中" + "已入库/失败"）。

### 5.6 可扩展性

- 抓取层抽象出 `BasePlatformFetcher`，未来 Bilibili/小红书 实现同接口即可接入。
- LLM/VLM 后端走配置驱动（`backend: local_qwen | glm_cloud | ollama`），换厂商不动业务代码。
- frontmatter 加 `pipeline_version` 字段，schema 升级时旧笔记可批量迁移。

---

## 6. 数据模型

### 6.1 frontmatter Schema（最终版，基于 T5 §B 调整）

```yaml
# === 来源 ===
source_url: string               # 飞书原始 URL，可能是 v.douyin.com 短链
canonical_url: string            # 解析后 douyin.com/video/{id}
video_id: string                 # aweme_id，文件名用，主键
platform: string                 # "douyin"（未来 bilibili/xhs）

# === 作者 ===
author_name: string
author_id: string                # 抖音号（人类可读）
uploader_id: string              # B3 修订（v2 2026-06-19）：sec_uid（稳定标识），从 yt-dlp uploader_url 正则提取
                                 # 字段名改为 uploader_id 而非 author_uid，未来扩展 Bilibili / 小红书时同字段复用

# === 视频元数据 ===
title: string
description: string              # 抖音 caption 原文
publish_time: datetime           # ISO 8601 +08:00
duration_sec: int
cover_url: string                # 本地相对路径
keyframes: list[string]          # 关键帧本地相对路径

# === 分类 ===
tags: list[string]               # YAML list 语法
topics: list[string]             # AI 推断的领域标签
manual_tags: list[string]        # 用户后期手动加

# === 字幕 ===
subtitle_source: string          # douyin_native_auto | douyin_native_creator | whisper_belle_v3_turbo_zh | whisper_belle_v3_zh
subtitle_lang: string            # zh / zh-CN / en
subtitle_confidence: float       # 0–1，Whisper 时为 lang_probability，原生字幕固定 0.99

# === AI 处理 ===
ai_summary_model: string         # qwen2.5-7b-instruct-awq | glm-4-flash | glm-4.5v
ai_summary_short: string         # ≤ 100 字
ai_keywords: list[string]
ocr_done: bool
ocr_keyframe_count: int
vlm_done: bool
vlm_model: string                # qwen2.5-vl-7b-instruct-awq | glm-4.5v | null
processing_mode: string          # subtitle_only | subtitle_plus_ocr | full | full_with_llm_fuse

# === 流水线状态 ===
fetched_at: datetime
processed_at: datetime
status: string                   # pending | fetching | transcribing | vlm | writing | done | failed
pipeline_version: string         # semver
error: object | null             # { code: string, message: string, retried: int }

# === 来源溯源 ===
source_message:
  channel: string                # feishu
  message_id: string             # 飞书 message_id（idempotency_key）
  chat_id: string
  received_at: datetime
```

### 6.2 示例笔记（落盘前 40 行）

```markdown
---
source_url: "https://v.douyin.com/iJkPCB42/"
canonical_url: "https://www.douyin.com/video/7412345678901234567"
video_id: "7412345678901234567"
platform: "douyin"
author_name: "李华"
author_id: "lihua_official"
uploader_id: "MS4wLjABAAAAabcdef"
title: "用三块板子搞定 PCIe Gen4 阻抗匹配"
description: "三种叠层方案对比 #PCB #高速信号"
publish_time: 2026-05-20T19:00:00+08:00
duration_sec: 187
cover_url: "attachments/douyin/7412345678901234567/cover.jpg"
keyframes:
  - "attachments/douyin/7412345678901234567/kf_001.jpg"
  - "attachments/douyin/7412345678901234567/kf_002.jpg"
tags:
  - douyin
  - inbox
  - hardware/pcb
  - 待整理
topics:
  - PCB
  - signal_integrity
manual_tags: []
subtitle_source: "douyin_native_auto"
subtitle_lang: "zh-CN"
subtitle_confidence: 0.99
ai_summary_model: "qwen2.5-7b-instruct-awq"
ai_summary_short: "讲了 PCIe Gen4 走线时的阻抗失配问题，给了三种叠层方案对比。"
ai_keywords: [PCIe, 阻抗, 叠层]
ocr_done: true
ocr_keyframe_count: 8
vlm_done: false
processing_mode: "subtitle_plus_ocr"
fetched_at: 2026-06-19T14:32:11+08:00
processed_at: 2026-06-19T14:35:48+08:00
status: "done"
pipeline_version: "1.0.0"
error: null
source_message:
  channel: "feishu"
  message_id: "om_xxx_msg_yyy"
  chat_id: "oc_xxx"
  received_at: 2026-06-19T14:31:50+08:00
---

# 用三块板子搞定 PCIe Gen4 阻抗匹配

> [原视频链接](https://www.douyin.com/video/7412345678901234567) · 作者 [李华](https://www.douyin.com/user/MS4wLjABAAAAabcdef) · 时长 187s

![封面](attachments/douyin/7412345678901234567/cover.jpg)

## 📝 AI 总结
讲了 PCIe Gen4 走线时的阻抗失配问题，给了三种叠层方案对比。

## 🎙️ 字幕原文
> 来源：douyin_native_auto · 置信度 0.99
（…字幕全文…）

## 🔍 关键帧 OCR
- kf_002 @ 00:23 — "Dk = 3.66 @ 10GHz"
- kf_005 @ 01:08 — "Loss tangent 0.0037"

## 🧠 我的思考
（人工补充）
```

---

## 7. 里程碑

### M1 · 字幕优先 MVP（覆盖大多数场景）

**周期**：1–2 周
**包含**：F1 + F2 + F3 + F7 + F8（PC 本地 + Git 冷备）+ F9（最简版）+ F10
**交付物**：
- 命令行可跑：`python pipeline.py --share-text "<飞书消息文本>"`
- openclaw skill / HTTP 接口对接（按 T4 §C OpenAPI）
- 笔记落 `inbox/douyin/YYYY-MM/`，PC 端 Git 冷备可跑；手机同步不阻塞 M1
- 飞书机器人能回写"已入库 + 路径"

**验收方法**：连续 5 天人工验证，分享 ≥ 30 个有原生字幕的知识视频，端到端成功率 ≥ 90%
**估算工作量**：30–40 小时
**风险**：
- openclaw 接口契约（HTTP vs CLI）未定 → 见第 8 节开放问题
- 抖音 cookie 过期处理流程要走通

### M2 · Whisper 兜底

**周期**：再 1 周
**包含**：F4 + F9 状态机扩展（transcribing 阶段）
**交付物**：
- faster-whisper + Belle turbo-zh 跑通，4070S 性能基线落到 README
- 实测 10 段无原生字幕视频 CER ≤ 8%
- 显存峰值监控，超 8GB 自动降级 batch_size

**验收方法**：在 M1 基础上分享 ≥ 10 条无字幕视频，全部产出可读笔记
**估算工作量**：15–20 小时
**风险**：
- cuDNN 9 / ctranslate2 4.5+ 版本踩坑（T3 §6.4）
- BELLE 模型首次 ct2 转换 1–3 分钟

### M3 · 视觉理解

**周期**：再 1–2 周
**包含**：F5 + F6
**交付物**：
- PySceneDetect + PaddleOCR + Qwen2.5-VL 全链路
- 启发式分流落地（subtitle_only / subtitle_plus_ocr / full / full_with_llm_fuse）
- VLM/LLM 后端可切（local_qwen / glm_cloud）
- LLM 融合 prompt 调优至少 1 轮（人工 review 5 条样本）

**验收方法**：分享 5 条 PPT 类、5 条图文混合类视频，OCR + VLM 输出能让笔记结构化
**估算工作量**：25–35 小时
**风险**：
- 4070S 12G 串行编排，模型切换开销
- VLM 长视频成本控制（T6 §风险 #3）

### M4 · 同步全场景 + 健壮性

**周期**：再 1 周
**包含**：F8 完整版（Git + Android/PC Syncthing 候选 + iOS Obsidian Sync/iCloud/Working Copy 候选）+ 错误处理强化 + 可观测性
**交付物**：
- PC 端 cron 自动 commit + push
- 失败重试机制完整（指数退避、状态机断点续传）
- 飞书回写错误码 + 建议
- 日志 + DataView 统计仪表盘
- README + EXECUTION.md 完成

**验收方法**：模拟 cookie 过期、视频被删、显存 OOM 三类故障，系统不崩、回写明确、可恢复
**估算工作量**：15–20 小时
**风险**：
- sync-conflict 处理流程未自动化（T5 §C.3 推荐手动）

### M5（TBD）扩展平台

**周期**：未定
**包含**：Bilibili 适配 + 自动归档分类
**触发**：M1–M4 稳定运行 1 个月后再讨论。

---

## 8. 风险与开放问题

### 8.1 已知风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 抖音 a_bogus 算法升级 | F2 抓取整体失败 | 不绑死单一工具，yt-dlp + DouK 双链路；定期 `pip install -U yt-dlp`（T2 §4） |
| cookie 频繁过期 | F2 出错率上升 | F10 提供 `cookiesfrombrowser` 自动读浏览器；过期时主动通知用户重新登录 |
| openclaw 破坏性变更 | skill 不工作 | M1 锚定具体版本（package.json engines + smoke 测试）；版本升级前先 dry-run |
| Belle 模型对方言/嘈杂音频掉点 | Whisper CER > 10% | M2 验收时跑 10 段实测；超阈值切回精度版 large-v3-zh + beam 5（T3 §8） |
| 4070S 12G 显存边界 | 多模型共存 OOM | 串行执行铁律；监控显存峰值；超阈值降 batch（T6 §风险 #7） |
| MiMo/GLM token 到期或协议限制 | 云端 LLM/ASR/VLM 备选失效 | 默认本地 Qwen + 本地 Whisper 主路径；云端调用走 OpenAI-compatible 抽象，按成本/合规随时替换 |
| HF 国内访问慢 | 模型首次下载失败 | F10 默认 `HF_ENDPOINT=hf-mirror.com`（T3 §6.4） |
| Syncthing-Android 后台被杀 | Android 同步延迟 | 加电池白名单；仅 WiFi+充电时同步（T5 §C.6） |
| iOS 设备无 Syncthing | 多端覆盖不全 | iOS 分支选择 Obsidian Sync / iCloud / Working Copy；不与 Syncthing 双主混用 |
| sync-conflict 文件累积 | vault 体积膨胀 | F7 写入 `if exists: append`，从源头降冲突；每周扫描 `*.sync-conflict-*` 提示 |

### 8.2 需要 Jovi 决策的开放问题

| # | 问题 | 选项 | 推荐 |
|---|---|---|---|
| Q1 | **openclaw 飞书频道运行模式？**（来自 T4 追问） | (a) WebSocket 长连接（推荐）<br>(b) HTTP webhook + tunnel | a — 无需公网，飞书官方推荐 |
| Q2 | **openclaw 部署形态？**（T4 追问） | (a) 命令行常驻进程<br>(b) Windows Hub 桌面端 + tray | b — 桌面端日常更友好，但需确认 Hub 是否支持自定义 skill |
| Q3 | **抖音解析服务与 openclaw 通信？**（T4 追问） | (a) HTTP 服务（OpenAPI YAML）<br>(b) openclaw skill 直接 spawn CLI<br>(c) 写一个 openclaw 内部 skill（TS/Node） | a — 解耦最干净；c 最贴 openclaw 但需要写 TS |
| Q4 | **openclaw 配置路径与版本？**（T4 追问） | 待 confirm | 启动前 `ls ~/.openclaw/config.json5` 给出 |
| Q5 | **云端模型厂商如何落地？** | 当前 MiMo token-plan 可用，但自动化后端存在协议风险；GLM/Qwen/DeepSeek 可替换 | M1 不依赖云端；M2/M3 做 OpenAI-compatible 抽象，默认本地优先 |
| Q6 | **Obsidian vault 路径？** | 已拍板 `E:\AI_Tools\Obsidian\data\notes-personal` | 写入逻辑必须严格落到 `notes-personal\`，不要污染 Obsidian 程序目录 |
| Q7 | **本地 LLM 主选什么后端？** | (a) Ollama（最省心）<br>(b) vLLM（吞吐高）<br>(c) Transformers + AWQ | a — 个人单用户场景，Ollama + Qwen2.5-7B AWQ 一键起 |
| Q8 | **失败时是否保留中间产物？** | (a) 保留 mp4/wav 便于调试<br>(b) 失败即清理，仅留笔记 | a — 调试期保留，30 天后自动清理 |

---

## 9. 度量与验收

### 9.1 项目整体验收标准

**功能侧**：
- [ ] M1–M4 全部里程碑达成
- [ ] 连续 30 天无人工干预，端到端成功率 ≥ 90%
- [ ] 失败案例 100% 可在飞书查到状态 + 错误码
- [ ] 笔记 schema 在 DataView 仪表盘正确索引（10 条样本验证）

**体验侧**：
- [ ] Jovi 主路径手动操作 ≤ 1 步（复制 → 粘贴）
- [ ] 90 分位端到端延迟达标（§5.1 表）
- [ ] 笔记可读性人工评分 ≥ 4/5（抽 20 条）
- [ ] M1：PC 端 Git 冷备正常；M2+：Android Syncthing 或 iOS 云同步分支至少一条通过验证

### 9.2 关键指标采集方式

| 指标 | 采集方式 | 频率 |
|---|---|---|
| 端到端成功率 | 日志结构化事件 `task.note_written` / `task.failed` 比值 | 实时 + 周报 |
| 90 分位延迟 | 日志事件 `task.received` → `task.note_written` 时间差，histogram | 周报 |
| 字幕命中率 | `subtitle_source = douyin_native*` 占比 | 周报 |
| Whisper CER 估算 | M2 起，定期抽样人工标注 5 条对比 | 月度 |
| 显存峰值 | nvidia-smi 监控脚本，每 10 秒采样写日志 | 实时告警 |
| 同步延迟 | Android 分支记录 Syncthing 文件 mtime；iOS 分支记录 Obsidian Sync/iCloud/Working Copy 最新文件 mtime | 抽查 |
| 错误码分布 | 日志 `task.failed` 按 code 分组 | 周报 |
| 笔记数量 | DataView `LENGTH(FROM "inbox/douyin")` | 实时 |

### 9.3 上线后健康检查

每周自动跑一次：
- 抖音 cookie 新鲜度（请求 `aweme/v1/web/aweme/detail/` 任一可访问视频）
- yt-dlp / DouK 版本检查 + 自动 `pip install -U`
- HF 镜像可达性
- Git 冷备任务正常；若启用 Syncthing/云盘，同步节点全在线
- Obsidian vault 大小、笔记总数、status 分布

---

## 附录 · 调研报告快速索引

| 报告 | 核心结论 | 在本 PRD 体现 |
|---|---|---|
| T2 douyin-extraction | yt-dlp 主 + DouK 备；原生字幕是最大优化点 | F1/F2/F3 |
| T3 whisper-local | faster-whisper + Belle turbo-zh；CER 3% | F4 |
| T4 feishu-openclaw | openclaw 是 GitHub `openclaw/openclaw`；飞书 WS 模式 | F1 / 第 8 节 Q1–Q4 |
| T5 obsidian-write + Web research | 文件系统直写 + DataView；同步通道按 Git/Syncthing/iCloud/Obsidian Sync 分支选择 | F7 / F8 / 第 6 节 schema |
| T6 multimodal-vision | PySceneDetect + PaddleOCR + Qwen2.5-VL；启发式分流 | F5 / F6 / 第 8 节 Q5 |

---

**文档结束。等待 Jovi 在第 8 节决策完后启动 EXECUTION.md。**
