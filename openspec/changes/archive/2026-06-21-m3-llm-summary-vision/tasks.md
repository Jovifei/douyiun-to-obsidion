# M3 实施任务清单

> Change: `m3-llm-summary-vision`
> Workflow: full (spec-driven)
> 总工时估算: **7-10 天**（LLM 总结 ~2 天，视觉理解 ~4 天，启发式分流 ~1 天，集成测试 ~2 天）
> 依赖：M1 + M2 完成

## 1. LLM 总结接口设计（0.5 天）

- [x] 1.1 创建 `src/llm/__init__.py`，定义 `SummaryResult` dataclass（summary_text / key_points / model / source / confidence）
- [x] 1.2 定义 `SummarizerClient` 抽象基类：`summarize(subtitle_text: str, metadata: dict) -> SummaryResult`
- [x] 1.3 定义 `get_summarizer(config) -> SummarizerClient` 工厂函数
- [x] 1.4 单元测试：mock SummarizerClient，验证 SummaryResult 字段

## 2. mimo-v2.5-pro 总结客户端（一期）（1 天）

- [x] 2.1 创建 `src/llm/mimo_summarizer.py`：`MimoSummarizer` 实现 `SummarizerClient`
- [x] 2.2 实现 `summarize(subtitle_text, metadata)`：构造 prompt → 调 mimo-v2.5-pro API → 解析返回
- [x] 2.3 prompt 模板实现：按 D-M3-4 格式，3-5 要点、中文、按重要性排序
- [x] 2.4 实现 prompt 超长截断：字幕 > 8000 字时截取前后各 4000 字 + 中间摘要提示
- [x] 2.5 错误处理：API 超时 / 返回空 / 格式不对 → ASRError("llm_failed")，上层调度器跳过总结
- [x] 2.6 openclaw MCP 工具注册：`src/bridge/mcp_server.py` 新增 `llm_summarize` 工具
- [x] 2.7 单元测试：mock API 调用，验证 SummaryResult

## 3. 视觉理解 — 关键帧抽取（1 天）

- [x] 3.1 创建 `src/vision/keyframe_extractor.py`：从视频文件抽取关键帧图片
- [x] 3.2 实现 ffmpeg scene detect：`ffmpeg -vf "select='gt(scene,0.4)'" -vsync vframe`
- [x] 3.3 实现按时间均匀采样（scene detect 帧太少时兜底，每 10 秒一帧）
- [x] 3.4 实现关键帧输出到 `tmp_dir/{video_id}_keyframes/`
- [x] 3.5 单元测试：mock ffmpeg，验证关键帧路径列表

## 4. 视觉理解 — OCR（0.5 天）

- [x] 4.1 创建 `src/vision/ocr_client.py`：调 PaddleOCR PP-OCRv5
- [x] 4.2 实现 `extract_text_from_image(image_path: Path) -> str`
- [x] 4.3 错误处理：OCR 失败 / 模型未装 → 返回空字符串，不阻塞
- [x] 4.4 单元测试：mock PaddleOCR，验证中文文字提取

## 5. 视觉理解 — VLM（1.5 天）

- [x] 5.1 创建 `src/vision/vlm_client.py`：VLM 理解模块
- [x] 5.2 一期：`MimoVLMClient` 调 mimo-v2-omni（走 openclaw MCP 工具）
- [x] 5.3 二期：`LocalVLMClient` 调本地 Qwen2.5-VL-7B AWQ-4bit（默认关闭）
- [x] 5.4 VLM prompt 设计："这是一段抖音知识视频的关键帧，请描述画面中的关键信息"
- [x] 5.5 实现逐帧推理 + 聚合描述
- [x] 5.6 openclaw MCP 工具注册：`mimo_vlm` 工具
- [x] 5.7 单元测试：mock API，验证 VLM 描述文本

## 6. 启发式分流（1 天）

- [x] 6.1 创建 `src/vision/heuristic_router.py`：视频类型判断
- [x] 6.2 实现 `classify_video(subtitle_text, video_duration, keyframe_count) -> str`
- [x] 6.3 返回值：`"summary_only"` / `"summary_with_vlm"` / `"ocr_only"`
- [x] 6.4 实现字幕密度计算：字幕字数 / 视频时长
- [x] 6.5 单元测试：mock 数据验证 3 种分流路径

## 7. 调度器集成（1.5 天）

- [x] 7.1 修改 `src/pipeline/scheduler.py` writing 阶段：加 LLM 总结分支
- [x] 7.2 修改 `src/obsidian/note_builder.py`：`## 摘要` 段从占位改为实际总结内容
- [x] 7.3 修改 frontmatter：`summary_status` 从 `not_run` 改为 `done`（LLM 成功时）
- [x] 7.4 修改 frontmatter：`ai_summary_model` 记录实际使用的模型名
- [x] 7.5 视觉理解集成（`config.yaml vision.enabled: true` 时触发）：
  - 关键帧抽取 → OCR → VLM → 写入 `## 关键帧` 段
- [x] 7.6 修改 `processing_mode`：根据实际路径更新（`subtitle_only` / `subtitle_vlm` / `full`）
- [x] 7.7 串行铁律：LLM 和 VLM 不并行，用锁或队列串行执行
- [x] 7.8 单元测试：mock LLM/VLM，验证笔记正文含总结 + 关键帧描述

## 8. 配置更新（0.5 天）

- [x] 8.1 更新 `config.example.yaml`：新增 `llm` 配置块（provider/mimo/api_key/base_url）和 `vision` 配置块（enabled/ocr_model/vlm_model）
- [x] 8.2 更新 `config.yaml`：默认 `vision.enabled: false`
- [x] 8.3 更新 `docs/m1/RUNBOOK.md`：新增 LLM 总结和视觉理解的启停说明

## 9. 端到端测试 + 文档（1 天）

- [x] 9.1 测试场景 1：curl 提交有字幕视频 → 笔记含 AI 总结（3-5 要点）
- [x] 9.2 测试场景 2：curl 提交无字幕视频 → ASR 转写 + LLM 总结
- [x] 9.3 测试场景 3：curl 提交 PPT 类视频（`vision.enabled: true`）→ 笔记含关键帧 OCR + VLM 描述
- [x] 9.4 测试场景 4：LLM 超时 → 笔记仍含字幕（summary 占位，summary_status=failed）
- [x] 9.5 测试场景 5：VLM 禁用（`vision.enabled: false`）→ 笔记只含总结，关键帧段为占位
- [x] 9.6 性能基准：5 条视频串行，平均端到端 ≤ 4 分钟/条（含 LLM 调用）
- [x] 9.7 更新 `docs/m2/KNOWLEDGE.md`：新增 LLM prompt 模板、VLM 选型对比、4070S 显存预算表
