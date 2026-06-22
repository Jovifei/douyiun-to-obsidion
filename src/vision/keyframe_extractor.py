"""关键帧抽取 — 按语音重点位置抽帧（不限帧不限时）。

策略：用 ASR segments（来自 faster-whisper 或 mimo-asr）的时间戳，
在每个 segment 起始点抽一帧。说话人换段 = 重点强调的位置，
比场景变化检测更智能。

Spec ref: D-M3-2 视觉分层（关键帧→OCR→VLM）
"""
import subprocess
from pathlib import Path


class VisionError(Exception):
    """视觉处理失败。"""


def extract_keyframes_by_segments(
    video_path: Path,
    output_dir: Path,
    asr_segments: list[dict],
) -> list[Path]:
    """按 ASR segments 时间戳从视频抽取关键帧（无上限）。

    每个 segment 起始点抽一帧，自然地捕获"语音重点"位置。
    不限帧数，由 4070S 本地推理能力兜底。

    Args:
        video_path: 视频文件路径
        output_dir: 输出根目录
        asr_segments: ASR segments 列表，每项含 `start` 字段（秒）

    Returns:
        关键帧路径列表（按时间顺序）
    """
    video_id = video_path.stem
    keyframes_dir = output_dir / f"{video_id}_keyframes"
    keyframes_dir.mkdir(parents=True, exist_ok=True)

    frames: list[Path] = []
    for i, seg in enumerate(asr_segments):
        start_sec = seg.get("start", 0.0)
        frame_path = keyframes_dir / f"emphasis_{i:04d}.jpg"
        try:
            _extract_frame(video_path, start_sec, frame_path)
            if frame_path.exists():
                frames.append(frame_path)
        except Exception:
            continue

    return frames


def extract_keyframes_fallback(
    video_path: Path,
    output_dir: Path,
    interval_sec: float = 10.0,
) -> list[Path]:
    """无 ASR segments 时的兜底：均匀采样（每 N 秒一帧，无上限）。

    Args:
        video_path: 视频文件路径
        output_dir: 输出根目录
        interval_sec: 采样间隔秒数，默认 10 秒
    """
    video_id = video_path.stem
    keyframes_dir = output_dir / f"{video_id}_keyframes"
    keyframes_dir.mkdir(parents=True, exist_ok=True)

    pattern = str(keyframes_dir / "fallback_%04d.jpg")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", f"fps=1/{interval_sec}",
        pattern,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except Exception as e:
        raise VisionError(f"ffmpeg fallback sampling failed: {e}") from e

    return sorted(keyframes_dir.glob("fallback_*.jpg"))


def _extract_frame(video_path: Path, time_sec: float, output_path: Path) -> None:
    """从视频指定时间点抽一帧。"""
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(time_sec),
        "-i", str(video_path),
        "-frames:v", "1",
        "-q:v", "2",
        str(output_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except Exception as e:
        raise VisionError(f"ffmpeg frame extraction failed at {time_sec}s: {e}") from e


def extract_keyframes(
    video_path: Path,
    output_dir: Path,
    asr_segments: list[dict] | None = None,
    max_frames: int | None = None,
) -> list[Path]:
    """统一入口：有 ASR segments 用语音重点抽帧，否则均匀采样兜底。

    Args:
        video_path: 视频文件路径
        output_dir: 输出根目录
        asr_segments: ASR segments 列表（含 start 字段）。None 时走 fallback。
        max_frames: 最大帧数限制，默认 None（不限帧）
    """
    if asr_segments:
        frames = extract_keyframes_by_segments(video_path, output_dir, asr_segments)
    else:
        frames = extract_keyframes_fallback(video_path, output_dir)

    if max_frames is not None:
        frames = frames[:max_frames]

    return frames
