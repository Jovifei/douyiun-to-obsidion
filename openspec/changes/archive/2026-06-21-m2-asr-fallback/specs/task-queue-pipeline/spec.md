## MODIFIED Requirements

### Requirement: 调度器 fetching 阶段 ASR 分支（M2 修改）

**原行为**：yt-dlp 抓不到字幕 → `failed(no_subtitle_in_m1)`
**新行为**：yt-dlp 抓不到字幕 → ffmpeg 抽音频 → ASR 转写 → `subtitle_source=asr_source` → writing

#### Scenario: 无字幕视频走 mimo-asr

- **WHEN** yt-dlp 抓不到字幕 + config.asr.provider = "mimo"
- **THEN** ffmpeg 抽 16kHz wav → 调 mimo-v2.5-asr → 转写成功 → subtitle_source="mimo_asr" → writing

#### Scenario: 无字幕视频走 whisper_local

- **WHEN** yt-dlp 抓不到字幕 + config.asr.provider = "whisper_local"
- **THEN** ffmpeg 抽音频 → 本地 Whisper → 转写成功 → subtitle_source="whisper_local" → writing

#### Scenario: ASR 失败降级

- **WHEN** mimo-asr 超时/失败 + 本地 Whisper 可用
- **THEN** 降级到 whisper_local；都失败 → `failed(asr_failed)`

#### Scenario: 有字幕视频不走 ASR

- **WHEN** yt-dlp 抓到字幕
- **THEN** 直接走字幕路径，不调 ASR（M1 行为不变）
