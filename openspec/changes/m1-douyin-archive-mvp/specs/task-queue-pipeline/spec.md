## ADDED Requirements

### Requirement: 任务状态机（v2 修订：删除 processing，4 状态严格机）

任务 SHALL 经历以下 4 状态，状态名与 pipeline 阶段名严格一一对应（**v2 修订**：删除冗余的 `processing` 状态，避免 `processing` 与 `fetching` 含义重叠）：

```
pending → fetching → writing → done
              ↓          ↓
            failed     failed
```

**状态语义**：
- `pending`：已入队，未被 worker 认领（`claimed_at IS NULL`）
- `fetching`：被 worker 认领并开始下载/解析/字幕判定（`claimed_at = now()`）。**v2 起 dequeue 直接置此状态**，不再经过 `processing`。
- `writing`：fetching 成功后切到 vault 写入阶段（`claimed_at` 不变，沿用 fetching 阶段的认领时间）
- `done`：vault 笔记已写入，临时文件已清理，终态
- `failed`：任一阶段异常，终态（含 `error_code` + `error_message`）

非法转移（如 `done → pending`、`pending → writing`、`fetching → fetching`）SHALL 拒绝并记录错误。

#### Scenario: 主路径成功

- **WHEN** 任务从 `pending` 进入 `fetching` → 进入 `writing` → 进入 `done`
- **THEN** 笔记已写入 vault，临时文件已清理，bishu 收到 `done` 终态

#### Scenario: fetching 阶段失败

- **WHEN** `fetching` 阶段抛异常（如下载失败、cookie 过期）
- **THEN** 任务状态置 `failed`，错误码 + 错误信息持久化到任务记录，**不**自动重试（M1 重试由 bishu 飞书提示用户手动重发）

#### Scenario: writing 阶段失败

- **WHEN** `writing` 阶段抛异常（如磁盘满、frontmatter 字段缺失）
- **THEN** 任务状态置 `failed`，错误码 `incomplete_frontmatter` 或类似；**不**回退到 `fetching`

#### Scenario: 非法状态转移

- **WHEN** 调度器试图把 `done` 状态任务改回 `pending`
- **THEN** 状态机拒绝，记录 `illegal_transition` 错误日志，任务状态不变

### Requirement: SQLite 队列 schema（v2：4 状态枚举）

任务表 SHALL 包含以下字段：

```sql
CREATE TABLE task (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  video_id TEXT NOT NULL,
  source_url TEXT NOT NULL,
  source_url_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'fetching', 'writing', 'done', 'failed')),
  claimed_at TIMESTAMP NULL,             -- B4: 占用标记（fetching/writing 阶段非空）
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
- **THEN** 任务以 `status='pending', claimed_at=NULL` 入表，返回 `task_id`

#### Scenario: status 枚举约束

- **WHEN** 任何 SQL 试图把 `status` 设为非枚举值（如 `'processing'`）
- **THEN** 数据库 CHECK 约束拒绝插入/更新，错误冒泡到调用方

#### Scenario: 字段约束

- **WHEN** 任何 `NOT NULL` 字段缺失
- **THEN** 数据库拒绝插入，错误冒泡到 bishu

### Requirement: 原子 dequeue（v2：直接置 fetching）

dequeue SHALL 通过单条 SQL 完成"挑选 + 占用 + 状态切换"，**直接置 `status='fetching'`**，不再经过 `processing`（B4 修订 v2）：

```sql
UPDATE task
SET claimed_at = CURRENT_TIMESTAMP,
    status = 'fetching',
    updated_at = CURRENT_TIMESTAMP
WHERE id = (
  SELECT id FROM task
  WHERE status = 'pending' AND claimed_at IS NULL
  ORDER BY id LIMIT 1
)
RETURNING *;
```

#### Scenario: 单 worker dequeue

- **WHEN** 调度器空闲且队列有 pending 任务
- **THEN** 上述 SQL 返回单条任务，`status='fetching', claimed_at=now()`

#### Scenario: fetching → writing 转移

- **WHEN** fetching 阶段成功完成（视频+字幕下载完毕）
- **THEN** 调度器 `UPDATE task SET status='writing', updated_at=now() WHERE id=? AND status='fetching'`；`claimed_at` 保持不变（沿用认领时间）

#### Scenario: 队列为空

- **WHEN** 队列无 pending 任务
- **THEN** dequeue SQL 返回空，调度器空转睡眠 5s 再试

### Requirement: 启动时复活 zombie 任务（v2：fetching + claimed_at 超时）

解析服务 SHALL 在启动时扫描"`status IN ('fetching', 'writing')` AND `claimed_at < now() - 30min`"的任务，全部重置回 `status='pending', claimed_at=NULL`。

**v2 修订理由**：删除 `processing` 后，"卡住的任务"在 `fetching` 或 `writing` 状态；两者都可能因进程崩溃而 stuck，都需复活。

#### Scenario: 进程崩溃后重启（fetching 状态卡住）

- **WHEN** 解析服务进程被 kill 后重启，发现 3 条 `fetching` 任务（claimed_at 全部 >30min 前）
- **THEN** 这 3 条全部回 `pending`，调度器正常消化

#### Scenario: 进程崩溃后重启（writing 状态卡住）

- **WHEN** 重启时发现 1 条 `writing` 任务（claimed_at = 45min 前）
- **THEN** 这条也回 `pending`（writing 阶段失败可重做；frontmatter 生成是幂等的）

#### Scenario: 正常运行中不复活

- **WHEN** 一条 `fetching` 任务 `claimed_at = now() - 5min`（仍在处理）
- **THEN** **不**复活，让调度器继续等

#### Scenario: 复活后的日志审计

- **WHEN** reclaim_zombie_tasks() 执行
- **THEN** 每条被复活的任务记录一条 `INFO zombie_reclaimed` 日志（含 task_id / 旧 status / claimed_at / 当前时间），便于排查为何卡住

### Requirement: bishu 轮询 API（v2：状态字段含 fetching/writing）

解析服务 SHALL 暴露以下 HTTP 端点供 bishu 轮询：

- `GET /tasks/{task_id}` — 返回单条任务状态 + frontmatter 路径（done 时）
- `GET /health` — 返回 `{"status": "ok", "queue": {"pending": N, "fetching": M, "writing": K, "failed_today": F, "done_today": D}}`
- `GET /queue/stats` — 详细队列统计

#### Scenario: bishu 轮询单任务

- **WHEN** bishu `GET /tasks/123`
- **THEN** 返回 `{"task_id": 123, "status": "done", "note_path": "inbox/douyin/2026-06/7234567890123.md", "correlation_id": "..."}`

#### Scenario: bishu 看到 fetching 进度

- **WHEN** bishu 轮询时任务在 `fetching` 状态
- **THEN** 返回 `{"task_id": 123, "status": "fetching", "claimed_at": "..."}`，bishu 可据此决定继续轮询或超时

#### Scenario: 健康检查

- **WHEN** 监控调 `GET /health`
- **THEN** 返回队列概要 + 服务存活标志；`fetching` 与 `writing` 分别计数（不再合并为 `processing`）

### Requirement: 端到端 correlation_id

每个任务 SHALL 持有一个 `correlation_id`（UUID v4），贯穿从 bishu 入队到 vault 写入的整条日志，便于排查。

#### Scenario: 日志串起

- **WHEN** 一条任务因 cookie 过期失败
- **THEN** 所有相关日志（fetching 阶段、download 失败、failed 状态变更、bishu 飞书回执）都含同一 `correlation_id`，grep 该 ID 能取出完整链路

### Requirement: 不允许并发 worker（M1 简化）

M1 阶段调度器 SHALL 单 worker 串行处理任务，不引入并发。

#### Scenario: 单 worker 处理

- **WHEN** 队列有 5 条 pending
- **THEN** 调度器按 FIFO 顺序逐条处理，最多 1 条 `fetching` 同时存在

> 此约束在 M4 阶段如需并发再放开，需重新评估 SQLite 行锁与 GPU 资源调度（M3 视觉模块启动后必须串行，见 PRD §5.3 串行铁律）。

### Requirement: 状态转移审计日志（v2 新增）

每次状态转移 SHALL 记录一条 `INFO state_transition` 日志，含 `task_id` / `from_status` / `to_status` / `correlation_id` / `timestamp` / `error_code`（如适用）。

#### Scenario: 正常转移日志

- **WHEN** 任务从 `fetching` 转到 `writing`
- **THEN** 日志：`INFO state_transition task_id=123 from=fetching to=writing correlation_id=abc-123`

#### Scenario: 失败转移日志

- **WHEN** 任务从 `fetching` 转到 `failed`（cookie 过期）
- **THEN** 日志：`INFO state_transition task_id=123 from=fetching to=failed correlation_id=abc-123 error_code=cookie_expired`

#### Scenario: zombie 复活日志

- **WHEN** 启动时复活一条 `fetching` 状态的 zombie
- **THEN** 日志：`INFO zombie_reclaimed task_id=123 old_status=fetching claimed_at=2026-06-19T10:00:00Z correlation_id=abc-123`
