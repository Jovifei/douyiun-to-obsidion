## Why

M1 只支持有抖音原生字幕的视频（约 70-80% 知识类视频）。无字幕视频（PPT 操作演示、纯音乐、部分口播）直接报 `no_subtitle_in_m1` 失败。用户需要**所有抖音视频都能归档**，无论有没有字幕。

## What Changes

- 新增 ASR 兜底模块：yt-dlp 抓不到字幕时，自动下载视频 → 抽音频 → 调 ASR 转写 → 用转写文字替代字幕写入笔记
- **一期**：调 `mimo-v2.5-asr` API（走 openclaw 工具层，合规方案 A，零本地装机成本）
- **二期**：本地 `faster-whisper` + `Belle-whisper-large-v3-turbo-zh`（4070S 12G，零 API 成本，离线可用）
- 调度器主循环改造：`fetching` 阶段加 ASR 分支
- 新增知识文档归纳（视频下载地址、模型调用、安装地址等技术参考）

## Capabilities

### New Capabilities

- `asr-mimo-api`: mimo-v2.5-asr API 调用模块（走 openclaw 工具层，合规方案 A）。接收音频文件路径，返回转写文本 + segments。
- `asr-local-whisper`: 本地 faster-whisper + Belle turbo 模块（二期）。GPU 推理，接收音频文件路径，返回转写文本 + segments。
- `asr-knowledge-docs`: 技术参考文档（视频下载地址、yt-dlp 参数、ASR 模型调用、安装地址、cuDNN 配对等）。

### Modified Capabilities

- `task-queue-pipeline`: 调度器 `process_task` 的 fetching 阶段加 ASR 分支（无字幕 → 抽音频 → ASR → 写笔记，替代 failed）
- `douyin-extraction`: downloader 加 `download_video_only` 函数（只下载视频不抓字幕，用于 ASR 路径）

## Impact

- 修改 `src/pipeline/scheduler.py`（fetching 阶段加 ASR 分支）
- 修改 `src/extractors/downloader.py`（加 download_video_only）
- 新增 `src/asr/mimo_client.py`（一期）
- 新增 `src/asr/local_whisper.py`（二期）
- 新增 `src/asr/__init__.py`（ASR 统一接口）
- 修改 `config.yaml`（加 asr 配置块）
- 修改 openclaw 配置（注册 mimo-asr 工具）
- 新增 `docs/m2/` 技术参考文档
