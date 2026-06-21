# Comet Design Handoff

- Change: m2-asr-fallback
- Phase: design
- Mode: compact
- Context hash: 912ce67668a7b9f8101860ff5087cd0fbcc69a4dc56c428db4d89fcb1b9b35d3

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/m2-asr-fallback/proposal.md

- Source: openspec/changes/m2-asr-fallback/proposal.md
- Lines: 1-35
- SHA256: fc4c59eea934dbf78cd0b985c2fcb20e82185c6e107157e31246b890e3ba14a6

```md
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
```

## openspec/changes/m2-asr-fallback/design.md

- Source: openspec/changes/m2-asr-fallback/design.md
- Lines: 1-90
- SHA256: cfd87bfa8a4e222221344d47d698f068efb47bcf074daacb8723a274bc135542

[TRUNCATED]

```md
## Context

M1 已跑通"字幕有 → 写笔记"的完整链路。M2 补"字幕无 → ASR 转写 → 写笔记"的兜底路径。

**关键约束**：
- MiMo token-plan 套餐合规（DECISIONS A15）：ASR 调用必须走 openclaw 工具层（方案 A）
- 4070S 12G 显存预算：本地 Whisper 必须串行，不能与 OCR/VLM 并行（PRD §5.3）
- M2 不涉及 LLM 总结（那是 M3）

## Goals / Non-Goals

**Goals**：
1. 无字幕视频自动 ASR 转写，写入 Obsidian 笔记
2. 一期用 mimo-v2.5-asr API（走 openclaw 工具层）
3. 二期用本地 faster-whisper + Belle turbo（零 API 成本）
4. ASR 统一接口：一期/二期可热切换
5. 技术参考文档归纳

**Non-Goals**：
- 不做 LLM 总结（M3）
- 不做关键帧 OCR/VLM（M3）
- 不做 iOS/Android 同步（M4）
- 不做实时流式 ASR

## Decisions

### D-M2-1: ASR 走 openclaw 工具层（合规方案 A）

MiMo token-plan 禁止自动化后端直调。ASR 调用通过 openclaw MCP 工具 `asr_transcribe(audio_path)` 完成，openclaw 内部打 mimo-v2.5-asr API。

### D-M2-2: ASR 统一接口

```python
class ASRResult:
    text: str           # 完整转写文本
    segments: list[dict]  # [{start, end, text}, ...]
    source: str         # "mimo_asr" | "whisper_local"
    confidence: float   # 0-1
```

一期实现 `MimoASRClient`，二期实现 `WhisperLocalClient`，都返回 `ASRResult`。config.yaml 切换：

```yaml
asr:
  provider: mimo  # 或 whisper_local
  mimo:
    model: mimo-v2.5-asr
  whisper:
    model: Belle-whisper-large-v3-turbo-zh
    device: cuda
    compute_type: int8_float16
```

### D-M2-3: 调度器 fetching 阶段加 ASR 分支

```
fetching:
  yt-dlp 下载视频 + 抓字幕
    ├─ 有字幕 → subtitle_source = douyin_native → writing
    └─ 无字幕 → ffmpeg 抽 16kHz wav → ASR 转写
        ├─ mimo-asr 成功 → subtitle_source = mimo_asr → writing
        └─ mimo-asr 失败 → 降级 whisper_local（如已装）
            ├─ whisper 成功 → subtitle_source = whisper_local → writing
            └─ 都失败 → failed(asr_failed)
```

### D-M2-4: 一期 mimo-asr 走 openclaw MCP 工具

openclaw 注册新 MCP 工具 `asr_transcribe`，由 `src/bridge/mcp_server.py` 暴露。解析服务调用 MCP 工具而非直连 API。

### D-M2-5: 二期本地 Whisper 装机但默认关闭

config.yaml `asr.provider: mimo`（默认）。二期装好 faster-whisper + Belle 后改 `asr.provider: whisper_local` 即可切换，零代码改动。

### D-M2-6: 技术参考文档

`docs/m2/KNOWLEDGE.md` 归纳：
- 视频下载地址（yt-dlp 参数、cookie 配置）
- ASR 模型调用步骤（mimo-asr API 格式、faster-whisper Python API）
- 安装地址（cuDNN、ctranslate2、Belle 模型 HuggingFace 链接）
```

Full source: openspec/changes/m2-asr-fallback/design.md

## openspec/changes/m2-asr-fallback/tasks.md

- Source: openspec/changes/m2-asr-fallback/tasks.md
- Lines: 1-67
- SHA256: 6ac18d214ad7f03bdc4707ee4383b50f26dfed4f6c717b21e2444edd3ae40e74

```md
# M2 实施任务清单

> Change: `m2-asr-fallback`
> Workflow: full (spec-driven)
> 总工时估算: **5-7 天**（一期 mimo-asr ~2 天，二期 whisper ~3 天，文档 ~1 天）
> 依赖：M1 完成（已归档）

## 1. ASR 统一接口设计（0.5 天）

- [ ] 1.1 创建 `src/asr/__init__.py`，定义 `ASRResult` dataclass（text / segments / source / confidence）
- [ ] 1.2 定义 `ASRClient` 抽象基类：`transcribe(audio_path: Path) -> ASRResult`
- [ ] 1.3 定义 `get_asr_client(config) -> ASRClient` 工厂函数（根据 config.asr.provider 返回对应实现）
- [ ] 1.4 单元测试：mock ASRClient，验证 ASRResult 字段完整性

## 2. mimo-v2.5-asr API 客户端（一期）（1 天）

- [ ] 2.1 创建 `src/asr/mimo_client.py`：`MimoASRClient` 实现 `ASRClient`
- [ ] 2.2 实现 `transcribe(audio_path)`：读音频文件 → base64 编码 → 调 openclaw MCP 工具 `asr_transcribe` → 解析返回 JSON
- [ ] 2.3 openclaw MCP 工具注册：在 `src/bridge/mcp_server.py` 新增 `asr_transcribe` 工具，内部调 mimo-v2.5-asr API
- [ ] 2.4 实现音频预处理：ffmpeg 抽 16kHz mono wav（复用 M1 的 `audio_extractor.py`）
- [ ] 2.5 错误处理：API 超时 / 返回空结果 / 音频太短 → 抛 `ASRError`，上层调度器捕获
- [ ] 2.6 单元测试：mock openclaw MCP 调用，验证 ASRResult 字段
- [ ] 2.7 集成测试：真实调 mimo-v2.5-asr（用 5 秒测试音频），验证转写结果

## 3. 本地 faster-whisper + Belle（二期）（2 天）

- [ ] 3.1 创建 `src/asr/local_whisper.py`：`WhisperLocalClient` 实现 `ASRClient`
- [ ] 3.2 实现模型加载：`faster-whisper` + `Belle-whisper-large-v3-turbo-zh`，CUDA + int8_float16
- [ ] 3.3 实现 `transcribe(audio_path)`：VAD 切片 + 批量推理 + 拼接 segments
- [ ] 3.4 实现模型懒加载：首次调用时加载，后续复用，`torch.cuda.empty_cache()` 卸载
- [ ] 3.5 单元测试：mock faster-whisper，验证 ASRResult
- [ ] 3.6 集成测试：真实转写（用 30 秒测试音频），验证 CER ≤ 5%
- [ ] 3.7 性能测试：4070S 上 30 秒音频转写 < 5 秒

## 4. 调度器 ASR 分支改造（1 天）

- [ ] 4.1 修改 `src/pipeline/scheduler.py` 的 `_download_with_fallback`：无字幕时调 `ffmpeg 抽音频` + `ASR 转写`，替代直接 failed
- [ ] 4.2 修改状态转移：fetching 阶段 ASR 成功 → `subtitle_source = asr_source` → writing
- [ ] 4.3 修改 `download_video_only`（downloader.py 新增）：只下载视频不抓字幕，用于 ASR 路径
- [ ] 4.4 修改 frontmatter：`subtitle_source` 新增值 `mimo_asr` / `whisper_local`
- [ ] 4.5 单元测试：mock ASR 客户端，验证无字幕视频走 ASR 路径成功写入笔记
- [ ] 4.6 单元测试：ASR 失败 → `failed(asr_failed)` 正确报错
- [ ] 4.7 集成测试：curl 提交无字幕视频 → 2 分钟内 vault 出现笔记（含转写文字）

## 5. 配置更新（0.5 天）

- [ ] 5.1 更新 `config.example.yaml`：新增 `asr` 配置块（provider / mimo / whisper）
- [ ] 5.2 更新 `config.yaml`：默认 `asr.provider: mimo`
- [ ] 5.3 更新 `.env.example`：新增 `MIMO_ASR_MODEL=mimo-v2.5-asr`（如需单独 key）
- [ ] 5.4 更新 `docs/m1/RUNBOOK.md`：新增 ASR 相关启动/停止/切换说明

## 6. 知识文档归纳（1 天）

- [ ] 6.1 创建 `docs/m2/KNOWLEDGE.md`：技术参考文档
- [ ] 6.2 视频下载地址章节：yt-dlp 参数、cookie 配置、抖音反爬现状
- [ ] 6.3 ASR 模型调用章节：mimo-v2.5-asr API 格式、faster-whisper Python API
- [ ] 6.4 安装地址章节：cuDNN 9.x 下载、ctranslate2 版本、Belle 模型 HuggingFace 链接
- [ ] 6.5 cuDNN 配对表：ctranslate2 ≥4.5 → cuDNN 9，<4.5 → cuDNN 8
- [ ] 6.6 性能基准：4070S 上各模型的速度/显存/CER 对比

## 7. 端到端测试（0.5 天）

- [ ] 7.1 测试场景 1：curl 提交**有字幕**视频 → 走字幕路径 → 笔记含字幕全文
- [ ] 7.2 测试场景 2：curl 提交**无字幕**视频 → 走 mimo-asr 路径 → 笔记含转写文字
- [ ] 7.3 测试场景 3：curl 提交**无字幕**视频 + ASR 失败 → `failed(asr_failed)`
- [ ] 7.4 测试场景 4：切换 `asr.provider: whisper_local` → 无字幕视频走本地 Whisper
- [ ] 7.5 性能基准：5 条无字幕视频串行处理，平均端到端 ≤ 3 分钟/条
```

## openspec/changes/m2-asr-fallback/specs/asr-local-whisper/spec.md

- Source: openspec/changes/m2-asr-fallback/specs/asr-local-whisper/spec.md
- Lines: 1-34
- SHA256: 46ebd57e02ed9a4921db0f6352700411bdc2690f82ccf2987dc985cbc2cc1d11

```md
## ADDED Requirements

### Requirement: 本地 Whisper 转写

系统 SHALL 通过 faster-whisper + Belle-whisper-large-v3-turbo-zh 在本地 4070S 12G 上转写音频。

#### Scenario: 正常转写

- **WHEN** 传入 30 秒中文音频，provider=whisper_local
- **THEN** 返回 ASRResult（source="whisper_local", confidence≥0.9）

#### Scenario: GPU 不可用降级

- **WHEN** CUDA 不可用
- **THEN** 抛 ASRError("gpu_unavailable")，调度器降级到 mimo-asr

#### Scenario: 显存不足

- **WHEN** 4070S 显存不足（<2GB 可用）
- **THEN** 抛 ASRError("oom")，调度器降级

### Requirement: 模型懒加载

Whisper 模型 SHALL 首次调用时加载，后续复用，卸载时调 `torch.cuda.empty_cache()`。

#### Scenario: 首次加载

- **WHEN** 第一次调用 transcribe
- **THEN** 模型加载耗时 <10 秒，后续调用无加载开销

#### Scenario: 卸载释放显存

- **WHEN** 调用 unload()
- **THEN** GPU 显存释放，torch.cuda.empty_cache() 被调用
```

## openspec/changes/m2-asr-fallback/specs/asr-mimo-api/spec.md

- Source: openspec/changes/m2-asr-fallback/specs/asr-mimo-api/spec.md
- Lines: 1-29
- SHA256: 9a526b7a8a1c65c8cdcaec614cd91177b564815f8ad13beca756f6a34e373ba1

```md
## ADDED Requirements

### Requirement: mimo-v2.5-asr 转写

系统 SHALL 通过 openclaw MCP 工具 `asr_transcribe` 调用 mimo-v2.5-asr API，接收音频文件路径，返回转写结果。

#### Scenario: 正常转写

- **WHEN** 传入 30 秒中文音频文件
- **THEN** 返回 ASRResult（text=转写全文, segments=[{start,end,text}], source="mimo_asr", confidence≥0.8）

#### Scenario: 音频太短

- **WHEN** 传入 <1 秒音频
- **THEN** 抛 ASRError("audio_too_short")

#### Scenario: API 超时

- **WHEN** openclaw MCP 调用超时 30 秒
- **THEN** 抛 ASRError("asr_timeout")，上层调度器捕获

### Requirement: openclaw MCP 工具注册

`src/bridge/mcp_server.py` SHALL 暴露 `asr_transcribe` 工具，内部调 mimo-v2.5-asr API。

#### Scenario: 工具可调用

- **WHEN** openclaw agent 调用 `asr_transcribe(audio_path="/tmp/test.wav")`
- **THEN** 返回 JSON 含 text / segments / source / confidence 字段
```

## openspec/changes/m2-asr-fallback/specs/douyin-extraction/spec.md

- Source: openspec/changes/m2-asr-fallback/specs/douyin-extraction/spec.md
- Lines: 1-15
- SHA256: a759c60329da71801f3f3dc449b88528b026b11e8c6d08b8346bb299c5cdc635

```md
## MODIFIED Requirements

### Requirement: download_video_only（M2 新增）

系统 SHALL 提供 `download_video_only(url, out_dir, cookies_path)` 函数，只下载视频不抓字幕，用于 ASR 路径。

#### Scenario: 只下载视频

- **WHEN** 调用 download_video_only（无 --write-subs 参数）
- **THEN** 返回 dict 含 video_path / info_dict，subtitle_path=None

#### Scenario: 下载失败

- **WHEN** yt-dlp 下载失败
- **THEN** 抛 DownloadError，上层捕获
```

## openspec/changes/m2-asr-fallback/specs/task-queue-pipeline/spec.md

- Source: openspec/changes/m2-asr-fallback/specs/task-queue-pipeline/spec.md
- Lines: 1-26
- SHA256: ec07692a7a84f012632989102904598c4d896ecff9c5a506a4eece8ea2efe814

```md
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
```

