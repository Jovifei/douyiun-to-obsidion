"""sleep-wake 检测：clock jump 超过阈值时返回 True（PC 从睡眠恢复）。

Spec ref: M4 Task 3 — D-M4-3: clock jump > 60s 阈值
"""
import time


def detect_sleep_wake(last_loop_time: float | None, threshold: int = 60) -> bool:
    """检测系统是否从睡眠/休眠恢复。

    通过比较上次循环时间与当前时间的差值判断：
    - 首次启动（last_loop_time=None）→ True（触发一次 zombie reclaim）
    - clock jump > threshold → True（PC 睡眠恢复）
    - clock jump <= threshold → False（正常间隔）

    Args:
        last_loop_time: 上次循环的时间戳（time.time()），首次为 None。
        threshold: 判断为 clock jump 的阈值（秒），默认 60。

    Returns:
        True 表示检测到 sleep/wake 或首次启动，需要触发 zombie reclaim。
    """
    if last_loop_time is None:
        return True

    elapsed = time.time() - last_loop_time
    return elapsed > threshold
