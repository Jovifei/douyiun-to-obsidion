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
