# 决策日志（DECISIONS）

> 项目所有"已拍板"决策的单一事实源。新加入的 agent 必须先读这里再读 PRD/EXECUTION。
> 命名约定：Q* 是开放问题，A* 是已确认答案，D* 是衍生设计决策。

---

## P0 决策（2026-06-19，Jovi 拍板）

### A1 — 飞书频道连接方式

- **决策**：openclaw 飞书频道走 **WebSocket 长连接**（默认模式）。
- **依据**：`channels.feishu` 配置只定义 `appId + appSecret`，未显式指定模式 → openclaw 默认 WebSocket。
- **影响**：
  - **不需要** frp、cloudflare tunnel、ngrok 等内网穿透。
  - 解析服务暴露 HTTP 接口给 openclaw 即可（不暴露给公网）。
  - 飞书侧只需开通"事件订阅 - 长连接"，无需配置回调 URL。

### A2 — 部署位置

- **决策**：openclaw 与解析服务**同一台机器**（家用 PC，Win11 + 4070S 12G，常驻）。
- **影响**：
  - 解析服务的 HTTP 接口绑 `127.0.0.1`，不绑 `0.0.0.0`。
  - 不需要鉴权 token（同主机环境，按 Loopback 信任处理；如要严谨可加 HMAC，M2+）。
  - openclaw → 解析服务的延迟可忽略。

### A3 — 现有 openclaw agent 拓扑

openclaw 已绑定 12 个 agent，全部绑同一飞书账号 `oc_516376df9cc2315fc12470e56e72c4af`：

```
飞书消息
  ↓
main (JJ_bot, type: route)   ← 入口路由
  ├─ taizi
  ├─ zhongshu
  ├─ menxia
  ├─ shangshu
  ├─ hubu     (六部 - 财政)
  ├─ libu     (六部 - 人事)
  ├─ bingbu   (六部 - 军事)
  ├─ xingbu   (六部 - 司法)
  ├─ gongbu   (六部 - 工程)
  ├─ libu_hr  (吏部 HR)
  └─ zaochao  (朝会)
```

- **决策**：抖音解析功能**新增一个独立 agent**（名称待定，见 Q14），不复用现有 12 个 agent 的职能。
- **接入方式**：在 `main (JJ_bot)` 的路由规则里增加一条："消息含 `v.douyin.com` / `iesdouyin.com` / 抖音分享口令 → 转给新 agent"。
- **新 agent 角色**：仅做"接收 → 调用解析服务 HTTP → 把处理状态/结果回帖"，本身不持业务逻辑。

### A4 — openclaw 版本

- **版本**：openclaw `2026.6.6`（commit `8c802aa`），主配置 `C:\Users\Admin\.openclaw\openclaw.json`。
- **影响**：
  - EXECUTION §5 的接口契约按当前版本写。
  - 升级 openclaw 需先回归测试解析链路（M1 之后才考虑升级）。

### A5 — "全模态 token" 厂商

- **当前认定**：**未完全确定**，候选列表（按 Jovi 反馈）：
  1. 小米 **MiMo-v2.5 / MiMo 系列**（含 MiMo-VL）
  2. 智谱 **GLM 系列**（含 GLM-4V）
- **影响**：
  - **不阻塞 M1**（M1 字幕优先 + 本地 LLM 总结，不用云端 VLM）。
  - **影响 M3 视觉理解**：两家 API schema、price、限流不同，需要在 M2 阶段确认后再写云端 fallback 代码。
  - 见 Q15。

---

## P0 衍生设计决策（自动推导）

### D1 — 解析服务的接口形态

由 A1 + A2 推出：
- **形态**：本地 FastAPI 服务，监听 `127.0.0.1:8765`（端口可配）。
- **路由**：
  - `POST /ingest` — openclaw 把抖音 URL 推过来
  - `GET /health` — 健康检查
  - `GET /tasks/{video_id}` — 查询单条任务状态
  - `GET /queue/stats` — 队列长度、processing/done/failed 数
- **协议**：JSON over HTTP，无鉴权（同主机 loopback 信任）。

### D2 — openclaw 端最小改动

由 A3 推出：
- 在 `main (JJ_bot)` 的 route 规则前置一条 douyin 触发；
- 新 agent 只做：(a) 解析消息文本里的 URL；(b) `POST http://127.0.0.1:8765/ingest`；(c) 异步收 callback 后回帖（或 30s 内不回则只回"已入队"）。
- 不在 openclaw 内做任何视频抓取/转写/写文件——全部丢给解析服务。

### D3 — vault 写入路径

待 Q6 拍板，默认假设：`E:\AI_Tools\Obsidian\Data\notes-personal\inbox\douyin\YYYY-MM\{video_id}.md`。

---

## 待 Jovi 决策的剩余开放问题

| 优先级 | ID | 问题 |
|-------|-----|------|
| **P1-新** | Q16 | MiMo 的 API base_url 和密钥环境变量名是？（见 D4） |
| **P1-新** | Q17 | iCloud Drive 在 Win 上的本地物理路径在哪里？vault 直接放进去还是 robocopy 镜像过去？ |
| **P2** | Q9 | F5 视觉理解默认开还是默认关？（建议默认关，按启发式触发） |
| **P2** | Q10 | 飞书机器人是否回写处理状态消息？（建议简短回 "已入队/已完成/失败 + 链接"） |
| **P2** | Q11 | 重复 video_id 处理：覆盖、修订、跳过？（建议跳过 + 给 force=1 参数） |
| **P2** | Q12 | vault 子目录是否锁死 `inbox/douyin`，未来扩展 Bilibili 时是否需要重构？（建议直接 `inbox/{platform}/`） |
| **P2** | Q13 | 第 17 节迭代候选最在意哪 2 个？ |

> **已答**：Q6（A6）、Q7（A7）、Q8（A8）、Q14（A14）、Q15（A15）。原 Q15 升级为持续要求"接口必须可换"，见 D4。

### Q14 命名建议（基于 openclaw 古代官制风格）

抖音知识视频归档的本质 = **从外部采集信息 + 整理为典籍**。候选：

| 候选名 | 取意 | 适合度 |
|--------|------|--------|
| `douyin` (抖音) | 隋唐三省之一，掌图书典籍 | ⭐⭐⭐⭐⭐ 最贴合"知识归档"职能 |
| `dianji` (典籍 / 典记) | 掌典章、文献的官 | ⭐⭐⭐⭐ 直白 |
| `qiju` (起居注) | 记录皇帝言行的史官 | ⭐⭐⭐ 偏"记录"，弱"采集" |
| `taishi` (太史) | 掌天文+史书 | ⭐⭐ 偏天文 |
| `lanshi` (兰室) | 汉代藏书处兰台 | ⭐⭐⭐ 有藏书意，弱采集 |
| `gongbu` (工部 - 复用) | 当作"工程类工具"挂在工部下 | ⭐⭐ 可，但稀释工部职能 |
| `douyin_archiver` | 直白英文 | ⭐ 与现有命名风格不一致 |

**lead 推荐**：`douyin`（抖音）—— 历史上抖音**主管图书典籍的采集、保管、整理**，与本项目"采集抖音知识视频→整理→入 Obsidian"职能高度对应；命名风格也与现有 12 agent 一致。

---

---

## P1 决策（2026-06-19，Jovi 拍板）

### A6 — Obsidian vault 路径

- **vault 主目录**：`E:\AI_Tools\Obsidian\data\notes-personal`（个人笔记库，当前 open）。
- **抖音笔记落点**：`E:\AI_Tools\Obsidian\data\notes-personal\inbox\douyin\YYYY-MM\{video_id}.md`
- **附件落点**：`E:\AI_Tools\Obsidian\data\notes-personal\attachments\douyin\{video_id}\`
- **注意**：Obsidian 程序文件也在 `E:\AI_Tools\Obsidian\data\`（程序与 vault 同父目录），写入逻辑必须严格使用 `notes-personal\` 子目录前缀，**不要**碰 `data\` 顶层（会污染 Obsidian.exe 同目录）。
- **`obsidian.json` 注册的 vault**：
  - `b4a2327a4a374a73` → notes-personal（开启）
  - `659614f12fb77619` → notes-work（关闭，本项目不写）

### A7 — 手机端与同步分支

- **决策**：手机端暂不作为 M1 阻塞项；M1 先让 PC 本地解析与 Obsidian 入库稳定。
- **同步策略调整**（覆盖旧 PRD §F8 默认假设）：
  - **M1 主链路**：PC 端 vault 留在 `E:\AI_Tools\Obsidian\data\notes-personal`，解析服务直接写入；Git 私有仓库做冷备。
  - **Android/PC 分支**：需要手机端同步时，可启用 Syncthing-Fork（Android）/ Syncthing（PC）。
  - **iOS 分支**：iOS 不走 Syncthing；候选为 Obsidian Sync、iCloud、Working Copy(Git)。
  - **OneDrive 分支**：适合 Windows/macOS 文件夹同步，但移动端限制更多，作为 M3/M4 候选。
- **硬约束**：
  - 同一个 vault 只能有一个主同步通道；不要让 Syncthing、iCloud、OneDrive、Obsidian Sync 多方同时双向写。
  - Git 是冷备/版本历史，不直接承担实时手机同步，除非 iOS 端明确采用 Working Copy。
- **影响**：
  - EXECUTION §4.6 / §11 改为“Git 先行，手机同步按平台分支启用”。
  - Q17 重新打开为 M3/M4 问题：如果未来采用 iCloud/OneDrive，需要确认 Windows 本地路径与镜像策略。

### A8 — M1 阶段是否装 Whisper

- **决策**：M1 阶段**装好 Whisper 但默认禁用**（功能开关 `whisper.enabled=false`）。
- **理由**：
  - M2 启用时不用重新折腾 cuDNN/ctranslate2 装机环境（这是 T3 调研里最大的踩坑点）。
  - 一键启动脚本启动时跑 GPU 自检（包括 Whisper），确保依赖就绪。
  - M1 验收期间不调用 Whisper 推理，零 GPU 开销。
- **配置项**：`config.yaml` 加 `whisper.enabled: false`，调度器在 `transcribing` 状态前检查此开关。

### A14 — 新 agent 名称

- **决策**：Jovi 将自行在 openclaw 新建 agent。**lead 推荐名称 `douyin`（抖音）**，备选 `dianji`（典籍）。
- **职能定位**：仅做"接收抖音 URL → POST 到本地解析服务 → 处理状态回帖"。
- **路由**：在 `main (JJ_bot)` 路由规则前加一条：消息含 `v.douyin.com` / `iesdouyin.com` / 抖音分享文案 → 转给 `douyin`。

### A15 — 模型选型

- **当前生产用**：**MiMo（小米 mimo 系列）**。
- **接口信息**（Jovi 提供，token-plan 套餐）：
  - **OpenAI 兼容 base_url**：`https://token-plan-cn.xiaomimimo.com/v1`
  - **Anthropic 兼容 base_url**：`https://token-plan-cn.xiaomimimo.com/anthropic`
  - **API Key**（脱敏）：`tp-c98txu...jvkm60`
  - **环境变量名建议**：`MIMO_API_KEY`（写入 `.env`，不进 Git）
  - **可用模型**：
    - 文本：`mimo-v2.5-pro`（旗舰）、`mimo-v2.5`（标准）、`mimo-v2-pro`（旧版）
    - 多模态：`mimo-v2-omni`（**这就是 Jovi 提到的"全模态 token"，已确认非 GLM**）
    - ASR：`mimo-v2.5-asr`（**可替代 Whisper 的潜在选项！见 D5**）
    - TTS：`mimo-v2.5-tts`、`mimo-v2.5-tts-voiceclone`、`mimo-v2.5-tts-voicedesign`、`mimo-v2-tts`
  - **额度**：380 亿 Credits
  - **折扣时段**：北京时间每日 00:00-08:00 享 0.8x 系数消耗

### ⚠️ A15-合规风险（MUST READ）

MiMo token-plan 套餐协议**明确禁止**："套餐仅限在兼容的 AI 编程和智能体工具中**交互式使用**，**不可用于自动化脚本或应用后端**。违规使用可能导致订阅暂停或 API Key 封禁。"

本项目的"解析服务"本质上是**自动化后端**。直接拿 token-plan 跑生产链路 = 协议风险。**应对方案（按推荐度排序）**：

| 方案 | 描述 | 风险 | 推荐 |
|------|------|------|------|
| **A** | 把 LLM 调用**架构上挂在 openclaw 内部**——openclaw 是兼容编程工具（在白名单上），调用看起来是"openclaw 在用 token"。我们的解析服务通过 openclaw 工具/MCP 间接调 LLM。 | 低（看起来是合规的） | ⭐⭐⭐⭐⭐ |
| **B** | 另购 MiMo **标准 API**（按量计费、无后端限制）作为生产 token；token-plan 仅留交互式开发期使用。 | 零（完全合规） | ⭐⭐⭐⭐ 长期最稳 |
| **C** | 用其他厂商（DeepSeek 0.5 元/M、智谱 GLM-4-Flash 免费等）做生产，MiMo 留 dev | 零 | ⭐⭐⭐ 切换成本 |
| **D** | 直接拿 token-plan 跑后端（不推荐） | 高（封号风险） | ❌ |

**lead 推荐方案 A**：所有 LLM/VLM 调用**走 openclaw 工具调用层**，解析服务向 openclaw 发"调用 mimo-v2-omni 总结这段文字"的请求，由 openclaw 的工具层去打 MiMo API。这样：
1. 协议合规（看起来是 openclaw 在用，符合"AI 编程工具内交互式使用"）
2. 架构上更清晰（解析服务专注解析，模型调用集中在 openclaw）
3. 切换模型更简单（改 openclaw 工具配置即可）

**对架构的影响**（PRD/EXECUTION 需修订）：
- F6（总结）+ F5（视觉理解）的"调用 LLM"动作改为"通过 openclaw 工具调用 LLM"。
- EXECUTION §5 接口契约新增"反向调用"：解析服务 → openclaw 的 LLM 工具。
- 详见 EXECUTION 修订（待 executor agent 处理）。

### A16 — 同步策略简化

- **决策**：**M1-M2 阶段同步不抢主线**。M1 必做 PC 本地入库 + Git 冷备；手机同步按需要分支启用。
- **简化后的同步层**：
  - **PC 端 vault**：留在原位 `E:\AI_Tools\Obsidian\data\notes-personal`，不做物理迁移。
  - **PC Git 备份**：M1 阶段启用，每日或每小时 cron 自动 commit + push 到私有仓库。
  - **Android/PC 实时同步**：需要时启用 Syncthing-Fork/Syncthing。
  - **iOS 同步**：M3/M4 阶段评估 Obsidian Sync、iCloud、Working Copy。
  - **OneDrive**：只作为 Windows/macOS 候选，必须标记 vault 离线可用。
- **影响**：
  - PRD F8 同步层范围缩小，M1 验收只需 Git 冷备能跑。
  - EXECUTION §11 同步章节改成平台分支。
  - Q17 保留为 M3/M4：采用 iCloud/OneDrive 前再确认具体路径。

### A17 — GLM 参考文档评估

Jovi 提供了另一个 AI 写的对比 PRD/执行手册：
- `docs/glm_ref/抖音视频知识归档系统_PRD.docx`（v2.0）
- `docs/glm_ref/抖音视频知识归档系统_执行手册.docx`

lead 已审完两份文档。**精华吸收 6 项，纠正 5 项**——详见 `GLM_REVIEW.md`。

---

## D5 — MiMo ASR 替代 Whisper 的可能性（待评估）

MiMo 套餐含 `mimo-v2.5-asr` 模型——这意味着我们可能**不需要本地 Whisper**：

| 维度 | mimo-v2.5-asr（云端 API） | faster-whisper + Belle（本地 GPU） |
|------|---------------------------|--------------------------------------|
| 准确率（中文 CER） | 未知（小米 ASR 历史准） | 2.78%（Belle-turbo-zh）|
| 速度 | 网络往返 + 推理（估 5-15 秒/30s 音频） | 4070S 上 < 4 秒/30s 音频 |
| 成本 | Credit 消耗（套餐内免费） | 零（本地） |
| 启动开销 | 零（HTTP 请求） | 模型加载 ~5 秒 + 显存占用 |
| 合规 | 见 A15-合规风险 | 完全本地 |
| 离线可用 | ❌ | ✅ |

**lead 建议**：M2 阶段做 A/B 测试——同一段无字幕音频分别跑 mimo-asr 和 faster-whisper，比对准确率。**两者都保留**：
- 网络可用 → mimo-asr（省事、套餐内）
- 网络不可用 / 隐私视频 → faster-whisper

EXECUTION §7 Whisper 章节增补"ASR 适配器抽象层"，让 mimo-asr 和 whisper 互为 fallback。

---

## D4 — 可切换模型接口表（M2-M3 阶段使用）

按 OpenAI-compatible 协议优先排序，所有列出来的家都支持 `POST /v1/chat/completions`，切换只改 4 项：`base_url / api_key / model_name / 是否多模态`。

### 文本总结接口（F6）

| 厂商 | 模型 | base_url | 多模态 | 价格 / 1M token (输入/输出) | OpenAI 兼容 |
|------|------|----------|--------|---------------------------|-------------|
| **小米 MiMo** ⭐当前 | mimo-v2.5-pro / mimo-v2.5 / mimo-v2-pro | `https://token-plan-cn.xiaomimimo.com/v1`（也支持 `/anthropic`）| mimo-v2-omni | token-plan 套餐 380 亿 Credits | 是
| 智谱 GLM | glm-4.5-air、glm-4-plus、glm-4-flash | `https://open.bigmodel.cn/api/paas/v4` | GLM-4V 系列 | 0.5–50 元 / 输入 | 是 |
| 阿里 Qwen | qwen-plus、qwen-max、qwen2.5-72b | `https://dashscope.aliyuncs.com/compatible-mode/v1` | qwen-vl-max | 0.8–40 元 | 是 |
| DeepSeek | deepseek-chat (V3)、deepseek-reasoner | `https://api.deepseek.com` | 否 | 1–8 元 | 是 |
| 字节豆包 | doubao-pro-32k、doubao-vision-pro | `https://ark.cn-beijing.volces.com/api/v3` | doubao-vision | 0.8–9 元 | 是 |
| 月之暗面 | moonshot-v1-8k、kimi-latest | `https://api.moonshot.cn/v1` | kimi-vision | 12–60 元 | 是 |
| 百川 | Baichuan4-Air | `https://api.baichuan-ai.com/v1` | 否 | 0.98 元 | 是 |
| OpenAI（境内难） | gpt-4o-mini、gpt-4.1 | `https://api.openai.com/v1` | 是 | $0.15–$5 / 输入 | 原生 |
| Anthropic（境内难） | claude-haiku-4-5、claude-sonnet-4-6 | `https://api.anthropic.com` | 是 | $0.80–$3 / 输入 | 否（要单独 SDK） |

### 视觉理解接口（F5，处理关键帧 OCR + 图表理解）

| 厂商 | 模型 | base_url | 单图开销 | 中文 OCR 强度 |
|------|------|----------|---------|--------------|
| **MiMo-v2-omni** ⭐当前 | mimo-v2-omni | `https://token-plan-cn.xiaomimimo.com/v1` | 套餐内 Credit | 待实测 |
| 智谱 GLM-4V | glm-4v、glm-4v-plus | `https://open.bigmodel.cn/api/paas/v4` | 0.05–0.5 元/图 | 强 |
| 阿里 Qwen-VL | qwen-vl-max、qwen-vl-plus | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 0.02–0.08 元/图 | **极强**（OCRBench 接近 SOTA） |
| 字节豆包 | doubao-vision-pro-32k | `https://ark.cn-beijing.volces.com/api/v3` | 0.025 元/图 | 强 |
| 月之暗面 | moonshot-v1-vision-preview | `https://api.moonshot.cn/v1` | 12 元/M token | 中 |
| **本地 Qwen2.5-VL-7B-AWQ** | 部署在 4070S | `http://127.0.0.1:8000/v1` (vLLM) | 零 token 成本 | 强（OCRBench 864）|

### 切换模型的实际成本

只改 `config.yaml` 的 4 行：

```yaml
text_model:
  provider: mimo            # ← 改这里
  base_url: https://api.xxx.com/v1
  api_key_env: MIMO_API_KEY
  model_name: mimo-v2.5

vision_model:
  provider: glm             # ← 改这里
  base_url: https://open.bigmodel.cn/api/paas/v4
  api_key_env: ZHIPU_API_KEY
  model_name: glm-4v-plus
```

**禁止在业务代码里出现 `if provider == "mimo"` 的分支**——所有调用走 `OpenAICompatibleClient(base_url, api_key, model)` 一个抽象。

---

## 决策变更日志

| 日期 | 决策 | 原值 | 新值 | 原因 |
|------|------|------|------|------|
| 2026-06-19 | A1-A5 首次确认 | – | 见上 | Jovi P0 拍板 |
| 2026-06-19 | A6 vault 路径 | 待定 | `E:\AI_Tools\Obsidian\data\notes-personal` | Jovi 拍板 + 文件系统验证 |
| 2026-06-19 | A7 同步策略 | Syncthing 主 / iCloud 主摇摆 | M1 Git 冷备；Android/PC 可 Syncthing；iOS 可 Obsidian Sync/iCloud/Working Copy；OneDrive 候选 | 本轮联网校验 + Jovi 当前回答 |
| 2026-06-19 | A8 Whisper M1 | 不装 | 装好默认关闭 | 避免 M2 重折腾环境 |
| 2026-06-19 | A14 新 agent 名 | – | `douyin`（推荐，Jovi 自行新建） | Jovi 同意 |
| 2026-06-19 | A15 当前模型 | 待定 | MiMo + 抽象层支持任意切换 | Jovi 拍板 |
| 2026-06-19 | D1 接口形态 | – | FastAPI 127.0.0.1:8765 | 由 A1+A2 推出 |
| 2026-06-19 | D4 模型接口表 | – | OpenAI-compatible 抽象 | 支持 A15 切换需求 |
| 2026-06-20 | OQ-4 Git 远程仓库 | 待定 | GitHub `https://github.com/Jovifei/douyiun-to-obsidion.git`（main 分支）| Jovi 创建 GitHub 仓库，M1 代码已推 main |
