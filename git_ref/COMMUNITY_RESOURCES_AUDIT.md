# 社区资源核验报告（COMMUNITY_RESOURCES_AUDIT）

**调研日期**：2026-06-19
**调研员**：调研 Agent
**任务**：核验"3 类现成资源"真伪
**核验工具**：WebFetch（GitHub API + 网页）、WebSearch（无回填）
**Tavily**：本日额度已耗尽

---

## 总判

**3 项资源中 1 项基本属实、1 项编造、1 项部分误描述：1.5 / 3。**

简言之：
- 资源 1（ClawHub 上的 douyin skill）：**ClawHub 真实，但其上没有 douyin 相关 skill**——**编造**。
- 资源 2（Obsidian 官方 Douyin Capture 插件，内置 Whisper）：**官方 community-plugins.json 不含 douyin/tiktok**，"内置 Whisper" 也不属实——**编造**；但社区 GitHub 上**确有**第三方 Obsidian 插件可参考。
- 资源 3（GitHub `video-link-pipeline` 全流程项目）：**真实存在 `xiexikang/video-link-pipeline`**，描述完全吻合，13 ⭐ 还在活跃更新——**真实**，但**不写 Obsidian**，需要补一层落地适配。

---

## 资源 1：ClawHub 上的 `douyin-video-fetch` / `douyin-transcribe`

**真伪判定**：⚠️ ClawHub 平台真实，但其上**没有任何 douyin 相关 skill**——具名 skill 是编造。

### 证据

- **ClawHub 平台存在**：`https://hub.openclaw.ai/` 可访问，是 openclaw 项目的官方 Skills/Plugins 注册中心。
- **openclaw/openclaw 真实**（GitHub API 直接命中）：
  - URL：https://github.com/openclaw/openclaw
  - stars：**379,476** ⭐（2026-06-19 抓取）
  - pushed_at：2026-06-19T13:04:23Z（**今日**仍在 push）
  - created_at：2025-11-24
  - description：`Your own personal AI assistant. Any OS. Any Platform. The lobster way. 🦞`
  - language：TypeScript
- **ClawHub 上 douyin 搜索结果**：
  - `hub.openclaw.ai/search?q=douyin` → "no results"
  - `hub.openclaw.ai/skills?q=video` → "**No skills found.**"
- **GitHub `community-plugins.json`** 也不含 `douyin`/`tiktok` 字符串（与资源 2 同步排查）。

### 能否用于本项目

**否**。两个具名 skill 不存在。**但** openclaw 本身（personal AI assistant，主仓 379k ⭐）作为参考架构值得一看（skill loader、gateway、companion app 模式），但与"抖音→Obsidian"无直接关系。

---

## 资源 2：Obsidian "Douyin Capture" 插件（内置 Whisper）

**真伪判定**：⚠️ **官方插件库不存在；第三方 GitHub 插件存在；"内置 Whisper" 不属实**。

### 证据

- **官方插件库** `obsidianmd/obsidian-releases/community-plugins.json` 全文检索 `douyin` / `tiktok`：**no matches**（直接拉取 raw JSON 验证）。
- **第三方 GitHub 插件**真实存在多个，最相关的是：
  - **`lyxdream/obsidian-douyin-capture`**
    - URL：https://github.com/lyxdream/obsidian-douyin-capture
    - stars：9 ⭐
    - 最新 release：2026-06-05；近 14 天有更新
    - README 摘录：捕获抖音分享链接到 Obsidian、复制文本和图片、**依赖本地 Python 后端**
    - **Whisper 不内置**——需要本地 Python + Whisper，与"插件即装即用、内置 Whisper"的描述不符。
  - 另有 `zhaoyaoyuan/obsidian-douyin-capture`（2 ⭐）等同名分支项目。
- **Obsidian 官方未收录任何抖音/TikTok 插件**。

### 能否用于本项目

**部分采纳**。`lyxdream/obsidian-douyin-capture` 是**自研 Obsidian 插件层时的最佳参考**（界面交互、链接解析、与 Python 后端对接的 IPC 设计），但**不是开箱即用的 Whisper 一体化插件**——架构上仍是"Obsidian 插件 + 外部 Python 后端"，与本 PRD 路线一致。

---

## 资源 3：GitHub `video-link-pipeline` 全流程项目

**真伪判定**：✅ **真实存在**，描述高度吻合 PRD 描述。

### 证据

- **`xiexikang/video-link-pipeline`**（主候选）：
  - URL：https://github.com/xiexikang/video-link-pipeline
  - stars：**13 ⭐**
  - forks：2
  - created_at：2026-02-03
  - pushed_at：**2026-06-18**（昨日活跃）
  - language：Python
  - description：`这是一个集成了视频下载、音频提取、字幕处理、语音转录和 AI 摘要生成的全流程工具集。支持 YouTube, Bilibili, TikTok/抖音, 快手 等多个平台`
  - README 关键能力：
    1. yt-dlp 主下载 + Selenium fallback
    2. faster-whisper / openai-whisper 本地转录
    3. Claude / OpenAI / Gemini 多模型 AI 摘要
    4. SRT/VTT 字幕互转、doctor 自检命令
    5. 输出至 job 文件夹（transcript.txt、subtitles、summary.md、keywords.json、manifest.json）
- **次候选 `yunqiasen/video-link-pipeline`**：2 ⭐、Feb 23 后无更新，能力描述相近但活跃度低，仅作备份参考。

### ⚠️ 重要差距

`xiexikang/video-link-pipeline` README **未提及 Obsidian 写入或 vault 集成**——它产出的是 job 目录下的 markdown/json 文件。**需要在本项目自研一层 Obsidian-writer 适配器**（把它的输出搬进 vault）。

### 能否用于本项目

**强烈推荐部分采纳**。可作为视频下载/转录/摘要管线的**参考实现或直接 fork 起点**，本项目只需补 Obsidian 落地层。技术栈（yt-dlp + faster-whisper + 多模型摘要）与 PRD 路线一致。

---

## 下载建议（不要立即执行，由 lead 决定）

如要克隆，建议如下命令（克隆到 `E:\project\douyin_to_obsidian\git_ref\<repo_name>`）：

```powershell
# 主候选（强烈推荐）：全流程参考管线
git clone https://github.com/xiexikang/video-link-pipeline.git "E:/project/douyin_to_obsidian/git_ref/video-link-pipeline"

# 次候选：自研 Obsidian 插件时的交互/IPC 参考
git clone https://github.com/lyxdream/obsidian-douyin-capture.git "E:/project/douyin_to_obsidian/git_ref/obsidian-douyin-capture"

# 备选 1：纯 Python 抖音→Obsidian skill 实现（4 ⭐，最近 5 月更新）
git clone https://github.com/baiye-10/douyin-to-obsidian.git "E:/project/douyin_to_obsidian/git_ref/baiye-10-douyin-to-obsidian"

# 备选 2：抖音收藏夹自动同步 Obsidian（0 ⭐ 但近 5 天有更新，思路新）
git clone https://github.com/CelesteZheng09/douyin-obsidian-sync.git "E:/project/douyin_to_obsidian/git_ref/CelesteZheng09-douyin-obsidian-sync"
```

> 不需要克隆 openclaw（与本项目无关）、`yunqiasen/video-link-pipeline`（活跃度差）、Obsidian 官方插件库（不含目标插件）。

---

## 最终建议

**继续按 PRD/EXECUTION 自研，但纳入两个真实参考**：

1. **架构基底**：`xiexikang/video-link-pipeline`（强烈建议 fork 或深度参考）——它已经把"yt-dlp + Whisper + 多模型摘要"工程化了，本项目只需补 **Obsidian writer** 一层（YAML frontmatter + vault 路径 + 标签策略）。
2. **Obsidian 端交互参考**：`lyxdream/obsidian-douyin-capture`——如果本项目最终需要在 Obsidian 内提供"粘贴链接即触发"的 UI，参考它的插件代码与本地后端 IPC 设计。

**剔除两条幻觉**：
- 不要再相信"ClawHub 上有 `douyin-video-fetch` skill"——**不存在**。
- 不要再相信"Obsidian 官方有 Douyin Capture 内置 Whisper 插件"——**不存在**。

**本项目仍需自研的核心**：抖音 share-URL 解析（去水印 + 反爬维护成本高）、Obsidian 笔记模板与标签自动化、可能的批量队列与去重——这些上游参考项目都未完整覆盖。

---

**附**：本次核验全部基于 GitHub API 与 raw 网页内容，无训练集回忆；openclaw 的 379,476 ⭐ 数据由 `api.github.com/repos/openclaw/openclaw` 直接返回，可信。
