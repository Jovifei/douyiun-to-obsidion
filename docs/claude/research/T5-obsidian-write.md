# T5 — Obsidian 集成调研：抖音笔记自动写入 + 多端同步

> 调研日期：2026-06-19  调研员：Claude (OMC research lane)
> 范围：外部脚本 → Obsidian vault 写入方式、抖音笔记 frontmatter schema、Syncthing/Git/iCloud 同步叠加策略、vault 目录布局
> 目标用户：Jovi（Windows PC 主用 + Android 手机随身）

---

## Part A：外部脚本写入 vault 的 4 种方式

| 方案 | 写入路径 | Obsidian 是否需在线 | 优点 | 缺点 | 适用场景 |
|------|---------|------------------|------|------|---------|
| **1. 直接文件系统写入** | `fs.writeFile`/`open()` 直接写 vault 目录下 `.md` | 否 | 零依赖；脚本端 100% 可控；可用任意语言；CI/cron 友好；与 Syncthing 配合天然 | 需要脚本端处理路径冲突、原子写入（先写 `.tmp` 再 rename）；Obsidian 桌面/手机端需要时间 reload index（一般 ≤2 秒） | **主方案推荐**：批量、离线、非交互场景 |
| **2. Local REST API 插件** | HTTP `PUT /vault/{path}` 带 Bearer token | 是（Obsidian 必须运行） | 触发 Obsidian 内部事件，索引立刻更新；可读 vault 状态、查询 metadata；自带 OpenAPI 规范 | Obsidian 必须前台/后台运行；HTTPS 用自签证书需 `-k`；手机端不可用；端口 27124（HTTPS）/27123（HTTP） | 桌面端实时写入 + 立即触发 DataView 刷新 |
| **3. Advanced URI** | `obsidian://adv-uri?vault=...&filepath=...&clipboard=true&mode=append` | 是 | 触发 Obsidian 内置动作（打开、跳转、heading 定位）；可结合 Templater | 内容须经剪贴板/URL 参数传输，长正文容易超 URL 长度限制；URL 编码繁琐；不适合后台批量；手机端需 deeplink | 单条交互写入、人工复核场景；不适合 1000+ 笔记批跑 |
| **4. Templater + DataView 元数据驱动** | 文件系统写入 frontmatter，DataView/Bases 动态视图 | 否（写入端）；查询端是 | 数据/视图分离；不污染笔记结构；后期 schema 演进容易 | 仅是"写入后展示层"，不是写入手段，须叠加方案 1 | 与方案 1 配合，作为查询/展示层 |

**推荐组合**

```
主方案 = (1) 直接文件系统写入  +  (4) DataView 视图层
兜底/补丁 = (2) Local REST API（仅当桌面在线时用，例如自动加 backlink、触发 reload）
不推荐 = (3) Advanced URI（仅手动场景 fallback）
```

理由：抖音笔记是**批量、后台、跨设备**生成的（cron / Whisper 离线转写动辄几十条），方案 1 唯一无依赖，且与 Syncthing 配合最干净（写入即同步）。Local REST API 留作"桌面在线时的优化通道"，可选不做。

---

## Part B：抖音视频笔记 frontmatter schema

设计原则：
- 字段名遵循 **Dataview 索引规则**：自动 lowercase + 空格转 dash，因此源字段一律 **snake_case** 或全小写、避免空格，确保查询稳定。
- `tags` 用 YAML list 语法（每行一个 `- xxx`），符合 Obsidian Properties 官方要求。
- 时间字段用 **ISO 8601**（`2026-06-19T14:30:00+08:00`），DataView 可识别为 date/datetime。
- 长文本（字幕、AI 总结）放在正文区，frontmatter 只保留可索引字段。

### 完整模板（保存为 `templates/douyin_note.md`）

```markdown
---
# === 来源 ===
source_url: "https://v.douyin.com/xxxxx/"
canonical_url: "https://www.douyin.com/video/7412345678901234567"
video_id: "7412345678901234567"
platform: "douyin"

# === 作者 ===
author_name: "李华"
author_id: "lihua_official"
author_uid: "MS4wLjABAAAAxxx"

# === 视频元数据 ===
title: "用三块板子搞定 PCIe Gen4 阻抗匹配"
publish_time: 2026-05-20T19:00:00+08:00
duration_sec: 187
cover_url: "attachments/douyin/7412345678901234567/cover.jpg"
keyframes:
  - "attachments/douyin/7412345678901234567/kf_001.jpg"
  - "attachments/douyin/7412345678901234567/kf_002.jpg"

# === 分类与标签（Dataview/Bases 友好） ===
tags:
  - douyin
  - inbox
  - hardware/pcb
  - 待整理
topics:
  - PCB
  - signal_integrity
manual_tags: []   # 用户手动追加

# === 字幕 ===
subtitle_source: "whisper_large_v3"   # douyin_native | whisper_large_v3 | whisper_finetuned
subtitle_lang: "zh"
subtitle_confidence: 0.92

# === AI 处理 ===
ai_summary_model: "glm-4.6"
ai_summary_short: "讲了 PCIe Gen4 走线时的阻抗失配问题，给了三种叠层方案对比。"
ai_keywords:
  - PCIe
  - 阻抗
  - 叠层
ocr_done: true
ocr_keyframe_count: 8

# === 流水线状态 ===
fetched_at: 2026-06-19T14:32:11+08:00
processed_at: 2026-06-19T14:35:48+08:00
status: "ready"   # pending | downloading | transcribing | summarizing | ready | failed
pipeline_version: "1.2.0"
error: null
---

# 用三块板子搞定 PCIe Gen4 阻抗匹配

> [原视频链接]({{source_url}}) · 作者 [{{author_name}}](https://www.douyin.com/user/{{author_uid}}) · 时长 {{duration_sec}}s

![封面]({{cover_url}})

## 📝 AI 总结
{{ai_summary_short}}

## 🎙️ 字幕原文
> 来源：{{subtitle_source}} · 置信度 {{subtitle_confidence}}

```text
（完整字幕折叠在 callout 中）
```

## 🔍 关键帧 OCR
- kf_002 @ 00:23 — "Dk = 3.66 @ 10GHz"
- kf_005 @ 01:08 — "Loss tangent 0.0037"

## 🧠 我的思考
（人工补充）

## 🔗 相关
（DataView 自动列出同 topics 的笔记）
```dataview
LIST
FROM "inbox/douyin"
WHERE contains(topics, this.topics) AND file.path != this.file.path
SORT publish_time DESC
LIMIT 5
```
```

### 示例笔记片段（实际写盘内容前 30 行）

```markdown
---
source_url: "https://v.douyin.com/iJkPCB42/"
canonical_url: "https://www.douyin.com/video/7412345678901234567"
video_id: "7412345678901234567"
platform: "douyin"
author_name: "李华"
author_id: "lihua_official"
author_uid: "MS4wLjABAAAAabcdef"
title: "用三块板子搞定 PCIe Gen4 阻抗匹配"
publish_time: 2026-05-20T19:00:00+08:00
duration_sec: 187
cover_url: "attachments/douyin/7412345678901234567/cover.jpg"
tags:
  - douyin
  - inbox
  - hardware/pcb
subtitle_source: "whisper_large_v3"
subtitle_confidence: 0.92
ai_summary_model: "glm-4.6"
ai_summary_short: "讲了 PCIe Gen4 走线时的阻抗失配问题..."
fetched_at: 2026-06-19T14:32:11+08:00
status: "ready"
pipeline_version: "1.2.0"
---

# 用三块板子搞定 PCIe Gen4 阻抗匹配
...
```

### Dataview 查询示例（验证 schema 可用性）

```dataview
TABLE author_name AS "作者", duration_sec AS "时长", subtitle_confidence AS "置信度"
FROM "inbox/douyin"
WHERE status = "ready" AND subtitle_confidence > 0.85
SORT publish_time DESC
```

---

## Part C：同步叠加策略（Syncthing 主 + Git 备 + iCloud/OneDrive 候选）

### C.1 Syncthing（主同步通道）

**`.stignore` 推荐内容**（放在 vault 根目录）：

```gitignore
# === 工作区状态（每端独立） ===
.obsidian/workspace
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.obsidian/cache
.obsidian/graph.json

# === 日志与缓存 ===
.obsidian/logs
.obsidian/snippets/.cache

# === 系统垃圾 ===
.DS_Store
Thumbs.db
desktop.ini

# === 回收站本地化 ===
.trash/

# === Syncthing 自身冲突文件不再扩散 ===
*.sync-conflict-*

# === 大附件目录可选排除（若决定走 OneDrive） ===
# attachments/raw_video/
```

**双向同步配置**：所有节点 send & receive；启用 *Watch for changes*（默认 10s）；对 vault 文件夹设置 *Ignore Permissions*（Windows ↔ Android 权限位差异大）；版本控制选 **Staggered File Versioning**（保 30 天）。

### C.2 Git（异地冷备 + 历史）

**`.gitignore`**：

```gitignore
.obsidian/workspace*
.obsidian/cache
.obsidian/graph.json
.obsidian/logs/
.trash/
*.sync-conflict-*

# 大文件不入库（用 Git LFS 或独立同步）
attachments/raw_video/
attachments/**/*.mp4
attachments/**/*.webm

# 系统垃圾
.DS_Store
Thumbs.db
```

**Commit 策略**：
- 由 PC 端定时任务负责 commit（如每小时 cron / Windows Task Scheduler），手机端**不**承担 git 责任。
- 抖音流水线脚本完成一批写入后调 `git add -A && git commit -m "douyin: $(date) +N notes"` 自动入库。
- 远端用 **GitHub 私库** 或自建 Gitea；不要 push origin/main 多端同时 push（Syncthing 已经在同步，避免环路）。

### C.3 sync-conflict 处理

Syncthing 冲突文件命名为 `xxx.sync-conflict-20260619-143022-AABBCCD.md`：
- 装 [Obsidian Note Refactor / Conflict Resolver 类社区插件] 不可靠，**推荐手动**：每周扫一次 `*.sync-conflict-*` glob，diff 后保留较新版本。
- 抖音笔记字段唯一键是 `video_id`，脚本端写入前应 `if exists: append section` 而非覆盖，从源头降低冲突。

### C.4 `.obsidian/` 是否同步

| 子项 | 同步？ | 理由 |
|-----|--------|------|
| `plugins/` | ✅ | 多端插件版本一致 |
| `themes/` | ✅ | 视觉一致 |
| `snippets/` | ✅ | CSS 片段共享 |
| `app.json`, `appearance.json`, `core-plugins.json`, `community-plugins.json`, `hotkeys.json` | ✅ | 配置统一 |
| `workspace*.json` | ❌ | 每端窗口/标签状态差异巨大，必冲突 |
| `cache`, `graph.json` | ❌ | 本地索引重新生成即可 |
| `plugins/*/data.json` | ⚠️ 视情况 | 含设备指纹的（如 Local REST API 的 token）建议每端独立 |

### C.5 附件策略

- **小附件**（封面、关键帧、≤5MB 图片）：随 vault 走 Syncthing。
- **大附件**（原始视频 mp4/webm）：放 `attachments/raw_video/`，**不进 Syncthing 也不进 Git**，单独走 OneDrive/网盘或仅留在 PC，frontmatter 里只存 URL。

### C.6 移动端实测痛点（Android）

- **Syncthing-Fork**（Catfriend1，F-Droid 长期维护）是目前 Android 上首选；原 Syncthing 官方 Android 版 2022 已停更。
- 痛点：① 手机厂商电池优化必须把 Syncthing 加白名单；② 后台被杀后只能等下次 Obsidian 启动触发；③ 大量小文件（关键帧）首次同步耗电明显，建议**仅 WiFi + 充电时同步**。
- iOS 没有官方 Syncthing → iOS 端只能走 Obsidian Sync（付费）或 iCloud Drive，是这套方案目前的最大缺口；如果 Jovi 未来加入 iOS 设备，建议把 vault 同时挂 iCloud 文件夹做单向只读分发。

### C.7 候选：iCloud / OneDrive

只在以下两种情况启用：
- 加入 iOS 设备，必走 iCloud（vault 路径放在 `~/Library/Mobile Documents/iCloud~md~obsidian/`）。
- 大附件外置到 OneDrive `attachments/raw_video/`，PC 端通过 junction/符号链接挂回 vault。

**不要把整个 vault 同时塞进 Syncthing + iCloud + OneDrive**——多通道并发写就是冲突地狱。同步通道**择一为主**，其余为只读或冷备。

---

## Part D：vault 目录布局建议

```
vault/
├── inbox/
│   └── douyin/                # 抖音笔记落地处（脚本写入目标）
│       ├── 2026-06/           # 按月分桶，避免单目录 1 万+ 文件
│       │   ├── 7412345678901234567.md
│       │   └── ...
│       └── 2026-07/
├── knowledge/                 # 人工整理后的归档
│   ├── hardware/
│   ├── ai/
│   └── ...
├── attachments/
│   └── douyin/
│       └── 7412345678901234567/
│           ├── cover.jpg
│           ├── kf_001.jpg
│           └── subtitle_raw.json
├── templates/                 # Templater 模板
│   ├── douyin_note.md
│   └── weekly_review.md
├── dashboards/                # DataView 仪表盘
│   ├── douyin_inbox.md        # 列出 status=pending 的待整理
│   └── douyin_stats.md        # 按作者/topic 统计
├── .obsidian/                 # 配置（部分同步，见 C.4）
└── .stignore
```

**约定**：
- 脚本只写 `inbox/douyin/YYYY-MM/{video_id}.md` 和 `attachments/douyin/{video_id}/*`，**不**改其他目录。
- Jovi 整理后把 `inbox/douyin/xxx.md` 手动移到 `knowledge/...`，frontmatter 的 `tags` 删掉 `inbox` 和 `待整理`，DataView 仪表盘自动从待办列表移除。
- `attachments/` 不跟着笔记移动（保持引用稳定）。

---

## 风险与缺口

1. **iOS 不在 Syncthing 覆盖内**——若未来加 iPhone/iPad，必须切到 iCloud 或 Obsidian Sync 付费。
2. **Local REST API 在手机端不可用**：Android 后台进程不稳定，手机端只能依赖文件系统同步后等 Obsidian 重新索引。
3. **Whisper 大文件并行**：转写耗时长，脚本应支持断点续传 + frontmatter 的 `status` 字段做幂等。
4. **frontmatter schema 演进**：未来加字段时旧笔记不会自动更新，建议给每个笔记打 `pipeline_version`，DataView 查询时过滤旧版本批量重写。
5. **DataView 字段大小写**：snake_case 在 Dataview 中会被 lowercase + dash 化，本 schema 已避免空格，但若以后字段含中文或大写需手动测试 query。
6. **Templater 不在写入路径上**：本方案脚本端不依赖 Templater，因此模板仅供人工新建用，不会阻塞批跑。

---

## 引用列表

1. [Obsidian Local REST API · GitHub](https://github.com/coddingtonbear/obsidian-local-rest-api) — 端口、Bearer token、PUT /vault/{path} 写入
2. [Obsidian Advanced URI · GitHub](https://github.com/Vinzent03/obsidian-advanced-uri) — `obsidian://adv-uri` 语法、URL 编码要求
3. [Obsidian Help · Properties](https://obsidian.md/help/properties) — 7 种属性类型、tags YAML 列表语法
4. [Dataview · Adding Metadata](https://blacksmithgu.github.io/obsidian-dataview/annotation/add-metadata/) — frontmatter 索引规则、字段 sanitize（lowercase + dash）
5. [Templater Docs](https://silentvoid13.github.io/Templater/) — `<% %>` 语法、tp.file.create_new、User Scripts
6. [Syncthing-Fork (Android)](https://github.com/Catfriend1/syncthing-android) — Android 端事实标准
7. Obsidian 官方文档 + 社区共识：`.obsidian/workspace*` 必排除（多端冲突主要来源）
