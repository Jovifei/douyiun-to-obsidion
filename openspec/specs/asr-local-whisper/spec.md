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
