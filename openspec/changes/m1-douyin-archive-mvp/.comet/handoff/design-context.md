# Comet Design Handoff

- Change: m1-douyin-archive-mvp
- Phase: design
- Mode: compact
- Context hash: aaa2b85cca3e766ffe8f92b998a337ce6154131e22ea4a0253aea4d1f892f622

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/m1-douyin-archive-mvp/proposal.md

- Source: openspec/changes/m1-douyin-archive-mvp/proposal.md
- Lines: 1-47
- SHA256: b83f4a85bae78dcca0515ed7cfd4d4449fbdbbf5ac91b99e794d82088aecf1ad

```md
## Why

Jovi 在手机刷抖音时遇到的知识类视频，目前没有一条自动化路径把"链接 + 视频内容"沉淀到 Obsidian。已搭好 `飞书自建机器人 → openclaw（Node 24 本地服务）` 通道，但 **openclaw → 解析 → Obsidian** 这一段缺失——M1 就补这一段，端到端跑通"分享链接到笔记入库"的最小闭环。

> 完整背景、用户故事与功能矩阵见 `docs/claude/PRD.md` v1.1（2026-06-19，已通过 Codex 反向审核）；本文件不复述。

## What Changes

M1 是抖音归档管线的最小可用版本，**只走"抖音原生字幕"主路径**，不引入本地 ASR、不做视觉理解、不做 LLM 总结、不做手机同步——这些在 m2/m3/m4 处理。

- 新增本地解析服务（FastAPI on `127.0.0.1:8765`）：接收抖音分享 URL → 调用 yt-dlp + 抖音原生字幕抓取 → 生成 Obsidian frontmatter markdown 直写入 vault
- 新增 `bishu` agent（在 openclaw 的 12 agent 体系内新增第 13 位）：飞书消息触发、5 秒响应窗口处理、异步状态回执
- 新增 SQLite 任务队列（含 B4 修订：`claimed_at` 原子占用 + 启动复活超时任务）防止崩溃后重复处理
- 新增 Git 冷备（每日 cron 自动 commit + push 到私有仓库）作为 M1 唯一同步层
- **复用** `git_ref/obsidian-content-capture-backend/script/` 作为 `src/extractors/` 基底（已验证 9⭐ 仓库，无 cookie 无付费 API），节约 30-50% 开发工时
- M1 验收标准：分享一条带原生字幕的抖音知识视频，**≤ 2 分钟**内 vault 出现完整笔记（frontmatter + 字幕全文 + 封面），飞书机器人回"已归档 + 路径"

**不做（明确推迟到后续 change）**：
- Whisper 兜底转写（→ m2-whisper-fallback）
- 关键帧 OCR + Qwen2.5-VL 视觉理解（→ m3-vision-llm-summary）
- LLM 总结（→ m3-vision-llm-summary）
- iOS / Android 同步、监控告警（→ m4-robustness-sync）

## Capabilities

### New Capabilities

- `douyin-extraction`: 抖音 share URL 解析（v.douyin.com 短链 / iesdouyin / 完整 URL）、yt-dlp 主路径下载、抖音原生字幕优先抽取、视频元数据提取（标题/作者/uploader_id/封面/时长）。基于 `git_ref/obsidian-content-capture-backend/script/douyin_resolver.py + downloader.py` 改造。
- `obsidian-archive-writer`: Obsidian frontmatter schema 拼装（snake_case + DataView 友好）、vault 路径计算（`E:\AI_Tools\Obsidian\data\notes-personal\inbox\douyin\YYYY-MM\{video_id}.md`）、原子写入（`.tmp` + rename 防 Syncthing/Obsidian 半文件）、附件目录（封面）保存。
- `bishu-feishu-bridge`: bishu agent 在 openclaw 内的注册与路由配置（飞书账号 `oc_516376df9cc2315fc12470e56e72c4af` + 触发条件 `消息含 douyin.com`）、飞书 5 秒响应窗口"立即被动回复 + 异步主动发消息"、`tenant_access_token` 缓存与刷新、bishu → 解析服务的 HTTP POST 调用契约。
- `task-queue-pipeline`: SQLite 任务队列（schema 含 B4 `claimed_at` 字段）、原子 dequeue（`UPDATE ... RETURNING`）、启动时复活 `claimed_at < now() - 30min` 的 zombie 任务、状态机（pending / fetching / writing / done / failed）、指数退避重试（最大 3 次）。
- `git-cold-backup`: vault 目录的 Git 私有仓库初始化、`.gitignore` 屏蔽 `.obsidian/workspace*` / cookies.txt / `.env` / 大附件、PowerShell 任务计划程序定时 commit + push、冲突文件命名约定。

### Modified Capabilities

无。这是首个 change，所有 capability 都是新增。

## Impact

- **新增源码目录**：`src/{extractors,obsidian,bridge,queue,pipeline,config}/`，预计 ~15 个 Python 模块
- **新增 openclaw agent**：`bishu`（用户在 openclaw UI 自行新建，本 change 提供配置模板）
- **新增依赖**：`fastapi`、`uvicorn[standard]`、`yt-dlp>=2026.x`、`sqlmodel` 或 `aiosqlite`、`pyyaml`、`httpx`；不引入 torch / faster-whisper / paddleocr（M1 无 GPU 推理需求）
- **新增配置文件**：`config.yaml`（路径/模型/凭证占位）、`.env`（真实凭证，不进 Git）、`.gitignore`、`.stignore`（Syncthing 占位）
- **新增 Obsidian vault 目录约定**：`inbox/douyin/YYYY-MM/`（笔记）、`attachments/douyin/{video_id}/`（封面）、`templates/`（M2+ 模板留位）
- **不影响**：openclaw 主配置（Jovi 自行新增 bishu agent）、其他 11 个现有 agent、抖音政策合规审查（不商用，个人留存）
- **可观测性**：日志位置 `logs/{module}/{date}.log`，关键事件含 `correlation_id` 串起整条管线
- **回滚成本**：本地 vault 文件可直接删除；SQLite 任务库可重建；不污染 Obsidian / openclaw 既有数据
```

## openspec/changes/m1-douyin-archive-mvp/design.md

- Source: openspec/changes/m1-douyin-archive-mvp/design.md
- Lines: 1-201
- SHA256: ff857cb4f2ff7c1c38024780add365863b1a8a3f1254b5eb31eb2e48e4c8db0d

[TRUNCATED]

```md
## Context

**项目背景**：详见 `docs/claude/PRD.md` v1.1（项目目标、用户故事、范围 In/Out）、`docs/claude/EXECUTION.md`（实施手册，3745 行）、`docs/claude/DECISIONS.md`（17 项已拍板决策 A1-A17 + 5 项衍生 D1-D5）。本设计文档**只补 m1 阶段的架构核心抉择**，不复述上述文档。

**现有约束**（从 DECISIONS.md 摘录关键项）：
- A1 飞书走 openclaw 默认 WebSocket 长连接，无需内网穿透
- A2 openclaw 与解析服务**同主机** 127.0.0.1
- A6 Vault 路径锁定 `E:\AI_Tools\Obsidian\data\notes-personal`
- A14 新 agent 命名 `bishu`（秘书省）
- A15 当前模型 MiMo（base_url `https://token-plan-cn.xiaomimimo.com/v1`）+ 套餐合规风险——**M1 不调 LLM 规避此风险**
- D1 解析服务接口形态：FastAPI 监听 `127.0.0.1:8765`

**社区参考**（详见 `git_ref/COMMUNITY_RESOURCES_AUDIT.md`）：
- `obsidian-content-capture-backend`（lyxdream）：抖音解析 + 下载 + faster-whisper（M2 用）已实现，无 cookie 无付费 API
- `video-link-pipeline`（xiexikang）：模块化 CLI 架构参考
- `douyin-to-obsidian`（baiye-10）：含中文 ASR 错字修正字典 `text_corrections.json`（M2 复用）

## Goals / Non-Goals

**Goals**：
1. **端到端最短路径打通**：飞书消息 → bishu agent → 解析服务 → vault 笔记 ≤ 2 分钟
2. **复用社区参考**：把 `obsidian-content-capture-backend/script/` 整体搬入 `src/extractors/`，仅做 Flask → FastAPI 改造与依赖修剪
3. **可靠性最小集**：SQLite 队列含 `claimed_at` 占用标记 + 启动复活 zombie 任务，确保进程崩溃重启可继续处理 pending
4. **零云端依赖**：M1 不调任何外部 LLM/ASR/VLM API，规避 MiMo 套餐合规风险，为 M3 走 openclaw 工具层调用打好接口契约（不实现）
5. **为 M2/M3 留接口位**：状态机 / Queue schema / frontmatter schema 都按"含 ASR/视觉"的最终形态设计，避免后续 M2/M3 改基础结构

**Non-Goals**：
1. 不做 Whisper（即便环境装好也默认关闭，A8 决策）
2. 不做关键帧/OCR/VLM
3. 不做 LLM 总结
4. 不做 iOS/Android 同步、不做 Obsidian Sync 配置
5. 不做监控告警系统（仅留日志）
6. 不做飞书群消息/post 富文本处理（仅私聊 text 消息）
7. 不做抖音用户主页批量、合集订阅
8. 不做 openclaw 主配置改动（bishu agent 由 Jovi 在 openclaw UI 自行新建，本 change 仅提供配置模板）

## Decisions

### D-1：架构形态采用 A2（独立 FastAPI + bishu HTTP 调用）

**Why**：M1 启动前 Jovi 在备选 A1（openclaw 内联 subprocess）和 A2（独立服务）之间倾向 A1，但 lead 评估后推荐 A2 并 Jovi 同意。

**Rationale**：
- A2 解析服务独立进程：openclaw 重启不会中断正在跑的解析任务；解析服务崩溃也不影响 openclaw 其他 11 个 agent
- 离线追赶 / 崩溃恢复机制天然——bishu 任何时候 POST 入队，解析服务从队列消化即可
- 接口契约清晰：`POST /ingest` + `GET /tasks/{id}` + `GET /health` + `GET /queue/stats`
- M3 阶段反向调用 openclaw 工具层时，A2 形态的接口边界比 A1 内联更清晰

**Alternative rejected**：
- A1（openclaw subprocess）：简单但 openclaw 重启或 bishu 阻塞会丢任务；不利于 M3 的 LLM 工具层接入
- A3（OpenClaw YAML 工作流）：缺显存资源约束语义（4070S M3 必须严控），已被 Codex 反向审核 R4 反驳

### D-2：解析服务**不调 LLM**，bishu agent 不调 LLM

**Why**：M1 范围明确不含 LLM 总结（用户答 AskUserQuestion 选项 A）。

**Rationale**：
- 让 M1 端到端先打通，避免 prompt 调优、错误处理、合规审视（A15-合规风险）拖慢 M1 进度
- M1 笔记内容 = frontmatter + 完整原生字幕 + 封面，对"知识检索"已有足够价值
- M3 才正式实现"通过 openclaw 工具层调 mimo-v2.5-pro 总结"，M1 做的接口契约能复用

**Alternative rejected**：
- M1 包含 LLM 总结：增加合规风险和 prompt 工程开销，不值

### D-3：参考 `obsidian-content-capture-backend` 解析思路自研 `src/extractors/`（**已修订**）

**Why**：build 前核验发现 backend 仓库**无 OSS license**（README 仅写"仅供学习与研究"，法律上 = All rights reserved），直接 vendoring 复用代码有侵权风险。**Jovi 决策**：不 vendoring，仅借鉴解析思路自研最小 extractor。

**Rationale**：
- yt-dlp 已原生支持 `v.douyin.com` 短链解析 + 抖音自动字幕（T2 调研结论，已验证）—— M1 主路径用 yt-dlp 已足够，不依赖 backend 的 SSR 解析
- backend 的 `douyin_resolver.py`（解析 `window._ROUTER_DATA` SSR）仅作为"实现参考"，看思路不拷代码
- backend 的 `downloader.py` 本质是 requests + yt-dlp 包装，自研同样工作量
- backend 的 `audio_extractor.py` 就是一行 ffmpeg 命令，无版权价值

**Trade-off**：
- 工时估算从 4-5 天上调到 **5-7 天**（自研 extractor +1-2 天）
- 但合规性 100%，长期可商用可开源

**Alternative rejected**：
- ~~Vendoring 复用 backend/script/~~：无 license 风险
```

Full source: openspec/changes/m1-douyin-archive-mvp/design.md

## openspec/changes/m1-douyin-archive-mvp/tasks.md

- Source: openspec/changes/m1-douyin-archive-mvp/tasks.md
- Lines: 1-142
- SHA256: 3ea15fd295f98f6658633ec1d27ea0a2e13c9a8249e6648e6c56f94328e03750

[TRUNCATED]

```md
# M1 实施任务清单

> Change: `m1-douyin-archive-mvp`
> Workflow: full (spec-driven)
> 总工时估算: **5-7 天**（D-3 修订：不 vendoring backend，自研 extractor）
> 顺序严格按下列分组执行，组内可并行
> ⚠️ **关键约束**：OQ-1（bishu agent schema）是飞书端到端 blocker——在 Jovi 提供现有 agent 样板前，§9 / §10 / §11.B **blocked**；§1-8 + §11.A 可独立推进

## 1. 环境与脚手架准备（0.5 天）

- [ ] 1.1 ~~确认 `git_ref/obsidian-content-capture-backend/LICENSE`~~ → ✅ 已确认无 OSS license，**不 vendoring**，仅借鉴思路自研（见 D-3 修订）
- [ ] 1.2 创建 `pyproject.toml`，锁定依赖：`fastapi>=0.110, uvicorn[standard], yt-dlp>=2026.0, sqlmodel, pyyaml, httpx, structlog`
- [ ] 1.3 创建目录骨架：`src/{extractors,obsidian,bridge,queue,pipeline,config,utils}/` + `tests/` + `scripts/` + `docs/m1/`
- [ ] 1.4 创建 `config.example.yaml`（路径/模型占位/凭证引用环境变量；端口锁 `8765`，D-9）
- [ ] 1.5 创建 `.env.example`（`FEISHU_APP_ID/FEISHU_APP_SECRET/MIMO_API_KEY` 占位）
- [ ] 1.6 创建 `.gitignore`（屏蔽 `.env` / `cookies.txt` / `logs/` / `__pycache__/` / `.venv/` / `*.tmp`）
- [ ] 1.7 验证 `python --version` ≥ 3.11，`yt-dlp --version` 可调用，`ffmpeg -version` 可调用
- [ ] 1.8 验证 vault 路径存在：`Test-Path E:\AI_Tools\Obsidian\data\notes-personal` 应返回 True
- [ ] 1.9 全局端口统一：把 `docs/claude/EXECUTION.md` 与 `docs/codex/EXECUTION.md` 全局 `18900` → `8765` 替换（D-9）

## 2. 自研 src/extractors/（参考 backend 思路，不 vendoring）（1.5 天，**工时上调**）

- [ ] 2.1 阅读 `git_ref/obsidian-content-capture-backend/script/douyin_resolver.py` 与 `downloader.py` 理解解析思路（**不复制代码**）
- [ ] 2.2 在 `src/extractors/douyin_resolver.py` 自研 URL 抽取：4 种形态（短链/完整链/iesdouyin/分享文案）+ 短链 302 跟随 + video_id 提取
- [ ] 2.3 在 `src/extractors/downloader.py` 自研 yt-dlp 包装：调用 `yt-dlp` Python API 下载视频 + 字幕，读 `info_dict["subtitles"]` vs `["automatic_captions"]` 判定字幕来源（B2 修订）
- [ ] 2.4 在 `src/extractors/audio_extractor.py` 自研 ffmpeg 音频抽取（一行命令：`-ar 16000 -ac 1 -c:a pcm_s16le`）
- [ ] 2.5 在 `src/extractors/metadata.py` 自研元数据提取：title / uploader / uploader_id（从 `uploader_url` 正则提取 sec_uid，B3 修订）/ duration / upload_date / thumbnail
- [ ] 2.6 在 `src/extractors/douk_fallback.py` 自研 DouK-Downloader 兜底（subprocess 调用）
- [ ] 2.7 添加 `src/extractors/__init__.py` 导出 `resolve_url`, `download_video`, `extract_subtitle`, `extract_metadata`
- [ ] 2.8 单元测试：投 1 条已知抖音短链（Jovi 提供样本），验证 resolve + download + 字幕判定成功

## 3. SQLite 队列与状态机（0.5 天）

- [ ] 3.1 在 `src/queue/schema.sql` 编写 task 表 schema（含 B4 `claimed_at` 字段 + 索引）
- [ ] 3.2 在 `src/queue/db.py` 实现 `init_db()`, `enqueue()`, `atomic_dequeue()`（B4 原子 UPDATE...RETURNING）
- [ ] 3.3 在 `src/queue/db.py` 实现 `reclaim_zombie_tasks()`（启动钩子：复活 `processing + claimed_at < now()-30min`）
- [ ] 3.4 在 `src/pipeline/state_machine.py` 实现状态机：pending → fetching → writing → done/failed（非法转移抛错）
- [ ] 3.5 单元测试：dequeue 并发场景模拟（M1 单 worker 无并发，但测试覆盖未来扩展）
- [ ] 3.6 单元测试：zombie 复活（手动改 `claimed_at` 为 1 小时前，调 reclaim 后验证回 pending）

## 4. FastAPI 服务（端口锁 8765，D-9）（0.5 天）

- [ ] 4.1 在 `src/bridge/main.py` 实现 `POST /ingest`（接收 `{source_url, force?}`，入队返回 `{task_id, status}`）
- [ ] 4.2 实现 `GET /tasks/{task_id}`（返回单任务状态 + 完成时 note_path）
- [ ] 4.3 实现 `GET /health`（返回 `{status, queue: {pending, processing, failed_today}}`）
- [ ] 4.4 实现 `GET /queue/stats`（详细队列统计）
- [ ] 4.5 重复检测：`/ingest` 入队前查 vault 是否已存在 `{video_id}.md`，若存在且 `force != true` 则返回 `{already_archived: true, note_path}` 不入队
- [ ] 4.6 启动钩子：调 `reclaim_zombie_tasks()` 后启动 uvicorn（host=127.0.0.1, port=8765）
- [ ] 4.7 集成测试：curl 调 `/ingest` → 验证任务入队 → 调度器消化 → 笔记落地

## 5. Obsidian 写入器（含 D-10 状态字段）（0.5 天）

- [ ] 5.1 在 `src/obsidian/frontmatter.py` 实现 frontmatter schema 拼装（按 specs/obsidian-archive-writer 规范，含 `summary_status`/`processing_mode`/`ai_summary_model` 3 个状态字段，D-10）
- [ ] 5.2 在 `src/obsidian/note_builder.py` 实现正文 5 段结构（摘要/字幕全文/关键帧/元数据/链接）
- [ ] 5.3 在 `src/obsidian/writer.py` 实现原子写入（`.md.tmp` + `os.rename`，见 specs D-7）
- [ ] 5.4 实现封面下载到 `attachments/douyin/{video_id}/cover.jpg` + frontmatter `local_cover_path`
- [ ] 5.5 实现路径计算 `inbox/douyin/{YYYY-MM}/{video_id}.md`（按"完成时刻"月份）
- [ ] 5.6 单元测试：写入一篇假笔记，验证 Obsidian 立即可见，DataView 查询能拉到
- [ ] 5.7 单元测试：写入失败时（mock 磁盘满）验证 `.tmp` 被删除，不留下半文件
- [ ] 5.8 单元测试：DataView `WHERE summary_status != "done"` 能正确过滤出 M1 笔记（D-10 防误判验证）

## 6. 调度器与 pipeline 编排（0.5 天）

- [ ] 6.1 在 `src/pipeline/scheduler.py` 实现单 worker `run_forever()` 循环：dequeue → process → mark done/failed
- [ ] 6.2 实现 `process_task(task)` 编排：fetching 阶段（douyin_resolver + downloader + 字幕判定）→ writing 阶段（frontmatter + writer）
- [ ] 6.3 实现错误分类：`no_subtitle_in_m1` / `download_failed_all_tools` / `cookie_expired` / `incomplete_frontmatter`
- [ ] 6.4 实现 correlation_id 生成（UUID v4）+ 贯穿所有日志
- [ ] 6.5 实现视频临时文件清理（笔记写入成功后删 .mp4 / .vtt）
- [ ] 6.6 实现 cookie 探活（启动时 + 下载失败时）
- [ ] 6.7 实现 DouK-Downloader 兜底（yt-dlp 失败重试 3 次后切换）

## 7. 日志与可观测性（0.25 天）

- [ ] 7.1 配置 structlog：JSON 格式 + correlation_id 注入
- [ ] 7.2 日志路径 `logs/{module}/{YYYY-MM-DD}.log`，按日 rotate
- [ ] 7.3 关键事件埋点：消息到达、抓取失败、写入成功、cookie 探活结果
- [ ] 7.4 单元测试：grep 一个 correlation_id 能取出完整管线日志

## 8. Git 冷备（0.25 天）

```

Full source: openspec/changes/m1-douyin-archive-mvp/tasks.md

## openspec/changes/m1-douyin-archive-mvp/specs/bishu-feishu-bridge/spec.md

- Source: openspec/changes/m1-douyin-archive-mvp/specs/bishu-feishu-bridge/spec.md
- Lines: 1-120
- SHA256: 27fcca947e57b657668a43e7d8a9d78a86b20a37fff5f3f9b97cf53edf750dd2

[TRUNCATED]

```md
## ADDED Requirements

### Requirement: bishu agent 路由触发

`bishu` agent（在 openclaw 的 12 agent 体系内新增第 13 位）SHALL 在飞书消息含以下任一关键词时被 `main (JJ_bot)` 路由触发：

- `v.douyin.com`
- `iesdouyin.com`
- `www.douyin.com/video/`
- `www.douyin.com/note/`
- 整段分享文案匹配 `9\.\d+.*https?://` 模式

#### Scenario: 标准短链触发

- **WHEN** 用户在飞书私聊机器人发 `https://v.douyin.com/iAbCdEf/`
- **THEN** main 路由规则匹配，转发给 bishu 处理，其他 11 个 agent 不被触发

#### Scenario: 非抖音 URL 不触发

- **WHEN** 用户发 `https://www.bilibili.com/video/BVxxx`
- **THEN** bishu **不**被触发，消息按原有逻辑走其他 agent

#### Scenario: 混合文案触发

- **WHEN** 用户发 `"9.99 复制打开抖音，看看【作者】的作品 https://v.douyin.com/iAbCdEf/ 🔥"`
- **THEN** bishu 被触发，并能从混合文案中提取出短链

### Requirement: 飞书 5 秒响应窗口处理

bishu SHALL 在收到消息后 ≤ 5 秒内通过飞书事件订阅的"被动回复"通道发回一条确认消息，避免飞书平台超时判定失败。

#### Scenario: 立即被动回复

- **WHEN** bishu 收到抖音 URL
- **THEN** ≤ 5 秒内向用户回复"已收到抖音链接，开始处理：{URL 截短}；任务 ID: {task_id}；处理完成后会主动通知"

#### Scenario: 5 秒响应失败

- **WHEN** bishu 在 5 秒内未能完成被动回复（如 openclaw 启动慢）
- **THEN** 飞书平台会判定事件超时并重试；bishu SHALL 在重试事件中识别 `X-Lark-Request-Id` 幂等性，不重复入队

### Requirement: 异步入队 + 异步回执

bishu SHALL 通过 HTTP POST `127.0.0.1:8765/ingest` 把任务入解析服务队列，拿回 `task_id`，然后**异步**轮询 `GET /tasks/{task_id}` 直至 `status` 进入终态（`done` 或 `failed`），再用飞书主动发消息 API 推送最终结果。

#### Scenario: 入队成功

- **WHEN** bishu 调用 `POST /ingest`
- **THEN** 解析服务返回 `{"task_id": "...", "status": "pending"}`，bishu 开始轮询

#### Scenario: 轮询指数退避

- **WHEN** bishu 开始轮询
- **THEN** 轮询间隔 = 1s, 3s, 10s, 30s, 60s, 60s, 60s（最多 5 分钟），任一轮询拿到终态则立即停止

#### Scenario: 5 分钟超时

- **WHEN** 5 分钟内 bishu 未拿到终态
- **THEN** bishu 主动发飞书消息"任务仍在处理中，已超 5 分钟，请稍后查看 vault 或手动重启解析服务"，但不取消任务（解析服务仍继续）

### Requirement: tenant_access_token 缓存与刷新

bishu SHALL 缓存飞书 `tenant_access_token`，过期前 60 秒自动刷新，确保异步回执能调用 `POST /open-apis/im/v1/messages`。

#### Scenario: 缓存命中

- **WHEN** bishu 调用主动发消息 API 且缓存未过期
- **THEN** 直接复用缓存 token，不发新的 token 请求

#### Scenario: 过期前 60 秒刷新

- **WHEN** 缓存剩余有效期 < 60 秒
- **THEN** 在下次发消息前自动调 `POST /open-apis/auth/v3/tenant_access_token/internal` 刷新，更新缓存

#### Scenario: token 获取失败

- **WHEN** 刷新 token 失败（app_secret 错误 / 网络异常）
- **THEN** 日志告警，飞书回执失败；任务仍在解析服务内正常运行（不阻塞），只是用户收不到"完成"通知

### Requirement: 错误回执
```

Full source: openspec/changes/m1-douyin-archive-mvp/specs/bishu-feishu-bridge/spec.md

## openspec/changes/m1-douyin-archive-mvp/specs/douyin-extraction/spec.md

- Source: openspec/changes/m1-douyin-archive-mvp/specs/douyin-extraction/spec.md
- Lines: 1-116
- SHA256: df62fe82178fb75cd765a120dfbcfd259ea346ce48d01a83a9608dae376b388e

[TRUNCATED]

```md
## ADDED Requirements

### Requirement: 接受多种抖音 URL 形态

系统 SHALL 接受以下 4 种输入形态并解析为标准 video_id + 完整 URL：

1. 短链 `https://v.douyin.com/{token}/`（需 302 跟随）
2. 完整链 `https://www.douyin.com/video/{video_id}`
3. 旧链 `https://www.iesdouyin.com/share/video/{video_id}`
4. 整段分享文案（含口令 + emoji + URL 的混合文本）

#### Scenario: 短链解析

- **WHEN** 解析服务收到 `https://v.douyin.com/iAbCdEf/`
- **THEN** 系统 302 跟随后得到完整 URL，并提取 `video_id`，返回 `{"video_id": ..., "canonical_url": ..., "source_url_type": "short"}`

#### Scenario: 分享文案解析

- **WHEN** 解析服务收到 `"9.99 复制打开抖音，看看【作者】的作品 https://v.douyin.com/iAbCdEf/ 🔥"`
- **THEN** 系统提取 URL 后按短链流程解析，忽略 emoji 与口令

#### Scenario: 非抖音 URL

- **WHEN** 解析服务收到 `https://www.bilibili.com/video/BVxxx`
- **THEN** 返回 `{"error": "not_douyin_url", "supported": false}`，不入队

### Requirement: yt-dlp 主路径下载

系统 SHALL 使用 yt-dlp 作为主下载工具，输出视频文件 + 字幕文件到任务临时目录。

#### Scenario: 带原生字幕视频

- **WHEN** 处理一条带抖音原生 CC 字幕的知识视频
- **THEN** 系统产出 `<video_id>.mp4` 和 `<video_id>.zh.vtt`（或同前缀 srt）两个文件，并标记 `subtitle_source = "douyin_native"`

#### Scenario: 无字幕视频（M1 边界）

- **WHEN** 处理一条无字幕视频（直播切片/纯音乐视频）
- **THEN** 系统产出 `<video_id>.mp4` 但**不**进入 Whisper 兜底（M1 不支持），任务状态置 `failed`，错误码 `no_subtitle_in_m1`，bishu agent 飞书回"该视频无字幕，M1 暂不支持，将推到 M2 自动处理"

### Requirement: 字幕来源判定

系统 SHALL 通过 yt-dlp 的 `info_dict["subtitles"]` vs `info_dict["automatic_captions"]` 两个 dict 判定字幕来源，**不**靠文件名扩展名区分（B2 修订）。

#### Scenario: 创作者上传字幕

- **WHEN** `info_dict["subtitles"]["zh"]` 存在
- **THEN** 标记 `subtitle_source = "creator_uploaded"`

#### Scenario: 平台自动字幕

- **WHEN** `info_dict["automatic_captions"]["zh"]` 存在但 `subtitles` 无 zh
- **THEN** 标记 `subtitle_source = "auto_generated"`

### Requirement: 视频元数据提取

系统 SHALL 从 yt-dlp info_dict 提取以下元数据：

- `title`（视频标题）
- `uploader`（作者昵称）
- `uploader_id`（从 `uploader_url` 正则提取 `sec_uid`，**不**用不存在的 `author_uid` 字段，B3 修订）
- `duration`（秒）
- `upload_date`（YYYYMMDD）
- `thumbnail`（封面 URL）

#### Scenario: 完整元数据

- **WHEN** 处理一条正常抖音视频
- **THEN** 元数据全部成功提取，写入 frontmatter 的 `title` / `author` / `uploader_id` / `duration_seconds` / `uploaded_at` / `cover_url` 字段

#### Scenario: uploader_id 提取失败

- **WHEN** `uploader_url` 不含 `/user/` 路径或正则不匹配
- **THEN** `uploader_id` 留空字符串 `""`，任务不失败，frontmatter 该字段值 `""`

### Requirement: yt-dlp 失败兜底走 DouK-Downloader

系统 SHALL 在 yt-dlp 主路径失败（非 4xx 重试或网络异常）时，调用 DouK-Downloader 作为备选下载工具。

#### Scenario: yt-dlp 失败 → DouK 成功
```

Full source: openspec/changes/m1-douyin-archive-mvp/specs/douyin-extraction/spec.md

## openspec/changes/m1-douyin-archive-mvp/specs/git-cold-backup/spec.md

- Source: openspec/changes/m1-douyin-archive-mvp/specs/git-cold-backup/spec.md
- Lines: 1-111
- SHA256: c71001cff3792aa7a20250308f240478e17d697cfa54382ef84919d40e725887

[TRUNCATED]

```md
## ADDED Requirements

### Requirement: vault Git 仓库初始化

系统 SHALL 在 `vault_root` 目录 `git init`，配置默认 user.name/email，提交首条 commit "init: 初始化 Obsidian vault"。

#### Scenario: 首次初始化

- **WHEN** 实施 git-cold-backup 模块时
- **THEN** vault 目录变成 git 仓库，首条 commit 包含除 `.gitignore` 屏蔽外的所有现有文件

### Requirement: .gitignore 屏蔽规则

`vault_root/.gitignore` SHALL 包含以下条目，确保敏感数据与运行时文件不进 Git：

```
# Obsidian 运行时
.obsidian/workspace*
.obsidian/cache/
.obsidian/plugins/*/data.json
.trash/

# 同步冲突
.sync-conflict-*
*.tmp

# 凭证（绝不能进版本控制）
.env
cookies.txt
secrets/
*.key

# 大附件（>50MB 不进 Git，由 Syncthing/iCloud 处理）
attachments/**/*.mp4
attachments/**/*.webm
attachments/**/full-video.*
```

#### Scenario: 屏蔽生效

- **WHEN** 笔记写入 vault
- **THEN** 笔记 `.md` 文件被 git 追踪；`cookies.txt` / `.env` / `*.mp4` 不被追踪

#### Scenario: 不屏蔽 frontmatter 必需字段

- **WHEN** frontmatter `cover_url` 含外部 URL
- **THEN** 该字段值作为字符串存在 `.md` 里，被 git 追踪（不是凭证）

### Requirement: 自动 commit + push 任务计划

系统 SHALL 通过 Windows 任务计划程序注册一个每日定时任务 `douyin-vault-git-backup`，每天 03:00（避开非高峰期）执行：

```powershell
cd E:\AI_Tools\Obsidian\data\notes-personal
git add .
git commit -m "auto: vault backup $(date)"
# push 最多重试 3 次，失败时日志告警但不阻塞下次执行
for i in 1..3 { git push origin main; if ($?) { break } }
```

#### Scenario: 定时执行

- **WHEN** 每天 03:00 触发
- **THEN** 如有未提交变更则 commit + push；无变更则跳过

#### Scenario: push 失败重试

- **WHEN** 首次 push 失败（网络问题）
- **THEN** 重试最多 3 次（间隔 5s），仍失败则记录到 `logs/git-backup/{date}.log`，不阻塞下次执行

### Requirement: 远程仓库地址配置

`vault_root/.git/config` SHALL 配置 `remote.origin.url` 指向 Jovi 选择的私有仓库（GitHub Private 或 Gitee 私仓）。

#### Scenario: 远程仓库就绪

- **WHEN** Jovi 决定仓库地址后（OQ-4 开放问题）
- **THEN** 通过 `git remote add origin <url>` 配置；`git push -u origin main` 首次成功

#### Scenario: 未配置远程仓库时降级
```

Full source: openspec/changes/m1-douyin-archive-mvp/specs/git-cold-backup/spec.md

## openspec/changes/m1-douyin-archive-mvp/specs/obsidian-archive-writer/spec.md

- Source: openspec/changes/m1-douyin-archive-mvp/specs/obsidian-archive-writer/spec.md
- Lines: 1-129
- SHA256: 6f287cae97ac1fb7492a26d296fb45c3552cbce9f34179bce503b9aad818d5ed

[TRUNCATED]

```md
## ADDED Requirements

### Requirement: frontmatter schema

每条抖音笔记 SHALL 包含以下 frontmatter 字段（YAML list 写 tags，时间用 ISO 8601，长内容入正文不入 frontmatter，snake_case 命名以兼容 DataView）：

```yaml
---
title: <string>
video_id: <string>
source_url: <string>
source_url_type: short | full | iesdouyin | share_text
author: <string>
uploader_id: <string>
duration_seconds: <int>
uploaded_at: <ISO 8601>
captured_at: <ISO 8601>
cover_url: <string>
local_cover_path: <relative path to vault root>
tags:
  - douyin
  - <auto-or-manual>
subtitle_source: douyin_native | creator_uploaded | auto_generated | whisper_local | mimo_asr
subtitle_language: zh | en | <other>
pipeline_version: "1.0"
status: pending | fetching | writing | done | failed
downloader_used: ytdlp | douk
correlation_id: <uuid>
# 状态字段（D-10 修订，避免 Dataview 误判）
summary_status: not_run | pending | done | failed
processing_mode: subtitle_only | subtitle_whisper | subtitle_vlm | full
ai_summary_model: null | "mimo-v2.5-pro" | "qwen2.5-72b" | "glm-4.5-air" | <other>
# 以下字段 M1 占位为空，M2/M3 填充
transcript_full: ""        # 已迁移到正文（不放 frontmatter）
summary: ""
vlm_results: []
---
```

#### Scenario: M1 完整 frontmatter

- **WHEN** 处理一条带原生字幕的抖音视频并成功入库
- **THEN** frontmatter 含上述全部字段；`subtitle_source ∈ {douyin_native, creator_uploaded, auto_generated}`，`summary = ""`，`vlm_results = []`，`pipeline_version = "1.0"`，`summary_status = "not_run"`，`processing_mode = "subtitle_only"`，`ai_summary_model = null`

#### Scenario: 字段不可缺失

- **WHEN** 写入时任何 SHALL 字段缺失（如 `correlation_id` 未生成）
- **THEN** 任务状态置 `failed`，错误码 `incomplete_frontmatter`，不写入半成品笔记

#### Scenario: 状态字段防误判（D-10 新增）

- **WHEN** M1 阶段写入笔记后，Dataview 查询 `WHERE summary_status != "done"` 过滤
- **THEN** 该笔记出现在结果集（因 `summary_status = "not_run"`），表明"待 M3 总结"；避免被旧 schema 的 `summary = ""` 误判为"已总结但空"

### Requirement: vault 路径计算

系统 SHALL 按以下规则计算笔记文件路径：

- 笔记：`{vault_root}/inbox/douyin/{YYYY-MM}/{video_id}.md`
- 附件：`{vault_root}/attachments/douyin/{video_id}/{filename}`

`vault_root` 来自 `config.yaml`，M1 锁定 `E:\AI_Tools\Obsidian\data\notes-personal`（DECISIONS A6）。

#### Scenario: 标准路径

- **WHEN** 处理 video_id = `7234567890123` 的视频，捕获时间 2026-06-19
- **THEN** 笔记路径 = `E:\AI_Tools\Obsidian\data\notes-personal\inbox\douyin\2026-06\7234567890123.md`，封面附件目录 = `E:\AI_Tools\Obsidian\data\notes-personal\attachments\douyin\7234567890123\`

#### Scenario: 跨月写入

- **WHEN** 6 月 30 日 23:59 触发任务，7 月 1 日 00:01 完成入库
- **THEN** 文件路径按"完成时刻"的月份计算 = `inbox/douyin/2026-07/...`（笔记是产物，按生成时刻归档，不按源视频发布时间）

### Requirement: 原子写入

系统 SHALL 先写入 `.tmp` 临时文件，再 `os.rename` 为最终文件名，确保 Syncthing / Obsidian 文件系统监听不会读到半文件。

#### Scenario: 正常流程

- **WHEN** 写笔记
```

Full source: openspec/changes/m1-douyin-archive-mvp/specs/obsidian-archive-writer/spec.md

## openspec/changes/m1-douyin-archive-mvp/specs/task-queue-pipeline/spec.md

- Source: openspec/changes/m1-douyin-archive-mvp/specs/task-queue-pipeline/spec.md
- Lines: 1-132
- SHA256: a42a34af4cfbbf5166e2c6a4c83a84f8278a4a7aef25d6bdce3a22fb4cfadc62

[TRUNCATED]

```md
## ADDED Requirements

### Requirement: 任务状态机

任务 SHALL 经历以下状态，转移规则严格按状态机定义：

```
pending → fetching → writing → done
            ↓           ↓
          failed      failed
```

非法转移（如 `done → pending`）SHALL 拒绝并记录错误。

#### Scenario: 主路径成功

- **WHEN** 任务从 `pending` 进入 `fetching` → 进入 `writing` → 进入 `done`
- **THEN** 笔记已写入 vault，临时文件已清理，bishu 收到 `done` 终态

#### Scenario: 任一阶段失败

- **WHEN** `fetching` 或 `writing` 阶段抛异常
- **THEN** 任务状态置 `failed`，错误码 + 错误信息持久化到任务记录，**不**自动重试（M1 重试由 bishu 飞书提示用户手动重发）

### Requirement: SQLite 队列 schema（含 B4 claimed_at）

任务表 SHALL 包含以下字段：

```sql
CREATE TABLE task (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id TEXT NOT NULL,
  source_url TEXT NOT NULL,
  source_url_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  claimed_at TIMESTAMP NULL,             -- B4 修订：占用标记
  error_code TEXT NULL,
  error_message TEXT NULL,
  correlation_id TEXT NOT NULL,          -- 串起整条管线日志
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  payload_json TEXT NOT NULL             -- 元数据/字幕全文等
);
CREATE INDEX idx_task_status_claimed ON task(status, claimed_at);
```

#### Scenario: 新任务入队

- **WHEN** bishu `POST /ingest` 推入一条新 URL
- **THEN** 任务以 `status=pending, claimed_at=NULL` 入表，返回 `task_id`

#### Scenario: 字段约束

- **WHEN** 任何 `NOT NULL` 字段缺失
- **THEN** 数据库拒绝插入，错误冒泡到 bishu

### Requirement: 原子 dequeue（B4 修订）

dequeue SHALL 通过单条 SQL 完成"挑选 + 占用 + 状态切换"，避免并发竞态：

```sql
UPDATE task
SET claimed_at = CURRENT_TIMESTAMP, status = 'processing', updated_at = CURRENT_TIMESTAMP
WHERE id = (
  SELECT id FROM task
  WHERE status = 'pending' AND claimed_at IS NULL
  ORDER BY id LIMIT 1
)
RETURNING *;
```

#### Scenario: 单 worker dequeue

- **WHEN** 调度器空闲且队列有 pending 任务
- **THEN** 上述 SQL 返回单条任务，`status='processing', claimed_at=now()`

#### Scenario: 队列为空

- **WHEN** 队列无 pending 任务
- **THEN** 返回空，调度器空转睡眠 5s 再试
```

Full source: openspec/changes/m1-douyin-archive-mvp/specs/task-queue-pipeline/spec.md

