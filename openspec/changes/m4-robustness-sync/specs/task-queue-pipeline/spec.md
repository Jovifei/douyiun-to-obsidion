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
