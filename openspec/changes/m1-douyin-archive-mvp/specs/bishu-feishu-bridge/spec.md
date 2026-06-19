## ADDED Requirements

### Requirement: bishu agent 路由触发

`bishu` agent（在 openclaw 的 12 agent 体系内新增第 13 位）SHALL 在飞书消息含以下任一关键词时被 `main (JJ_bot)` 路由触发：

- `v.douyin.com`
- `iesdouyin.com`
- `www.douyin.com/video/`
- `www.douyin.com/note/`
- 整段分享文案匹配 `9\.\d+.*https?://` 模式

#### Scenario: 标准短链触发

- **WHEN** 用户在飞书私聊机器人发 `https://v.douyin.com/iAbCdEf/`
- **THEN** main 路由规则匹配，转发给 bishu 处理，其他 11 个 agent 不被触发

#### Scenario: 非抖音 URL 不触发

- **WHEN** 用户发 `https://www.bilibili.com/video/BVxxx`
- **THEN** bishu **不**被触发，消息按原有逻辑走其他 agent

#### Scenario: 混合文案触发

- **WHEN** 用户发 `"9.99 复制打开抖音，看看【作者】的作品 https://v.douyin.com/iAbCdEf/ 🔥"`
- **THEN** bishu 被触发，并能从混合文案中提取出短链

### Requirement: 飞书 5 秒响应窗口处理

bishu SHALL 在收到消息后 ≤ 5 秒内通过飞书事件订阅的"被动回复"通道发回一条确认消息，避免飞书平台超时判定失败。

#### Scenario: 立即被动回复

- **WHEN** bishu 收到抖音 URL
- **THEN** ≤ 5 秒内向用户回复"已收到抖音链接，开始处理：{URL 截短}；任务 ID: {task_id}；处理完成后会主动通知"

#### Scenario: 5 秒响应失败

- **WHEN** bishu 在 5 秒内未能完成被动回复（如 openclaw 启动慢）
- **THEN** 飞书平台会判定事件超时并重试；bishu SHALL 在重试事件中识别 `X-Lark-Request-Id` 幂等性，不重复入队

### Requirement: 异步入队 + 异步回执

bishu SHALL 通过 HTTP POST `127.0.0.1:8765/ingest` 把任务入解析服务队列，拿回 `task_id`，然后**异步**轮询 `GET /tasks/{task_id}` 直至 `status` 进入终态（`done` 或 `failed`），再用飞书主动发消息 API 推送最终结果。

#### Scenario: 入队成功

- **WHEN** bishu 调用 `POST /ingest`
- **THEN** 解析服务返回 `{"task_id": "...", "status": "pending"}`，bishu 开始轮询

#### Scenario: 轮询指数退避

- **WHEN** bishu 开始轮询
- **THEN** 轮询间隔 = 1s, 3s, 10s, 30s, 60s, 60s, 60s（最多 5 分钟），任一轮询拿到终态则立即停止

#### Scenario: 5 分钟超时

- **WHEN** 5 分钟内 bishu 未拿到终态
- **THEN** bishu 主动发飞书消息"任务仍在处理中，已超 5 分钟，请稍后查看 vault 或手动重启解析服务"，但不取消任务（解析服务仍继续）

### Requirement: tenant_access_token 缓存与刷新

bishu SHALL 缓存飞书 `tenant_access_token`，过期前 60 秒自动刷新，确保异步回执能调用 `POST /open-apis/im/v1/messages`。

#### Scenario: 缓存命中

- **WHEN** bishu 调用主动发消息 API 且缓存未过期
- **THEN** 直接复用缓存 token，不发新的 token 请求

#### Scenario: 过期前 60 秒刷新

- **WHEN** 缓存剩余有效期 < 60 秒
- **THEN** 在下次发消息前自动调 `POST /open-apis/auth/v3/tenant_access_token/internal` 刷新，更新缓存

#### Scenario: token 获取失败

- **WHEN** 刷新 token 失败（app_secret 错误 / 网络异常）
- **THEN** 日志告警，飞书回执失败；任务仍在解析服务内正常运行（不阻塞），只是用户收不到"完成"通知

### Requirement: 错误回执

bishu SHALL 在解析服务返回 `failed` 终态时，把错误原因用人类可读语言发回飞书。

#### Scenario: 无字幕视频

- **WHEN** 解析服务返回 `failed` 且 `error_code = "no_subtitle_in_m1"`
- **THEN** bishu 飞书回"该视频无字幕，M1 阶段暂不支持；将在 M2 阶段启用 Whisper 自动转写"

#### Scenario: 下载失败

- **WHEN** 解析服务返回 `failed` 且 `error_code = "download_failed_all_tools"`
- **THEN** bishu 飞书回"视频下载失败，可能链接已失效或抖音反爬升级；请稍后重试或换条视频"

#### Scenario: cookie 过期

- **WHEN** 解析服务返回 `failed` 且 `error_code = "cookie_expired"`
- **THEN** bishu 飞书回"抖音 cookie 已过期，请按 EXECUTION §13.4 重新导出 cookies.txt 并重启解析服务"

### Requirement: 配置模板（M1 启动前 Jovi 自行注册）

本 change SHALL 在 `docs/m1/bishu_agent_template.json`（或 yaml）提供一份 bishu agent 在 openclaw 内的注册配置模板，包含：

- agent id: `bishu`
- 中文名: `秘书省`
- type: 按现有 12 agent 的同类型
- model: `mimo-v2.5-pro`（M1 不调 LLM，但留位）
- systemPrompt: 简短职责描述
- HTTP 工具定义：调 `127.0.0.1:8765/ingest` 与 `GET /tasks/{id}`
- binding: 飞书账号 `oc_516376df9cc2315fc12470e56e72c4af`
- 触发条件：消息含 `douyin.com` 等

#### Scenario: 模板可被 Jovi 直接套用

- **WHEN** Jovi 在 openclaw UI 新建 agent，复制本模板并填入真实 app_secret
- **THEN** bishu agent 应能注册成功并接收抖音 URL 触发

#### Scenario: openclaw 配置 schema 不匹配

- **WHEN** Jovi 反馈 openclaw 实际配置 schema 与模板不同
- **THEN** lead 根据现有 agent（如 taizi）的配置 schema 重新生成模板
