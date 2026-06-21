"""audio_preprocess — M2 Task 3: 从视频文件抽取 16kHz mono WAV + 分片。

通过 ffmpeg 将视频文件转换为 16kHz mono pcm_s16le WAV，
并对超过 mimo-asr 10MB 限制的音频自动分片。
"""
import subprocess
from pathlib import Path

from src.asr import ASRError

# mimo-asr API 单次上传限制 10MB
# 16kHz mono 16bit WAV = 32000 bytes/sec
# 10MB ≈ 312 秒，留余量取 240 秒/片
MAX_CHUNK_DURATION_SEC = 240
BYTES_PER_SEC = 16000 * 2  # 16kHz * 16bit = 32000 bytes/sec


def extract_audio_for_asr(video_path: Path, output_path: Path) -> Path:
    """从视频文件抽取 16kHz mono pcm_s16le WAV。"""
    try:
        subprocess.run(
            ["ffmpeg", "-i", str(video_path), "-ar", "16000", "-ac", "1",
             "-c:a", "pcm_s16le", "-y", str(output_path)],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        raise ASRError("ffmpeg_failed", str(e.stderr[:200]) if e.stderr else "")
    return output_path


def get_audio_duration(audio_path: Path) -> float:
    """获取音频时长（秒）。"""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        # fallback：用文件大小估算
        size = audio_path.stat().st_size
        return size / BYTES_PER_SEC


def split_audio_chunks(audio_path: Path, output_dir: Path, chunk_duration: int = MAX_CHUNK_DURATION_SEC) -> list[Path]:
    """将音频按固定时长分片（每片 ≤ 10MB）。

    Args:
        audio_path: 输入 WAV 文件路径。
        output_dir: 分片输出目录。
        chunk_duration: 每片时长（秒），默认 240 秒（约 7.5MB）。

    Returns:
        分片文件路径列表（按时间顺序）。
    """
    duration = get_audio_duration(audio_path)
    if duration <= chunk_duration:
        # 不需要分片，直接返回原文件
        return [audio_path]

    output_dir.mkdir(parents=True, exist_ok=True)
    chunks = []
    start = 0.0
    idx = 0

    while start < duration:
        chunk_path = output_dir / f"{audio_path.stem}_chunk{idx:03d}.wav"
        try:
            subprocess.run(
                ["ffmpeg", "-i", str(audio_path), "-ss", str(start),
                 "-t", str(chunk_duration), "-ar", "16000", "-ac", "1",
                 "-c:a", "pcm_s16le", "-y", str(chunk_path)],
                check=True, capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            raise ASRError("ffmpeg_split_failed", str(e.stderr[:200]) if e.stderr else "")
        chunks.append(chunk_path)
        start += chunk_duration
        idx += 1

    return chunks
