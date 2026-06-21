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
