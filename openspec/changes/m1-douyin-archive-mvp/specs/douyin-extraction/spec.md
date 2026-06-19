## ADDED Requirements

### Requirement: 接受多种抖音 URL 形态

系统 SHALL 接受以下 4 种输入形态并解析为标准 video_id + 完整 URL：

1. 短链 `https://v.douyin.com/{token}/`（需 302 跟随）
2. 完整链 `https://www.douyin.com/video/{video_id}`
3. 旧链 `https://www.iesdouyin.com/share/video/{video_id}`
4. 整段分享文案（含口令 + emoji + URL 的混合文本）

#### Scenario: 短链解析

- **WHEN** 解析服务收到 `https://v.douyin.com/iAbCdEf/`
- **THEN** 系统 302 跟随后得到完整 URL，并提取 `video_id`，返回 `{"video_id": ..., "canonical_url": ..., "source_url_type": "short"}`

#### Scenario: 分享文案解析

- **WHEN** 解析服务收到 `"9.99 复制打开抖音，看看【作者】的作品 https://v.douyin.com/iAbCdEf/ 🔥"`
- **THEN** 系统提取 URL 后按短链流程解析，忽略 emoji 与口令

#### Scenario: 非抖音 URL

- **WHEN** 解析服务收到 `https://www.bilibili.com/video/BVxxx`
- **THEN** 返回 `{"error": "not_douyin_url", "supported": false}`，不入队

### Requirement: yt-dlp 主路径下载

系统 SHALL 使用 yt-dlp 作为主下载工具，输出视频文件 + 字幕文件到任务临时目录。

#### Scenario: 带原生字幕视频

- **WHEN** 处理一条带抖音原生 CC 字幕的知识视频
- **THEN** 系统产出 `<video_id>.mp4` 和 `<video_id>.zh.vtt`（或同前缀 srt）两个文件，并标记 `subtitle_source = "douyin_native"`

#### Scenario: 无字幕视频（M1 边界）

- **WHEN** 处理一条无字幕视频（直播切片/纯音乐视频）
- **THEN** 系统产出 `<video_id>.mp4` 但**不**进入 Whisper 兜底（M1 不支持），任务状态置 `failed`，错误码 `no_subtitle_in_m1`，bishu agent 飞书回"该视频无字幕，M1 暂不支持，将推到 M2 自动处理"

### Requirement: 字幕来源判定

系统 SHALL 通过 yt-dlp 的 `info_dict["subtitles"]` vs `info_dict["automatic_captions"]` 两个 dict 判定字幕来源，**不**靠文件名扩展名区分（B2 修订）。

#### Scenario: 创作者上传字幕

- **WHEN** `info_dict["subtitles"]["zh"]` 存在
- **THEN** 标记 `subtitle_source = "creator_uploaded"`

#### Scenario: 平台自动字幕

- **WHEN** `info_dict["automatic_captions"]["zh"]` 存在但 `subtitles` 无 zh
- **THEN** 标记 `subtitle_source = "auto_generated"`

### Requirement: 视频元数据提取

系统 SHALL 从 yt-dlp info_dict 提取以下元数据：

- `title`（视频标题）
- `uploader`（作者昵称）
- `uploader_id`（从 `uploader_url` 正则提取 `sec_uid`，**不**用不存在的 `author_uid` 字段，B3 修订）
- `duration`（秒）
- `upload_date`（YYYYMMDD）
- `thumbnail`（封面 URL）

#### Scenario: 完整元数据

- **WHEN** 处理一条正常抖音视频
- **THEN** 元数据全部成功提取，写入 frontmatter 的 `title` / `author` / `uploader_id` / `duration_seconds` / `uploaded_at` / `cover_url` 字段

#### Scenario: uploader_id 提取失败

- **WHEN** `uploader_url` 不含 `/user/` 路径或正则不匹配
- **THEN** `uploader_id` 留空字符串 `""`，任务不失败，frontmatter 该字段值 `""`

### Requirement: yt-dlp 失败兜底走 DouK-Downloader

系统 SHALL 在 yt-dlp 主路径失败（非 4xx 重试或网络异常）时，调用 DouK-Downloader 作为备选下载工具。

#### Scenario: yt-dlp 失败 → DouK 成功

- **WHEN** yt-dlp 因抖音反爬返回 412/403/429 重试 3 次仍失败
- **THEN** 系统切换到 DouK-Downloader，使用相同 video_id 重试；如 DouK 成功则任务继续，标记 `downloader_used = "douk"`

#### Scenario: 双工具都失败

- **WHEN** yt-dlp 与 DouK-Downloader 都失败
- **THEN** 任务状态置 `failed`，错误码 `download_failed_all_tools`，bishu 飞书回"下载失败，请手动检查链接有效性"

### Requirement: Cookie 失效检测

系统 SHALL 在启动时和每次下载失败时，用一个已知有效的抖音视频 URL 做 cookie 探活（如果配置了 cookies.txt）。

#### Scenario: 启动时探活

- **WHEN** 解析服务启动
- **THEN** 如配置了 cookies.txt，跑一次已知 URL 探活；失败时日志警告"cookie 可能已过期"但不阻止启动

#### Scenario: 下载失败时触发探活

- **WHEN** yt-dlp 返回 401/403
- **THEN** 触发探活；探活也失败则 bishu 飞书回"抖音 cookie 过期，请重新导出 cookies.txt"

### Requirement: 视频文件清理

系统 SHALL 在笔记写入 vault 成功后，删除临时视频文件（节省磁盘），**保留**封面图（已写入 vault 附件目录）。

#### Scenario: 成功入库后清理

- **WHEN** 笔记 + 附件成功写入 vault
- **THEN** 删除 `<video_id>.mp4` 和 `<video_id>.zh.vtt`；frontmatter 字段 `cover_url` 保留原 URL，`local_cover_path` 保留 vault 内附件相对路径

#### Scenario: 入库失败时保留视频

- **WHEN** 笔记写入失败
- **THEN** 视频文件保留在临时目录供排查，但任务状态 `failed`，bishu 飞书回失败原因
