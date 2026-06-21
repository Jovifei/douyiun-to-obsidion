# M4 实施任务清单

> Change: `m4-robustness-sync`
> Workflow: full (spec-driven)
> 总工时估算: **5-7 天**
> 依赖：M1 + M2 + M3 完成

## 1. cookie 自动探活与轮转（1 天）

- [ ] 1.1 增强 `src/utils/cookie_probe.py`：`probe_and_rotate(cookies_path, backup_dir) -> bool`
- [ ] 1.2 下载失败时自动探活（HTTP HEAD 已知抖音视频，200=有效）
- [ ] 1.3 cookies.txt 全过期时在 `cookies_backup/` 找更旧备份轮换
- [ ] 1.4 全部过期 → 发飞书 webhook 告警
- [ ] 1.5 单元测试：mock httpx，验证探活/轮换/告警路径

## 2. 下载重试指数退避（0.5 天）

- [ ] 2.1 修改 `src/pipeline/scheduler.py` `_download_with_fallback`：指数退避（0s→5s→30s→2m→10m）
- [ ] 2.2 新增 `src/pipeline/errors.py` `is_retryable(error) -> bool` 判断哪些错误可重试
- [ ] 2.3 单元测试：mock sleep + 计数，验证退避时间序列

## 3. sleep-wake 检测（0.5 天）

- [ ] 3.1 scheduler 主循环加 clock jump 检测（当前时间 - 上次循环时间 > 60s = sleep-wake）
- [ ] 3.2 检测到 sleep-wake 时触发 zombie reclaim + 队列消化
- [ ] 3.3 单元测试：mock time，验证 clock jump 触发 reclaim

## 4. 飞书 webhook 告警（1 天）

- [ ] 4.1 新增 `src/utils/monitor.py`：`send_feishu_alert(webhook_url, title, content)`
- [ ] 4.2 配置 `config.yaml`：`monitor.feishu_webhook_url` + `monitor.enabled`
- [ ] 4.3 实现告警去重（30 分钟内同类型不重复发）
- [ ] 4.4 告警场景：cookie 过期 / 连续失败≥3 / 队列堆积>20>30min
- [ ] 4.5 单元测试：mock httpx，验证告警 payload 格式

## 5. 修复 pre-existing 测试（0.5 天）

- [ ] 5.1 `tests/asr/test_asr_interface.py`：`from src.asr import MimoASRClient` → 修正导入路径（M2 遗留）
- [ ] 5.2 `tests/asr/test_audio_preprocess.py`：ffmpeg 断言补 `capture_output=True`（M2 遗留）
- [ ] 5.3 `tests/asr/test_asr_interface.py`：WhisperLocalClient 工厂传参对齐（model_name 参数）
- [ ] 5.4 全量测试 273/273 绿

## 6. 集成测试 + 文档（1 天）

- [ ] 6.1 E2E：cookie 过期 → 自动探活 → 告警
- [ ] 6.2 E2E：下载失败 → 退避重试 → 成功/失败标记
- [ ] 6.3 E2E：模拟 clock jump → 队列自动消化
- [ ] 6.4 更新 `docs/m1/RUNBOOK.md`：新增监控告警、cookie 轮转、sleep-wake 说明
- [ ] 6.5 更新 `docs/m2/KNOWLEDGE.md`：新增 cookie 管理策略、重试退避算法
