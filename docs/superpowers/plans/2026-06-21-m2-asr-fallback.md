---
change: m2-asr-fallback
design-doc: docs/superpowers/specs/2026-06-21-m2-asr-fallback-design.md
base-ref: ec35c7a8d3e7687d99a4cf39728532ea8ba3e802
archived-with: 2026-06-21-m2-asr-fallback
---

# M2 ASR Fallback Implementation Plan

> Timeline: 5-7 days
> Base: M1 (archived)
> Constraint: D-M2-1 openclaw 合规, D-M2-2 ASRResult 统一, D-M2-5 本地默认关闭, 4070S 12G 串行铁律

archived-with: 2026-06-21-m2-asr-fallback
---

## Task 1: ASR 统一接口与数据模型 (0.5d)

**Goal**: 定义 ASRResult / ASRClient / factory，为后续两期实现提供契约。

### Steps

1. **[RED] 写测试** — `E:\project\douyin_to_obsidian\tests\asr\test_asr_interface.py`
   - 断言 `ASRResult` dataclass 四字段 (text, segments, source, confidence) 可实例化、可序列化
   - 断言 `ASRClient` 抽象基类 `transcribe(audio_path: Path) -> ASRResult` 存在且不可直接实例化
   - 断言 `get_asr_client({"asr": {"provider": "mimo"}})` 返回 `MimoASRClient` 实例
   - 断言 `get_asr_client({"asr": {"provider": "whisper_local"}})` 返回 `WhisperLocalClient` 实例
   - 断言未知 provider → `ValueError`
   - **Spec ref**: D-M2-2 (ASRResult 统一接口)

2. **[GREEN] 实现** — `E:\project\douyin_to_obsidian\src\asr\__init__.py`
   - `ASRResult` dataclass: `text: str`, `segments: list[dict]`, `source: str`, `confidence: float`
   - `ASRClient` ABC: `transcribe(self, audio_path: Path) -> ASRResult`
   - `get_asr_client(config: dict) -> ASRClient` 工厂
   - 异常类 `ASRError(Exception)` 带 `code` 字段 (asr_timeout / audio_too_short / oom / gpu_unavailable)

3. **[REFACTOR] 验证**
   - `pytest tests/asr/test_asr_interface.py -v` 全绿
   - 确认 `ASRError.code` 可被调度器匹配 (e.g. `if err.code == "asr_timeout"`)

### Verification
- [ ] `ASRResult(text="test", segments=[], source="mimo_asr", confidence=0.9)` 序列化后 round-trip
- [ ] 工厂函数对 mimo / whisper_local / 未知 provider 三种输入均正确路由
- [ ] Spec D-M2-2 WHEN 传入正常字段 THEN 返回完整 ASRResult 通过

archived-with: 2026-06-21-m2-asr-fallback
---

## Task 2: mimo-v2.5-asr API 客户端 — 一期 (1d)

**Goal**: 实现 MimoASRClient，通过 openclaw MCP 工具调用 mimo-v2.5-asr API。D-M2-1 合规方案 A。

### Steps

1. **[RED] 写测试** — `E:\project\douyin_to_obsidian\tests\asr\test_mimo_client.py`
   - **Spec ref asr-mimo-api**: WHEN 传入 30s 中文音频 THEN 返回 ASRResult (source="mimo_asr", confidence>=0.8)
   - **Spec ref asr-mimo-api**: WHEN 传入 <1s 音频 THEN 抛 ASRError("audio_too_short")
   - **Spec ref asr-mimo-api**: WHEN openclaw MCP 调用超时 30s THEN 抛 ASRError("asr_timeout")
   - Mock `openclaw.call_tool("asr_transcribe", ...)` 返回预设 JSON
   - 断言 audio_path 被 base64 编码后传入 MCP 工具

2. **[GREEN] 实现** — `E:\project\douyin_to_obsidian\src\asr\mimo_client.py`
   - `MimoASRClient(ASRClient)`:
     - `transcribe(audio_path)`:
       - 校验音频时长 (ffprobe < 1s → ASRError("audio_too_short"))
       - 读文件 → base64 编码
       - 调 `openclaw.call_tool("asr_transcribe", {"audio_base64": ..., "format": "wav"})` (D-M2-1)
       - 30s 超时 → ASRError("asr_timeout")
       - 解析 JSON → ASRResult(source="mimo_asr")
   - 复用 M1 的 `audio_extractor.py` 做 16kHz mono wav 预处理

3. **[GREEN] MCP 工具注册** — `E:\project\douyin_to_obsidian\src\bridge\mcp_server.py`
   - 新增 `asr_transcribe(audio_base64: str, format: str)` 工具
   - 内部解码 → 写临时文件 → 调 mimo-v2.5-asr API → 返回 JSON (text/segments/source/confidence)
   - **Spec ref**: WHEN openclaw agent 调用 `asr_transcribe(audio_path="/tmp/test.wav")` THEN 返回 JSON 含四字段

4. **[REFACTOR] 验证**
   - `pytest tests/asr/test_mimo_client.py -v` 全绿
   - 手动 5s 测试音频走 MCP 工具调用，确认返回 ASRResult

### Verification
- [ ] Mock MCP: 30s 音频 → ASRResult(text 非空, segments 列表, source="mimo_asr", confidence>=0.8)
- [ ] Mock MCP: 0.5s 音频 → ASRError, code="audio_too_short"
- [ ] Mock MCP: 超时 → ASRError, code="asr_timeout"
- [ ] D-M2-1: 无直连 mimo API 的 import，所有调用经 openclaw

archived-with: 2026-06-21-m2-asr-fallback
---

## Task 3: 音频预处理 — ffmpeg 抽取 (0.5d)

**Goal**: 从视频文件抽取 16kHz mono WAV，供 ASR 使用。

### Steps

1. **[RED] 写测试** — `E:\project\douyin_to_obsidian\tests\asr\test_audio_preprocess.py`
   - 给定 10s 测试视频 → 抽出 WAV 为 16kHz / mono / PCM
   - 输入不存在的文件 → 抛 FileNotFoundError
   - 输入损坏视频 → 抛 ASRError("audio_extract_failed")
   - **Spec ref task-queue-pipeline**: WHEN 无字幕 THEN ffmpeg 抽 16kHz wav

2. **[GREEN] 实现** — `E:\project\douyin_to_obsidian\src\asr\audio_preprocess.py`
   - `extract_audio(video_path: Path, out_path: Path = None) -> Path`:
     - 调 ffmpeg `-i video -vn -acodec pcm_s16le -ar 16000 -ac 1 out.wav`
     - 校验输出文件存在且 > 0 bytes
     - 返回 out_path (默认 tempdir)
   - 复用 M1 已有的 ffmpeg subprocess 封装模式

3. **[REFACTOR] 验证**
   - `pytest tests/asr/test_audio_preprocess.py -v` 全绿
   - 手动 ffmpeg 命令对比输出文件 header 确认 16kHz mono

### Verification
- [ ] 10s 视频 → WAV 文件 ffprobe 报告 sample_rate=16000, channels=1
- [ ] 不存在文件 → FileNotFoundError
- [ ] 损坏文件 → ASRError, code="audio_extract_failed"

archived-with: 2026-06-21-m2-asr-fallback
---

## Task 4: 本地 faster-whisper + Belle — 二期 (2d)

**Goal**: WhisperLocalClient，4070S 12G 本地推理，默认关闭。D-M2-5。

### Steps

1. **[RED] 写测试** — `E:\project\douyin_to_obsidian\tests\asr\test_whisper_local.py`
   - **Spec ref asr-local-whisper**: WHEN 传入 30s 中文音频, provider=whisper_local THEN ASRResult(source="whisper_local", confidence>=0.9)
   - **Spec ref asr-local-whisper**: WHEN CUDA 不可用 THEN ASRError("gpu_unavailable")
   - **Spec ref asr-local-whisper**: WHEN 显存不足(<2GB) THEN ASRError("oom")
   - **Spec ref asr-local-whisper**: WHEN 首次调用 THEN 模型加载耗时 <10s, 后续无加载开销
   - **Spec ref asr-local-whisper**: WHEN 调用 unload() THEN torch.cuda.empty_cache() 被调用
   - Mock `faster_whisper.WhisperModel` 返回预设 segments

2. **[GREEN] 实现** — `E:\project\douyin_to_obsidian\src\asr\local_whisper.py`
   - `WhisperLocalClient(ASRClient)`:
     - `__init__(config)`: 读 config.asr.whisper (model/device/compute_type)
     - `_ensure_model()`: 懒加载 faster-whisper + Belle-whisper-large-v3-turbo-zh, CUDA, int8_float16
     - `transcribe(audio_path)`:
       - 检查 CUDA 可用性 → 不可用则 ASRError("gpu_unavailable")
       - 检查显存 (torch.cuda.mem_get_info) < 2GB → ASRError("oom")
       - VAD 切片 + 批量推理 + 拼接 segments
       - 返回 ASRResult(source="whisper_local")
     - `unload()`: `del self._model; torch.cuda.empty_cache()`
   - **4070S 串行铁律**: 不启动后台线程，transcribe 是阻塞调用

3. **[REFACTOR] 验证**
   - `pytest tests/asr/test_whisper_local.py -v` 全绿 (mock 模式)
   - 如有 GPU 环境: 30s 测试音频真实转写，确认 CER <= 5%
   - 显存监控: 转写期间 peak VRAM < 10GB (12G 预算)

### Verification
- [ ] Mock: 30s 音频 → ASRResult(source="whisper_local", confidence>=0.9)
- [ ] Mock: CUDA=False → ASRError, code="gpu_unavailable"
- [ ] Mock: 显存不足 → ASRError, code="oom"
- [ ] Mock: 首次调用后 _model 不为 None，第二次不重新加载
- [ ] Mock: unload() 后 _model 为 None, empty_cache 被调用
- [ ] D-M2-5: config.example.yaml 默认 provider=mimo，whisper_local 需手动切换

archived-with: 2026-06-21-m2-asr-fallback
---

## Task 5: 调度器 ASR 分支改造 (1d)

**Goal**: scheduler.py fetching 阶段加 ASR 分支，替代 M1 的 failed(no_subtitle_in_m1)。核心改动。

### Steps

1. **[RED] 写测试** — `E:\project\douyin_to_obsidian\tests\pipeline\test_scheduler_asr.py`
   - **Spec ref task-queue-pipeline**: WHEN yt-dlp 抓不到字幕 + provider=mimo THEN ffmpeg 抽音频 → mimo-asr → subtitle_source="mimo_asr" → writing
   - **Spec ref task-queue-pipeline**: WHEN yt-dlp 抓不到字幕 + provider=whisper_local THEN ffmpeg 抽音频 → whisper → subtitle_source="whisper_local" → writing
   - **Spec ref task-queue-pipeline**: WHEN mimo-asr 失败 + whisper_local 可用 THEN 降级; 都失败 → failed(asr_failed)
   - **Spec ref task-queue-pipeline**: WHEN yt-dlp 抓到字幕 THEN 直接走字幕路径，不调 ASR (M1 不变)
   - **Spec ref douyin-extraction**: WHEN 调用 download_video_only THEN 返回 dict(video_path, info_dict, subtitle_path=None)
   - Mock downloader + ASR client，验证状态转移

2. **[GREEN] downloader 改造** — `E:\project\douyin_to_obsidian\src\extractors\downloader.py`
   - 新增 `download_video_only(url, out_dir, cookies_path) -> dict`:
     - yt-dlp 只下载视频 (无 --write-subs)
     - 返回 `{"video_path": Path, "info_dict": dict, "subtitle_path": None}`
     - 失败 → 抛 DownloadError
   - **Spec ref douyin-extraction**: WHEN 无 --write-subs 参数 THEN subtitle_path=None

3. **[GREEN] scheduler 改造** — `E:\project\douyin_to_obsidian\src\pipeline\scheduler.py`
   - `_download_with_fallback` 原逻辑: 无字幕 → failed
   - 新逻辑:
     ```
     subtitle = yt-dlp 尝试抓字幕
     if subtitle:
         subtitle_source = "douyin_native"  # M1 不变
     else:
         video_path = download_video_only(...)
         wav_path = extract_audio(video_path)  # Task 3
         asr_client = get_asr_client(config)   # Task 1
         try:
             result = asr_client.transcribe(wav_path)
             subtitle_source = result.source
         except ASRError as e:
             # 降级逻辑
             if e.code in ("asr_timeout", ...) and config 有 whisper_local:
                 result = whisper_client.transcribe(wav_path)
                 subtitle_source = "whisper_local"
             else:
                 raise  # → failed(asr_failed)
     ```
   - frontmatter `subtitle_source` 新增值: `mimo_asr` / `whisper_local`

4. **[REFACTOR] 验证**
   - `pytest tests/pipeline/test_scheduler_asr.py -v` 全绿
   - 确认 M1 有字幕路径零改动 (diff 干净)

### Verification
- [ ] 有字幕视频 → subtitle_source="douyin_native" (M1 不变)
- [ ] 无字幕 + mimo 成功 → subtitle_source="mimo_asr", 笔记含转写文字
- [ ] 无字幕 + mimo 失败 + whisper 成功 → subtitle_source="whisper_local"
- [ ] 无字幕 + 全部失败 → failed(asr_failed)
- [ ] download_video_only 返回 subtitle_path=None

archived-with: 2026-06-21-m2-asr-fallback
---

## Task 6: 配置更新 (0.5d)

**Goal**: config / .env / RUNBOOK 新增 ASR 配置块。

### Steps

1. **[RED] 写测试** — `E:\project\douyin_to_obsidian\tests\config\test_asr_config.py`
   - 解析 config.example.yaml 中 asr 块 → dict 含 provider / mimo / whisper
   - 默认 provider == "mimo"
   - 切换 provider == "whisper_local" 后工厂返回 WhisperLocalClient

2. **[GREEN] 实现**
   - `E:\project\douyin_to_obsidian\config.example.yaml`: 新增 asr 配置块 (D-M2-2)
     ```yaml
     asr:
       provider: mimo  # mimo | whisper_local
       mimo:
         model: mimo-v2.5-asr
       whisper:
         model: Belle-whisper-large-v3-turbo-zh
         device: cuda
         compute_type: int8_float16
     ```
   - `E:\project\douyin_to_obsidian\.env.example`: 新增 `MIMO_ASR_MODEL=mimo-v2.5-asr`
   - `E:\project\douyin_to_obsidian\docs\m1\RUNBOOK.md`: 新增 ASR 启停/切换说明

3. **[REFACTOR] 验证**
   - `pytest tests/config/test_asr_config.py -v` 全绿
   - config.example.yaml 可被 yaml.safe_load 无报错

### Verification
- [ ] config.example.yaml 包含 asr.provider / asr.mimo / asr.whisper 三块
- [ ] 默认值 provider=mimo (D-M2-5)
- [ ] .env.example 包含 MIMO_ASR_MODEL

archived-with: 2026-06-21-m2-asr-fallback
---

## Task 7: 知识文档 + 端到端测试 (1d)

**Goal**: KNOWLEDGE.md 技术参考 + E2E 回归。

### Steps

1. **[RED] 写 E2E 测试** — `E:\project\douyin_to_obsidian\tests\e2e\test_asr_e2e.py`
   - **场景 1**: curl 提交有字幕视频 → 字幕路径 → 笔记含字幕全文 (M1 回归)
   - **场景 2**: curl 提交无字幕视频 → mimo-asr 路径 → 笔记含转写文字
   - **场景 3**: 无字幕 + ASR 失败 → failed(asr_failed)
   - **场景 4**: 切换 whisper_local → 无字幕视频走本地 Whisper
   - **性能**: 5 条无字幕视频串行，平均 <= 3min/条
   - **Spec ref task-queue-pipeline**: 全部 4 个 WHEN/THEN 场景

2. **[GREEN] 文档** — `E:\project\douyin_to_obsidian\docs\m2\KNOWLEDGE.md`
   - 视频下载地址: yt-dlp 参数、cookie 配置、抖音反爬现状
   - ASR 模型调用: mimo-v2.5-asr API 格式、faster-whisper Python API
   - 安装地址: cuDNN 9.x、ctranslate2 版本、Belle HuggingFace 链接
   - cuDNN 配对表: ctranslate2 >=4.5 → cuDNN 9, <4.5 → cuDNN 8
   - 性能基准: 4070S 速度/显存/CER 对比

3. **[REFACTOR] 验证**
   - E2E 测试全绿
   - KNOWLEDGE.md 无占位符/TODO
   - 5 条视频串行跑通，vault 出现笔记

### Verification
- [ ] 有字幕视频 → M1 路径正常 (回归)
- [ ] 无字幕视频 → vault 出笔记，frontmatter 含 subtitle_source=mimo_asr
- [ ] ASR 全部失败 → failed(asr_failed) 状态正确
- [ ] whisper_local 切换后 无字幕视频 → subtitle_source=whisper_local
- [ ] KNOWLEDGE.md 四章节完整，无 TODO

archived-with: 2026-06-21-m2-asr-fallback
---

## 关键约束检查表

| 约束 | 检查点 |
|------|--------|
| D-M2-1 openclaw 合规 | mimo_client.py 无直连 mimo API 的 import; 所有调用经 MCP 工具 |
| D-M2-2 ASRResult 统一 | MimoASRClient / WhisperLocalClient 均返回 ASRResult |
| D-M2-3 调度器 ASR 分支 | scheduler.py 无字幕 → ASR 而非 failed |
| D-M2-4 MCP 工具 | mcp_server.py 暴露 asr_transcribe |
| D-M2-5 默认关闭 | config.example.yaml provider=mimo |
| 4070S 串行铁律 | local_whisper.py 无并行线程，transcribe 阻塞调用 |
| M1 回归 | 有字幕路径 diff 零改动 |

## 任务依赖

```
Task 1 (接口) ─┬─→ Task 2 (mimo)  ─┬─→ Task 5 (调度器) ─→ Task 7 (E2E)
               │                    │
               └─→ Task 4 (whisper) ┘        ↑
                                              │
Task 3 (音频) ───────────────────────────────┘
                                              │
Task 6 (配置) ───────────────────────────────┘
```

## 工时汇总

| Task | 工时 | 里程碑 |
|------|------|--------|
| 1. ASR 接口 | 0.5d | Day 1 AM |
| 2. mimo 客户端 | 1d | Day 1-2 |
| 3. 音频预处理 | 0.5d | Day 2 |
| 4. 本地 Whisper | 2d | Day 3-4 |
| 5. 调度器改造 | 1d | Day 5 |
| 6. 配置更新 | 0.5d | Day 5 |
| 7. E2E + 文档 | 1d | Day 6-7 |
| **合计** | **6.5d** | |
