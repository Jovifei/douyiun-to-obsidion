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
