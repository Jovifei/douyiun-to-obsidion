# Brainstorm Summary

- Change: m1-douyin-archive-mvp
- Date: 2026-06-19

> 注：本 change 的设计决策已在前期 PRD/EXECUTION/DECISIONS/AUDIT 会话中充分 brainstorm 并通过 Codex 反向审核；Comet-design 1b 要求"不削弱 brainstorming clarification flow"——本 summary 把已确认决策固化作为 design proposal，给 user 在 1c blocking point 做最终确认。
> 2026-06-19 v2 修订：Jovi 在 1c blocking point 提了 4 项调整要求，本 summary 已同步吸收：D-3 改为不 vendoring、加 D-9 端口统一、加 D-10 frontmatter 状态字段、OQ-1 升级为飞书 E2E blocker。

## Confirmed Technical Approach

### D-1: 架构形态 = A2（独立 FastAPI + bishu HTTP 调用）

```
飞书 → openclaw main(JJ_bot) → bishu agent
                                ├─ 5秒被动回复
                                ├─ HTTP POST 127.0.0.1:8765/ingest
                                ├─ 轮询 GET /tasks/{id}（指数退避）
                                └─ 完成后飞书主动发消息（tenant_access_token 缓存）

解析服务（FastAPI on 8765）独立进程
  ├─ SQLite 队列（B4 claimed_at 占用）
  ├─ 调度器（单 worker 串行）
  ├─ src/extractors/（自研，参考 community backend 思路）
  ├─ src/obsidian/writer.py（原子 rename 写入 vault）
  └─ Git 冷备（vault 目录 cron commit+push）
```

**Why A2 over A1**：独立进程崩溃不拖 openclaw；接口契约清晰；M3 反向调用 openclaw 工具层时边界好。
**Alternative rejected**：A1（openclaw subprocess，简单但 openclaw 重启丢任务）；A3（YAML 工作流缺显存约束语义，Codex R4 反驳）。

### D-2: M1 不调 LLM（含 mimo / GLM / Qwen 等）

- bishu 在 M1 只做"路由 + 入队 + 回执"，不调任何 LLM
- 解析服务**只产出 frontmatter + 字幕全文 + 封面**，无 AI 总结
- 笔记正文 `## 摘要` 段 M1 留空占位，M3 填充
- **副作用**：完全规避 MiMo token-plan 套餐合规风险（DECISIONS A15），M3 才正式通过 openclaw 工具层调 mimo-v2.5-pro

### D-3: 参考 `obsidian-content-capture-backend` 解析思路自研 `src/extractors/`（**已修订 v2**）

**v1 方案**：vendoring 复用 backend/script/，节约 30-50% 工时。
**v2 修订（Jovi 拍板）**：build 前核验发现 backend 仓库**无 OSS license**（README 仅写"仅供学习与研究"），法律上 = All rights reserved，vendoring 复用代码有侵权风险。**改为**：仅借鉴解析思路自研最小 extractor，**不复制任何代码**到 `src/`。

**实际策略**：
- M1 主路径直接用 yt-dlp（MIT license，已原生支持 v.douyin.com 解析 + 抖音自动字幕）
- backend 的 `douyin_resolver.py`（SSR 解析）仅作为"实现参考"看思路，不拷贝
- backend 的 `downloader.py`（requests + yt-dlp 包装）自研同等工作量
- backend 的 `audio_extractor.py`（一行 ffmpeg 命令）无版权价值
- backend 仍保留在 `git_ref/` 作为 M2 Whisper 集成时的对照实现

**Trade-off**：工时从 4-5 天 → 5-7 天（自研 extractor +1-2 天）；合规性 100%，长期可商用可开源。

**Alternative rejected**：
- ~~Vendoring 复用 backend/script/~~：无 license 风险
- 联系作者 lyxdream 申请许可：build 阶段不能等

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
启动钩子扫 `status IN ('fetching','writing') AND claimed_at < now()-30min` 全部回 pending（zombie 复活，v2 修订：删除 processing 状态，4 状态严格机）。

### D-5: frontmatter schema 含 M2/M3 字段占位

按 `openspec/changes/m1-douyin-archive-mvp/specs/obsidian-archive-writer/spec.md` 定义的 17 字段 schema（v2 含 D-10 加的 3 个状态字段）。M1 实际填充的有 11 个，`subtitle_source ∈ {douyin_native, creator_uploaded, auto_generated}`，`summary=""`、`vlm_results=[]` 占位。**避免 M2/M3 启用时改 schema 触发 vault 历史笔记迁移**。

### D-6: bishu agent 在 M1 阶段只做"路由 + 入队 + 回执"

不在 bishu 内做 LLM 调用、不做重计算。逻辑步骤：
1. 抽 URL（短链/完整链/iesdouyin/分享文案 4 种形态）
2. ≤5 秒飞书被动回复"已收到"
3. HTTP POST `127.0.0.1:8765/ingest` 拿 task_id
4. 指数退避轮询 `GET /tasks/{id}`（1/3/10/30/60/60/60s，最多 5 分钟）
5. 终态时飞书主动发消息（按 error_code 翻译人类可读）

### D-7: vault 写入用"原子 rename"

先写 `{video_id}.md.tmp` → `os.rename` 切换为 `{video_id}.md`。
Windows 上同卷 rename 是原子的，Syncthing/Obsidian 监听表现为"瞬时出现"。

### D-8: bishu 轮询 vs 解析服务回调 = 选 bishu 轮询

**选 bishu 轮询**：解析服务对外仅 HTTP，不持飞书凭证，避免反向 RPC + 凭证管理复杂度。
**Alternative rejected**：解析服务回调 bishu/openclaw → 持飞书 token 反向调 openclaw，复杂度爆炸。

### D-9: 端口统一为 8765（**v2 新增**）

**Why**：早期 `docs/codex/EXECUTION.md` 用 18900，新 OpenSpec `docs/claude/DECISIONS.md` D1 用 8765，两套文档并存易引误。Jovi 拍板按 OpenSpec 用 **8765**。

**Action**：build 前把 `docs/claude/EXECUTION.md` 与 `docs/codex/EXECUTION.md` 全局 `18900` → `8765` 替换（共 ~13 处）；`config.example.yaml` 锁 `port: 8765`。

**Rationale**：8765 是 DECISIONS D1 已确认的权威值，与 OpenSpec 5 份 spec 一致。

### D-10: frontmatter 加状态字段防 DataView 误判（**v2 新增**）

**Why**：Jovi 指出 `summary: ""` / `vlm_results: []` 容易被 DataView/脚本误判为"已总结但内容为空"。需要显式状态字段区分"未跑"vs"已跑但空"。

**新增 3 字段**：

```yaml
summary_status: not_run | pending | done | failed      # M1 全部 not_run
processing_mode: subtitle_only | subtitle_whisper | subtitle_vlm | full   # M1 全部 subtitle_only
ai_summary_model: null | "mimo-v2.5-pro" | "qwen2.5-72b" | ...  # M1 全部 null
```

**M1 默认值**：`summary_status=not_run, processing_mode=subtitle_only, ai_summary_model=null`。

**收益**：M1 笔记 `summary_status=not_run` 可被 DataView `WHERE summary_status != "done"` 正确过滤为"待 M3 总结"，避免旧 schema 的 `summary=""` 误判。

## Key Trade-offs and Risks

| Risk | 缓解 |
|------|------|
| 抖音反爬变化致 yt-dlp 失败 | DouK-Downloader 兜底；cookie 探活；失败飞书提示 |
| ~~community backend 上游 license 风险~~ | ✅ 已规避（D-3 v2 改为不 vendoring，自研 extractor） |
| B4 `claimed_at` 并发竞态 | M1 单 worker 无并发；M2+ 加并发时切 BEGIN IMMEDIATE |
| openclaw 不支持新增 agent / schema 不公开 | Jovi 提供现有 agent 样板后即解决（OQ-1） |
| Git 自动 commit 含敏感数据 | `.gitignore` 屏蔽 `.env`/cookies.txt/secrets/ |
| bishu 轮询频率浪费 | 指数退避，最多 5 分钟超时 |
| **端口 18900 vs 8765 残留混乱** | ✅ D-9 已拍板 8765，build 前全局替换 |
| **frontmatter 旧 schema 被 Dataview 误判** | ✅ D-10 加状态字段解决 |

## Testing Strategy

### 单元测试（pytest）
- `src/extractors/douyin_resolver.py` — 4 种 URL 形态解析
- `src/queue/db.py` — enqueue / atomic_dequeue / reclaim_zombie_tasks
- `src/obsidian/writer.py` — 原子写入 / 失败回滚
- `src/obsidian/frontmatter.py` — 字段完整性检查 + D-10 状态字段
- `src/pipeline/state_machine.py` — 合法/非法状态转移

### 集成测试（pytest + httpx）
- `POST /ingest` → 队列入队 → 调度器消化 → 笔记落地
- 重复检测 / force 覆盖

### 端到端测试（两批，**因 OQ-1 blocker**）
**11.A 不依赖 bishu（OQ-1 解决前可跑）**：
1. curl `POST /ingest` 带字幕视频 → ≤2 min 笔记 + done
2. curl 无字幕视频 → failed + `no_subtitle_in_m1`
3. curl 同 URL 两次 → 第二次 `already_archived`
4. 解析服务崩溃后重启 → pending 自动消化（B4 zombie 复活）
5. cookie 过期模拟 → failed + `cookie_expired`
6. 网络断开 30 秒恢复 → 后续消息正常入队
7. 性能基准：5 条串行 ≤2 min/条

**11.B 飞书端到端（blocked by OQ-1）**：
6 个对应飞书场景，待 bishu agent 注册后才能跑。

### 性能基准
5 条带字幕视频串行处理，平均端到端 ≤2 min/条。

## Spec Patches

**v2 修订**：specs/obsidian-archive-writer/spec.md frontmatter schema 加 3 个状态字段（`summary_status` / `processing_mode` / `ai_summary_model`）+ 对应 Scenario。这是补丁式增量，不重写 spec。

## Open Questions

| ID | 问题 | 状态 |
|----|------|------|
| OQ-1 | bishu agent 在 openclaw 内的具体配置 schema | ⚠️ **BLOCKER**：未解决前不能宣称"飞书端到端"完成；可先做 curl → FastAPI → pipeline → vault 闭环 |
| OQ-2 | ~~`obsidian-content-capture-backend` 的 license~~ | ✅ **已关闭**：仓库无 OSS license，决定不 vendoring（D-3 v2） |
| OQ-3 | M1 阶段是否需要 cookies.txt | 待 build 阶段实测（tasks.md §6.6） |
| OQ-4 | Git 私有仓库地址 | 待 build 阶段（tasks.md §8.3） |
| OQ-5 | 端口统一（18900 vs 8765） | ✅ **已关闭**：拍板 8765（D-9） |

OQ-1 是飞书 E2E blocker，但**不阻塞 build 阶段启动**——可先做 §1-8 + §11.A 自研部分，§9-10 + §11.B 待 OQ-1 解决后补做。
