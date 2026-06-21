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
