# T4 · 飞书 → openclaw 链路调研

> 调研员：平台调研员
> 调研日期：2026-06-19
> 调研范围：openclaw 身份判定 + 飞书自建机器人 → 本地 agent 链路

---

## Part A · "openclaw" 身份判定

### 结论（高置信度）

**`openclaw` = GitHub `openclaw/openclaw` —— 一个开源的"个人 AI 助理"项目（TypeScript / Node 24，跨平台，2025-11 上线）。Jovi 把它当作链路里的"本机消费方"。**

证据（GitHub REST API 直查，非搜索页 LLM 摘要）：

- 仓库：`https://github.com/openclaw/openclaw`，主页 `https://openclaw.ai`，文档 `https://docs.openclaw.ai`。
- 创建于 2025-11-24，2026-06-19 仍在更新（`pushed_at` 当日）；TypeScript 主语言；topics: `ai / assistant / openclaw / own-your-data / personal`。
- README 自我描述："a personal AI assistant you run on your own devices … answers you on the channels you already use"。
- README 明确列出**支持的频道**："WhatsApp, Telegram, Slack, Discord, Google Chat, Signal, iMessage, IRC, Microsoft Teams, Matrix, **Feishu**, LINE, Mattermost, Nextcloud Talk, Nostr, Synology Chat, Tlon, Twitch, Zalo, Zalo Personal, WeChat, QQ, WebChat"。
- 安装入口 `openclaw onboard`（CLI 引导式安装，macOS / Linux / **Windows** 全平台），Windows 用户可装 Windows Hub 桌面端（含 tray、本地 MCP）。
- 仓库根目录可见 `apps/ extensions/ skills/ ui/` 等，含 `CLAUDE.md`、`AGENTS.md`、`crabbox.yaml`，是典型的"Gateway + 多频道适配 + 多 agent skill"结构。
- 飞书频道官方文档 `https://docs.openclaw.ai/channels/feishu`：**默认 WebSocket 长连接模式**，需在飞书开放平台勾选"持久连接"，订阅 `im.message.receive_v1`，配 App ID + App Secret 即可；可选 webhook 模式默认监听 `127.0.0.1:3000/feishu/events`，需额外 verification token + encrypt key。

### 三个候选解释及证据强度

| # | 候选 | 证据 | 判定 |
|---|---|---|---|
| 1 | **GitHub `openclaw/openclaw` 个人 AI 助理（TS/Node）** | API 实测仓库存在、活跃、明确支持 Feishu 频道、CLI `openclaw onboard`、Windows 全平台 | ✅ **就是它** |
| 2 | Anthropic Claude Code 的口语讹传（"open-claude" → "openclaw"） | 发音相近；但 Claude Code 不直接接飞书频道，且 Jovi 已在用 Claude Code（本会话即是），同名混淆不合理 | ❌ 排除 |
| 3 | 1997 经典 2D 游戏 *Captain Claw* 的开源复刻引擎（同名 GitHub `OpenClawProject/openclaw`，C++）| 存在但与飞书 / AI / 自动化无任何关联 | ❌ 同名巧合 |

### 仍需向 Jovi 追问（精准化用）

1. **飞书频道运行模式**：是默认 WebSocket 长连接（无需公网），还是开了 webhook 模式（已配 tunnel）？决定 T6/T7 是否要复用隧道。
2. **OpenClaw 部署位置**：本机常驻还是用 Windows Hub 桌面端？决定我们的解析服务跟它跨进程通信用 HTTP 还是 stdin/stdout。
3. **现有 agent 绑定**：飞书消息进 OpenClaw 之后，目前是路由到哪个 skill / agent？我们要新写一个抖音解析 skill，还是从外部 HTTP 拉走？
4. **OpenClaw 版本 / config 路径**：方便我们在 T6 直接读 `~/.openclaw/config.json5`（或类似），不要瞎猜端口和绑定。

---

## Part B · 飞书自建机器人 → 本机 OpenClaw 链路

### B.1 链路总览（结合 Jovi 现状）

```
┌──────────────┐     1. 复制抖音 share URL        ┌──────────────┐
│  抖音 App    │ ───────────────────────────────▶ │ 飞书 (手机)  │
└──────────────┘                                  └──────┬───────┘
                                                         │  发给"自建机器人"会话
                                                         ▼
                                          ┌────────────────────────────┐
                                          │ 飞书开放平台事件中台         │
                                          │  event=im.message.receive_v1│
                                          └──────────┬─────────────────┘
                                                     │
                              ┌──────────────────────┴───────────────────────┐
                              │ A) 持久连接 (WebSocket，推荐) ←── Jovi 大概率走这条
                              │ B) HTTP webhook 回调  →  需公网 / tunnel
                              └──────────────────────┬───────────────────────┘
                                                     ▼
                                          ┌────────────────────────────┐
                                          │ 本机：OpenClaw Gateway     │
                                          │  127.0.0.1:3000            │
                                          │  feishu channel adapter    │
                                          │  → 解析 message.content    │
                                          │  → 提取 URL                │
                                          │  → 路由到 skill / agent    │
                                          └──────────┬─────────────────┘
                                                     │  (T5 解析服务接手)
                                                     ▼
                                          ┌────────────────────────────┐
                                          │ 抖音解析服务 (待建)         │
                                          │  返回 markdown + 媒体        │
                                          └──────────┬─────────────────┘
                                                     ▼
                                          ┌────────────────────────────┐
                                          │ Obsidian Vault (T7)         │
                                          └────────────────────────────┘
```

### B.2 飞书侧最关键的事实

- **事件**：`im.message.receive_v1`，header 含 `event_id`（幂等键）+ `token`（校验）+ `app_id` + `tenant_key`。
- **消息体**（event.message）核心字段：
  - `message_id` — 全局唯一，**幂等去重必须用它**。
  - `chat_type` — `p2p`（私聊）/ `group`。
  - `message_type` — `text` / `post` / `share_chat` / `share_user` / `image` / `audio` / `file` / `media`。
  - `content` — **JSON 序列化后的字符串**，结构因 message_type 而异：
    - `text`：`"{\"text\":\"<原文，含 URL>\"}"`，抖音分享链接以纯文本形式出现，可正则抽取。
    - `post`：富文本结构，URL 嵌在子节点；T5 的 URL 抽取要兼容这种。
- **两种接入模式**：
  - **持久连接（WebSocket / long-connection）**：飞书官方 SDK 主推，本机不需要公网。Python 走 `lark-channel-sdk`（旧入口 `lark_oapi.channel` 兼容到 2027-06-02），Go/Java/Node 也都有。
  - **HTTP webhook**：飞书把事件 POST 到你给的 URL，本机暴露需要 cloudflare tunnel / frp / ngrok / natapp。OpenClaw 默认地址 `127.0.0.1:3000/feishu/events`，因此走 webhook 模式时 tunnel 终点指过去。

### B.3 OpenClaw 飞书频道关键行为（来自 docs.openclaw.ai/channels/feishu）

1. **接入门控**：DM 走 `dmPolicy`，群消息走 `groupPolicy` + `requireMention` + 白名单。
2. **媒体规范化**：`file_key` JSON → 标准 placeholder；音频可走飞书自带转写或本地转写。
3. **路由**：消息按预绑定的 agent 派发，或开启"per-user dynamic agent"自动建会话 agent。
4. **会话映射**：按 `dmScope` / `group session scope` 分配 session。

→ **对我们的含义**：抖音 URL 进 OpenClaw 后，要么写一个 OpenClaw skill 直接调 T5 解析服务，要么让 OpenClaw 把消息透传给一个"占位 agent"，agent 通过 HTTP 调 T5。后者侵入更小，推荐。

### B.4 持久连接最小代码骨架（Python，参考实现）

```python
# 仅作链路示意，真实落地由 OpenClaw 内置 channel 适配，无需我们实现
import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

def on_message(data: P2ImMessageReceiveV1) -> None:
    msg = data.event.message
    if msg.message_type != "text":
        return
    content = json.loads(msg.content)            # {"text": "...https://v.douyin.com/xxx/..."}
    url = extract_douyin_url(content["text"])    # T5 模块负责
    if not url:
        return
    # 幂等：用 msg.message_id 做 key，避免飞书重投
    if seen(msg.message_id):
        return
    forward_to_parser(url, message_id=msg.message_id, chat_id=msg.chat_id)

client = (lark.ws.Client(APP_ID, APP_SECRET, log_level=lark.LogLevel.INFO)
          .register(P2ImMessageReceiveV1, on_message)
          .build())
client.start()
```

### B.5 错误重试 / 幂等 / 回写

- **重试**：飞书事件中台对 5xx / 超时会按指数退避重投（最多 ~3 次，间隔分钟级）；`message_id` + `event_id` 都得当作幂等键。
- **回写状态**：用 `im/v1/messages/reply`（reply 接口）把"解析中 / 已入库 / 失败"作为线程消息发回原 chat，给用户可见反馈。
- **超时策略**：T5 解析 > 3s 时，OpenClaw skill 应先 ack（reply"已收到，处理中"），再异步回写结果。

---

## Part C · 模块间接口契约建议

下面是 **OpenClaw（或其 skill）→ T5 抖音解析服务** 的 HTTP 契约。OpenClaw 侧是调用方，T5 是被调方。

### C.1 OpenAPI 片段（YAML）

```yaml
openapi: 3.0.3
info:
  title: Douyin Parser Service
  version: 0.1.0

paths:
  /v1/parse:
    post:
      summary: 解析单条抖音分享 URL，返回 markdown + 媒体清单
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ParseRequest'
      responses:
        '200':
          description: 解析成功
          content:
            application/json:
              schema: { $ref: '#/components/schemas/ParseResponse' }
        '202':
          description: 已受理，将异步通知 callback_url
          content:
            application/json:
              schema:
                type: object
                properties: { task_id: { type: string } }
        '400': { description: URL 不是抖音可识别格式 }
        '409': { description: idempotency_key 命中已存在结果，body 同 200 }
        '422': { description: URL 已失效 / 视频被删 }
        '429': { description: 触发抖音限频，建议稍后重试 }
        '500': { description: 解析器内部错误 }

  /v1/tasks/{task_id}:
    get:
      summary: 异步任务状态查询
      parameters:
        - { name: task_id, in: path, required: true, schema: { type: string } }
      responses:
        '200':
          content:
            application/json:
              schema: { $ref: '#/components/schemas/TaskStatus' }

components:
  schemas:
    ParseRequest:
      type: object
      required: [url, idempotency_key]
      properties:
        url: { type: string, format: uri, description: "抖音分享 URL，支持 v.douyin.com 短链" }
        idempotency_key:
          type: string
          description: "建议用飞书 message_id；同 key 重复请求返回同结果"
        callback_url:
          type: string
          format: uri
          description: "可选；提供则走异步，结果 POST 到此 URL"
        source:
          type: object
          description: "上游溯源元信息"
          properties:
            channel:    { type: string, enum: [feishu, slack, manual] }
            chat_id:    { type: string }
            sender_id:  { type: string }
            received_at:{ type: string, format: date-time }
        options:
          type: object
          properties:
            include_video:    { type: boolean, default: false }
            include_images:   { type: boolean, default: true }
            include_subtitle: { type: boolean, default: true }
            ocr_subtitle:     { type: boolean, default: false }

    ParseResponse:
      type: object
      properties:
        idempotency_key: { type: string }
        douyin_id:       { type: string, description: "aweme_id" }
        author:
          type: object
          properties:
            nickname: { type: string }
            sec_uid:  { type: string }
        title:           { type: string }
        description:     { type: string }
        published_at:    { type: string, format: date-time }
        markdown:        { type: string, description: "可直接写入 Obsidian 的 md 文本" }
        assets:
          type: array
          items:
            type: object
            properties:
              kind:       { type: string, enum: [video, image, audio, cover] }
              local_path: { type: string, description: "本机绝对路径，受 Jovi 全局下载路径约束" }
              sha256:     { type: string }
              bytes:      { type: integer }
        warnings:        { type: array, items: { type: string } }

    TaskStatus:
      type: object
      properties:
        task_id: { type: string }
        state:   { type: string, enum: [pending, running, succeeded, failed] }
        result:  { $ref: '#/components/schemas/ParseResponse' }
        error:   { type: object, properties: { code: { type: string }, message: { type: string } } }
```

### C.2 错误码约定

| code | 含义 | 上游应对 |
|------|------|----------|
| `INVALID_URL` | 不是抖音 URL | OpenClaw 回写"不是有效的抖音链接" |
| `URL_EXPIRED` | 短链失效 / 视频被删 | 回写"链接已失效" |
| `RATE_LIMITED` | 抖音侧限频 | 退避重试，告知"稍后重试" |
| `PARSE_FAILED` | 解析器自身报错 | T5 写日志，OpenClaw 回写"解析失败，已记录" |
| `STORAGE_FAILED` | 媒体下载到本地失败 | 同上 |

### C.3 CLI 备选契约（如果 Jovi 想把 T5 直接做成 OpenClaw skill 子命令而非独立 HTTP 服务）

```
$ douyin-parse \
    --url "https://v.douyin.com/abc/" \
    --idempotency-key "feishu:msg_id:om_xxx" \
    --out-dir "E:/Claude_allow/Download/douyin/" \
    --emit-json
# stdout: 与 ParseResponse schema 对齐的 JSON
# exit:   0 / 2 (INVALID_URL) / 3 (URL_EXPIRED) / 4 (RATE_LIMITED) / 1 (其他)
```

OpenClaw skill 可直接 spawn 这个二进制，stdout JSON 拼装回飞书 reply。这种方式比 HTTP 简单一档，缺点是 skill 进程崩了会丢任务 —— 不如 HTTP 服务可观测。**建议默认 HTTP，CLI 模式作为 fallback。**

---

## 风险与缺口

1. **OpenClaw 飞书频道是 webhook 还是 WS 模式未知** —— 影响 T6/T7 的隧道决策。Lead 必须问 Jovi。
2. **OpenClaw 是 2025-11 才上线的项目，破坏性变更概率高** —— 我们的 skill 要锚定具体版本（`package.json` engines 字段）+ CI smoke。
3. **抖音 URL 可能藏在飞书 `post` / `share` 富文本里，而非纯文本** —— T5 的 URL 抽取必须兼容多种 message_type。
4. **媒体下载路径**：Jovi 全局策略要求 `E:\Claude_allow\Download\` 下载。T5 的 `--out-dir` 默认值要这么设。
5. **OpenClaw 国际化文档未必同步**：英文 docs 是权威；中文页 `docs.openclaw.ai/zh-CN/channels/feishu` 可能滞后。
6. **WebFetch 在 Google/GitHub 搜索页面有幻觉风险** —— 本次调研中第一次 GitHub 搜索摘要把不存在的"VoltAgent/awesome-openclaw-skills 50.4k stars"写进结果，**最终结论全部基于 GitHub REST API 实测验证**，不引用 WebFetch 摘要给的不确定 star 数。

---

## 引用

- GitHub REST API: `https://api.github.com/repos/openclaw/openclaw`（实测，2026-06-19）
- OpenClaw README: `https://github.com/openclaw/openclaw#readme`
- OpenClaw Feishu 频道文档: `https://docs.openclaw.ai/channels/feishu`
- 飞书事件订阅 - 接收消息 v2.0 (`im.message.receive_v1`): `https://open.feishu.cn/document/server-docs/im-v1/message/events/receive`
- 飞书事件 payload reference: `https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/events/receive`
- 飞书 Python SDK 长连接: `https://github.com/larksuite/oapi-sdk-python`（lark-channel-sdk）
- OpenClaw 官网 / 文档站: `https://openclaw.ai` / `https://docs.openclaw.ai`
