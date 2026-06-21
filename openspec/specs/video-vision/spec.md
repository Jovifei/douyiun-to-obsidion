## ADDED Requirements

### Requirement: 关键帧抽取

系统 SHALL 从视频文件抽取关键帧图片，供 OCR 和 VLM 使用。

#### Scenario: scene detect 抽取

- **WHEN** 视频含 PPT 切换/图表变化（场景变化率 > 0.4）
- **THEN** 抽取 N 张关键帧到 `tmp_dir/{video_id}_keyframes/`

#### Scenario: 兜底均匀采样

- **WHEN** scene detect 抽到的帧 < 3 张
- **THEN** 每 10 秒补抽 1 帧，最多 30 帧

### Requirement: OCR 文字提取

系统 SHALL 用 PaddleOCR PP-OCRv5 从关键帧图片提取中文文字。

#### Scenario: 正常 OCR

- **WHEN** 传入含中文文字的 PPT 截图
- **THEN** 返回识别文字字符串（中文准确率 > 95%）

#### Scenario: OCR 失败

- **WHEN** 模型未装 / 图片模糊
- **THEN** 返回空字符串，不阻塞后续流程

### Requirement: VLM 视觉理解

系统 SHALL 通过 openclaw MCP 工具 `mimo_vlm` 调用 mimo-v2-omni，接收关键帧图片，返回画面描述。

#### Scenario: 正常 VLM

- **WHEN** 传入 PPT 关键帧图片
- **THEN** 返回描述文本（"PPT展示了XXX流程图"）

#### Scenario: VLM 禁用

- **WHEN** config.yaml `vision.enabled: false`
- **THEN** 跳过 VLM，笔记关键帧段写"视觉理解已禁用"

#### Scenario: VLM 超时

- **WHEN** API 超时 30 秒
- **THEN** 返回"VLM 超时，画面内容未提取"，不阻塞笔记生成

### Requirement: 启发式分流

系统 SHALL 根据字幕内容 + 视频特征判断视频类型，决定处理路径。

#### Scenario: 口播类视频（summary_only）

- **WHEN** 字幕密度 > 0.5 字/秒 且 场景变化率 < 0.3
- **THEN** 只走 LLM 总结，不走 VLM

#### Scenario: PPT/图表类视频（summary_with_vlm）

- **WHEN** 字幕密度 < 0.3 字/秒 且 场景变化率 > 0.5
- **THEN** 走 LLM 总结 + 关键帧 OCR + VLM

#### Scenario: 混合类视频（summary_with_vlm）

- **WHEN** 字幕密度介于 0.3-0.5 之间
- **THEN** 走 LLM 总结 + 关键帧 OCR + VLM（保守策略）
