# M1/M2/M3 RUNBOOK

运维手册：启动服务、切换 ASR provider、LLM 总结、视觉理解、故障排查。

## 1. 启动服务

```bash
# 确保 config.yaml 存在（从 config.example.yaml 复制）
cp config.example.yaml config.yaml

# 编辑 config.yaml 填写真实路径

# 启动解析服务（FastAPI + scheduler 自动启动）
python -m src.bridge.main
# 服务监听 127.0.0.1:8765
```

## 2. ASR Provider 切换

### 切换到 mimo（默认，云端）

```yaml
# config.yaml
asr:
  provider: mimo
  mimo:
    model: mimo-v2.5-asr
```

前置条件：
- `MIMO_API_KEY` 环境变量已设置（见 `.env`）
- openclaw MCP 工具 `asr_transcribe` 可用

### 切换到 whisper_local（本地 GPU）

```yaml
# config.yaml
asr:
  provider: whisper_local
  whisper:
    model: Belle-whisper-large-v3-turbo-zh
    device: cuda
    compute_type: int8_float16
```

前置条件：
- NVIDIA GPU（推荐 4070S 及以上）
- CUDA + cuDNN 9.x 已安装
- `pip install faster-whisper`
- Belle 模型首次运行会自动从 HuggingFace 下载（约 3GB）

### 切换步骤

1. 停止服务（Ctrl+C）
2. 修改 `config.yaml` 中 `asr.provider` 字段
3. 重启服务：`python -m src.bridge.main`
4. 验证：提交一个无字幕视频，观察日志中 `asr_fallback_triggered` 和 provider 信息

## 3. LLM 总结启停

### 启用 LLM 总结（M3）

```yaml
# config.yaml
llm:
  provider: mimo
  mimo:
    api_key: "YOUR_MIMO_API_KEY"
    base_url: "https://token-plan-cn.xiaomimimo.com/v1"
    model: mimo-v2.5-pro
```

前置条件：
- `MIMO_API_KEY` 环境变量或 config.yaml 中填写 `api_key`
- 网络可访问 `token-plan-cn.xiaomimimo.com`

### 禁用 LLM 总结

```yaml
# config.yaml — 删除 llm 段或设 provider 为空
llm:
  provider: ""
```

笔记中 `summary_status` 将显示为 `failed`，摘要区显示占位文字。

### 验证

提交一个有字幕视频，检查笔记中是否包含 `summary_status: done` 和 AI 摘要要点。

## 4. 视觉理解启停

### 启用视觉理解（M3）

```yaml
# config.yaml
vision:
  enabled: true
  keyframe_max: 30
  scene_threshold: 0.4
```

前置条件：
- LLM 总结已启用（串行铁律：LLM 先执行，VLM 后执行）
- 视频文件可正常下载（`video_path` 存在）
- 4070S 显存充足（VLM ~8GB，需串行调度避免 OOM）

### 禁用视觉理解（默认）

```yaml
# config.yaml
vision:
  enabled: false
```

笔记关键帧段显示"视觉理解已禁用"。

### 启发式分流

| 视频类型 | 条件 | 处理路径 |
|---------|------|---------|
| 口播类 | 字幕密度高 + 场景变化低 | 只跑 LLM 总结（summary_only） |
| PPT/图表类 | 字幕密度低 + 场景变化高 | LLM 总结 + OCR + VLM |
| 混合类 | 其他情况 | LLM 总结 + OCR + VLM（保守策略） |

## 5. M4 健壮性

### 5.1 Cookie 轮转

服务启动时自动探测 cookie 有效性。若当前 cookie 过期，自动从备份目录轮转。

**配置**：
```yaml
downloader:
  cookies_path: "E:\\project\\douyin_to_obsidian\\cookies.txt"
```

**备份目录约定**：
```
data/
  cookies/                      # 备份目录（与 cookies.txt 同级）
    cookies_backup_20260620.txt # 备份文件，按日期命名
    cookies_backup_20260615.txt
```

**probe_and_rotate 流程**：
1. `probe_cookie()` 用 HTTP 请求探测当前 cookies
2. 若有效 → 直接使用，不轮换
3. 若过期 → 在 `data/cookies/` 中按修改时间降序逐个探测备份
4. 找到第一个有效备份 → `shutil.copy2` 覆盖主 cookies 文件
5. 全部过期 → 日志告警，下载任务标记 `cookie_expired`

**手动轮转**：
```bash
# 导出新 cookies 后放入备份目录
cp new_cookies.txt data/cookies/cookies_backup_$(date +%Y%m%d).txt
# 重启服务自动轮转
python -m src.bridge.main
```

### 5.2 退避重试

下载失败时按指数退避重试，序列 `[0, 5, 30, 120, 600]` 秒。

| 尝试 | 退避 | 累计等待 |
|------|------|---------|
| 1    | 0s   | 0s      |
| 2    | 5s   | 5s      |
| 3    | 30s  | 35s     |
| 4    | 120s | 155s    |
| 5    | 600s | 755s    |

**不可重试错误**（直接跳过退避）：
- HTTP 403/404（forbidden / not found）
- `NoSubtitleError`（内容问题，非网络）
- 消息含 `403`、`404`、`forbidden`、`not found`

**可重试错误**：
- `TimeoutError`、`OSError`（网络层）
- 消息含 `timeout`、`502`、`503`、`429`、`connection reset`

退避后若仍失败，尝试 DouK 兜底（需配置 `downloader.douk_path`）。

### 5.3 Sleep-Wake 检测

PC 从睡眠/休眠恢复时，自动检测时钟跳变并触发 zombie 任务回收。

**阈值**：60 秒（`detect_sleep_wake(last_loop_time, threshold=60)`）

**触发条件**：
- 首次启动（`last_loop_time=None`）→ 触发一次 zombie reclaim
- `time.time()` 两次调用差 > 60s → 触发 zombie reclaim
- 正常间隔（< 60s）→ 不触发

**zombie reclaim**：将 `fetching`/`writing` 状态且 `claimed_at` 超时的任务重置为 `pending`。

### 5.4 飞书 Webhook 告警

关键事件通过飞书 incoming webhook 推送，30 分钟内同类型告警去重。

**配置**：
```yaml
monitor:
  enabled: true
  feishu_webhook_url: "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx"
```

**告警事件**：
- `cookie_expired`：cookie 全部过期，无法轮转
- `download_failed_all_tools`：yt-dlp + DouK 均失败
- `asr_failed`：ASR 转写失败

**去重机制**：内存缓存 `{alert_key: last_sent_timestamp}`，同一 `alert_key` 30 分钟内不重复发送。

## 6. 故障排查

| 症状 | 原因 | 处理 |
|------|------|------|
| `asr_client_init_failed` | provider 配置错误或依赖缺失 | 检查 `config.yaml` asr 配置；`pip install faster-whisper` |
| `gpu_unavailable` | CUDA 不可用 | `nvidia-smi` 检查 GPU；确认 cuDNN 版本 |
| `asr_timeout` | mimo API 超时 | 检查网络；确认 MIMO_API_KEY 有效 |
| `ffmpeg_failed` | ffmpeg 未安装或不在 PATH | 安装 ffmpeg 并加入 PATH |
| `empty_result` | ASR 返回空文本 | 音频质量差或时长太短；检查源视频 |
| `llm_timeout` | LLM API 超时 | 检查网络；确认 mimo API key 有效 |
| `llm_api_error` | LLM API 返回非 200 | 检查 `config.yaml` llm 配置；查看日志 |
| `empty_summary` | LLM 返回空内容 | 可能 prompt 过长被截断；检查字幕质量 |

## 7. 日志查看

```bash
# 实时查看日志
Get-Content logs\douyin-*.log -Wait

# 搜索 ASR 相关日志
Select-String -Path logs\douyin-*.log -Pattern "asr"
```
