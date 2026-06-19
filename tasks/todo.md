# 抖音知识视频归档到 Obsidian 文档修订 Todo

> 日期：2026-06-19
> 目标：基于 Jovi 当前需求与联网资料，修订 PRD、执行文档和决策记录，让文档可直接指导后续 M1 实施。

## 计划

- [x] 审核 `docs/claude` 执行方案与研究资料，对比 `docs/codex`。
- [x] 对同意项补入 Codex 文档或计划。
- [x] 对不同意项写明反驳理由。
- [x] 验证吸收后的文档路径、引用和 todo 状态。
- [x] 审核 `openspec/changes/m1-douyin-archive-mvp/.comet/handoff/brainstorm-summary.md` 与已生成 design/tasks 是否可进入 build。
- [x] 复审 Comet design v2、tasks v2、5 份 OpenSpec specs 与端口替换结果，判断是否可以启动 build 配置。

## 上轮文档修订计划

- [x] 读取 `$brainstorming` 技能要求，确认先设计与文档化。
- [x] 检查现有项目文件、PRD、EXECUTION、DECISIONS、GLM_REVIEW 与 `.omc/research` 调研。
- [x] 联网校验 Obsidian Sync/同步方案、Obsidian 写入 API、OpenClaw 飞书通道、抖音抓取、faster-whisper 资料。
- [x] 新增联网资料吸收记录，留下来源链接与结论。
- [x] 修订 PRD：同步策略、模型厂商、vault 路径、手机端分支、验收指标。
- [x] 修订 EXECUTION：同步实施步骤、vault 路径、PaddleOCR 验证命令、资料索引。
- [x] 修订 DECISIONS：把本轮“Syncthing -> Git -> iCloud/OneDrive”策略写成阶段决策。
- [x] 自检文档：编码、关键旧词残留、文件存在性、任务状态。

## 过程记录

- 已确认 Obsidian 不负责解析视频内容；解析应由本地 PC 常驻服务完成，写 Markdown 到 vault。
- 已确认 Obsidian 官方支持付费 Obsidian Sync，也列出 iCloud、OneDrive、Google Drive、Syncthing、Git/Working Copy 等替代同步方式。
- 已确认 OpenClaw 飞书通道文档写明 WebSocket 是默认模式，webhook 是可选模式。
- 已确认 Obsidian Local REST API/MCP 可作为增强写入与 AI agent 访问通道，但主链路仍应文件系统直写，降低对 Obsidian GUI 在线状态的依赖。

## Review

- Claude 审核已完成：采纳 B1-B5、S2-S8，并写入 `docs/codex/EXECUTION.md` 与 `docs/codex/CLAUDE_REVIEW.md`。
- 直接反驳 4 项：继续把 GLM token 75% 当有效判断、把断网离线追赶等同于重启追赶、把手机同步作为 M1 必需、用 OpenClaw YAML 立即替代 Python 调度器。
- 已新增 `docs/codex/WEB_RESEARCH_2026-06-19.md`，覆盖 Obsidian Sync/同步方案、Local REST API/MCP、OpenClaw 飞书、抖音抓取、faster-whisper。
- 已把 `docs/codex/PRD.md` 升级到 v1.1，新增“Obsidian 同步结论”，并把 F8 改为 M1 Git 冷备、M2 Android/PC Syncthing、M3/M4 iOS/云盘分支。
- 已修订 `docs/codex/EXECUTION.md`，统一 vault 到 `E:\AI_Tools\Obsidian\data\notes-personal`，修正 PaddleOCR 3.x 验证命令，并把手机同步改为平台分支。
- 已修订 `docs/codex/DECISIONS.md` 的 A7/A16，同步策略不再写死 Syncthing 或 iCloud 单主。
- 自检命令确认 5 个目标文件存在；旧词扫描仅剩历史变更日志里的旧值说明和 PaddleOCR 2.x 反例说明，均为有意保留。
- Comet/OpenSpec 方案审核结论：可进入本地解析服务 build，但飞书端到端 build 需先确认 OQ-1（bishu/openclaw agent 样板）；D-3 复用社区 backend 必须先过 LICENSE；D-5 frontmatter 需补 `summary_status`/`processing_mode` 等状态字段；`8765` 与旧 EXECUTION `18900` 端口残留需统一。
- Comet design v2 复审结论：`phase=build` 状态正确，端口替换已验证；但 build 配置前需修正 D-3 残留 vendoring 文案，以及 task queue 的 `processing`/`fetching` 状态机不一致。
- Comet design v2 二次复核：主要 drift 已修复；已清理 `tasks.md` 中残留的 `processing` health/zombie 文案，并修正 design 中 vendoring 删除线说明。
- Plan-ready 复审通过：`docs/superpowers/plans/2026-06-19-m1-douyin-archive.md` header/base-ref 正确，D-3/D-4/D-9/D-10 与 OQ-1 分组已落地；3 个 plan TODO 不阻塞 Step 3。
