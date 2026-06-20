"""ffmpeg 音频抽取（M2 Whisper 用，M1 仅留接口，不在主路径调用）。

一行命令：ffmpeg -i input.mp4 -ar 16000 -ac 1 -c:a pcm_s16le output.wav
"""
import subprocess
from pathlib import Path


class AudioExtractionError(Exception):
    """音频抽取失败。"""


def extract_audio(video_path: Path, out_path: Path) -> Path:
    """从视频抽 16kHz 单声道 PCM wav，供 M2 Whisper 使用。

    M1 阶段此函数不被主路径调用，仅 M2 启用时复用。
    """
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
        str(out_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except Exception as e:
        raise AudioExtractionError(f"ffmpeg failed: {e}") from e
    return out_path
