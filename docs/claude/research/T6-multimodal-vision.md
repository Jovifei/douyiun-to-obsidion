# T6 — 多模态视觉信息获取调研（抖音→Obsidian）

> 调研日期：2026-06-19 · 目标硬件：RTX 4070S 12 GB · 任务：在 Whisper/字幕主链路之外，把 PPT、图表、手写笔记等"画面信息"也吸进 Obsidian。

---

## TL;DR · 推荐主链路

```
ffmpeg 解码 ─► PySceneDetect (ContentDetector, t=27)
                       │
                       ▼  保存 1 帧 / 场景（典型 5–25 帧/分钟）
              ┌──────────────────────────┐
              │ 启发式分流（场景密度+OCR密度）│
              └──────────────────────────┘
            说话头     PPT/图表        图文混合
              │          │                │
              │     PaddleOCR PP-OCRv5    │
              │     (server)              │
              │          │           Qwen2.5-VL-7B-Instruct-AWQ
              │          │           （本地 4-bit，~6 GB 显存）
              │          ▼                ▼
              └────► 字幕 + OCR + VLM 描述 → LLM 融合 → Markdown
```

- **本地基线**：`ffmpeg + PySceneDetect + PaddleOCR PP-OCRv5(server) + Qwen2.5-VL-7B-Instruct AWQ-4bit`，全部 12 GB 显存内一次装下。
- **云端备选**：**智谱 GLM-4.5V / GLM-4V-Plus**——见 Part D 的判断。
- **不要**: GPT-4o（境内访问）、Claude Vision（境内访问 + 价格高）做主链路；只留作"重要长视频精修"。

---

## Part A · 关键帧抽取

### 方案对比

| 方案 | 命中率（PPT 切换） | 帧数控制 | 计算成本 | 适合场景 |
|---|---|---|---|---|
| `ffmpeg -vf select='gt(scene,0.4)'` | 中 | 中 | 极低（一次解码） | 快速预筛、无 Python 依赖 |
| `ffmpeg -vf thumbnail=N` | 低 | 强（每 N 帧选 1 张代表性帧） | 低 | 缩略图 / 海报，**不适合** PPT 抽取 |
| **PySceneDetect ContentDetector** | **高** | 中（可调 t） | 中（HSV 差分） | **推荐主力**，PPT/板书切换敏感 |
| PySceneDetect AdaptiveDetector | 中-高 | 高 | 中 | 镜头剧烈晃动的 vlog |
| 字幕中点采样 | 中 | 强（=字幕段数） | 极低 | 配合 Whisper 时间轴，画面信息少时省 |
| 均匀采样 N 秒 | 低 | 强 | 极低 | 兜底/调试 |

PySceneDetect 三个 detector：`ContentDetector`（HSV 差分，默认 27.0，PPT 切换最准）、`ThresholdDetector`（RGB 平均亮度，专门抓淡入淡出）、`AdaptiveDetector`（滚动均值，默认 3.0/min 15.0，抗摄像头晃动）。来源：scenedetect.com 官方文档。

### 命令模板

**ffmpeg 场景切分（最快预筛，输出 PNG）**：
```bash
ffmpeg -i input.mp4 -vf "select='gt(scene,0.4)',showinfo" -vsync vfr keyframe_%04d.png
```

**PySceneDetect Python（推荐主力）**：
```python
from scenedetect import detect, ContentDetector
from scenedetect.output import save_images

scenes = detect("input.mp4", ContentDetector(threshold=27.0, min_scene_len=15))
# min_scene_len=15 帧，约 0.5s @30fps，过滤掉转场抖动
save_images(scenes, video=open_video("input.mp4"),
            num_images=1, image_extension="jpg",
            output_dir="frames/", image_name_template="$SCENE_NUMBER")
```

**字幕中点采样（与 T5 Whisper 输出对齐）**：
```bash
# 给定 srt，每段中点抽 1 帧
python -c "import pysrt, subprocess; \
  subs=pysrt.open('out.srt'); \
  [subprocess.run(['ffmpeg','-ss',str((s.start+s.end)/2),'-i','in.mp4','-frames:v','1',f'mid_{i:04d}.jpg']) for i,s in enumerate(subs)]"
```

### 推荐策略

- 默认走 `PySceneDetect ContentDetector(t=27, min_scene_len=15帧)`。
- 对纯说话头视频（无 PPT），降级为字幕中点采样，降帧率到 1 帧/30 秒。
- 长视频 (>30 min) 先 `ffmpeg scene>0.5` 粗筛 → 再 PySceneDetect 精筛，省 30–50% 时间。

---

## Part B · 本地 OCR 横评

| 引擎 | 中文准确率（印刷体） | 显存(GPU) | 速度(单图 1080p) | 部署 | 备注 |
|---|---|---|---|---|---|
| **PaddleOCR PP-OCRv5 server** | **0.9013**（识别）+ **0.945**（检测） | ~10 GB(峰值，server-rec) | 0.3–0.6 s | Paddle/ONNX | **推荐**；比 v4 端到端 +13 pp（PaddleOCR 官方文档） |
| PaddleOCR PP-OCRv5 mobile | 0.8605 / 0.905 | ~2.4 GB | 0.1–0.2 s | Paddle/ONNX | 4070S 不需要降级；CPU 部署用 |
| PaddleOCR PP-OCRv4 | 0.8486 / 0.888 | ~3 GB | 0.2–0.4 s | Paddle/ONNX | 旧版，无理由还用 |
| **RapidOCR (PP-OCRv4/v5 ONNX)** | 与 PP-OCR 一致 | ~1–3 GB | 0.2–0.4 s | **纯 ONNX**，无 Paddle | **CPU/移动端推荐**；GPU 上比 Paddle 略慢 |
| EasyOCR | 0.85 左右（社区评测） | ~3 GB | 0.5–0.8 s | PyTorch | 多语种好；中文不如 PP-OCR |
| Tesseract 5 + chi_sim | 0.70–0.80 | CPU only | 1–2 s | C++ | **不推荐**：竖排/手写/倾斜场景拉胯；现代 OCR 全面碾压 |

**推荐**：4070S 上直接 PP-OCRv5 server 模型，启用 `use_gpu=True, use_tensorrt=True`，batch=4 单卡能稳吃。如果未来要打包给非 NVIDIA 同学，切到 RapidOCR (ONNXRuntime CPU/DirectML) 兼容性最好。

---

## Part C · 本地多模态大模型横评

| 模型 | 总参数 | 量化 4-bit 显存 | OCR/中文 | 推理后端 | 评价 |
|---|---|---|---|---|---|
| **Qwen2.5-VL-7B-Instruct** | 8B | **~6 GB**(AWQ-4bit) / ~16 GB(BF16) | **OCRBench 864**（超 GPT-4o-mini、InternVL2.5-8B） | Transformers / **vLLM** / SGLang / llama.cpp / Ollama | **首推**；142 个量化版本 |
| MiniCPM-V 2.6 | 8B (SigLip-400M + Qwen2-7B) | **~7 GB**(int4 官方版) / ~16 GB(BF16) | OCRBench 超 GPT-4o；支持 1344×1344 高分图 | Transformers + 官方 llama.cpp/Ollama 分支 | 高分辨率 PPT 优势；Ollama 装最省心 |
| InternVL2.5-8B | 8B | 8 GB(8-bit) / ~16 GB(BF16) | 多语种 OCR 强，图表/数学好 | Transformers / **vLLM** / Docker | 4-bit 官方支持有限，**显存吃紧**（要 8-bit 才稳） |
| GLM-4V-9B | 14B（实际更胖，~28 GB BF16） | ~10 GB(int4) | OCRBench 786 | Transformers `trust_remote_code` | **不推荐**：上下文 8K 太短；vLLM 无原生支持 |
| GLM-4.5V | 106B MoE / 12B 激活 | **不可能本地跑** | SOTA 级；支持 4K 图、64K 上下文 | SGLang(FA3) | 留给云端 |
| Llama 3.2 Vision 11B | 11B | 7–8 GB(4-bit) | 中文一般，OCR 弱 | Transformers / Ollama | 中文场景**不推荐** |
| Idefics3-8B | 8B | 6 GB(4-bit) | 英文为主 | Transformers | 中文场景**不推荐** |

**4070S 12 GB 落点**（量化 → 速度 → 显存）：

| 模型 | 4-bit 显存 | 推理 token/s（vLLM, 单图 + 200 tok 输出） | 适合 |
|---|---|---|---|
| Qwen2.5-VL-7B AWQ | ~6.5 GB | 35–50 t/s | **常驻**，PPT/图表/中文笔记最稳 |
| MiniCPM-V 2.6 int4 | ~7 GB | 25–40 t/s | 高分辨率 PPT、Ollama 一键部署 |
| InternVL2.5-8B 8-bit | ~9 GB | 15–25 t/s | OCR + 图表混合，但显存紧 |

> **建议**：Qwen2.5-VL-7B-Instruct-AWQ 走 vLLM serve，留 4–5 GB 给 Whisper/PaddleOCR 同进程协作；或者按需轮换。

---

## Part D · 云端多模态备选

> 价格随时变，下表为公开费率参考，**Jovi 接入前请去官方 pricing 页二次确认**。

| 厂商 / 模型 | 输入 ¥/1M tok（图+文） | 输出 ¥/1M tok | 单图 token 估算 | 限流（典型免费层） | API 易用度 |
|---|---|---|---|---|---|
| **智谱 GLM-4.5V** | ~14 / ~14（参考价） | ~14 | 1024–4096/张（按分辨率） | RPM 50 / TPM 数十万 | OpenAI 兼容 SDK，国内最稳 |
| **智谱 GLM-4V-Plus** | ~10 / ~10 | ~10 | 1k 左右 | 同上 | 兼容 SDK |
| **智谱 GLM-4V-Flash** | **0 / 0（免费）** | 0 | 1k 左右 | RPM 较紧 | 兼容 SDK；**调试首选** |
| 阿里 Qwen-VL-Max | ~20 / ~20 | ~20 | 1k–2k | 百炼控制台调 | DashScope SDK，文档好 |
| 阿里 Qwen-VL-Plus | ~3 / ~9 | ~9 | 1k–2k | 同上 | 同上 |
| 字节豆包 Doubao-1.5-Vision-Pro | ~3 / ~9 | ~9 | 1k–4k | 火山引擎工单 | 火山 SDK，文档稍乱 |
| 字节豆包 Vision-Lite | ~0.6 / ~1.5 | ~1.5 | 同上 | 同上 | 同上 |
| 百度文心 4.0 Vision | ~30 / ~60 | ~60 | 1k 左右 | 千帆控制台 | 国企风格，集成繁琐 |
| OpenAI GPT-4o | ¥17.5 / ¥70 (USD 2.5/10) | ¥70 | ~1100/张 | 境外卡+网络 | 文档最好；**境内访问难** |
| OpenAI GPT-4o-mini | ¥1.05 / ¥4.2 | ¥4.2 | ~1100/张 | 同上 | 同上 |
| Anthropic Claude 4 Sonnet | ¥21 / ¥105 (USD 3/15) | ¥105 | ~1.6k/张 | 境外卡+网络 | 视觉精度顶级；**境内访问难** |

### 关于 Jovi 的"全模态大模型 token"——明确判断

**最可能是智谱 GLM 系列**，置信度 ~75%：
1. **"全模态"**这个词在中文 AI 圈是智谱的官方提法（GLM-4 系列宣传文案的高频词，对应 image+video+audio+text 全覆盖）。阿里叫"通义千问视觉"，字节叫"豆包视觉理解"，百度叫"文心 ERNIE-VL"——只有智谱明文用"全模态"。
2. 智谱有 **2 个月有效期的 alpha/beta token 发放历史**（开放平台经常给注册用户/比赛参与者发限期 token）；其他厂商更多是新人券+长期账单。
3. GLM-4.5V/4V-Plus/GLM-4V-Flash 同时覆盖图、视频、文，符合"全模态"定位。

**次可能（~15%）**：阿里通义"全模态"也被偶尔提及（Qwen2.5-Omni），但多用于大版本发布，发 token 较少。

**建议**：Jovi 先把 token 厂商 confirm 一下；如果是智谱，**调试期直接用 GLM-4V-Flash（免费）打底，重要视频升级到 GLM-4.5V**。

---

## Part E · 融合策略

### 启发式分流规则

每个视频的关键帧抽完后，先量化两个指标：

```python
scene_density = num_scenes / duration_min       # 场景/分钟
ocr_char_density = mean(chars_per_frame)        # 平均字符数/帧（PaddleOCR 输出）
```

| 场景 | scene_density | ocr_char_density | 处理链路 | 单视频成本 |
|---|---|---|---|---|
| 说话头 / vlog | < 3 | < 20 | **只字幕**，跳过 OCR/VLM | 0 |
| 纯 PPT / 板书 | 3–15 | > 50 | **字幕 + OCR**，不跑 VLM | 低 |
| 图文混合教学 | 5–20 | 20–80 | **字幕 + OCR + VLM** | 中 |
| 信息密集型（图表/手写公式） | > 10 | > 100 | **全开 + LLM 融合** | 高 |

实现伪代码：
```python
mode = "subtitle_only"
if scene_density >= 3 and ocr_char_density >= 50:
    mode = "subtitle_plus_ocr"
if scene_density >= 5 and 20 <= ocr_char_density <= 80:
    mode = "full"
if scene_density > 10 or ocr_char_density > 100:
    mode = "full_with_llm_fuse"
```

### LLM 融合 prompt 模板

```text
你是一个把抖音视频转成 Obsidian Markdown 笔记的助手。

【输入】
1) 字幕（按时间戳排序，已 Whisper 转写并合并为段落）：
{subtitles_with_timestamps}

2) 关键帧 OCR（按时间戳排序，每行一个文本块）：
{ocr_blocks_with_timestamps}

3) 关键帧视觉描述（仅图表/PPT/手写笔记类帧，已由 VLM 描述）：
{vlm_descriptions_with_timestamps}

【任务】
- 以"字幕"为骨架，按内容自然分节（H2 标题）。
- 每节末尾把对应时间窗内的 OCR/VLM 信息融合进来：PPT 文字直接列点，图表/示意图用一句话概括 + ![[frame_xxxx.jpg]] 嵌入。
- 删去重复（字幕已说 + OCR 重复出现的同一句口播）。
- 输出 Obsidian Markdown，开头加 frontmatter（source、duration、tags）。

【风格】
- 中文输出
- 技术名词保留英文
- 不要营销口吻，不要"总结一下"
```

### VLM 单帧 prompt（中文 PPT/图表）

```text
请提取这张 PPT/图表的核心信息：
- 标题 / 主题
- 关键文字（按视觉层级列出）
- 如果是图表：横纵轴、数据趋势、结论
- 如果是手写笔记：识别公式/示意图含义
不要复读 OCR 已经能提取的纯文字；只补 OCR 抓不到的结构化信息。
输出格式：纯 Markdown 列表，不超过 200 字。
```

---

## 风险与缺口

1. **PPT 切换检测漏帧**：若 PPT 是淡入淡出过渡，ContentDetector 可能漏。**对策**：与 ThresholdDetector 并联取并集。
2. **OCR 中文手写体**：PP-OCRv5 对手写比 v4 改善明显，但**潦草板书** F1 仍 < 0.8。**对策**：手写场景直接交给 VLM。
3. **VLM 长视频成本**：本地 Qwen2.5-VL 跑 100 帧 ≈ 5–10 分钟。**对策**：用 Part E 启发式严格筛选；只送 ≤ 30 帧给 VLM。
4. **云端隐私**：抖音视频含说话人脸，**送智谱/阿里前应模糊或裁剪**。
5. **Jovi 的 token 厂商未确认**：报告基于"最可能是智谱"假设，请 Jovi 在 Part D 选型前 confirm。
6. **GLM-4V-9B 上下文 8K** 限制：长字幕+多图融合可能溢出，所以未推荐。
7. **RTX 4070S 12 GB 同时跑** Whisper(large-v3 ~3 GB) + PP-OCRv5 server (~2.5 GB 推理) + Qwen2.5-VL-7B AWQ (~6.5 GB) ≈ **12 GB 边界**；建议串行而非并行，或把 Whisper 切到 large-v3-turbo。

---

## 引用

- Qwen2.5-VL-7B-Instruct model card — https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct
- MiniCPM-V 2.6 model card — https://huggingface.co/openbmb/MiniCPM-V-2_6
- InternVL2.5-8B model card — https://huggingface.co/OpenGVLab/InternVL2_5-8B
- GLM-4V-9B model card — https://huggingface.co/THUDM/glm-4v-9b
- GLM-4.5V model card — https://huggingface.co/zai-org/GLM-4.5V
- PaddleOCR README & PP-OCRv5 doc — https://github.com/PaddlePaddle/PaddleOCR · https://paddlepaddle.github.io/PaddleOCR/main/version3.x/algorithm/PP-OCRv5/PP-OCRv5.html
- PySceneDetect detectors — https://www.scenedetect.com/docs/latest/cli/detectors.html
- PySceneDetect API — https://www.scenedetect.com/docs/latest/api.html
- 智谱开放平台 pricing — https://open.bigmodel.cn/pricing
- 阿里云百炼 / 通义视觉 — https://help.aliyun.com/zh/model-studio/
- 火山方舟豆包 — https://www.volcengine.com/product/doubao
- Anthropic / OpenAI 价格——以官方 pricing 页面为准

