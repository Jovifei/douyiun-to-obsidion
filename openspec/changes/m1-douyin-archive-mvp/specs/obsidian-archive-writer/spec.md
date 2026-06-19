## ADDED Requirements

### Requirement: frontmatter schema

每条抖音笔记 SHALL 包含以下 frontmatter 字段（YAML list 写 tags，时间用 ISO 8601，长内容入正文不入 frontmatter，snake_case 命名以兼容 DataView）：

```yaml
---
title: <string>
video_id: <string>
source_url: <string>
source_url_type: short | full | iesdouyin | share_text
author: <string>
uploader_id: <string>
duration_seconds: <int>
uploaded_at: <ISO 8601>
captured_at: <ISO 8601>
cover_url: <string>
local_cover_path: <relative path to vault root>
tags:
  - douyin
  - <auto-or-manual>
subtitle_source: douyin_native | creator_uploaded | auto_generated | whisper_local | mimo_asr
subtitle_language: zh | en | <other>
pipeline_version: "1.0"
status: pending | fetching | writing | done | failed
downloader_used: ytdlp | douk
correlation_id: <uuid>
# 状态字段（D-10 修订，避免 Dataview 误判）
summary_status: not_run | pending | done | failed
processing_mode: subtitle_only | subtitle_whisper | subtitle_vlm | full
ai_summary_model: null | "mimo-v2.5-pro" | "qwen2.5-72b" | "glm-4.5-air" | <other>
# 以下字段 M1 占位为空，M2/M3 填充
transcript_full: ""        # 已迁移到正文（不放 frontmatter）
summary: ""
vlm_results: []
---
```

#### Scenario: M1 完整 frontmatter

- **WHEN** 处理一条带原生字幕的抖音视频并成功入库
- **THEN** frontmatter 含上述全部字段；`subtitle_source ∈ {douyin_native, creator_uploaded, auto_generated}`，`summary = ""`，`vlm_results = []`，`pipeline_version = "1.0"`，`summary_status = "not_run"`，`processing_mode = "subtitle_only"`，`ai_summary_model = null`

#### Scenario: 字段不可缺失

- **WHEN** 写入时任何 SHALL 字段缺失（如 `correlation_id` 未生成）
- **THEN** 任务状态置 `failed`，错误码 `incomplete_frontmatter`，不写入半成品笔记

#### Scenario: 状态字段防误判（D-10 新增）

- **WHEN** M1 阶段写入笔记后，Dataview 查询 `WHERE summary_status != "done"` 过滤
- **THEN** 该笔记出现在结果集（因 `summary_status = "not_run"`），表明"待 M3 总结"；避免被旧 schema 的 `summary = ""` 误判为"已总结但空"

### Requirement: vault 路径计算

系统 SHALL 按以下规则计算笔记文件路径：

- 笔记：`{vault_root}/inbox/douyin/{YYYY-MM}/{video_id}.md`
- 附件：`{vault_root}/attachments/douyin/{video_id}/{filename}`

`vault_root` 来自 `config.yaml`，M1 锁定 `E:\AI_Tools\Obsidian\data\notes-personal`（DECISIONS A6）。

#### Scenario: 标准路径

- **WHEN** 处理 video_id = `7234567890123` 的视频，捕获时间 2026-06-19
- **THEN** 笔记路径 = `E:\AI_Tools\Obsidian\data\notes-personal\inbox\douyin\2026-06\7234567890123.md`，封面附件目录 = `E:\AI_Tools\Obsidian\data\notes-personal\attachments\douyin\7234567890123\`

#### Scenario: 跨月写入

- **WHEN** 6 月 30 日 23:59 触发任务，7 月 1 日 00:01 完成入库
- **THEN** 文件路径按"完成时刻"的月份计算 = `inbox/douyin/2026-07/...`（笔记是产物，按生成时刻归档，不按源视频发布时间）

### Requirement: 原子写入

系统 SHALL 先写入 `.tmp` 临时文件，再 `os.rename` 为最终文件名，确保 Syncthing / Obsidian 文件系统监听不会读到半文件。

#### Scenario: 正常流程

- **WHEN** 写笔记
- **THEN** 先写 `{video_id}.md.tmp`，调用 `os.rename` 切换为 `{video_id}.md`，整个写入对监听者表现为"瞬时出现"

#### Scenario: 写入失败回滚

- **WHEN** `.tmp` 写入过程中磁盘满 / 权限错误
- **THEN** 删除 `.tmp`，任务状态 `failed`，**不**留下 `.md` 文件，**不**触发 Obsidian/Syncthing 监听

### Requirement: 重复检测

系统 SHALL 在入队前检查 vault 是否已存在同 video_id 的笔记：

#### Scenario: 已存在跳过

- **WHEN** 飞书推送的 URL 已对应 vault 中已存在的 `{video_id}.md`
- **THEN** 任务不入队，bishu 飞书回"该视频已归档：{vault 相对路径}"

#### Scenario: force=1 强制覆盖

- **WHEN** bishu 推送时携带 `force: true` 字段
- **THEN** 跳过重复检测，按正常流程覆盖写入（仍走原子 rename）

### Requirement: 笔记正文结构

笔记正文（frontmatter 之后）SHALL 包含以下段落，按顺序：

1. `## 摘要`（M1 留空，仅占位标题 + 一行"M1 阶段无 LLM 总结，待 M3 填充"）
2. `## 字幕全文`（含时间戳，按 `## 字幕全文` + 完整 VTT 解析后的 segments 渲染）
3. `## 关键帧`（M1 留空，仅占位标题）
4. `## 元数据`（含原始 URL、作者主页、视频时长、封面 markdown 嵌入）
5. `## 链接`（飞书触发消息的原始内容、correlation_id、处理时间）

#### Scenario: M1 完整笔记正文

- **WHEN** 笔记写入完成
- **THEN** 上述 5 段都存在；M1 时 `## 摘要` 与 `## 关键帧` 仅有占位提示文字，其他段落有实质内容

### Requirement: 附件管理

封面图 SHALL 下载到 vault 附件目录，frontmatter 的 `local_cover_path` 用相对 vault 根的路径（如 `attachments/douyin/7234567890123/cover.jpg`），笔记正文用 `![[attachments/douyin/7234567890123/cover.jpg]]` Obsidian 嵌入语法。

#### Scenario: 封面下载成功

- **WHEN** yt-dlp info 含 thumbnail URL 且下载成功
- **THEN** 封面存到 `attachments/douyin/{video_id}/cover.jpg`，frontmatter `local_cover_path = "attachments/douyin/{video_id}/cover.jpg"`，正文用 Obsidian 嵌入语法

#### Scenario: 封面下载失败

- **WHEN** thumbnail URL 不存在或下载失败
- **THEN** frontmatter `local_cover_path = ""`，`cover_url` 保留原 URL，正文渲染为外链 `[封面]({cover_url})`；任务不失败
