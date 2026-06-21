# Brainstorm Summary
- Change: m4-robustness-sync
- Date: 2026-06-21

## Confirmed Technical Approach
cookie 轮转 + 指数退避 + sleep-wake 检测 + 飞书 webhook 告警。不实现 iOS 同步。3 个 pre-existing 测试修复。

## Key Trade-offs
cookie 轮转只做单文件替换，不做多账户管理；告警只用飞书 webhook，不做邮件/Slack。
