"""关键帧抽取 — M3 Task 3。

ffmpeg scene detect 抽关键帧，均匀采样兜底。
Spec ref: D-M3-2 视觉分层（关键帧→OCR→VLM）
"""
import json
import subprocess
from pathlib import Path


class VisionError(Exception):
    """视觉处理失败。"""


def extract_keyframes(
    video_path: Path,
    output_dir: Path,
    max_frames: int = 30,
) -> list[Path]:
    """从视频抽取关键帧。

    1. ffmpeg scene detect (-vf "select='gt(scene,0.4)'" -vsync vframe)
    2. 若 scene detect 帧 < 3，均匀采样兜底（每 10 秒一帧）
    3. 最多 max_frames 帧

    Args:
        video_path: 视频文件路径
        output_dir: 输出根目录
        max_frames: 最大帧数，默认 30

    Returns:
        关键帧路径列表
    """
    video_id = video_path.stem
    keyframes_dir = output_dir / f"{video_id}_keyframes"
    keyframes_dir.mkdir(parents=True, exist_ok=True)

    duration = _get_duration(video_path)

    # Step 1: scene detect
    frames = _scene_detect(video_path, keyframes_dir)

    # Step 2: 均匀采样兜底
    if len(frames) < 3 and duration > 0:
        frames = _uniform_sampling(video_path, keyframes_dir, duration)

    # Step 3: 截断到 max_frames
    frames = frames[:max_frames]

    return frames


def _get_duration(video_path: Path) -> float:
    """用 ffprobe 获取视频时长（秒）。"""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True)
        info = json.loads(result.stdout)
        return float(info["format"]["duration"])
    except Exception:
        return 0.0


def _scene_detect(video_path: Path, keyframes_dir: Path) -> list[Path]:
    """ffmpeg scene detect 抽帧。"""
    pattern = str(keyframes_dir / "frame_%04d.jpg")
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", "select='gt(scene,0.4)'",
        "-vsync", "vframe",
        pattern,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except Exception as e:
        raise VisionError(f"ffmpeg scene detect failed: {e}") from e

    frames = sorted(keyframes_dir.glob("frame_*.jpg"))
    return frames


def _uniform_sampling(
    video_path: Path,
    keyframes_dir: Path,
    duration: float,
) -> list[Path]:
    """每 10 秒一帧的均匀采样兜底。"""
    # 清除之前 scene detect 的帧（跳过 ffmpeg glob pattern 占位文件）
    for f in keyframes_dir.glob("frame_*.jpg"):
        if "%" not in f.name:
            f.unlink(missing_ok=True)

    pattern = str(keyframes_dir / "uniform_%04d.jpg")
    # fps = 1/10，每 10 秒取一帧
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf", "fps=1/10",
        pattern,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except Exception as e:
        raise VisionError(f"ffmpeg uniform sampling failed: {e}") from e

    frames = sorted(keyframes_dir.glob("uniform_*.jpg"))
    return frames
