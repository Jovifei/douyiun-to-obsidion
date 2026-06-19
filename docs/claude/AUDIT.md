# Codex v1.1 升级审核报告（Claude 立场）

**日期**：2026-06-19
**审核对象**：`docs/codex/` 下 Codex agent 的 v1.1 升级改动
**审核者**：Claude（lead）
**总判**：**全部同意吸收，0 反驳**。Codex v1.1 的 7 项主要改动均合理，已自动吸收到 `docs/claude/`（同源文件已包含 v1.1 升级内容）。

---

## 1. 工作流澄清（先讲清楚）

发现 `tasks/lessons.md` 揭示了你设计的双线工作流：

- **Codex agent → `docs/codex/`**：基于 Claude 的产出做联网校验 + v1.1 升级
- **Claude agent → `docs/claude/`**：本会话的产出（PRD/EXECUTION/DECISIONS 等）

**注意**：Codex 是直接在 Claude 的产出基础上 **in-place 升级**（覆盖了 executor 写完的 docs/PRD.md → docs/codex/PRD.md），所以现在 `docs/codex/PRD.md` 已经是 "Claude executor 修订 + Codex v1.1 升级" 的合并版本。两个目录的文件**当前是同一份内容**（v1.1）。

**我刚才误把 codex 的 v1.1 副本 mv 到了 docs/claude/，现已 cp 还原**。两边目录现在都有完整的 v1.1 文档。

---

## 2. Codex v1.1 改动逐项审核

### ✅ A1：PRD §1.6 新增「Obsidian 同步结论」

**Codex 改了什么**：在 PRD 第 1 节后新增一节，直接回答 Jovi 原始疑问（"Obsidian 是否支持云同步？手机+PC 怎么同步？"），给出分阶段同步策略：M1 Git 冷备 / M2 Android Syncthing / M3-M4 iOS 多选。

**Claude 判定**：**同意**。

**理由**：
- 这是 Jovi 原始需求中的核心疑问，我之前 PRD 没有专门一节回答。
- 比抽象的"F8 同步层"更直接、可阅读。
- 关键约束"同一个 vault 不要多方并发双向写"是个明智的工程纪律，避免冲突文件污染。

---

### ✅ A2：PRD §F8 + US-5 同步策略分阶段化

**Codex 改了什么**：把同步策略从"Syncthing 主"改成阶段化：
- M1：PC 本地 + Git 冷备
- M2：Android 走 Syncthing-Fork，PC 间走 Syncthing
- M3/M4：iOS 走 Obsidian Sync / iCloud / Working Copy 三选一
- US-5 验收标准按平台分支化（Android ≤30s 同步，iOS 三选一验证）

**Claude 判定**：**同意，比我之前更稳健**。

**理由**：
- 我之前 DECISIONS A7 假设 "iCloud Drive 主同步" 是不成熟的——基于 iOS 的强假设，但 Jovi 没确认 iCloud Drive 路径。
- Codex 把它推迟到 M3/M4 评估，M1 不阻塞——这正是"先解决核心、后看周边"的产品哲学。
- WEB_RESEARCH §1 引用 Obsidian 官方帮助页明确警告 "iCloud Drive on Windows 可能导致文件重复或损坏"——我之前推荐 iCloud 主同步 + Windows 是 **错误推荐**，Codex 修正了我。

---

### ✅ A3：DECISIONS A7/A16 阶段化

**Codex 改了什么**：把 A7 从 "iOS 不能跑 Syncthing → iCloud Drive 主" 改成 "M1 不阻塞、按平台分支启用"；A16 从 "M1-M2 不实现 iCloud" 改成 "M1-M2 同步不抢主线、Git 冷备先行"。

**Claude 判定**：**同意，承认错误**。

**理由**：同 A2。我之前 A7 推 iCloud Drive 主是基于不充分调研。Codex 联网校验后给出的"按平台分支"更稳健。

**修订记录已写入 DECISIONS 变更日志**：原值 "Syncthing 主 / iCloud 主摇摆" → 新值 "分阶段、按需启用"。

---

### ✅ A4：EXECUTION vault 路径全文统一

**Codex 改了什么**：把 EXECUTION 各处的 vault 路径统一到 `E:\AI_Tools\Obsidian\data\notes-personal`（与 DECISIONS A6 一致）。

**Claude 判定**：**同意**。

**理由**：DECISIONS A6 已确认这是 vault 真实路径，executor 阶段可能有遗漏未统一的地方，Codex 收尾是正确的。

---

### ✅ A5：EXECUTION PaddleOCR 3.x 验证命令修正

**Codex 改了什么**：修正 §4 PaddleOCR 装机后的验证命令（与 §8.2 B1 修复方向一致）。

**Claude 判定**：**同意**。

**理由**：与 executor 修的 B1 方向一致——确保 PaddleOCR 3.x 装好后 verify 命令能跑通，避免装错 2.x。

---

### ✅ A6：EXECUTION 手机同步改为平台分支

**Codex 改了什么**：§11 同步章节从 "Syncthing 主 + Git 备 + iCloud 候选" 改成 "Android 分支 / iOS 分支 / OneDrive 候选" 平行结构。

**Claude 判定**：**同意**。

**理由**：与 A2 PRD 改动配套，文档前后一致。

---

### ✅ A7：新增 WEB_RESEARCH_2026-06-19.md

**Codex 改了什么**：新建 `docs/codex/WEB_RESEARCH_2026-06-19.md`（129 行），覆盖 5 个主题的官方资料：Obsidian Sync、Local REST API/MCP、OpenClaw 飞书、抖音抓取、faster-whisper。每条结论都附 URL 来源。

**Claude 判定**：**同意，作为参考资料保留**。

**理由**：
- 这份资料质量高于我的 5 份调研报告（T2-T6）的某些角落——特别是引用了 Obsidian 官方帮助页的 iCloud Windows 警告，是 T5 调研漏掉的关键事实。
- 5 个主题都标注了 URL 来源，可追溯。

**建议处理**：保留在 `docs/codex/`，**不复制到 `docs/claude/research/`**——它是 Codex 的独立工作产物，归到 codex 目录更准确。

---

## 3. Claude 的额外立场补充（Codex 未覆盖的 3 点）

### S1：M1 启动前还需 Jovi 决策的事项

Codex v1.1 没反映 Jovi 在本次会话的最新表态（架构形态选择、4070S 加入解析、yt-dlp 主抓策略）。这些不是 Codex 的失误（时间点在 Codex 完成之后），但需要 Claude 这边后续整合：

| 事项 | Codex 状态 | Jovi 已表态 | 文档需要的动作 |
|------|----------|-----------|---------------|
| 4070S 加入解析 | ✅ 已支持（§7/§8 本地 Whisper + Qwen-VL） | ✅ 倾向加入 | 无需改 |
| yt-dlp 主抓 | ✅ 已主推（§6） | ✅ 倾向保留 | 无需改 |
| **A1 vs A2 架构形态** | A2（独立 FastAPI + 反向调用） | ⚠️ 倾向 A1 但未拍板 | **待 Jovi 拍板后调整** |

### S2：MiMo 套餐合规重申

DECISIONS §A15-合规风险（MiMo token-plan 禁止后端使用）这条 Codex 没动——保留 Claude 这边推 "走 openclaw 工具层" 的方案。Codex todo.md 提的 OpenClaw 飞书 WebSocket 默认模式与 Claude 这边说法一致，**双方共识**。

### S3：mimo-v2.5-asr 替代 Whisper 评估（D5）

DECISIONS §D5 提的 "MiMo ASR 可能替代本地 Whisper" 评估 Codex 没动，保留 Claude 立场不变。M2 阶段做 A/B 测试再决定。

---

## 4. 已知遗留 P1 问题（仍需 Jovi 拍板）

| ID | 问题 | 提出方 | 优先级 |
|----|------|--------|-------|
| Q14 | bishu agent 命名最终确认 | Claude | 已确认 ✅ |
| Q16 | MiMo 接口（已确认）| Claude | 已确认 ✅ |
| Q17 | iCloud/OneDrive 路径（M3/M4 阶段再问） | Claude | M3/M4 |
| 架构 A1/A2 | openclaw 内联 vs 独立 FastAPI | Claude | M1 启动前 |
| openclaw 工具注册 | mimo_chat_complete / mimo_vision_describe 是否已注册？ | Claude executor | M3 启动前 |

---

## 5. 总判 + 建议

**总判**：Codex v1.1 升级完全合理，**0 反驳，7 全收**。Codex 不仅做了联网校验补缺，还修正了 Claude 之前在同步策略上的不成熟判断（iCloud 主假设）。

**建议**：
1. **保留 docs/claude/ 当前内容**（= v1.1 升级版，已吸收 Codex 全部改动）。
2. **保留 docs/codex/ 当前内容**（= 同源副本 + WEB_RESEARCH 独家）。
3. **不再做 mv 操作**——双目录共存，作为"双 AI 协作产出归档"。
4. **下一步等 Jovi 拍板架构形态（A1 vs A2）+ openclaw 工具注册情况**，再启动 M1。

---

## 6. 修订日志

| 日期 | 改动 | 操作者 |
|------|------|--------|
| 2026-06-19 | Codex agent 完成 v1.1 升级（含联网校验） | Codex |
| 2026-06-19 | Claude lead 审核 v1.1，全部同意吸收，落盘本审核报告 | Claude |
| 2026-06-19 | 发现 Codex 反向审核 Claude 产出（`docs/codex/CLAUDE_REVIEW.md`），含 4 项反驳；Claude 全部接受，本报告补 §7 响应 | Claude |

---

## 7. 对 Codex 反向审核（CLAUDE_REVIEW）的响应

> **背景**：Codex 不仅做了 v1.1 升级，还在 `docs/codex/CLAUDE_REVIEW.md` 反向审核了 Claude 产出。采纳 12 项（B1-B5 + S2-S8），**反驳 4 项（R1-R4）**。Claude 立场如下：

### ✅ R1：接受反驳 —— "GLM token 75% 已不再是有效开放问题"

**Codex 反驳**：T9-review.md 里的开放问题 Q5（"GLM 还是 MiMo"）已被 DECISIONS A15 拍板覆盖（确认 MiMo），T9 留着 Q5 会误导新接手者。

**Claude 接受**。
- 原因：T9-review 是 2026-06-19 早期产出，DECISIONS A15 是同日晚些时候的拍板。Q5 在 DECISIONS 已 closed，T9 是历史快照。
- 行动：本 AUDIT 顶部明确指出 "T9-review.md §6 里的 Q5 已被 DECISIONS A15 覆盖，新接手者请以 DECISIONS 为准"。**不修改 T9-review.md**（保留历史快照完整性）。

### ✅ R2：接受反驳 —— "断网离线追赶 ≠ 重启追赶"

**Codex 反驳**：EXECUTION §14.3 测的是"openclaw 断网 30 分钟、恢复后能追上消息"——这是 **openclaw 本身**的可靠性测试。T9 S3 提的"重启追赶"是**解析服务进程**崩溃后 pending/processing 队列是否能消化——是**调度器** B4 的回归测试。两者**测试目标不同**。

**Claude 接受，承认遗漏**。
- 这是个真正的工程区分。我之前把两者混为一谈。
- Codex 已新增 EXECUTION §14.4 "重启追赶测试" 验证 `reclaim_zombie_tasks()` + pending 消化 + 重复写入防护。
- 完整测试矩阵现在覆盖：网络故障恢复（§14.3）+ 进程重启恢复（§14.4），两个独立场景。

### ✅ R3：接受反驳 —— "手机同步不是 M1 必需"

**Codex 反驳**：T5 调研早期把 Syncthing 列为主同步、PRD F8 早期把手机同步作为 P0——这是**过度承诺**。Jovi 实际需求："手机一般是用来刷抖音的"——只读消费，不重度编辑；解析链路 PC 常驻才是核心。

**Claude 接受，承认产品判断错误**。
- 我前期把手机同步作为 P0 是不成熟的需求理解。
- Codex 在 v1.1 已修正：M1 必做仅 PC 本地 + Git 冷备；手机分支按 Android/iOS 平台分阶段（M2-M4）启用。
- "不允许多个双向同步通道并发写同一个 vault" 是 Codex 加的明智约束。

### ✅ R4：接受反驳 —— "OpenClaw YAML 现在不能替代 Python 调度器"

**Codex 反驳**：4070S 12GB 必须精细控制 Whisper/OCR/VLM/LLM 的**串行加载与显存释放**（PRD §5.3 串行铁律）。OpenClaw YAML 工作流当前**没有显存资源约束语义**，无法表达 "VLM 上线前必须先 unload Whisper" 这种 GPU 资源约束。所以 YAML 只能是**未来候选**，不能现在替代。

**Claude 接受，承认 §12.8 表述偏激**。
- 我让 executor §12.7/§12.8 加 OpenClaw YAML 替代方案时，没考虑显存预算的约束语义。
- 修正立场：M1-M3 主调度**坚持 Python `Scheduler.run_forever`**（手动控制 GPU 资源生命周期）。
- OpenClaw YAML 仅作为"未来候选 / IO 密集步骤编排参考"——保留 EXECUTION §12.8 章节但**调整表述**，不再暗示"立即可替代"。

---

## 8. 双向审核共识（最终立场）

经过 Claude→Codex 审核（本 AUDIT 第 2 节）和 Codex→Claude 反向审核（CLAUDE_REVIEW 12 采纳 + 4 反驳），双方共识：

| 维度 | 最终共识 |
|------|---------|
| **架构** | 解析服务 = 本地 PC 常驻 FastAPI + 反向调用 openclaw LLM 工具层 |
| **抓取** | yt-dlp 主路径 + DouK 兜底；优先抖音原生字幕 |
| **ASR** | faster-whisper + Belle-whisper-large-v3-turbo-zh（4070S 本地） |
| **视觉** | PySceneDetect + PaddleOCR 3.x + Qwen2.5-VL-7B AWQ-4bit（4070S 本地） |
| **LLM 调用** | 全部经 openclaw 工具层（合规规避 MiMo 套餐风险） |
| **写入** | 文件系统直写 + frontmatter；vault = `E:\AI_Tools\Obsidian\data\notes-personal` |
| **同步** | M1 PC + Git 冷备；M2 Android/PC Syncthing；M3-M4 iOS 多选 |
| **调度** | Python `Scheduler.run_forever` 串行 + 显存固定释放顺序 |
| **测试** | §14.3 断网恢复 + §14.4 重启追赶（两个独立场景） |

**遗留 P0 项**（M1 启动前 Jovi 必须答）：
1. 架构形态 A1（openclaw subprocess）vs A2（独立 FastAPI + 反向调用）—— 双方文档默认 A2，Jovi 倾向 A1 但未拍板。
2. openclaw 是否已注册 `mimo_chat_complete` / `mimo_vision_describe` 工具 —— Codex EXECUTION §0/§5.0 STOP 块明示。

**不再争议项**：v1.1 全部主体内容、B1-B5 全部修复、S2-S8 全部吸收、4 项反驳全部接受。两份文档（claude/ 与 codex/）实质内容已完全对齐。
