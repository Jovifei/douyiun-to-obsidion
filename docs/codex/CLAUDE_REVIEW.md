# Codex 对 `docs/claude` 的审核结论

> 日期：2026-06-19
> 审核对象：`docs/claude/PRD.md`、`docs/claude/EXECUTION.md`、`docs/claude/DECISIONS.md`、`docs/claude/research/*`、`docs/claude/verify/T9-review.md`
> 输出原则：同意的吸收到 `docs/codex`；不同意的直接反驳并保留理由。

## 总判

Claude 的主方案总体可采纳：它已经覆盖“飞书/OpenClaw 入站、本地 PC 常驻解析、字幕优先、Whisper 兜底、OCR/VLM 可选、Markdown 直写 Obsidian、Git/同步分支”的主链路。Codex 已将 Claude 主文档恢复为 `docs/codex` 基底，并在此基础上追加本轮审核吸收项。

## 已采纳并吸收

| 项 | Claude 观点 | Codex 处理 |
|---|---|---|
| B1 PaddleOCR 3.x API | 旧 `use_angle_cls/use_gpu/.ocr()` 不可用，必须用 `PaddleOCR(lang="ch", device="gpu")` 与 `.predict()` | 已采纳，保留在 `EXECUTION.md §8.2`，并修正环境验证命令 |
| B2 字幕来源判定 | 不能靠 `*.srt` 文件名区分创作者字幕/自动字幕，必须读 `info_dict["subtitles"]` 与 `automatic_captions` | 已采纳，保留在 `EXECUTION.md §6.1` |
| B3 uploader_id | yt-dlp 无 `author_uid`，应从 `uploader_url` 提取 `sec_uid` 写 `uploader_id` | 已采纳，保留在 `EXECUTION.md §10.1` 与 PRD schema |
| B4 claimed_at | SQLite dequeue 必须原子 claim，启动时回收 zombie task | 已采纳，保留在 `EXECUTION.md §5.5` |
| B5 OpenClaw STOP | M1 开始前必须确认 OpenClaw 通道/部署/通信/配置版本 | 已加强，新增 `EXECUTION.md §0` STOP 块和 `§5.0` CAUTION |
| S2 显存释放顺序 | 固定 `Whisper -> OCR -> VLM -> LLM`，避免显存碎片和共存 OOM | 已吸收到 `EXECUTION.md §8.2` |
| S3 重启追赶测试 | 需要模拟 scheduler 崩溃后重启继续处理 | 已新增 `EXECUTION.md §14.4` |
| S4 correlation_id | 日志要用一个 ID 串起整条管线 | 已吸收到 `EXECUTION.md §15.2` |
| S5 大附件门禁 | >50MB 文件不能混入主同步通道 | 已新增 `EXECUTION.md §11.6` |
| S6 模块依赖图 | 除架构图/时序图外，还需要模块依赖图 | 已新增 `EXECUTION.md §1.2.1` |
| S7 ASR 超时降级 | Whisper 不能无限卡住 worker，超时保留中间产物 | 已新增 `EXECUTION.md §7.6` |
| S8 cookie known-good 探活 | cookie 预检应支持已知可访问视频 URL | 已增强 `EXECUTION.md §13.4` |

## 直接反驳

### R1：反驳“GLM token 75% 是有效开放问题”

Claude T9 仍把 “GLM token 75%” 当作待确认判断。这个已经过时。Jovi 后续确认当前可用的是 MiMo token-plan，且 `DECISIONS.md A15/D4` 已改为 MiMo 当前可用、OpenAI-compatible 抽象、云厂商可切换。

Codex 决策：

- M1 不依赖云端 GLM/MiMo。
- M2/M3 统一走 OpenAI-compatible 抽象，不把业务代码绑死在 GLM 或 MiMo。
- MiMo token-plan 存在自动化后端协议风险，生产链路应优先本地模型或另购标准 API。

### R2：反驳“断网离线追赶测试等于重启追赶测试”

Claude 执行文档已有 `§14.3 离线追赶测试`，但它测试的是网络恢复，不等价于进程崩溃/重启恢复。T9 的 S3 指的是“队列里 pending/processing，服务重启后继续处理”。

Codex 处理：

- 保留 Claude 的离线追赶测试。
- 新增 `§14.4 重启追赶测试`，验证 `reclaim_zombie_tasks()`、pending 消化和重复写入防护。

### R3：反驳“手机同步是 M1 必需项”

Claude research/T5 早期目标用户写成 Android 手机随身，并把 Syncthing 作为主同步。Jovi 当前需求更明确：解析链路先在 PC 常驻，手机端同步可以后置，且 iOS/Android 路径不同。

Codex 决策：

- M1 必做：PC 本地 vault + Git 冷备。
- Android/PC：可选 Syncthing-Fork/Syncthing。
- iOS：Obsidian Sync / iCloud / Working Copy 三选一。
- 不允许多个双向同步通道同时写同一个 vault。

### R4：反驳“OpenClaw YAML 工作流现在替代 Python 调度器”

Claude/GLM 的 YAML 工作流范式有参考价值，但当前不能替代 Python scheduler。原因是 4070S 12GB 下必须精细控制 Whisper/OCR/VLM/LLM 的串行加载和释放，OpenClaw YAML 当前没有显存资源约束语义。

Codex 决策：

- M1-M3 主调度仍是 Python scheduler。
- OpenClaw YAML 只保留为未来替代选项或 IO 密集步骤编排参考。

## 下一步进入 M1 前的 Codex 检查

- 确认 `docs/codex/EXECUTION.md §0` 和 `§5.0` 的 OpenClaw STOP 块已读。
- 确认 `docs/codex/WEB_RESEARCH_2026-06-19.md` 作为同步与 Obsidian 官方资料来源。
- 确认 `docs/codex/PRD.md F8` 仍是 Git 冷备优先，手机同步分支启用。
- 确认 `docs/codex/EXECUTION.md §14.4` 重启追赶测试纳入 M1 验证清单。
