"""audio_preprocess — M2 Task 3: 从视频文件抽取 16kHz mono WAV。

通过 ffmpeg 将视频文件转换为 16kHz mono pcm_s16le WAV，
供后续 ASR 转写使用。
"""
import subprocess
from pathlib import Path

from src.asr import ASRError


def extract_audio_for_asr(video_path: Path, output_path: Path) -> Path:
    """从视频文件抽取 16kHz mono pcm_s16le WAV。

    Args:
        video_path: 输入视频文件路径。
        output_path: 输出 WAV 文件路径。

    Returns:
        输出文件路径。

    Raises:
        ASRError: ffmpeg 执行失败时抛出，code 为 "ffmpeg_failed"。
    """
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-i", str(video_path),
                "-ar", "16000",
                "-ac", "1",
                "-c:a", "pcm_s16le",
                "-y", str(output_path),
            ],
            check=True,
        )
    except subprocess.CalledProcessError:
        raise ASRError("ffmpeg_failed")

    return output_path
