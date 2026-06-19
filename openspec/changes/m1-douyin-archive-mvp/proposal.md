## Why

Jovi 在手机刷抖音时遇到的知识类视频，目前没有一条自动化路径把"链接 + 视频内容"沉淀到 Obsidian。已搭好 `飞书自建机器人 → openclaw（Node 24 本地服务）` 通道，但 **openclaw → 解析 → Obsidian** 这一段缺失——M1 就补这一段，端到端跑通"分享链接到笔记入库"的最小闭环。

> 完整背景、用户故事与功能矩阵见 `docs/claude/PRD.md` v1.1（2026-06-19，已通过 Codex 反向审核）；本文件不复述。

## What Changes

M1 是抖音归档管线的最小可用版本，**只走"抖音原生字幕"主路径**，不引入本地 ASR、不做视觉理解、不做 LLM 总结、不做手机同步——这些在 m2/m3/m4 处理。

- 新增本地解析服务（FastAPI on `127.0.0.1:8765`）：接收抖音分享 URL → 调用 yt-dlp + 抖音原生字幕抓取 → 生成 Obsidian frontmatter markdown 直写入 vault
- 新增 `bishu` agent（在 openclaw 的 12 agent 体系内新增第 13 位）：飞书消息触发、5 秒响应窗口处理、异步状态回执
- 新增 SQLite 任务队列（含 B4 修订：`claimed_at` 原子占用 + 启动复活超时任务）防止崩溃后重复处理
- 新增 Git 冷备（每日 cron 自动 commit + push 到私有仓库）作为 M1 唯一同步层
- **参考**（不 vendoring）`git_ref/obsidian-content-capture-backend/` 的解析思路自研 `src/extractors/`：build 前核验发现该仓库**无 OSS license**（仅"仅供学习与研究"），vendoring 复用代码有侵权风险，故仅阅读参考思路、自研最小 extractor（见 design D-3 v2）
- M1 验收标准：分享一条带原生字幕的抖音知识视频，**≤ 2 分钟**内 vault 出现完整笔记（frontmatter + 字幕全文 + 封面），飞书机器人回"已归档 + 路径"

**不做（明确推迟到后续 change）**：
- Whisper 兜底转写（→ m2-whisper-fallback）
- 关键帧 OCR + Qwen2.5-VL 视觉理解（→ m3-vision-llm-summary）
- LLM 总结（→ m3-vision-llm-summary）
- iOS / Android 同步、监控告警（→ m4-robustness-sync）

## Capabilities

### New Capabilities

- `douyin-extraction`: 抖音 share URL 解析（v.douyin.com 短链 / iesdouyin / 完整 URL）、yt-dlp 主路径下载、抖音原生字幕优先抽取、视频元数据提取（标题/作者/uploader_id/封面/时长）。**自研**，仅参考 `git_ref/obsidian-content-capture-backend/` 的解析思路（不 vendoring）。
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
