"""飞书 webhook 告警：通过 incoming webhook 推送关键事件。

Spec ref: M4 Task 4 — D-M4-4: 飞书 webhook 30 分钟去重

配置：
  config.yaml monitor.feishu_webhook_url + monitor.enabled

告警失败不阻塞主流程（所有异常被捕获，返回 False）。
"""
import time

import httpx

# 内存缓存：{alert_key: last_sent_timestamp}
_alert_cache: dict[str, float] = {}


def is_alert_duplicate(alert_key: str, cooldown_minutes: int = 30) -> bool:
    """检查告警是否在冷却期内（30 分钟去重）。

    Args:
        alert_key: 告警类型标识。
        cooldown_minutes: 冷却时间（分钟），默认 30。

    Returns:
        True 表示在冷却期内（应跳过），False 表示可以发送。
    """
    if alert_key not in _alert_cache:
        return False

    elapsed = time.time() - _alert_cache[alert_key]
    return elapsed < cooldown_minutes * 60


def send_feishu_alert(
    webhook_url: str,
    title: str,
    content: str,
    alert_type: str = "info",
) -> bool:
    """通过飞书 incoming webhook 发送告警。

    Args:
        webhook_url: 飞书 webhook 地址。
        title: 告警标题。
        content: 告警内容（支持 markdown）。
        alert_type: 告警类型（用于去重 key）。

    Returns:
        True 发送成功，False 发送失败或跳过。
    """
    if not webhook_url:
        return False

    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
            },
            "elements": [
                {"tag": "markdown", "content": content},
            ],
        },
    }

    try:
        resp = httpx.post(webhook_url, json=payload, timeout=10.0)
        return resp.status_code == 200
    except Exception:
        return False
