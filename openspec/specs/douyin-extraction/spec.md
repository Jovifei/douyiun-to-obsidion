## MODIFIED Requirements

### Requirement: download_video_only（M2 新增）

系统 SHALL 提供 `download_video_only(url, out_dir, cookies_path)` 函数，只下载视频不抓字幕，用于 ASR 路径。

#### Scenario: 只下载视频

- **WHEN** 调用 download_video_only（无 --write-subs 参数）
- **THEN** 返回 dict 含 video_path / info_dict，subtitle_path=None

#### Scenario: 下载失败

- **WHEN** yt-dlp 下载失败
- **THEN** 抛 DownloadError，上层捕获
