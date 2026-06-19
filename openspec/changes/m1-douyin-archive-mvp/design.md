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
2. **自研 extractor**（D-3 v2 修订）：不 vendoring community backend（无 OSS license），仅参考其解析思路自研 `src/extractors/`，避免侵权风险
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
- ~~Vendoring 复用 backend/script/~~：无 OSS license，存在侵权风险
- 联系作者 lyxdream 申请许可：build 阶段不能等
- 用 yt-dlp 完全替代（不写自己的 resolver）：可行但失去"分享文案解析"等场景的灵活性（M1 暂保留自研 resolver）

**仍保留 git_ref/obsidian-content-capture-backend/** 作为：M2 Whisper 集成时的对照实现 + 学习参考，不复制代码到 `src/`。

### D-4：SQLite 队列含 B4 修订（`claimed_at` + 启动复活）

**Why**：`docs/claude/verify/T9-review.md` B4 阻塞项 + Codex CLAUDE_REVIEW R2 强调"重启追赶 ≠ 网络追赶"，是两个独立测试。

**Rationale**：
- `claimed_at` 字段做原子占用标记，dequeue 用 `UPDATE ... WHERE id=(SELECT...) RETURNING *` 单条 SQL 完成"挑选 + 占用 + 状态切换"
- 启动钩子扫一遍 `WHERE status IN ('fetching', 'writing') AND claimed_at < now() - 30min`，全部重置回 pending（zombie 复活，v2 修订：删除 processing 状态）
- 同时支持"网络故障恢复"（消息根本没到 → openclaw 自己处理）+"进程崩溃恢复"（消息到了 pending 卡住 → 启动复活）

### D-5：frontmatter schema 含 M2/M3 字段占位

**Why**：避免 M2/M3 启用后再改 schema 触发 vault 历史笔记迁移。

**Rationale**：
- `subtitle_source: "douyin_native" | "whisper_local" | "mimo_asr"`（M1 仅 douyin_native，但字段位先占）
- `summary: ""`（M1 留空，M3 填充）
- `vlm_results: []`（M1 空数组，M3 填充）
- `pipeline_version: "1.0"`（M1 起步版本，每个里程碑递增）

完整 schema 见 `docs/claude/PRD.md §6` + `docs/claude/EXECUTION.md §10.1`。

### D-6：bishu agent 在 M1 阶段只做"路由 + 入队 + 回执"

**Why**：bishu 不做 LLM 调用（D-2）、不做重计算，职责最小化。

**bishu 在 M1 的逻辑**：
1. 飞书消息触发 → 抽 URL（含 v.douyin.com / iesdouyin / 整段分享文案）
2. 立即被动回复"已收到，开始处理"（5 秒响应窗口内）
3. 异步 HTTP POST `127.0.0.1:8765/ingest`，拿 task_id
4. 轮询 `GET /tasks/{task_id}`（或解析服务回调 bishu，二选一，待 D-8 决定）
5. 完成时主动发飞书消息"已归档：{vault 路径}"或"失败：{原因}"

### D-7：vault 写入用"原子 rename"（B5 风格）

**Why**：Syncthing/Obsidian 都监听文件系统，半文件被读到会出问题。

**实现**：先写 `{video_id}.md.tmp`，写完 `os.rename` 到 `{video_id}.md`。Windows 上 `os.rename` 是原子的（同卷）。

### D-8：解析服务通知 bishu 完成 = bishu 轮询 `GET /tasks/{id}`

**Why**：避免解析服务持有飞书 token 反向调用 openclaw（增加耦合 + 凭证管理复杂度）。

**Rationale**：
- bishu 入队后开始 backoff 轮询：1s / 3s / 10s / 30s / 60s / 60s ...
- 解析服务对外仅 HTTP，不持任何凭证
- 飞书回执完全由 bishu 一处控制

**Alternative rejected**：
- 解析服务回调 bishu/openclaw：要求解析服务持飞书凭证或反向 RPC，复杂度爆炸

### D-9：端口统一为 8765（**新增**）

**Why**：早期 `docs/codex/EXECUTION.md` 用 18900，新 OpenSpec `docs/claude/DECISIONS.md` D1 用 8765，两套文档并存易引误。Jovi 拍板按 OpenSpec 用 **8765**。

**Action**：build 前把 `docs/claude/EXECUTION.md` 与 `docs/codex/EXECUTION.md` 全局 `18900` → `8765` 替换（共 ~13 处）；`config.example.yaml` 锁 `port: 8765`。

**Rationale**：
- 8765 是 DECISIONS D1 已确认的权威值，与 OpenSpec 5 份 spec 一致
- 18900 是早期 executor agent 推测值，无外部约束力

### D-10：frontmatter 加状态字段防 DataView 误判（**新增**）

**Why**：Jovi 指出 `summary: ""` / `vlm_results: []` 容易被 DataView/脚本误判为"已总结但内容为空"。需要显式状态字段区分"未跑"vs"已跑但空"。

**Rationale**：Dataview 按 frontmatter 字段值过滤时，`summary = ""` 与 `summary` 字段缺失行为不同；引入枚举字段更清晰。

**新增 3 字段**（写入 `specs/obsidian-archive-writer/spec.md` frontmatter schema）：

```yaml
summary_status: not_run | pending | done | failed      # M1 全部 not_run
processing_mode: subtitle_only | subtitle_whisper | subtitle_vlm | full   # M1 全部 subtitle_only
ai_summary_model: null | "mimo-v2.5-pro" | "qwen2.5-72b" | ...  # M1 全部 null
```

**M1 默认值**：`summary_status=not_run, processing_mode=subtitle_only, ai_summary_model=null`。

**Scenario 示例**：
- M1 笔记：`summary_status=not_run, summary=""` → DataView 可过滤 `where summary_status != "done"` 找出"待 M3 总结"的笔记
- M3 笔记：`summary_status=done, summary="<3-5要点>", ai_summary_model="mimo-v2.5-pro"`

## Risks / Trade-offs

| Risk | 缓解 |
|------|------|
| **抖音反爬变化导致 yt-dlp 失败** | DouK-Downloader 兜底；启动时 cookie 探活检查；失败时 bishu 飞书提示 "cookie 过期"，不静默失败 |
| ~~复用 `obsidian-content-capture-backend` 的代码 license/上游变更风险~~ | ✅ 已规避：v2 决定不 vendoring，仅参考思路自研（D-3） |
| **B4 `claimed_at` SQL 在并发场景下的行锁** | M1 单 worker 串行无并发；M2+ 加并发时再切到 `BEGIN IMMEDIATE` 事务 |
| **vault 物理路径含中文不会但有空格 / 特殊字符** | 路径配置在 `config.yaml`，全程 `os.path.join` + UTF-8，单测覆盖 |
| **bishu 轮询频率过高浪费请求** | 指数退避 1/3/10/30/60s，最多 5 分钟（短视频处理超 5 分钟极少见） |
| **openclaw 不支持新增 agent / agent 配置 schema 不公开** | M1 启动前 Jovi 提供一份现有 agent（如 taizi）配置作样板（DECISIONS Q3 已答） |
| **文件系统 Watcher 在大量写入时 reload 抖动** | M1 单条处理，写入频率低；M3+ 批量场景再加节流 |
| **Git 自动 commit 内容含敏感数据** | `.gitignore` 屏蔽 `.env` / cookies.txt / `secrets/`；CI lint 规则待 M4 引入 |

## Migration Plan

M1 是首个 change，**无既有系统迁移**。部署步骤：

1. 安装依赖（`uv sync` 或 `pip install -r requirements.txt`），约 30 个依赖（不含 torch）
2. 参考 `git_ref/obsidian-content-capture-backend/` 解析思路自研 `src/extractors/`（**不复制代码**，仅阅读参考）
3. 创建 `config.yaml` + `.env`（占位 + 真实凭证）
4. 初始化 SQLite 队列：`alembic upgrade head` 或一次性 `init_db()`
5. 启动解析服务：`uvicorn src.bridge.main:app --host 127.0.0.1 --port 8765`
6. Jovi 在 openclaw UI 新建 bishu agent（lead 提供配置模板）
7. 飞书发一条带原生字幕的抖音视频，验证端到端

**回滚**：删除 `src/`、SQLite 文件、vault 中 `inbox/douyin/` 即可，无副作用。

## Open Questions

| ID | 问题 | 解决时机 | 状态 |
|----|------|---------|------|
| OQ-1 | bishu agent 在 openclaw 内的具体配置 schema（YAML/JSON 字段名） | **build 前**（Jovi 提供 1 个现有 agent 样板） | ⚠️ **BLOCKER**：未解决前不能宣称"飞书端到端"完成；可先做 curl → FastAPI → pipeline → vault 闭环 |
| OQ-2 | ~~`obsidian-content-capture-backend` 的 license~~ | – | ✅ **已关闭**：仓库无 OSS license，决定不 vendoring，仅借鉴思路自研（见 D-3 修订） |
| OQ-3 | M1 阶段是否需要 cookies.txt（默认参考项目说不需要，但抖音 2026 反爬变化频繁） | tasks.md §6.6 cookie 探活实测时确认 | 待 build 阶段实测 |
| OQ-4 | Git 私有仓库地址（GitHub Private 还是 Gitee 私仓？SSH 还是 HTTPS？） | tasks.md §8.3 实施 git-cold-backup 时由 Jovi 决定 | 待 build 阶段 |
| OQ-5 | 端口统一（18900 vs 8765） | – | ✅ **已关闭**：拍板 8765（见 D-9） |
