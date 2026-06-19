# T9 评审：PRD + EXECUTION

**评审日期**：2026-06-19
**评审范围**：`docs/PRD.md`、`docs/EXECUTION.md` + 全部 5 份调研报告
**评审主体**：critic agent（Opus）+ lead 整合
**说明**：critic agent 因 sandbox 写权限受限，未直接落盘原始评审正文；本文档由 lead 整合 critic 的核心判定 + 已知项目上下文补全。

---

## 1. 总判

**通过但有改进项**。

主线设计扎实，调研采纳完整，4070S 12G 串行铁律在调度器代码层真实落地（不是文档口号）。**5 个阻塞项需要在 M1 启动前修复**，修完即可启动开发。

---

## 2. 阻塞性问题（必须修，按严重度排序）

| ID | 严重度 | 文档/位置 | 问题 | 建议修法 |
|----|-------|----------|------|---------|
| **B1** | 🔴 高 | EXECUTION §8.2 | PaddleOCR 代码骨架用了 2.x 老 API（`use_angle_cls=True`、`use_gpu=True`、`det_model_name`、`show_log=False`、`.ocr(img, cls=True)`），PaddleOCR 3.0+ 全部失效，按骨架直跑会 `TypeError: __init__() got an unexpected keyword argument`。 | 切到 3.x API：构造改 `PaddleOCR(lang="ch", device="gpu", text_recognition_model_name=...)`；调用改 `.predict(img)` 返回结构化 dict 而非旧 list。或固定依赖到 `paddleocr<3.0` + 注释解释。 |
| **B2** | 🟠 中 | EXECUTION §6.1 | 字幕"自动生成 vs 创作者上传"判定靠扩展名 glob，但 yt-dlp 两类输出文件名都是 `*.{lang}.srt`，无法区分。 | 改读 `info_dict["subtitles"]`（创作者上传）与 `info_dict["automatic_captions"]`（自动生成）两个 dict，按存在性判断 `caption_source`。 |
| **B3** | 🟠 中 | EXECUTION §10.1 | frontmatter 里 `fetcher.get("author_uid")` 永远为空——yt-dlp 的抖音 info 没有这个字段。 | 从 `uploader_url`（形如 `https://www.douyin.com/user/MS4wLj...`）正则截 `sec_uid`；或写入 `uploader_id` 字段并在 schema 里相应改名。 |
| **B4** | 🟠 中 | EXECUTION §5.5（队列） | dequeue 操作未加占用标记，进程崩溃→重启会重复出队同一条任务。 | 给 SQLite 队列表加 `claimed_at TIMESTAMP NULL` 字段；dequeue 用 `UPDATE ... SET claimed_at=now() WHERE id=(SELECT...) RETURNING *` 原子化；启动时把超过 30 分钟仍未 done 的 `claimed_at` 重置为 NULL。 |
| **B5** | 🟡 中 | PRD §8 + EXECUTION §5.0 | T4 调研列出的 4 个待 Jovi 确认问题（openclaw 运行模式 / 部署位置 / 现有 agent 绑定 / 版本+config 路径）只在 PRD 末尾开放问题表里，文档顶部和 EXECUTION §5 没有醒目 STOP 标记，新接手者容易直接动工。 | 在 EXECUTION §0 阅读指南顶部加红色"启动前必读"块；在 §5.0 用 `> [!CAUTION]` admonition 列出这 4 个未决项 + "未确认时的默认假设"。 |

---

## 3. 建议性问题（可修可不修）

> critic 提到约 15 条建议项，未返回完整文本。lead 基于已知上下文复盘，归纳如下高价值建议：

| ID | 类型 | 描述 |
|----|------|------|
| S1 | frontmatter | `tags` 用 YAML list 而非 inline，给 Dataview 更稳定 |
| S2 | 显存 | EXECUTION §8.6 模型 unload 顺序应固定为 `Whisper → OCR → VLM`（按显存占用从小到大释放，避免碎片） |
| S3 | 测试 | §14 e2e 测试缺一条"重启追赶"场景（模拟队列里有 pending，重启后能消化） |
| S4 | 日志 | §15.2 关键事件需加 `correlation_id`（一个 video_id 串起整条管线日志） |
| S5 | 同步 | `.stignore` 应附 Obsidian 默认 `attachments/` 大文件检测（>50MB 自动拒同步） |
| S6 | 文档 | EXECUTION mermaid 图建议加一张"模块依赖图"补在 §1，与现有时序图互补 |
| S7 | 备选 | F4 Whisper 兜底可加"超时即判失败、保留视频文件供人工"的优雅降级路径 |
| S8 | cookie | §13.4 应加 cookie 过期自动检测（启动时跑一个 known-good URL 探活） |

---

## 4. 表扬点

- ✅ **PRD §5.3 串行铁律真实落地**：EXECUTION §12 调度器是单 worker `asyncio.to_thread` 包同步推理，不是嘴上说说。
- ✅ **依赖矩阵精确**：T3 的 cuDNN 9.x ↔ ctranslate2 ≥4.5.0 配对表被 EXECUTION §4.1/§7.1 完整复用，避免了最大踩坑点。
- ✅ **里程碑切分合理**：M1（字幕优先 MVP）刻意把 Whisper 拿掉，30-40h 即可见到价值——符合"先解决 80% 知识视频"的产品哲学。
- ✅ **frontmatter schema snake_case + 长内容入正文**：完全规避 Dataview 已知索引性能坑。
- ✅ **openclaw 身份判定**：T4 没有靠猜，是用 GitHub REST API 实测复核 + 引用了 `openclaw/openclaw` 真实仓库。
- ✅ **离线追赶**：F9 + EXECUTION §12.6 把"开机扫一遍 pending"明确写为启动钩子，体验闭环。
- ✅ **隐私边界清晰**：cookies.txt、智谱 token、飞书 secret 全部明确不进 Git/Syncthing，且 `.env` 有示例。

---

## 5. 评审清单结果

| 节 | 项 | 结论 | 备注 |
|----|-----|------|------|
| **A 需求覆盖** | A1 PRD 覆盖 7 项原始诉求 | ✅ 通过 | 全覆盖，含"链路如何打通"的明确回答 |
|  | A2 失败路径覆盖 | ✅ 通过 | 无字幕/离线/cookie 失效/反爬变化 4 条均有 |
|  | A3 范围 In/Out 清晰 | ✅ 通过 | Out 表明确"不做飞书 bot 注册" |
| **B 架构假设** | B1 openclaw 角色 | ⚠️ 需修 | 见阻塞项 B5 |
|  | B2 WebSocket vs HTTP | ✅ 通过 | T4 已说清，PRD 采纳 |
|  | B3 离线追赶设计 | ⚠️ 需修 | 见阻塞项 B4 |
|  | B4 串行铁律真落地 | ✅ 通过 | EXECUTION §12 代码层强制 |
|  | B5 GLM token 75% 列为开放问题 | ✅ 通过 | PRD §8 Q5 |
| **C 实施步骤** | C1 cuDNN/ctranslate2 配对 | ✅ 通过 | §4.1 给具体 pip 行 |
|  | C2 openclaw 桥接完整性 | ⚠️ 需修 | 见阻塞项 B5 |
|  | C3 yt-dlp 三件齐 | ⚠️ 需修 | 见阻塞项 B2 |
|  | C4 Whisper 完整性 | ✅ 通过 | BELLE + VAD + 显存自检全 |
|  | C5 视觉骨架完整性 | 🔴 需修 | 见阻塞项 B1（PaddleOCR API） |
|  | C6 Obsidian 原子写 | ⚠️ 需修 | 见阻塞项 B3（uid 字段） |
|  | C7 .stignore/.gitignore | ✅ 通过 | 关键条目都在 |
|  | C8 调度器 5 件齐 | ⚠️ 需修 | 见阻塞项 B4 |
|  | C9 测试可执行 | ✅ 通过 | 给了具体命令 |
| **D 选型一致** | D1 PRD ↔ EXECUTION | ✅ 通过 | 一一对应 |
|  | D2 调研结论被采纳 | ✅ 通过 | 无未解释偏离 |
| **E Frontmatter** | E1 snake_case + YAML list | ✅ 通过 | – |
|  | E2 长内容不入 frontmatter | ✅ 通过 | 字幕/总结都在正文 |
|  | E3 Dataview 查询例子 | ✅ 通过 | 有给最近 10 条查询 |
| **F 安全隐私** | F1 凭证不进版本控制 | ✅ 通过 | – |
|  | F2 日志不泄漏 | ⚠️ 建议 | 见 S4，可加 correlation_id 同时 mask token |
| **G 可读性** | G1 长度与术语 | ✅ 通过 | – |
|  | G2 mermaid 渲染 | ✅ 通过 | 语法干净 |
|  | G3 跨文档引用 | ✅ 通过 | 一致 |

---

## 6. Jovi 必须先做的决策（开放问题汇总）

> 按优先级排序。**P0 是 M1 启动的硬阻塞**，**P1 是 M1 进行中需明确**，**P2 是后续里程碑前明确即可**。

| 优先级 | ID | 问题 | 建议 |
|-------|----|------|------|
| **P0** | Q1 | openclaw 飞书频道当前是 WebSocket 长连接还是 HTTP webhook？ | 跑 `openclaw status` 或看 `~/.openclaw/config.*` 确认 |
| **P0** | Q2 | openclaw 部署在哪台机器、哪个端口、是否同主机与解析服务共置？ | 影响 §5 接口契约（HTTP localhost vs 总线 vs 跨网） |
| **P0** | Q3 | openclaw 现在已经绑定了哪些 agent / hook？飞书消息进来后默认走哪条 chain？ | 决定我们是新增一个 hook 还是在现有 chain 后端串接 |
| **P0** | Q4 | openclaw 版本号和 config.yaml 路径？ | 调研报告以 2025-11 上线版本为准，跨版本可能要做兼容 |
| **P0** | Q5 | "全模态 token" 厂商确认：智谱 GLM？阿里 Qwen？字节豆包？ | 影响 F6 总结层云端 fallback 选型，调研判定 75% 智谱 |
| **P1** | Q6 | Obsidian vault 真实路径？是否软链到 `E:\AI_Tools\Obsidian\Data\notes-personal`？ | 关系 §10.2 文件路径生成 + Syncthing 共享目录 |
| **P1** | Q7 | 手机端 Obsidian 是 iOS 还是 Android？iOS 的 Syncthing 现状有缺口（T5 已警示） | 决定是否需要 Git+Working Copy 优先于 Syncthing |
| **P1** | Q8 | M1 阶段是否真的不要 Whisper（仅字幕优先）？还是希望 M1 就装好 Whisper 但默认关闭？ | 影响 §4 环境准备的安装范围 |
| **P2** | Q9 | F5 视觉理解默认开还是默认关？建议默认关（按启发式条件触发） | 减少 4070S 显存压力 |
| **P2** | Q10 | 飞书机器人是否需要回写处理状态消息（成功/失败提示）？ | 决定 §15.3 告警实现 |
| **P2** | Q11 | 一个 video_id 重复推送时：覆盖、追加修订、跳过？ | §10.5 重复检测策略 |
| **P2** | Q12 | 项目名 / vault 子目录是否锁死 `inbox/douyin`，未来扩展 Bilibili 时是否需要顶层 `inbox/{platform}` 重构？ | 建议直接 `inbox/{platform}/` 结构以减少未来迁移成本 |
| **P2** | Q13 | EXECUTION 第 17 节迭代候选里你最在意哪 2 个？ | 影响是否在 M1 阶段做"扩展点预留" |

---

## 7. 下一步建议（评审通过后立即可做）

1. **Jovi 拍板 P0 决策（Q1-Q5）**：建议通过 5 分钟问答完成，最长 1 小时内能拿到答案。
2. **修阻塞项 B1-B4**（约 30-60 分钟工作量）：B1 改 PaddleOCR 调用、B2 改字幕判定、B3 改 uid 字段、B4 加 claimed_at。可派一个 executor 修。
3. **修 B5 文档高亮**（约 10 分钟）：在 EXECUTION §0 和 §5.0 加 STOP/CAUTION admonition。
4. **建 GitHub repo + push 现有文档**：先把 PRD/EXECUTION/research 落版本控制，避免后续修改丢追溯。
5. **启动 M1 实施第一周**：环境准备（§4 全部步骤 + 验证）+ openclaw 桥接最小可用版（依赖 P0 决策）+ yt-dlp 主路径打通。完成后端到端跑一条带字幕的抖音视频，验证 vault 出笔记。

---

**评审到此结束。修完阻塞项即可启动 M1。**
