---
comet_change: m4-robustness-sync
role: technical-design
canonical_spec: openspec
archived-with: 2026-06-21-m4-robustness-sync
status: final
---

# M4 健壮性 + 监控 — 技术设计文档

> 日期：2026-06-21
> 上游：`openspec/changes/m4-robustness-sync/`

## Context

M1-M3 核心管线完成。M4 补生产级健壮性，不实现 iOS 同步（DECISIONS A7 延后）。Jovi 选了 MiMo token-plan 作为 LLM/ASR provider，cookie 经浏览器导出。

## 决策

### D-M4-1: cookie 轮转策略

`cookies.txt` 过期检测：下载失败 → HTTP HEAD 已知视频 URL 探活 → 200=有效/其他=过期 → `cookies_backup/` 找旧有效文件替换 → 全过期则飞书告警手动刷新。

### D-M4-2: 指数退避

```
失败1→立即重试 / 失败2→5s / 失败3→30s / 失败4→2m / 失败5→10m→标记 failed
```
不可重试错误（404 video not found）直接 failed。

### D-M4-3: sleep-wake 检测

scheduler 主循环记录 `last_loop_time`，sleep 5s 后检查 `now - last_loop_time > 60s` = PC 睡眠恢复 → 触发一次 zombie reclaim + 队列消化。

### D-M4-4: 飞书 webhook 告警

配置 `monitor.feishu_webhook_url`（Jovi 创建 incoming webhook bot），30 分钟内同类型告警不重复推送。

### D-M4-5: 不实现 iOS 同步

DECISIONS A7: iOS 候选 Obsidian Sync/iCloud/Working Copy。M4 仅规划，不实现。

## 测试策略

- cookie 探活：mock httpx，验证 200/403/轮换路径
- 重试退避：mock sleep + 计数，验证时间序列
- sleep-wake：mock time.time()，验证 clock jump 触发 reclaim
- 告警去重：mock httpx，验证 30 分钟去重窗口
