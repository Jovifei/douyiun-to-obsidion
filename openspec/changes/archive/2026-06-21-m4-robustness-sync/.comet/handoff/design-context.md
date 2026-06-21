# Comet Design Handoff

- Change: m4-robustness-sync
- Phase: design
- Mode: compact
- Context hash: 87df02fd149262f6ccff68be6c5f55f4aa560aec78ec4237c869db18aad8f0e7

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/m4-robustness-sync/proposal.md

- Source: openspec/changes/m4-robustness-sync/proposal.md
- Lines: 1-32
- SHA256: a7316a79870d11d802fb40c5d7bbde82fdbad8c3fc552c2db0b23fab072a2003

```md
## Why

M1-M3 核心管线（字幕+ASR+LLM+VLM→笔记）已验证通过。M4 补生产级健壮性：让系统能在真实环境下长期稳定运行，不因网络抖动、cookie 过期、进程崩溃等边缘情况中断。

## What Changes

- **cookie 过期自动刷新**：下载失败时自动探活 + 定期轮转 cookies.txt
- **重试增强**：下载失败指数退避 + 失败重放队列
- **监控告警**：关键事件飞书推送（cookie 过期、队列堆积、连续失败）
- **离线队列追赶**：PC 睡眠/断网后恢复时自动消化积压任务
- **M1 测试修复**：修复 3 个 pre-existing ASR 测试（`test_asr_interface.py` 导入路径 + `test_audio_preprocess.py` capture_output 断言）

## Capabilities

### New Capabilities

- `cookie-auto-refresh`: cookie 过期检测 + 定期轮转 + 失败时触发重试
- `monitor-alerts`: 关键事件飞书推送（cookie 过期、队列堆积、连续失败 N 次）
- `offline-recovery`: 进程重启后自动恢复积压任务（已有 zombie reclaim，M4 加 sleep-wake 检测）

### Modified Capabilities

- `task-queue-pipeline`: scheduler 加指数退避重试 + sleep-wake 检测 + cookie 自动探活增强
- `douyin-extraction`: downloader 加 cookie 轮转钩子

## Impact

- 修改 `src/pipeline/scheduler.py`（重试增强、sleep-wake 检测）
- 修改 `src/utils/cookie_probe.py`（cookie 过期自动轮转）
- 新增 `src/utils/monitor.py`（飞书 webhook 告警）
- 修改 `src/pipeline/errors.py`（新增 retryable 错误分类）
- 新增 `tests/utils/test_monitor.py`
```

## openspec/changes/m4-robustness-sync/design.md

- Source: openspec/changes/m4-robustness-sync/design.md
- Lines: 1-58
- SHA256: 62c3ac57768b46b5375a267cffa2cbcfb8b803058990284d80372cb2a257712f

```md
## Context

M1-M3 核心管线完成。M4 补生产级健壮性。Jovi 选 iOS 同步（Obsidian Sync 或 iCloud，DECISIONS A7 分阶段），M4 不实现 iOS 同步（Jovi 明确"M1-M2 不同步手机端"）。

## Goals / Non-Goals

**Goals**：
1. cookie 过期自动检测 + 轮转
2. 下载失败指数退避 + 最大重试次数
3. 离线恢复（sleep-wake 检测 + 积压消化）
4. 关键事件飞书 webhook 告警
5. 修复 3 个 pre-existing 测试

**Non-Goals**：
- 不做 iOS 同步（DECISIONS A7: iOS 候选 Obsidian Sync/iCloud/Working Copy，M4 仅规划不实现）
- 不做 Android 同步（DECISIONS A7: M2 才考虑 Syncthing）
- 不做云盘备份（iCloud/OneDrive 延后）
- 不做多用户
- 不做实时监控仪表盘

## Decisions

### D-M4-1: cookie 轮转策略

cookies.txt 过期检测：下载失败时自动探活（HTTP HEAD 已知抖音视频），失败则在 `/cookies/` 目录找更旧的有效 cookies 备份；全部过期则发飞书告警。

### D-M4-2: 重试指数退避

```
第1次重试：立即
第2次重试：5秒
第3次重试：30秒
第4次重试：2分钟
第5次重试：10分钟（最终，失败标记 done with error）
```

### D-M4-3: sleep-wake 检测

PC 从睡眠恢复时（检测到系统 clock jump），立刻触发一次 zombie reclaim + 队列消化，不让积压任务卡住。

### D-M4-4: 飞书 webhook 告警

配置 `monitor.feishu_webhook_url`（Jovi 在飞书群里创建一个 incoming webhook bot），关键事件 JSON push：
- cookie 过期（单独告警）
- 连续失败 ≥ 3 次（同 video_id）
- 队列堆积 > 20 条 pending 持续 > 30 分钟

### D-M4-5: 不实现 iOS 同步

DECISIONS A7: iOS 候选 Obsidian Sync / iCloud / Working Copy。M4 仅规划，不实现。手机端 Jovi 当前只在 PC 使用。M4 完成后再开 M5（如 Jovi 需要）。

## Risks

| Risk | 缓解 |
|------|------|
| 飞书 webhook 告警刷屏 | 30 分钟内同一告警不重复发 |
| cookie 轮转替换错文件 | 只替换 `cookies.txt`，备份在 `cookies_backup/` |
| sleep-wake 检测误判 | clock jump 阈值 60 秒，低于不算 |
```

## openspec/changes/m4-robustness-sync/tasks.md

- Source: openspec/changes/m4-robustness-sync/tasks.md
- Lines: 1-49
- SHA256: 9e99b72db3884d601016ed60c9773fc1d68733c33e167296f6c11deb854c29b9

```md
# M4 实施任务清单

> Change: `m4-robustness-sync`
> Workflow: full (spec-driven)
> 总工时估算: **5-7 天**
> 依赖：M1 + M2 + M3 完成

## 1. cookie 自动探活与轮转（1 天）

- [ ] 1.1 增强 `src/utils/cookie_probe.py`：`probe_and_rotate(cookies_path, backup_dir) -> bool`
- [ ] 1.2 下载失败时自动探活（HTTP HEAD 已知抖音视频，200=有效）
- [ ] 1.3 cookies.txt 全过期时在 `cookies_backup/` 找更旧备份轮换
- [ ] 1.4 全部过期 → 发飞书 webhook 告警
- [ ] 1.5 单元测试：mock httpx，验证探活/轮换/告警路径

## 2. 下载重试指数退避（0.5 天）

- [ ] 2.1 修改 `src/pipeline/scheduler.py` `_download_with_fallback`：指数退避（0s→5s→30s→2m→10m）
- [ ] 2.2 新增 `src/pipeline/errors.py` `is_retryable(error) -> bool` 判断哪些错误可重试
- [ ] 2.3 单元测试：mock sleep + 计数，验证退避时间序列

## 3. sleep-wake 检测（0.5 天）

- [ ] 3.1 scheduler 主循环加 clock jump 检测（当前时间 - 上次循环时间 > 60s = sleep-wake）
- [ ] 3.2 检测到 sleep-wake 时触发 zombie reclaim + 队列消化
- [ ] 3.3 单元测试：mock time，验证 clock jump 触发 reclaim

## 4. 飞书 webhook 告警（1 天）

- [ ] 4.1 新增 `src/utils/monitor.py`：`send_feishu_alert(webhook_url, title, content)`
- [ ] 4.2 配置 `config.yaml`：`monitor.feishu_webhook_url` + `monitor.enabled`
- [ ] 4.3 实现告警去重（30 分钟内同类型不重复发）
- [ ] 4.4 告警场景：cookie 过期 / 连续失败≥3 / 队列堆积>20>30min
- [ ] 4.5 单元测试：mock httpx，验证告警 payload 格式

## 5. 修复 pre-existing 测试（0.5 天）

- [ ] 5.1 `tests/asr/test_asr_interface.py`：`from src.asr import MimoASRClient` → 修正导入路径（M2 遗留）
- [ ] 5.2 `tests/asr/test_audio_preprocess.py`：ffmpeg 断言补 `capture_output=True`（M2 遗留）
- [ ] 5.3 `tests/asr/test_asr_interface.py`：WhisperLocalClient 工厂传参对齐（model_name 参数）
- [ ] 5.4 全量测试 273/273 绿

## 6. 集成测试 + 文档（1 天）

- [ ] 6.1 E2E：cookie 过期 → 自动探活 → 告警
- [ ] 6.2 E2E：下载失败 → 退避重试 → 成功/失败标记
- [ ] 6.3 E2E：模拟 clock jump → 队列自动消化
- [ ] 6.4 更新 `docs/m1/RUNBOOK.md`：新增监控告警、cookie 轮转、sleep-wake 说明
- [ ] 6.5 更新 `docs/m2/KNOWLEDGE.md`：新增 cookie 管理策略、重试退避算法
```

## openspec/changes/m4-robustness-sync/specs/cookie-auto-refresh/spec.md

- Source: openspec/changes/m4-robustness-sync/specs/cookie-auto-refresh/spec.md
- Lines: 1-20
- SHA256: 8a0336d6c4c3e571f6938129fe1c6d361a27096a65fa29950c741307741ee6c7

```md
## ADDED Requirements

### Requirement: cookie 过期检测与自动轮转

系统 SHALL 在下载失败时自动探活 cookies.txt，过期则轮换到备份。

#### Scenario: cookie 有效

- **WHEN** 下载失败 + 探活 HTTP HEAD 返回 200
- **THEN** 不轮换，记录 "cookie_valid" 日志，继续正常重试

#### Scenario: cookie 过期 + 备份可用

- **WHEN** 探活失败 + `cookies_backup/` 存在更旧的有效 cookies
- **THEN** 自动替换 `cookies.txt` + 发飞书告警 + 重试下载

#### Scenario: 全部 cookie 过期

- **WHEN** 探活失败 + 备份目录无有效 cookie
- **THEN** 发飞书告警 "cookies 全部过期，请手动刷新" + 任务标记 `cookie_expired`
```

## openspec/changes/m4-robustness-sync/specs/monitor-alerts/spec.md

- Source: openspec/changes/m4-robustness-sync/specs/monitor-alerts/spec.md
- Lines: 1-25
- SHA256: d18fd6f4aa315cc747b71838c10c84c4bf113baa8e12394f0f8376cce3307725

```md
## ADDED Requirements

### Requirement: 飞书 webhook 告警

系统 SHALL 通过飞书 incoming webhook 推送关键事件告警。

#### Scenario: cookie 过期告警

- **WHEN** cookie 探活失败
- **THEN** 推送飞书消息 "⚠️ 抖音 cookie 已过期，请手动刷新 cookies.txt"

#### Scenario: 连续失败告警

- **WHEN** 同 video_id 连续失败 ≥ 3 次
- **THEN** 推送 "❌ 视频 {video_id} 连续失败 3 次：{error_code}"

#### Scenario: 队列堆积告警

- **WHEN** pending > 20 持续 > 30 分钟
- **THEN** 推送 "📦 队列堆积：{pending} 条任务待处理，已持续 {duration}"

#### Scenario: 告警去重

- **WHEN** 同类型告警 30 分钟内已发
- **THEN** 不重复推送
```

## openspec/changes/m4-robustness-sync/specs/task-queue-pipeline/spec.md

- Source: openspec/changes/m4-robustness-sync/specs/task-queue-pipeline/spec.md
- Lines: 1-26
- SHA256: da46bb6bf4838f16b75647a00da26631f1e793332134b5878e1197ade0ca8abc

```md
## MODIFIED Requirements

### Requirement: scheduler 重试增强 + sleep-wake 检测（M4 修改）

**原行为**：下载失败直接标记 failed
**新行为**：下载失败指数退避重试 + 进程 sleep-wake 后自动恢复

#### Scenario: 下载失败指数退避

- **WHEN** yt-dlp 下载失败 + error 可重试
- **THEN** 按 0s→5s→30s→2m→10m 退避重试，第 5 次失败标记 failed

#### Scenario: 不可重试错误直接失败

- **WHEN** yt-dlp 下载失败 + error 不可重试（如 video not found 404）
- **THEN** 立即标记 failed，不退避

#### Scenario: sleep-wake 检测

- **WHEN** 系统 clock jump（当前时间 - 上次循环时间 > 60s）
- **THEN** 立刻触发 zombie reclaim + 队列消化，不等下一个正常循环

#### Scenario: 正常循环不误触发

- **WHEN** 正常 5 秒 sleep 后 clock jump < 60s
- **THEN** 不触发 reclaim，正常继续
```

