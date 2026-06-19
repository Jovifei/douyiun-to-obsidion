# GLM 参考文档评估（v2.0 PRD + 执行手册对比）

> 版本：v1.0  日期：2026-06-19  作者：technical-editor
> 评估对象：`docs/glm_ref/抖音视频知识归档系统_PRD.docx`（v2.0）+ `docs/glm_ref/抖音视频知识归档系统_执行手册.docx`
> 对照基准：本项目 `PRD.md` / `EXECUTION.md` + 调研报告 T2/T3/T6

---

## 摘要

GLM v2.0 PRD 总体方向与本方案一致——**字幕优先 + Whisper 兜底 + 关键帧 VLM + 飞书 bot + Obsidian 文件直写**——但部分技术选型已过时半年到一年，且漏掉了若干本项目调研已经发现的关键优化点。**两份文档可互补**：GLM 的 OpenClaw YAML 范式 + VTT 解析骨架 + 飞书 token 缓存代码值得吸收；我方的 yt-dlp 原生 auto_caption + Belle 中文 ASR + Qwen2.5-VL + cuDNN 9 配对表是 GLM 缺的。

---

## 1. GLM 文档值得吸收的精华（按价值排序）

### 1.1 ⭐⭐⭐⭐⭐ VTT 字幕解析的 Python 完整实现（GLM PRD §4.2，约 40 行）

GLM 给出了完整的 `parse_vtt()` 函数，覆盖时间戳行、HTML 标签清洗（`<c.colorFFFFFF>` 之类）、空行切段、最后一段补齐四种常见坑。**直接可拷**到我方 `EXECUTION §6.6`，作为"yt-dlp 拿到 vtt 后转结构化 segments"的标准实现。本项目原 `subtitle_normalizer.py` 偏向 SRT，对 VTT 处理薄弱，GLM 这段刚好补齐。

### 1.2 ⭐⭐⭐⭐⭐ OpenClaw 工作流声明式 YAML 定义（GLM PRD §4.5，约 80 行）

GLM 用一份 `openclaw-workflow.yaml` 把"事件触发 → URL 抽取 → 去重 → 下载 → 字幕分支 → VLM → 总结 → 写笔记 → 回执"九步声明式串起来，含 `if/then/else`、`on_error`、`on_result` 三类控制流。**这是个好范式**。本项目主调度仍用 Python `Scheduler.run_forever()`（更易调试 + 显存编排紧密），但把 YAML 范式作为 EXECUTION §12.7 的"可选第二种实现"补充进去——未来想把调度逻辑从 Python 迁到 openclaw 工作流配置时有现成参照，且在团队协作场景下声明式 pipeline 比 Python 代码更可观测。

### 1.3 ⭐⭐⭐⭐⭐ Obsidian 角色澄清段落（GLM PRD §1.2，整段约 200 字）

GLM 一句话回答了 Jovi 早期的核心疑问——"Obsidian 能解析视频吗"——给出了清晰边界："**Obsidian 本身不能解析任何视频内容，它只是 Markdown 笔记的读写和展示工具**。正确的架构是让 OpenClaw 调用外部工具链完成解析，将结果以 Markdown 文件形式写入 Vault 目录，Obsidian 通过文件系统监听自动感知。" 这一论点应直接纳入我方 PRD §1（已在本次修订时加入 §1.5 子节）。

### 1.4 ⭐⭐⭐⭐ VLM 调用 prompt 设计（GLM PRD §4.4）

GLM 的 VLM prompt 有一句兜底："**如果画面无重要信息请回复'无关键信息'**。"——避免 VLM 看到说话头/转场帧时硬编出一段虚构描述（典型 VLM 幻觉模式）。我方 `EXECUTION §8.3` 的 `VLM_PROMPT` 没有这条兜底，在调试期建议补一句"无重要信息请只回复'无关键信息'四字"，让分流后处理更鲁棒。

### 1.5 ⭐⭐⭐⭐ 飞书"立即确认 + 异步回执"5 秒响应窗口处理（GLM 执行手册 Phase 6）

GLM 明确指出抖音归档 pipeline 耗时 2-6 分钟，**远超过飞书事件 5 秒响应窗口**——必须采用"收到链接后立即被动回复'已收到，开始处理'，pipeline 完成后通过飞书主动发消息 API 推送结果"双段式。我方 EXECUTION §5.2 `ack_reply` 字段已经踩中这点，但**没有展开"主动发消息"的实现细节**。GLM 的双段式描述工程上更完整。

### 1.6 ⭐⭐⭐⭐ 飞书 tenant_access_token 缓存与刷新代码（GLM 执行手册 §6.4，约 50 行）

GLM 给出了完整 `get_tenant_access_token()` + `send_message()` Python 实现，含：
- token 缓存（`_token_cache` 全局 dict）
- 提前 60 秒刷新（`time.time() < expires_at - 60`）
- 错误码检查（`data.get('code') != 0`）
- `receive_id_type=chat_id` 参数（飞书 v1 API 必传）

直接可拷到我方 `EXECUTION §5.7` 作为飞书主动发消息工具骨架。本项目 `bridge/feishu_reply.py` 当前只在 §15.3 简单 mock，缺这套 token 管理。

---

## 2. GLM 文档的不足（我方调研已覆盖或纠正）

### 2.1 🔴 GLM 完全没注意到 yt-dlp 原生支持 auto_caption（最大盲点）

GLM 在 §4.2 的描述是："yt-dlp `--write-subs` 会优先下载创作者字幕，其次自动 CC 字幕；下载到的是 WebVTT 格式，需要解析为纯文本"——但**没说 yt-dlp 已经实现了抖音 `auto_caption` 抓取逻辑**（T2 调研 §51-59 行明确指出 yt-dlp 的 DouyinIE 继承 TikTokBaseIE，`_get_subtitles()` 同时处理 `interaction_stickers.auto_video_caption_info.auto_captions` 和 `video.cla_info.caption_infos` 两条路径）。这意味着：

- **GLM 假设默认要写 VTT 解析逻辑** → 我方调研发现：开启 `writeautomaticsub=True` + `writesubtitles=True` 后，yt-dlp 直接产出 srt（经 `FFmpegSubtitlesConvertor`），不需要自己解析 VTT。
- **GLM 字幕命中率估算"95%+"是粗估** → 我方按 T2 实测分类："知识类口播视频 80%+ 命中 auto_caption"。
- **GLM 字幕下载链路是次优的**：本质上仍可工作，但无法区分"创作者上传 vs 抖音自动生成"两类来源。我方 EXECUTION §6.1 通过 `info_dict["subtitles"]` vs `info_dict["automatic_captions"]` 双 dict 区分（即 B2 修订点）。

**结论**：直接拷 GLM 的字幕链路会损失 source 元数据，且多写一段 VTT 解析逻辑（虽然 GLM 这段代码本身写得很好，可在 yt-dlp 失败的备援场景里复用）。

### 2.2 🔴 GLM 推荐 Whisper medium + INT8（CER 约 7%），落后 2.5x

GLM 推荐：`WhisperModel('medium', device='cuda', compute_type='int8_float16')`——属于 OpenAI 原版多语言 medium。我方调研 T3 §3 横评表明：

| 模型 | AISHELL-1 CER | 4070S 速度 |
|---|---|---|
| Whisper medium fp16（GLM 推荐） | ~7% | ~30s/5min 视频 |
| Whisper large-v3 fp16 | 4.34% | 1.5x medium |
| **Belle-whisper-large-v3-turbo-zh**（我方推荐）| **2.78%** | 与 large-v3 turbo 持平 |

Belle 是 BELLE-2 团队针对中文场景在 large-v3-turbo 之上**全参数微调**的模型，对方言、口语化、专业术语显著提升。**准确率提升 2.5x，速度无损**——GLM 漏掉这一节是因为 Belle 模型 2025 年底才在 HuggingFace 火起来，GLM 训练数据没覆盖。

### 2.3 🟠 GLM 推荐 Qwen2-VL-7B + Ollama，已可换更新组合

GLM 在 §4.4 推荐"长期切到 Qwen2-VL-7B-Instruct（Ollama 部署）"。我方调研 T6 §C 横评：

| 模型 | OCRBench | 显存（7B） | 4070S 推理 |
|---|---|---|---|
| Qwen2-VL-7B-Instruct（GLM 推荐） | ~820 | ~14 GB fp16 | OOM 风险 |
| **Qwen2.5-VL-7B-Instruct AWQ-4bit**（我方推荐）| **864** | **~6.5 GB** | 稳定 |

Qwen 团队 2025 Q1 发布 2.5-VL 系列，OCRBench 全面提升、AWQ 量化已官方支持。Ollama 当前对 Qwen2.5-VL AWQ 支持不稳定，所以我方走 vLLM/Transformers 直接加载 AWQ。**GLM 漏掉的是模型迭代节奏 + 量化方案的组合优化**。

### 2.4 🔴 GLM 假设 iOS 端可用 Syncthing —— 错误

GLM PRD §4.6 明确推荐"PC 和手机都安装 Syncthing"。**iOS 端无官方 Syncthing 客户端**——第三方 Mobius Sync 已停更（最后版本 2024 年初），App Store 也已下架。这条路径在 iOS 上根本不通。我方 PRD F8 + DECISIONS A7 已纠正：iOS 端走 iCloud Drive（Windows 端 `C:\Users\Admin\iCloudDrive\` 镜像 vault），未来叠加 Working Copy 做 Git。**GLM 的多端同步章节在 iOS 用户那里不可执行**。

### 2.5 🟠 GLM 没有 cuDNN 9 vs 8 / ctranslate2 4.5 配对表 —— 装机最大踩坑点

GLM 执行手册 Phase 0 只检查 CUDA Driver / nvidia-smi，**没有提到 cuDNN 版本 vs ctranslate2 版本绑定关系**。这是 T3 调研 §6.4 反复强调的最大踩坑点：

- ctranslate2 ≥ 4.5.0 必须配 cuDNN 9.x（`cudnn_ops64_9.dll`）
- ctranslate2 < 4.5.0 必须配 cuDNN 8.x
- 错配的症状是运行时 `RuntimeError: cudnn could not load: cudnn_ops_infer64_8.dll` 或反向

我方 EXECUTION §4.1 + §7.1 明确给了 `Test-Path 'cudnn_ops64_9.dll'` 的预检命令和配对表。装机阶段直接照 GLM 的检查清单走会在第一次跑 faster-whisper 时崩。

### 2.6 🟠 GLM 用 GPT-4o 做云端 VLM —— 境内访问困难，未结合 Jovi 实际可用 token

GLM PRD §4.4 推荐"短期用 GPT-4o / Claude / Gemini 做云端 VLM"。境内不挂代理无法访问 GPT-4o 和 Claude API，Gemini 同样不可达。Jovi 实际持有的是 **MiMo token-plan 套餐**（小米 MiMo 系列，含 mimo-v2-omni 多模态）和潜在的智谱 GLM token——这些 GLM 文档完全没提，因为 GLM 在写文档时不知道 Jovi 的具体 token 持有情况。我方 DECISIONS A15 + D4 已经把"OpenAI-compatible 抽象 + 厂商可换 + MiMo 当前主选"落地，且单独标注了 MiMo token-plan 套餐**禁止用于自动化后端**的合规风险（MUST READ）—— GLM 同样漏了合规层面的考量。

---

## 3. 整体评价

GLM v2.0 PRD 作为 v1.0 升级 v2.0 写得**有结构、有详细代码骨架、有版本对照**——它知道自己是 v2.0 文档，对比着 v1.0 写差异点（§附录 A 还有专门差异表），文档工程性强。但部分技术选型已过时半年到一年（Whisper medium、Qwen2-VL-7B、Syncthing 假设、GPT-4o 云端），且漏掉了若干本项目实际场景（MiMo 合规、cuDNN 配对、yt-dlp 原生 auto_caption、Belle 中文模型）。

**互补关系**：

| GLM 强 / 我方弱 | 我方强 / GLM 弱 |
|---|---|
| OpenClaw YAML 声明式工作流范式 | yt-dlp 原生 auto_caption 利用 + 字幕来源区分 |
| VTT 解析 Python 实现 | Belle-whisper turbo-zh（中文 CER 2.78%） |
| 飞书 tenant_access_token 缓存 + 刷新 | Qwen2.5-VL AWQ-4bit + vLLM 推理 |
| 飞书"立即确认 + 异步回执"双段式描述 | cuDNN 9 / ctranslate2 4.5 配对表 |
| VLM 兜底"无关键信息"prompt 设计 | iOS 端 iCloud Drive 同步策略（GLM Syncthing 错误） |
| | MiMo token-plan 合规风险 + OpenAI-compatible 抽象层 |

**本次修订动作**（详见 EXECUTION.md / PRD.md 的 v2 修订标记）：

1. PRD §1.5 新增 Obsidian 角色澄清子节（吸收 GLM §1.2）
2. EXECUTION §6.6 新增 VTT 解析完整实现（吸收 GLM §4.2）
3. EXECUTION §5.6 + §5.7 新增飞书 5 秒响应窗口处理 + 主动发消息工具（吸收 GLM 执行手册 §6.4）
4. EXECUTION §12.7 新增 OpenClaw 工作流声明式 YAML 替代选项（吸收 GLM §4.5，标注为 alternate 而非替代主调度）
5. EXECUTION §9 加 MiMo 合规风险声明 + 走 openclaw 工具层调用（DECISIONS A15 推荐方案 A）
6. EXECUTION §5.8 新增反向调用：解析服务 → openclaw 的 LLM 工具

**对 GLM 文档的最终判定**：作为参考资料价值高，但**不能直接拿来当实施手册用**——技术选型需要按本项目实际硬件 / token / 平台约束重新评估。代码骨架（VTT 解析、飞书工具）可拷，模型选型（Whisper / VLM）必须替换，同步层（Syncthing iOS）必须重写。

---

**文档结束**。后续如有 GLM 文档新版本，按本评估结构增补 v2 章节即可。
