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
