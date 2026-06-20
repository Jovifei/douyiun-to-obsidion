---
comet_change: m1-douyin-archive-mvp
role: technical-design
canonical_spec: openspec
---

# M1 抖音知识视频归档系统 — 技术设计文档

> 日期：2026-06-19
> 上游 OpenSpec change：`openspec/changes/m1-douyin-archive-mvp/`
> 上游 handoff：`openspec/changes/m1-douyin-archive-mvp/.comet/handoff/design-context.md`（hash `6a451f9f...`）
> Brainstorm summary：`openspec/changes/m1-douyin-archive-mvp/.comet/handoff/brainstorm-summary.md`
> 总工时估算：5-7 天

## 1. 上下文

Jovi 在做个人项目"抖音知识视频自动归档到 Obsidian"。已搭好 `飞书自建机器人 → openclaw（本地 Node 24 服务）` 通道，本项目 m1 补 `openclaw → 解析 → Obsidian` 这一段，端到端跑通"分享链接 → 笔记入库"的最小闭环。

完整背景见 `docs/claude/PRD.md` v1.1（已通过 Codex 反向审核）。本设计文档**仅补 m1 阶段的技术决策与实施约束**，不复述 PRD/EXECUTION 内容。

## 2. 目标与非目标

### 2.1 目标

1. **端到端最短路径打通**：飞书消息 → bishu agent → 解析服务 → vault 笔记 ≤ 2 分钟
2. **自研 extractor**（D-3 v2 修订）：不 vendoring community backend（无 license），仅借鉴思路自研最小 `src/extractors/`
3. **可靠性最小集**：SQLite 队列含 B4 `claimed_at` 占用 + 启动复活 zombie 任务
4. **零云端依赖**：M1 不调任何 LLM/ASR/VLM API，规避 MiMo 套餐合规风险
5. **为 M2/M3 留接口位**：状态机、queue schema、frontmatter schema 都按"含 ASR/视觉"的最终形态设计

### 2.2 非目标

- 不做 Whisper（M2 处理）
- 不做关键帧/OCR/VLM（M3 处理）
- 不做 LLM 总结（M3 处理）
- 不做 iOS/Android 同步、不做 Obsidian Sync 配置（M4 处理）
- 不做监控告警系统（仅留日志）
- 不做飞书群消息/post 富文本处理（仅私聊 text 消息）
- 不做抖音用户主页批量、合集订阅

## 3. 决策矩阵

### D-1: 架构形态 A2（独立 FastAPI + bishu HTTP 调用）

```
飞书 → openclaw main(JJ_bot) → bishu agent
                                ├─ 5秒被动回复
                                ├─ HTTP POST 127.0.0.1:8765/ingest
                                ├─ 轮询 GET /tasks/{id}（指数退避）
                                └─ 完成后飞书主动发消息

解析服务（FastAPI on 8765）独立进程
  ├─ SQLite 队列（B4 claimed_at）
  ├─ 调度器（单 worker 串行）
  ├─ src/extractors/（自研）
  ├─ src/obsidian/writer.py（原子 rename）
  └─ Git 冷备（vault cron commit+push）
```

**Why A2 over A1**：独立进程崩溃不拖 openclaw；接口契约清晰；M3 反向调用 openclaw 工具层时边界好。
**Alternative rejected**：A1（openclaw subprocess，简单但 openclaw 重启丢任务）；A3（YAML 工作流缺显存约束语义，Codex R4 反驳）。

### D-2: M1 不调 LLM

- bishu 在 M1 只做"路由 + 入队 + 回执"
- 解析服务**只产出 frontmatter + 字幕全文 + 封面**
- 笔记正文 `## 摘要` 段 M1 留空占位
- **副作用**：规避 MiMo token-plan 套餐合规风险

### D-3: 自研 src/extractors/（v2 修订）

**v1 方案**：vendoring 复用 `git_ref/obsidian-content-capture-backend/script/`。
**v2 修订**：build 前核验发现该仓库**无 OSS license**（README 仅写"仅供学习与研究"，法律上 = All rights reserved），vendoring 有侵权风险。**改为**：仅借鉴解析思路自研，不复制代码。

**实际策略**：
- M1 主路径直接用 yt-dlp（MIT license，已原生支持 v.douyin.com + 抖音自动字幕）
- backend `douyin_resolver.py` 的 SSR 解析仅作为"实现参考"
- backend `downloader.py`（requests + yt-dlp 包装）自研同等工作量
- backend `audio_extractor.py`（一行 ffmpeg 命令）无版权价值
- backend 仍保留在 `git_ref/` 作为 M2 Whisper 集成时的对照实现

**Trade-off**：工时 4-5 天 → 5-7 天（+1-2 天自研成本）；合规性 100%。

### D-4: SQLite 队列含 B4 修订

```sql
CREATE TABLE task (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id, source_url, source_url_type,
  status TEXT NOT NULL DEFAULT 'pending',
  claimed_at TIMESTAMP NULL,             -- B4: 占用标记
  error_code, error_message, correlation_id, payload_json,
  created_at, updated_at
);
CREATE INDEX idx_task_status_claimed ON task(status, claimed_at);
```

dequeue 用单条原子 SQL `UPDATE ... WHERE id=(SELECT...) RETURNING *`。
启动钩子扫 `status IN ('fetching','writing') AND claimed_at < now()-30min` 全部回 pending（zombie 复活，D-4 v2 修订：删除 processing 状态）。

### D-5: frontmatter schema 含 M2/M3 字段占位

按 `specs/obsidian-archive-writer/spec.md` 定义的 17 字段 schema。M1 实际填充 11 个，`subtitle_source ∈ {douyin_native, creator_uploaded, auto_generated}`，`summary=""`、`vlm_results=[]` 占位。避免 M2/M3 启用时改 schema 触发 vault 历史笔记迁移。

### D-6: bishu agent M1 职责最小化

仅做"路由 + 入队 + 回执"，不做 LLM 调用、不做重计算：
1. 抽 URL（4 种形态）
2. ≤5 秒飞书被动回复
3. HTTP POST `127.0.0.1:8765/ingest` 拿 task_id
4. 指数退避轮询 `GET /tasks/{id}`（1/3/10/30/60/60/60s，最多 5 分钟）
5. 终态时飞书主动发消息

### D-7: vault 写入用原子 rename

先写 `{video_id}.md.tmp` → `os.rename` 切换为 `{video_id}.md`。Windows 上同卷 rename 是原子的，Syncthing/Obsidian 监听表现为"瞬时出现"。

### D-8: bishu 轮询 vs 解析服务回调 = 选 bishu 轮询

解析服务对外仅 HTTP，不持飞书凭证，避免反向 RPC + 凭证管理复杂度。

### D-9: 端口统一 8765（v2 新增）

`docs/codex/EXECUTION.md` 早期用 18900，新 OpenSpec 用 8765。Jovi 拍板按 OpenSpec 用 **8765**。
build 前全局 `18900 → 8765` 替换已完成（docs/claude + docs/codex 共 28 处）；`config.example.yaml` 锁 `port: 8765`。

### D-10: frontmatter 加状态字段防 Dataview 误判（v2 新增）

`summary: ""` / `vlm_results: []` 会被 Dataview 误判为"已总结但空"。加 3 字段：

```yaml
summary_status: not_run | pending | done | failed      # M1 全部 not_run
processing_mode: subtitle_only | subtitle_whisper | subtitle_vlm | full   # M1 全部 subtitle_only
ai_summary_model: null | "mimo-v2.5-pro" | "qwen2.5-72b" | ...  # M1 全部 null
```

M1 默认值：`summary_status=not_run, processing_mode=subtitle_only, ai_summary_model=null`。
收益：M1 笔记可被 DataView `WHERE summary_status != "done"` 正确过滤为"待 M3 总结"。

## 4. 风险与缓解

| Risk | 缓解 |
|------|------|
| 抖音反爬变化致 yt-dlp 失败 | DouK-Downloader 兜底；cookie 探活；失败飞书提示 |
| B4 `claimed_at` 并发竞态 | M1 单 worker 无并发；M2+ 加并发时切 BEGIN IMMEDIATE |
| openclaw 不支持新增 agent / schema 不公开 | OQ-1 BLOCKER，Jovi 提供现有 agent 样板后解决 |
| Git 自动 commit 含敏感数据 | `.gitignore` 屏蔽 `.env`/cookies.txt/secrets/ |
| bishu 轮询频率浪费 | 指数退避，最多 5 分钟超时 |

## 5. 测试策略

### 单元测试（pytest）
- `src/extractors/douyin_resolver.py` — 4 种 URL 形态解析
- `src/queue/db.py` — enqueue / atomic_dequeue / reclaim_zombie_tasks
- `src/obsidian/writer.py` — 原子写入 / 失败回滚
- `src/obsidian/frontmatter.py` — 字段完整性 + D-10 状态字段
- `src/pipeline/state_machine.py` — 合法/非法状态转移

### 集成测试（pytest + httpx）
- `POST /ingest` → 队列入队 → 调度器消化 → 笔记落地
- 重复检测 / force 覆盖

### 端到端测试（两批，因 OQ-1 blocker）
**11.A 不依赖 bishu**（OQ-1 解决前可跑）：
1. curl `POST /ingest` 带字幕视频 → ≤2 min 笔记 + done
2. curl 无字幕视频 → failed + `no_subtitle_in_m1`
3. curl 同 URL 两次 → 第二次 `already_archived`
4. 解析服务崩溃后重启 → pending 自动消化（B4 zombie 复活）
5. cookie 过期模拟 → failed + `cookie_expired`
6. 网络断开 30 秒恢复 → 后续消息正常入队
7. 性能基准：5 条串行 ≤2 min/条

**11.B 飞书端到端**（blocked by OQ-1）：
6 个对应飞书场景，待 bishu agent 注册后才能跑。

## 6. 迁移与回滚

m1 是首个 change，无既有系统迁移。部署步骤：

1. 安装依赖（`uv sync` 或 `pip install -r requirements.txt`）
2. 创建 `config.yaml` + `.env`
3. 初始化 SQLite 队列（`init_db()`）
4. 启动解析服务：`uvicorn src.bridge.main:app --host 127.0.0.1 --port 8765`
5. Jovi 在 openclaw UI 新建 bishu agent（lead 提供配置模板）
6. 飞书发一条带原生字幕的抖音视频，验证端到端

**回滚**：删除 `src/`、SQLite 文件、vault 中 `inbox/douyin/` 即可，无副作用。

## 7. Open Questions

| ID | 问题 | 状态 |
|----|------|------|
| OQ-1 | bishu agent 在 openclaw 内的具体配置 schema | ⚠️ BLOCKER（飞书 E2E），不阻塞 build §1-8 |
| OQ-2 | ~~backend LICENSE~~ | ✅ 已关闭：无 OSS license，决定不 vendoring（D-3 v2） |
| OQ-3 | M1 是否需要 cookies.txt | 待 build 阶段实测（tasks §6.6） |
| OQ-4 | Git 私有仓库地址 | 待 build 阶段（tasks §8.3） |
| OQ-5 | ~~端口统一~~ | ✅ 已关闭：拍板 8765（D-9） |

## 8. Spec Patches

- `specs/obsidian-archive-writer/spec.md` frontmatter schema 加 3 个状态字段（D-10）
- 其他 4 份 spec 无需 patch

## 9. 与 PRD/EXECUTION 的关系

- 本 Design Doc 是 `docs/claude/PRD.md` + `docs/claude/EXECUTION.md` 的**M1 阶段技术补丁**
- DECISIONS.md A1-A17 + D1-D5 仍是上游决策
- 本 Design Doc 的 D-1~D-10 是 m1 阶段的具体实施约束
- 实施时以本 Design Doc + OpenSpec specs 为准；EXECUTION.md 提供更细的命令和代码骨架作为参考

## 10. 下一步

进入 `comet-build` 阶段，按 `tasks.md` 12 任务组执行。Build 优先顺序：
1. **§1-2** 环境准备 + 自研 extractor（独立可跑）
2. **§3-7** 队列 + FastAPI + Obsidian writer + 调度器 + 日志（curl 端到端闭环）
3. **§8** Git 冷备
4. **§11.A** 6 个 curl E2E 测试场景验证
5. **§9-10 + §11.B** 待 OQ-1 解决后补做飞书端
6. **§12** 文档归档

完成后进入 `comet-verify` 阶段做验收。
