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
- [ ] 3.3 在 `src/queue/db.py` 实现 `reclaim_zombie_tasks()`（启动钩子：复活 `fetching/writing + claimed_at < now()-30min`）
- [ ] 3.4 在 `src/pipeline/state_machine.py` 实现状态机：pending → fetching → writing → done/failed（非法转移抛错）
- [ ] 3.5 单元测试：dequeue 并发场景模拟（M1 单 worker 无并发，但测试覆盖未来扩展）
- [ ] 3.6 单元测试：zombie 复活（手动改 `claimed_at` 为 1 小时前，调 reclaim 后验证回 pending）

## 4. FastAPI 服务（端口锁 8765，D-9）（0.5 天）

- [ ] 4.1 在 `src/bridge/main.py` 实现 `POST /ingest`（接收 `{source_url, force?}`，入队返回 `{task_id, status}`）
- [ ] 4.2 实现 `GET /tasks/{task_id}`（返回单任务状态 + 完成时 note_path）
- [ ] 4.3 实现 `GET /health`（返回 `{status, queue: {pending, fetching, writing, failed_today, done_today}}`）
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

- [ ] 8.1 在 vault 根目录 `git init` + 首条 commit "init: 初始化 Obsidian vault"
- [ ] 8.2 写 `vault_root/.gitignore`（按 specs/git-cold-backup 规范）
- [ ] 8.3 Jovi 决定远程仓库地址（OQ-4），配置 `git remote add origin <url>`（暂未决定则跳过 push）
- [ ] 8.4 写 `scripts/git-backup.ps1`（add + commit + push 重试 3 次）
- [ ] 8.5 注册 Windows 任务计划程序 `douyin-vault-git-backup` 每天 03:00 触发
- [ ] 8.6 验证：手动改一条笔记 → 跑 ps1 → 远程仓库（如有）出现新 commit

---

## ⚠️ 以下任务组 blocked by OQ-1（bishu agent schema）

> Jovi 提供现有 agent（如 taizi）的配置样板后，§9-§11.B 才可启动。
> §11.A 不依赖 bishu，可在 OQ-1 解决前先跑。

## 9. bishu agent 配置模板（0.25 天，**Jovi 配合**）

- [ ] 9.1 ⚠️ Jovi 提供 1 个现有 agent（如 `taizi`）的配置作 schema 样板（OQ-1，**BLOCKER**）
- [ ] 9.2 在 `docs/m1/bishu_agent_template.json`（或 .yaml 视 schema 而定）编写 bishu 注册配置
- [ ] 9.3 配置含：id=bishu, 中文名=秘书省, model=mimo-v2.5-pro, 飞书账号 oc_516376df9cc2315fc12470e56e72c4af, 触发条件含 douyin.com
- [ ] 9.4 在模板中附 bishu 的 systemPrompt（M1 职责：URL 抽取 + HTTP POST + 轮询 + 飞书回执）
- [ ] 9.5 Jovi 在 openclaw UI 用模板新建 bishu agent，重启 openclaw
- [ ] 9.6 验证 bishu 注册成功：飞书发一条非抖音消息（如"你好"）确认 bishu 不被错误触发

## 10. bishu agent 端逻辑（0.5 天）

- [ ] 10.1 实现 bishu 端 URL 抽取（短链/完整链/iesdouyin/分享文案 4 种形态）
- [ ] 10.2 实现 5 秒响应窗口被动回复"已收到，开始处理"
- [ ] 10.3 实现 `POST 127.0.0.1:8765/ingest` 调用，拿 task_id
- [ ] 10.4 实现轮询 `GET /tasks/{id}` 指数退避（1s/3s/10s/30s/60s/60s/60s）
- [ ] 10.5 实现 tenant_access_token 缓存与 60 秒前刷新
- [ ] 10.6 实现飞书主动发消息 API（`POST /open-apis/im/v1/messages`）
- [ ] 10.7 实现错误回执（按 error_code 翻译为人类可读飞书消息）
- [ ] 10.8 实现 5 分钟超时回执"任务仍在处理中"

## 11. 端到端集成测试（0.5 天）

### 11.A 不依赖 bishu（OQ-1 解决前可跑）

- [ ] 11.A.1 测试场景 1：curl `POST /ingest` 一条**带原生字幕**视频 → ≤ 2 分钟 vault 出现完整笔记 + `GET /tasks/{id}` 返回 done
- [ ] 11.A.2 测试场景 2：curl `POST /ingest` 一条**无字幕**视频 → ≤ 30 秒 `GET /tasks/{id}` 返回 failed + `error_code = "no_subtitle_in_m1"`
- [ ] 11.A.3 测试场景 3：curl 同 URL 两次（不带 force） → 第二次 `/ingest` 返回 `{already_archived: true}`
- [ ] 11.A.4 测试场景 4：解析服务进程崩溃后重启 → pending 任务自动消化（B4 zombie 复活）
- [ ] 11.A.5 测试场景 5：cookie 过期模拟（用错误 cookies.txt） → 任务 failed + `error_code = "cookie_expired"`
- [ ] 11.A.6 测试场景 6：网络断开 30 秒后恢复 → 后续 curl `/ingest` 能正常入队处理
- [ ] 11.A.7 性能基准：5 条带字幕视频串行处理，平均端到端 ≤ 2 分钟/条

### 11.B 飞书端到端（**blocked by OQ-1**，bishu agent 注册后才能跑）

- [ ] 11.B.1 测试场景 1：飞书发一条带原生字幕视频 → ≤ 2 分钟 vault 出现完整笔记 + 飞书回执"已归档"
- [ ] 11.B.2 测试场景 2：飞书发一条无字幕视频 → ≤ 30 秒 bishu 飞书回"该视频无字幕，M1 阶段暂不支持"
- [ ] 11.B.3 测试场景 3：飞书发同一条 URL 两次 → 第二次 bishu 回"已归档：{path}"
- [ ] 11.B.4 测试场景 4：解析服务进程崩溃后重启 → bishu 5 分钟超时回执触发 + 重启后任务自动消化
- [ ] 11.B.5 测试场景 5：cookie 过期 → bishu 飞书回"cookie 过期，请重新导出 cookies.txt"
- [ ] 11.B.6 测试场景 6：网络断开 30 秒后恢复 → 后续飞书消息能正常入队处理

## 12. 文档与归档准备（0.25 天）

- [ ] 12.1 在 `docs/m1/RUNBOOK.md` 写部署与运维手册（启动/停止/查日志/重启/cron 任务管理）
- [ ] 12.2 在 `docs/m1/TROUBLESHOOTING.md` 写常见报错与排查（cookie 过期 / 反爬升级 / openclaw 重启 / 笔记没出现）
- [ ] 12.3 在 `docs/m1/ACCEPTANCE.md` 列出 11.A 和 11.B 测试场景的预期结果与人工核验步骤
- [ ] 12.4 commit 所有代码到本 change 的 worktree（待 comet-build 阶段执行）
- [ ] 12.5 准备进入 comet-verify 阶段
