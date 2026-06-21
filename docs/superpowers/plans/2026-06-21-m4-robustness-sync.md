---
change: m4-robustness-sync
design-doc: docs/superpowers/specs/2026-06-21-m4-robustness-sync-design.md
base-ref: c15c25643ae3aa9f6344dd08ce94c7c4e415a8fd
archived-with: 2026-06-21-m4-robustness-sync
---

# M4 实施计划：健壮性 + 监控

> 总工时：5-7 天
> 前置条件：M1 + M2 + M3 完成（base-ref: c15c256）
> 依赖：无外部依赖，纯内部增强

archived-with: 2026-06-21-m4-robustness-sync
---

## Task Group 1: cookie 自动探活与轮转（1 天）

**设计约束**：D-M4-1 — cookies_backup 目录找旧有效文件；全部过期发飞书告警

### T1.1 RED — `probe_and_rotate` 函数签名 + 探活有效场景

**文件**：`tests/utils/test_cookie_probe.py`

新增测试类 `TestProbeAndRotate`：

- **WHEN** 下载失败 + 探活 HTTP HEAD 返回 200
- **THEN** 返回 `True`，不轮换，记录 "cookie_valid" 日志

```python
class TestProbeAndRotateValid:
    """cookie-auto-refresh spec: cookie 有效场景。"""

    @patch("src.utils.cookie_probe.httpx")
    def test_probe_returns_true_no_rotation(self, mock_httpx, tmp_path):
        """WHEN probe returns 200 THEN no rotation, return True."""
        cookies_file = tmp_path / "cookies.txt"
        cookies_file.write_text("...\ttoken\tabc123\n")
        backup_dir = tmp_path / "cookies_backup"
        backup_dir.mkdir()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx.Client.return_value.__enter__.return_value.get.return_value = mock_response

        from src.utils.cookie_probe import probe_and_rotate
        result = probe_and_rotate(str(cookies_file), str(backup_dir))

        assert result is True
        # 验证没有文件操作（未轮换）
        assert list(backup_dir.iterdir()) == []
```

### T1.2 RED — cookie 过期 + 备份可用场景

- **WHEN** 探活失败 + `cookies_backup/` 存在更旧的有效 cookies
- **THEN** 自动替换 `cookies.txt` + 返回 `True`（可重试）

```python
class TestProbeAndRotateBackupAvailable:
    """cookie-auto-refresh spec: cookie 过期 + 备份可用。"""

    @patch("src.utils.cookie_probe.probe_cookie")
    def test_rotates_to_backup_when_main_expired(self, mock_probe, tmp_path):
        """WHEN main cookie expired AND backup valid THEN rotate."""
        cookies_file = tmp_path / "cookies.txt"
        cookies_file.write_text("...\texpired_token\told_value\n")
        backup_dir = tmp_path / "cookies_backup"
        backup_dir.mkdir()
        backup_file = backup_dir / "cookies_20260620.txt"
        backup_file.write_text("...\tvalid_token\tnew_value\n")

        # 第一次 probe（main）失败，第二次 probe（backup）成功
        mock_probe.side_effect = [False, True]

        from src.utils.cookie_probe import probe_and_rotate
        result = probe_and_rotate(str(cookies_file), str(backup_dir))

        assert result is True
        assert cookies_file.read_text() == backup_file.read_text()
```

### T1.3 RED — 全部 cookie 过期场景

- **WHEN** 探活失败 + 备份目录无有效 cookie
- **THEN** 返回 `False`（标记 `cookie_expired`）

```python
class TestProbeAndRotateAllExpired:
    """cookie-auto-refresh spec: 全部 cookie 过期。"""

    @patch("src.utils.cookie_probe.probe_cookie")
    def test_returns_false_when_all_expired(self, mock_probe, tmp_path):
        """WHEN all cookies expired THEN return False."""
        cookies_file = tmp_path / "cookies.txt"
        cookies_file.write_text("...\texpired\tvalue\n")
        backup_dir = tmp_path / "cookies_backup"
        backup_dir.mkdir()
        backup_file = backup_dir / "cookies_old.txt"
        backup_file.write_text("...\talso_expired\tvalue\n")

        mock_probe.return_value = False

        from src.utils.cookie_probe import probe_and_rotate
        result = probe_and_rotate(str(cookies_file), str(backup_dir))

        assert result is False
```

### T1.4 GREEN — 实现 `probe_and_rotate`

**文件**：`src/utils/cookie_probe.py`

```python
def probe_and_rotate(cookies_path: str, backup_dir: str, test_url: str = "...") -> bool:
    """探活 + 轮转。返回 True 表示有可用 cookie。"""
    # 1. 探活主 cookie
    if probe_cookie(cookies_path, test_url):
        return True  # cookie_valid
    # 2. 遍历 backup_dir 找有效备份（按修改时间倒序）
    backup_path = Path(backup_dir)
    if backup_path.exists():
        for f in sorted(backup_path.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if probe_cookie(str(f), test_url):
                # 轮换：复制 backup → cookies.txt
                Path(cookies_path).write_text(f.read_text())
                return True
    # 3. 全部过期
    return False
```

### T1.5 REFACTOR — 集成到 `_download_with_fallback`

**文件**：`src/pipeline/scheduler.py` — `_download_with_fallback`

下载失败时调用 `probe_and_rotate`，成功则重试；失败则标记 `cookie_expired`。

archived-with: 2026-06-21-m4-robustness-sync
---

## Task Group 2: 下载重试指数退避（0.5 天）

**设计约束**：D-M4-2 — 退避序列 0s→5s→30s→2m→10m；可重试/不可重试错误分类

### T2.1 RED — `is_retryable` 函数

**文件**：`tests/pipeline/test_errors.py`

```python
class TestIsRetryable:
    """task-queue-pipeline spec: 可重试/不可重试错误分类。"""

    def test_network_error_is_retryable(self):
        """WHEN yt-dlp DownloadError (network) THEN retryable."""
        import yt_dlp
        from src.pipeline.errors import is_retryable
        error = yt_dlp.utils.DownloadError("network timeout")
        assert is_retryable(error) is True

    def test_404_not_found_is_not_retryable(self):
        """WHEN yt-dlp DownloadError (HTTP 404) THEN not retryable."""
        import yt_dlp
        from src.pipeline.errors import is_retryable
        error = yt_dlp.utils.DownloadError("HTTP Error 404: Not Found")
        assert is_retryable(error) is False

    def test_video_not_found_is_not_retryable(self):
        """WHEN yt-dlp DownloadError (Video not found) THEN not retryable."""
        import yt_dlp
        from src.pipeline.errors import is_retryable
        error = yt_dlp.utils.DownloadError("Video not found")
        assert is_retryable(error) is False

    def test_cookie_error_is_not_retryable(self):
        """WHEN cookie expired THEN not retryable (need rotation, not backoff)."""
        from src.pipeline.errors import is_retryable
        error = Exception("cookie has expired")
        assert is_retryable(error) is False

    def test_generic_exception_is_retryable(self):
        """WHEN unknown transient error THEN retryable."""
        from src.pipeline.errors import is_retryable
        error = Exception("connection reset by peer")
        assert is_retryable(error) is True
```

### T2.2 GREEN — 实现 `is_retryable`

**文件**：`src/pipeline/errors.py`

```python
# 不可重试关键词
_NON_RETRYABLE_PATTERNS = [
    "404", "not found", "video not found",
    "private video", "removed", "unavailable",
    "cookie", "login required",
]

def is_retryable(error: Exception) -> bool:
    """判断错误是否值得指数退避重试。"""
    error_str = str(error).lower()
    for pattern in _NON_RETRYABLE_PATTERNS:
        if pattern in error_str:
            return False
    return True
```

### T2.3 RED — 指数退避时间序列测试

**文件**：`tests/pipeline/test_scheduler.py`

```python
class TestExponentialBackoff:
    """task-queue-pipeline spec: 下载失败指数退避。"""

    @patch("src.pipeline.scheduler.time.sleep")
    @patch("src.pipeline.scheduler.is_retryable", return_value=True)
    def test_backoff_sequence(self, mock_retryable, mock_sleep, tmp_path):
        """WHEN download fails 5 times with retryable error THEN backoff 0,5,30,120,600s."""
        # 验证 sleep 调用序列
        from src.pipeline.scheduler import _download_with_fallback
        # mock download_video 连续失败 5 次
        # 断言 sleep.call_args_list == [call(0), call(5), call(30), call(120), call(600)]
```

### T2.4 GREEN — 修改 `_download_with_fallback` 实现退避

**文件**：`src/pipeline/scheduler.py`

退避序列常量：
```python
BACKOFF_SEQUENCE = [0, 5, 30, 120, 600]  # 秒
```

修改 `_download_with_fallback`：用 `BACKOFF_SEQUENCE` 替代简单重试循环，不可重试错误直接 `break`。

### T2.5 REFACTOR — 清理旧重试逻辑

移除 `yt_dlp_retries` 配置项的硬编码依赖，统一用 `BACKOFF_SEQUENCE` 控制。

archived-with: 2026-06-21-m4-robustness-sync
---

## Task Group 3: sleep-wake 检测（0.5 天）

**设计约束**：D-M4-3 — clock jump > 60s 触发 reclaim；正常 5s sleep 不误触发

### T3.1 RED — clock jump 检测测试

**文件**：`tests/pipeline/test_scheduler.py`

```python
class TestSleepWakeDetection:
    """task-queue-pipeline spec: sleep-wake 检测。"""

    @patch("src.pipeline.scheduler.db.reclaim_zombie_tasks", return_value=0)
    @patch("src.pipeline.scheduler.db.atomic_dequeue", return_value=None)
    @patch("src.pipeline.scheduler.time.sleep")
    @patch("src.pipeline.scheduler.time.time")
    def test_clock_jump_triggers_reclaim(
        self, mock_time, mock_sleep, mock_dequeue, mock_reclaim, tmp_path
    ):
        """WHEN clock jump > 60s THEN trigger zombie reclaim + queue digest."""
        # 模拟：第一次循环 time()=1000, sleep(5), 第二次循环 time()=1070 (jump=70s)
        mock_time.side_effect = [1000.0, 1070.0, 1075.0, 1075.0]
        # 第三次 dequeue 返回 None → 退出循环
        mock_dequeue.side_effect = [None, None, None]

        from src.pipeline.scheduler import run_forever
        # 验证 reclaim_zombie_tasks 被调用 2 次（启动时 + clock jump 时）
        # ...

    @patch("src.pipeline.scheduler.db.reclaim_zombie_tasks", return_value=0)
    @patch("src.pipeline.scheduler.db.atomic_dequeue", return_value=None)
    @patch("src.pipeline.scheduler.time.sleep")
    @patch("src.pipeline.scheduler.time.time")
    def test_normal_sleep_does_not_trigger_reclaim(
        self, mock_time, mock_sleep, mock_dequeue, mock_reclaim, tmp_path
    ):
        """WHEN normal 5s sleep (jump < 60s) THEN no extra reclaim."""
        mock_time.side_effect = [1000.0, 1005.0, 1010.0]
        mock_dequeue.side_effect = [None, None, None]

        from src.pipeline.scheduler import run_forever
        # 验证 reclaim_zombie_tasks 只调用 1 次（启动时）
```

### T3.2 GREEN — 实现 clock jump 检测

**文件**：`src/pipeline/scheduler.py` — `run_forever`

```python
CLOCK_JUMP_THRESHOLD = 60  # 秒

# run_forever 主循环中：
last_loop_time = time.time()
while True:
    now = time.time()
    if now - last_loop_time > CLOCK_JUMP_THRESHOLD:
        _get_logger().info("sleep_wake_detected", jump_seconds=now - last_loop_time)
        zombie_count = db.reclaim_zombie_tasks(conn, ...)
        if zombie_count > 0:
            _get_logger().info("zombies_reclaimed_after_wake", count=zombie_count)
    last_loop_time = now
    # ... 正常 dequeue 逻辑
```

### T3.3 REFACTOR — 提取 `_check_clock_jump` 函数

将 clock jump 检测逻辑提取为独立函数，便于测试。

archived-with: 2026-06-21-m4-robustness-sync
---

## Task Group 4: 飞书 webhook 告警（1 天）

**设计约束**：D-M4-4 — `monitor.feishu_webhook_url`；30 分钟去重

### T4.1 RED — `send_feishu_alert` 函数签名 + payload 格式

**文件**：`tests/utils/test_monitor.py`

```python
class TestSendFeishuAlert:
    """monitor-alerts spec: 飞书 webhook 告警。"""

    @patch("src.utils.monitor.httpx")
    def test_sends_correct_payload(self, mock_httpx):
        """WHEN send_feishu_alert called THEN POST correct JSON to webhook."""
        from src.utils.monitor import send_feishu_alert
        send_feishu_alert("https://hook.feishu.test/xxx", "Cookie 过期", "cookies 全部过期")

        mock_httpx.Client.return_value.__enter__.return_value.post.assert_called_once()
        call_args = mock_httpx.Client.return_value.__enter__.return_value.post.call_args
        payload = call_args[1]["json"] if "json" in call_args[1] else call_args[0][1]
        assert "Cookie 过期" in str(payload)
```

### T4.2 RED — 告警去重测试

- **WHEN** 同类型告警 30 分钟内已发
- **THEN** 不重复推送

```python
class TestAlertDedup:
    """monitor-alerts spec: 告警去重。"""

    @patch("src.utils.monitor.httpx")
    def test_duplicate_alert_suppressed_within_30min(self, mock_httpx):
        """WHEN same alert type within 30 min THEN second call suppressed."""
        from src.utils.monitor import AlertDeduplicator
        dedup = AlertDeduplicator()

        # 第一次发送
        dedup.check_and_send("https://hook.test", "cookie_expired", "msg")
        # 30 分钟内第二次发送（相同 key）
        dedup.check_and_send("https://hook.test", "cookie_expired", "msg")

        # httpx.post 只被调用 1 次
        assert mock_httpx.Client.return_value.__enter__.return_value.post.call_count == 1
```

### T4.3 RED — 三种告警场景测试

```python
class TestAlertScenarios:
    """monitor-alerts spec: cookie过期 / 连续失败 / 队列堆积。"""

    def test_cookie_expired_alert(self):
        """WHEN cookie 探活失败 THEN push cookie 过期告警。"""

    def test_consecutive_failure_alert(self):
        """WHEN 同 video_id 连续失败 ≥ 3 次 THEN push 连续失败告警。"""

    def test_queue_backlog_alert(self):
        """WHEN pending > 20 持续 > 30 分钟 THEN push 队列堆积告警。"""
```

### T4.4 GREEN — 实现 `src/utils/monitor.py`

```python
class AlertDeduplicator:
    """30 分钟内同类型告警去重。"""
    def __init__(self):
        self._sent: dict[str, float] = {}  # key → timestamp
        self._ttl = 1800  # 30 分钟

    def should_send(self, key: str) -> bool:
        now = time.time()
        if key in self._sent and now - self._sent[key] < self._ttl:
            return False
        self._sent[key] = now
        return True

def send_feishu_alert(webhook_url: str, title: str, content: str) -> None:
    """发送飞书 incoming webhook 告警。"""
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": title}},
            "elements": [{"tag": "div", "text": {"tag": "plain_text", "content": content}}],
        },
    }
    with httpx.Client() as client:
        client.post(webhook_url, json=payload, timeout=10.0)
```

### T4.5 GREEN — 配置集成

**文件**：`config.yaml` — 新增 `monitor` 段：

```yaml
monitor:
  enabled: false
  feishu_webhook_url: ""
  dedup_ttl_seconds: 1800
```

### T4.6 REFACTOR — 集成告警到 cookie 探活和 scheduler

- cookie 全过期 → `send_feishu_alert("cookie_expired", "...")`
- 连续失败 ≥ 3 → `send_feishu_alert("consecutive_failure", "...")`
- 队列堆积 → `send_feishu_alert("queue_backlog", "...")`

archived-with: 2026-06-21-m4-robustness-sync
---

## Task Group 5: 修复 pre-existing 测试（0.5 天）

**设计约束**：M2 遗留 3 个测试，目标 273/273 绿

### T5.1 RED → GREEN — `test_asr_interface.py` 导入路径

**问题**：`from src.asr import MimoASRClient` 可能导入失败（M2 遗留路径问题）

**修复**：确认 `src/asr/__init__.py` 已导出 `MimoASRClient`，或改为 `from src.asr.mimo_client import MimoASRClient`

```python
# tests/asr/test_asr_interface.py — 修复后
def test_mimo_provider(self):
    from src.asr.mimo_client import MimoASRClient  # 直接导入
    client = get_asr_client({"asr": {"provider": "mimo", "mimo": {"api_key": "test"}}})
    assert isinstance(client, MimoASRClient)
```

### T5.2 RED → GREEN — `test_audio_preprocess.py` capture_output 断言

**问题**：`subprocess.run` 调用缺少 `capture_output=True` 参数断言

**修复**：确认 `src/asr/audio_preprocess.py` 第 21-26 行已包含 `capture_output=True`（已验证：当前代码已正确），测试断言需对齐。

```python
# tests/asr/test_audio_preprocess.py — 确认断言匹配实际调用
mock_run.assert_called_once_with(
    [...],
    check=True,
    capture_output=True,  # 已存在于源码，断言需加上
)
```

### T5.3 RED → GREEN — `WhisperLocalClient` 工厂传参对齐

**问题**：`get_asr_client` 传 `model_name` 但 `WhisperLocalClient.__init__` 签名可能是 `model`

**修复**：确认 `WhisperLocalClient.__init__(self, model_name: str | None = None, ...)` 与工厂函数 `model_name=whisper_cfg.get("model", ...)` 对齐。当前代码已正确（已验证 `local_whisper.py` 第 24 行），测试需用正确的参数名。

### T5.4 全量测试验证

```bash
pytest tests/ -v --tb=short 2>&1 | tail -5
# 期望: 273/273 passed
```

archived-with: 2026-06-21-m4-robustness-sync
---

## Task Group 6: 集成测试 + 文档（1 天）

### T6.1 RED → GREEN — E2E: cookie 过期 → 自动探活 → 告警

**文件**：`tests/e2e/test_m4_e2e.py`

```python
class TestM4CookieExpiryE2E:
    """cookie-auto-refresh + monitor-alerts 集成。"""

    def test_cookie_expired_triggers_rotation_and_alert(self, tmp_path):
        """完整链路：下载失败 → 探活 → 轮转 → 告警。"""
        # 1. 构造过期 cookies.txt + 有效 backup
        # 2. mock 下载失败（cookie 错误）
        # 3. 运行 process_task
        # 4. 验证：cookie 被轮转 + 飞书告警已发
```

### T6.2 RED → GREEN — E2E: 下载失败 → 退避重试 → 成功/失败标记

```python
class TestM4BackoffE2E:
    """task-queue-pipeline spec: 退避重试集成。"""

    def test_download_fails_backoff_then_succeeds(self):
        """前 2 次失败，第 3 次成功 → task done。"""

    def test_download_fails_all_retries_marks_failed(self):
        """5 次全部失败 → task failed + error_code。"""

    def test_non_retryable_error_skips_backoff(self):
        """404 错误 → 立即 failed，不退避。"""
```

### T6.3 RED → GREEN — E2E: 模拟 clock jump → 队列自动消化

```python
class TestM4SleepWakeE2E:
    """task-queue-pipeline spec: sleep-wake 集成。"""

    def test_clock_jump_reclaims_zombie_tasks(self):
        """模拟 clock jump > 60s → zombie 任务被 reclaim。"""
```

### T6.4 文档更新 — RUNBOOK.md

**文件**：`docs/m1/RUNBOOK.md`

新增章节：
- **cookie 轮转**：`cookies_backup/` 目录结构、手动刷新步骤
- **监控告警**：飞书 webhook 配置、告警类型说明
- **sleep-wake 检测**：clock jump 阈值、自动恢复行为

### T6.5 文档更新 — KNOWLEDGE.md

**文件**：`docs/m2/KNOWLEDGE.md`

新增章节：
- **cookie 管理策略**：探活 → 轮转 → 告警链路
- **重试退避算法**：BACKOFF_SEQUENCE 定义、可重试/不可重试分类

archived-with: 2026-06-21-m4-robustness-sync
---

## 执行顺序与依赖

```
T5 (修复 pre-existing) ──→ 无依赖，最先执行
T1 (cookie 轮转) ──→ 依赖 T5（确保测试基线绿）
T2 (指数退避) ──→ 依赖 T1（cookie 探活集成）
T3 (sleep-wake) ──→ 无强依赖，可与 T2 并行
T4 (飞书告警) ──→ 依赖 T1（cookie 过期告警场景）
T6 (集成测试 + 文档) ──→ 依赖 T1-T4 全部完成
```

**推荐串行顺序**：T5 → T1 → T2 → T3 → T4 → T6

**并行优化**：T2 和 T3 可并行（无共享状态）；T4 的基础 `send_feishu_alert` 可与 T2/T3 并行。

archived-with: 2026-06-21-m4-robustness-sync
---

## 验收标准

- [ ] 全量测试 ≥ 273/273 绿（含 M4 新增测试）
- [ ] cookie 过期 → 自动轮转 → 飞书告警链路验证通过
- [ ] 指数退避序列 [0, 5, 30, 120, 600] 秒正确执行
- [ ] clock jump > 60s 触发 reclaim，< 60s 不误触发
- [ ] 飞书告警 30 分钟去重生效
- [ ] 3 个 pre-existing 测试修复，无回归
- [ ] RUNBOOK.md + KNOWLEDGE.md 文档更新
