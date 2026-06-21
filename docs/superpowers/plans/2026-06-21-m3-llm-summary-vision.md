---
change: m3-llm-summary-vision
design-doc: docs/superpowers/specs/2026-06-21-m3-llm-summary-vision-design.md
base-ref: 8fcb17541db0614a0a9991ec7ccccbfd23caa73a
archived-with: 2026-06-21-m3-llm-summary-vision
---

# M3 LLM 总结 + 视觉理解 Implementation Plan

> Timeline: 7-10 days
> Base: M1 + M2 (archived)
> Constraint: D-M3-1 openclaw 合规, D-M3-2 视觉分层, D-M3-3 启发式分流, D-M3-4 prompt 模板, D-M3-5 frontmatter 更新, D-M3-6 串行铁律, vision.enabled 默认 false

archived-with: 2026-06-21-m3-llm-summary-vision
---

## Task 1: LLM 总结接口设计 (0.5d)

**Goal**: 定义 SummaryResult / SummarizerClient / factory，为后续实现提供契约。

### Steps

1. **[RED] 写测试** — `E:\project\douyin_to_obsidian\tests\llm\test_summarizer_interface.py`
   - 断言 `SummaryResult` dataclass 五字段 (summary_text, key_points, model, source, confidence) 可实例化、可序列化
   - 断言 `SummarizerClient` 抽象基类 `summarize(subtitle_text: str, metadata: dict) -> SummaryResult` 存在且不可直接实例化
   - 断言 `get_summarizer(config)` 返回 `MimoSummarizer` 实例
   - 断言未知 provider → `ValueError`
   - **Spec ref llm-summarizer**: WHEN 传入 500 字字幕 THEN 返回 SummaryResult (confidence>=0.8)

2. **[GREEN] 实现** — `E:\project\douyin_to_obsidian\src\llm\__init__.py`
   - `SummaryResult` dataclass: `summary_text: str`, `key_points: list[str]`, `model: str`, `source: str`, `confidence: float`
   - `SummarizerClient` ABC: `summarize(self, subtitle_text: str, metadata: dict) -> SummaryResult`
   - `get_summarizer(config: dict) -> SummarizerClient` 工厂
   - 异常类 `LLMError(Exception)` 带 `code` 字段 (llm_timeout / llm_failed / subtitle_too_short)

3. **[REFACTOR] 验证**
   - `pytest tests/llm/test_summarizer_interface.py -v` 全绿
   - 确认 `LLMError.code` 可被调度器匹配

### Verification
- [ ] `SummaryResult(summary_text="test", key_points=["a","b"], model="mimo", source="mimo_llm", confidence=0.9)` 序列化 round-trip
- [ ] 工厂函数对 mimo provider 正确路由
- [ ] Spec llm-summarizer WHEN 正常总结 THEN 返回完整 SummaryResult 通过

archived-with: 2026-06-21-m3-llm-summary-vision
---

## Task 2: mimo-v2.5-pro 总结客户端 (1d)

**Goal**: 实现 MimoSummarizer，通过 openclaw MCP 工具调 mimo-v2.5-pro。D-M3-1 合规方案 A。

### Steps

1. **[RED] 写测试** — `E:\project\douyin_to_obsidian\tests\llm\test_mimo_summarizer.py`
   - **Spec ref llm-summarizer**: WHEN 传入 500 字字幕 + 视频标题 THEN 返回 SummaryResult (key_points 3-5 条, model="mimo-v2.5-pro", confidence>=0.8)
   - **Spec ref llm-summarizer**: WHEN 字幕 < 50 字 THEN 返回 SummaryResult (summary_text="字幕内容过短", key_points=[], confidence=0.5)
   - **Spec ref llm-summarizer**: WHEN openclaw MCP 调用超时 30s THEN 抛 LLMError("llm_timeout")
   - **Spec ref llm-summarizer**: WHEN 字幕 > 8000 字 THEN 自动截取前后各 4000 字 + 中间省略提示
   - Mock `openclaw.call_tool("llm_summarize", ...)` 返回预设 JSON
   - 断言 prompt 包含 D-M3-4 模板内容 (3-5 要点、中文、按重要性排序)

2. **[GREEN] 实现** — `E:\project\douyin_to_obsidian\src\llm\mimo_summarizer.py`
   - `MimoSummarizer(SummarizerClient)`:
     - `summarize(subtitle_text, metadata)`:
       - 校验字幕长度 (< 50 字 → SummaryResult 短文本提示)
       - 超长截断: > 8000 字 → 前 4000 + "...[中间内容已省略]..." + 后 4000
       - 构造 prompt (D-M3-4 模板)
       - 调 `openclaw.call_tool("llm_summarize", {"prompt": ..., "metadata": ...})` (D-M3-1)
       - 30s 超时 → LLMError("llm_timeout")
       - 解析返回 → SummaryResult(source="mimo_llm")

3. **[GREEN] MCP 工具注册** — `E:\project\douyin_to_obsidian\src\bridge\mcp_server.py`
   - 新增 `llm_summarize(prompt: str, metadata: dict)` 工具
   - 内部调 mimo-v2.5-pro API → 返回 JSON (summary_text/key_points/model/confidence)
   - **Spec ref llm-summarizer**: WHEN openclaw agent 调用 `llm_summarize` THEN 返回 JSON 含四字段

4. **[REFACTOR] 验证**
   - `pytest tests/llm/test_mimo_summarizer.py -v` 全绿
   - 手动 500 字字幕走 MCP 工具调用，确认返回 SummaryResult

### Verification
- [ ] Mock MCP: 500 字字幕 → SummaryResult(key_points 3-5 条, model="mimo-v2.5-pro")
- [ ] Mock MCP: 30 字字幕 → SummaryResult(confidence=0.5, key_points=[])
- [ ] Mock MCP: 超时 → LLMError, code="llm_timeout"
- [ ] Mock MCP: 10000 字字幕 → prompt 包含截断标记
- [ ] D-M3-1: 无直连 mimo API 的 import，所有调用经 openclaw

archived-with: 2026-06-21-m3-llm-summary-vision
---

## Task 3: 视觉理解 — 关键帧抽取 (1d)

**Goal**: 从视频文件抽取关键帧图片，供 OCR 和 VLM 使用。D-M3-2 第一层。

### Steps

1. **[RED] 写测试** — `E:\project\douyin_to_obsidian\tests\vision\test_keyframe_extractor.py`
   - **Spec ref video-vision**: WHEN 视频含 PPT 切换 (scene change rate > 0.4) THEN 抽取 N 张关键帧到 `tmp_dir/{video_id}_keyframes/`
   - **Spec ref video-vision**: WHEN scene detect 帧 < 3 张 THEN 每 10 秒补抽 1 帧，最多 30 帧
   - Mock ffmpeg subprocess，验证关键帧路径列表
   - 断言输出目录结构正确

2. **[GREEN] 实现** — `E:\project\douyin_to_obsidian\src\vision\keyframe_extractor.py`
   - `KeyframeExtractor`:
     - `extract(video_path: Path, video_id: str, tmp_dir: Path) -> list[Path]`:
       - ffmpeg scene detect: `-vf "select='gt(scene,0.4)'" -vsync vframe`
       - 如帧数 < 3 → 兜底均匀采样 (每 10s 一帧, max 30 帧)
       - 输出到 `tmp_dir/{video_id}_keyframes/frame_NNN.jpg`
       - 返回关键帧路径列表
   - 创建 `E:\project\douyin_to_obsidian\src\vision\__init__.py`

3. **[REFACTOR] 验证**
   - `pytest tests/vision/test_keyframe_extractor.py -v` 全绿
   - 手动 ffmpeg 命令对比输出帧数

### Verification
- [ ] Mock ffmpeg: PPT 视频 → 关键帧列表非空，路径含 video_id
- [ ] Mock ffmpeg: scene detect 帧 < 3 → 兜底采样触发，帧数 >= 3
- [ ] 输出目录结构: `tmp_dir/{video_id}_keyframes/frame_001.jpg`

archived-with: 2026-06-21-m3-llm-summary-vision
---

## Task 4: 视觉理解 — OCR (0.5d)

**Goal**: PaddleOCR PP-OCRv5 从关键帧提取中文文字。D-M3-2 第二层。

### Steps

1. **[RED] 写测试** — `E:\project\douyin_to_obsidian\tests\vision\test_ocr_client.py`
   - **Spec ref video-vision**: WHEN 传入含中文文字的 PPT 截图 THEN 返回识别文字字符串 (中文准确率 > 95%)
   - **Spec ref video-vision**: WHEN 模型未装 / 图片模糊 THEN 返回空字符串，不阻塞
   - Mock `paddleocr.PaddleOCR`，验证中文文字提取

2. **[GREEN] 实现** — `E:\project\douyin_to_obsidian\src\vision\ocr_client.py`
   - `OCRClient`:
     - `extract_text(image_path: Path) -> str`:
       - 调 PaddleOCR PP-OCRv5 (use_angle_cls=True, lang="ch")
       - 返回拼接文字
       - 异常 → 返回空字符串 (不阻塞)
   - 懒加载 PaddleOCR 模型 (首次调用时初始化)

3. **[REFACTOR] 验证**
   - `pytest tests/vision/test_ocr_client.py -v` 全绿
   - 手动 PPT 截图 OCR，确认中文提取

### Verification
- [ ] Mock PaddleOCR: 中文 PPT 截图 → 文字字符串非空
- [ ] Mock PaddleOCR: 模型异常 → 返回空字符串
- [ ] 懒加载: 首次调用后 _ocr 不为 None

archived-with: 2026-06-21-m3-llm-summary-vision
---

## Task 5: 视觉理解 — VLM (1.5d)

**Goal**: VLM 理解模块。一期 mimo-v2-omni (openclaw)，二期本地 Qwen2.5-VL-7B。D-M3-2 第三层。

### Steps

1. **[RED] 写测试** — `E:\project\douyin_to_obsidian\tests\vision\test_vlm_client.py`
   - **Spec ref video-vision**: WHEN 传入 PPT 关键帧图片 THEN 返回描述文本 ("PPT展示了XXX流程图")
   - **Spec ref video-vision**: WHEN config `vision.enabled: false` THEN 跳过 VLM
   - **Spec ref video-vision**: WHEN API 超时 30s THEN 返回"VLM 超时"，不阻塞
   - Mock openclaw MCP 工具调用，验证 VLM 描述文本

2. **[GREEN] 实现** — `E:\project\douyin_to_obsidian\src\vision\vlm_client.py`
   - `VLMClient` ABC: `describe(image_path: Path) -> str`
   - `MimoVLMClient(VLMClient)`:
     - 调 `openclaw.call_tool("mimo_vlm", {"image_base64": ...})` (D-M3-1)
     - 30s 超时 → 返回"VLM 超时，画面内容未提取"
   - `LocalVLMClient(VLMClient)`:
     - 调本地 Qwen2.5-VL-7B AWQ-4bit (默认关闭)
   - `get_vlm_client(config) -> VLMClient` 工厂

3. **[GREEN] MCP 工具注册** — `E:\project\douyin_to_obsidian\src\bridge\mcp_server.py`
   - 新增 `mimo_vlm(image_base64: str)` 工具
   - 内部调 mimo-v2-omni API → 返回描述文本

4. **[REFACTOR] 验证**
   - `pytest tests/vision/test_vlm_client.py -v` 全绿
   - 手动 PPT 截图走 MCP 工具调用，确认返回描述

### Verification
- [ ] Mock MCP: PPT 截图 → 描述文本非空
- [ ] Mock MCP: 超时 → 返回"VLM 超时"字符串
- [ ] Mock MCP: vision.enabled=false → 工厂返回 None / 跳过
- [ ] D-M3-1: 无直连 mimo API 的 import

archived-with: 2026-06-21-m3-llm-summary-vision
---

## Task 6: 启发式分流 (1d)

**Goal**: 视频类型判断，决定走"纯字幕总结"还是"字幕 + 视觉理解"。D-M3-3。

### Steps

1. **[RED] 写测试** — `E:\project\douyin_to_obsidian\tests\vision\test_heuristic_router.py`
   - **Spec ref video-vision**: WHEN 字幕密度 > 0.5 字/秒 且 场景变化率 < 0.3 THEN 返回 "summary_only"
   - **Spec ref video-vision**: WHEN 字幕密度 < 0.3 字/秒 且 场景变化率 > 0.5 THEN 返回 "summary_with_vlm"
   - **Spec ref video-vision**: WHEN 字幕密度介于 0.3-0.5 THEN 返回 "summary_with_vlm" (保守策略)
   - Mock 数据验证 3 种分流路径

2. **[GREEN] 实现** — `E:\project\douyin_to_obsidian\src\vision\heuristic_router.py`
   - `classify_video(subtitle_text: str, video_duration: float, keyframe_count: int) -> str`:
     - 字幕密度 = len(subtitle_text) / video_duration
     - 场景变化率 = keyframe_count / (video_duration / 10)  # 归一化
     - 口播类 (density > 0.5, change_rate < 0.3) → "summary_only"
     - PPT 类 (density < 0.3, change_rate > 0.5) → "summary_with_vlm"
     - 混合类 → "summary_with_vlm" (保守)

3. **[REFACTOR] 验证**
   - `pytest tests/vision/test_heuristic_router.py -v` 全绿
   - 边界值测试: density=0.5, change_rate=0.3

### Verification
- [ ] 高密度低变化 → "summary_only"
- [ ] 低密度高变化 → "summary_with_vlm"
- [ ] 中间值 → "summary_with_vlm"
- [ ] 边界值不崩溃

archived-with: 2026-06-21-m3-llm-summary-vision
---

## Task 7: 调度器集成 (1.5d)

**Goal**: scheduler.py writing 阶段加 LLM 总结 + 视觉理解分支。核心改动。

### Steps

1. **[RED] 写测试** — `E:\project\douyin_to_obsidian\tests\pipeline\test_scheduler_m3.py`
   - **Spec ref task-queue-pipeline**: WHEN writing 阶段 + LLM 成功 THEN `## 摘要` 写入 3-5 要点, summary_status=done, ai_summary_model="mimo-v2.5-pro"
   - **Spec ref task-queue-pipeline**: WHEN LLM 超时/失败 THEN `## 摘要` 保留占位, summary_status=failed, 笔记仍入库
   - **Spec ref task-queue-pipeline**: WHEN vision.enabled=true + summary_with_vlm THEN 关键帧→OCR→VLM→`## 关键帧` 写入描述, processing_mode="subtitle_vlm"
   - **Spec ref task-queue-pipeline**: WHEN vision.enabled=false THEN 跳过视觉, processing_mode="subtitle_only", `## 关键帧` 写"视觉理解已禁用"
   - **Spec ref task-queue-pipeline**: WHEN 同时需要 LLM 和 VLM THEN 先 LLM 后 VLM，不并行 (D-M3-6)
   - Mock LLM/VLM/OCR，验证笔记正文

2. **[GREEN] scheduler 改造** — `E:\project\douyin_to_obsidian\src\pipeline\scheduler.py`
   - writing 阶段新逻辑:
     ```
     # 1. LLM 总结
     summarizer = get_summarizer(config)
     try:
         summary = summarizer.summarize(subtitle_text, metadata)
         summary_status = "done"
     except LLMError:
         summary = None
         summary_status = "failed"

     # 2. 启发式分流
     video_type = classify_video(subtitle_text, duration, keyframe_count)

     # 3. 视觉理解 (串行铁律: LLM 完成后才开始)
     vlm_result = None
     if config.vision.enabled and video_type == "summary_with_vlm":
         keyframes = extractor.extract(video_path, video_id, tmp_dir)
         ocr_texts = [ocr.extract_text(kf) for kf in keyframes]
         vlm_client = get_vlm_client(config)
         vlm_result = vlm_client.describe(keyframes)  # 逐帧推理 + 聚合

     # 4. 写笔记
     note = build_note(summary, vlm_result, ...)
     ```

3. **[GREEN] note_builder 改造** — `E:\project\douyin_to_obsidian\src\obsidian\note_builder.py`
   - `## 摘要` 段: summary 非空 → 写 key_points; 为空 → 写"LLM 总结失败：{原因}"
   - `## 关键帧` 段: vlm_result 非空 → 逐帧写描述; vision.enabled=false → 写"视觉理解已禁用"
   - **Spec ref obsidian-archive-writer**: WHEN SummaryResult.summary_text 非空 THEN `## 摘要` 写入 key_points
   - **Spec ref obsidian-archive-writer**: WHEN VLMResult.descriptions 非空 THEN `## 关键帧` 逐帧写入描述

4. **[GREEN] frontmatter 更新** — `E:\project\douyin_to_obsidian\src\obsidian\note_builder.py`
   - `summary_status`: "done" / "failed" (从 "not_run" 改)
   - `ai_summary_model`: "mimo-v2.5-pro" (记录模型名)
   - `processing_mode`: "subtitle_only" / "subtitle_vlm" / "full" (根据实际路径)
   - **Spec ref obsidian-archive-writer**: D-M3-5 全部字段更新

5. **[REFACTOR] 验证**
   - `pytest tests/pipeline/test_scheduler_m3.py -v` 全绿
   - 确认 M1/M2 路径零改动 (diff 干净)

### Verification
- [ ] LLM 成功 → summary_status=done, ai_summary_model="mimo-v2.5-pro"
- [ ] LLM 失败 → summary_status=failed, 笔记仍入库
- [ ] vision.enabled=true + PPT 视频 → processing_mode="subtitle_vlm"
- [ ] vision.enabled=false → processing_mode="subtitle_only", 关键帧段为占位
- [ ] LLM 和 VLM 串行 (无并行线程/协程)
- [ ] M1/M2 回归: 有字幕/ASR 路径 diff 零改动

archived-with: 2026-06-21-m3-llm-summary-vision
---

## Task 8: 配置更新 (0.5d)

**Goal**: config / .env / RUNBOOK 新增 LLM + vision 配置块。

### Steps

1. **[RED] 写测试** — `E:\project\douyin_to_obsidian\tests\config\test_m3_config.py`
   - 解析 config.example.yaml 中 llm 块 → dict 含 provider/mimo/api_key/base_url
   - 解析 config.example.yaml 中 vision 块 → dict 含 enabled/ocr_model/vlm_model
   - 默认 vision.enabled == false (D-M3-6)

2. **[GREEN] 实现**
   - `E:\project\douyin_to_obsidian\config.example.yaml`: 新增 llm + vision 配置块
     ```yaml
     llm:
       provider: mimo  # mimo
       mimo:
         model: mimo-v2.5-pro
         api_key: ${MIMO_API_KEY}
         base_url: ${MIMO_BASE_URL}

     vision:
       enabled: false  # D-M3-6: 默认关闭
       ocr_model: paddleocr_ppocrv5
       vlm:
         provider: mimo  # mimo | local
         mimo:
           model: mimo-v2-omni
         local:
           model: Qwen2.5-VL-7B-AWQ
           device: cuda
     ```
   - `E:\project\douyin_to_obsidian\.env.example`: 新增 `MIMO_API_KEY`, `MIMO_BASE_URL`
   - `E:\project\douyin_to_obsidian\docs\m1\RUNBOOK.md`: 新增 LLM 总结和视觉理解启停说明

3. **[REFACTOR] 验证**
   - `pytest tests/config/test_m3_config.py -v` 全绿
   - config.example.yaml 可被 yaml.safe_load 无报错

### Verification
- [ ] config.example.yaml 包含 llm.provider / llm.mimo / vision.enabled / vision.vlm 四块
- [ ] 默认值 vision.enabled=false (D-M3-6)
- [ ] .env.example 包含 MIMO_API_KEY, MIMO_BASE_URL

archived-with: 2026-06-21-m3-llm-summary-vision
---

## Task 9: 端到端测试 + 文档 (1d)

**Goal**: E2E 回归 + KNOWLEDGE.md 技术参考。

### Steps

1. **[RED] 写 E2E 测试** — `E:\project\douyin_to_obsidian\tests\e2e\test_m3_e2e.py`
   - **场景 1**: curl 提交有字幕视频 → 笔记含 AI 总结 (3-5 要点) (Spec llm-summarizer WHEN 正常总结)
   - **场景 2**: curl 提交无字幕视频 → ASR 转写 + LLM 总结 (Spec task-queue-pipeline)
   - **场景 3**: curl 提交 PPT 类视频 (vision.enabled=true) → 笔记含关键帧 OCR + VLM 描述 (Spec video-vision)
   - **场景 4**: LLM 超时 → 笔记仍含字幕, summary_status=failed (Spec llm-summarizer WHEN API 超时)
   - **场景 5**: vision.enabled=false → 笔记只含总结, 关键帧段为占位 (Spec video-vision WHEN VLM 禁用)
   - **性能**: 5 条视频串行，平均端到端 <= 4 分钟/条

2. **[GREEN] 文档** — `E:\project\douyin_to_obsidian\docs\m3\KNOWLEDGE.md`
   - LLM prompt 模板: D-M3-4 完整模板 + 截断策略
   - VLM 选型对比: mimo-v2-omni vs Qwen2.5-VL-7B (速度/质量/显存)
   - 4070S 显存预算表: LLM ~8GB, OCR ~2GB, VLM ~8GB, 串行铁律
   - 启发式分流参数: density 阈值, change_rate 阈值

3. **[REFACTOR] 验证**
   - E2E 测试全绿
   - KNOWLEDGE.md 无占位符/TODO
   - 5 条视频串行跑通，vault 出现笔记含摘要

### Verification
- [ ] 有字幕视频 → vault 笔记含 `## 摘要` 3-5 要点
- [ ] 无字幕视频 → ASR + LLM 总结，frontmatter 含 subtitle_source + summary_status=done
- [ ] PPT 视频 (vision=true) → 笔记含 `## 关键帧` 描述
- [ ] LLM 超时 → summary_status=failed，笔记仍正常
- [ ] vision=false → 关键帧段为占位文字
- [ ] KNOWLEDGE.md 四章节完整，无 TODO

archived-with: 2026-06-21-m3-llm-summary-vision
---

## 关键约束检查表

| 约束 | 检查点 |
|------|--------|
| D-M3-1 openclaw 合规 | mimo_summarizer.py / vlm_client.py 无直连 mimo API import; 所有调用经 MCP 工具 |
| D-M3-2 视觉分层 | keyframe_extractor → ocr_client → vlm_client 三层独立 |
| D-M3-3 启发式分流 | heuristic_router.py 三档分流: summary_only / summary_with_vlm / ocr_only |
| D-M3-4 prompt 模板 | 3-5 要点、中文、按重要性排序、超长截断 |
| D-M3-5 frontmatter | summary_status / ai_summary_model / processing_mode 从占位改为实际值 |
| D-M3-6 串行铁律 | LLM 和 VLM 不并行; config 默认 vision.enabled=false |
| M1/M2 回归 | 有字幕/ASR 路径 diff 零改动 |

## 任务依赖

```
Task 1 (接口) ─┬─→ Task 2 (mimo)  ─┬─→ Task 7 (调度器) ─→ Task 9 (E2E)
               │                    │
               └─→ Task 5 (VLM)  ──┘        ↑
                                              │
Task 3 (关键帧) ─→ Task 4 (OCR) ────────────┘
                                              │
Task 6 (分流) ───────────────────────────────┘
                                              │
Task 8 (配置) ───────────────────────────────┘
```

## 工时汇总

| Task | 工时 | 里程碑 |
|------|------|--------|
| 1. LLM 接口 | 0.5d | Day 1 AM |
| 2. mimo 总结客户端 | 1d | Day 1-2 |
| 3. 关键帧抽取 | 1d | Day 2-3 |
| 4. OCR | 0.5d | Day 3 |
| 5. VLM | 1.5d | Day 3-4 |
| 6. 启发式分流 | 1d | Day 5 |
| 7. 调度器集成 | 1.5d | Day 5-6 |
| 8. 配置更新 | 0.5d | Day 7 |
| 9. E2E + 文档 | 1d | Day 7-8 |
| **合计** | **8.5d** | |
