"""audio_preprocess 单元测试 — M2 Task 3 TDD (RED phase).

验证 extract_audio_for_asr 函数从视频文件抽取 16kHz mono WAV。
"""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.asr import ASRError
from src.asr.audio_preprocess import extract_audio_for_asr


class TestExtractAudioForAsrExists:
    """extract_audio_for_asr 函数存在性。"""

    def test_function_exists(self):
        """extract_audio_for_asr 是可调用函数。"""
        assert callable(extract_audio_for_asr)


class TestExtractAudioNormal:
    """正常抽取场景。"""

    def test_calls_ffmpeg_with_correct_args(self, tmp_path: Path):
        """调用 ffmpeg 抽取 16kHz mono pcm_s16le WAV。"""
        video_file = tmp_path / "input.mp4"
        video_file.write_bytes(b"fake-video-data")
        output_file = tmp_path / "output.wav"

        with patch("src.asr.audio_preprocess.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = extract_audio_for_asr(video_file, output_file)

            mock_run.assert_called_once_with(
                [
                    "ffmpeg",
                    "-i", str(video_file),
                    "-ar", "16000",
                    "-ac", "1",
                    "-c:a", "pcm_s16le",
                    "-y", str(output_file),
                ],
                check=True,
                capture_output=True,
            )
            assert result == output_file

    def test_returns_output_path(self, tmp_path: Path):
        """返回输出文件路径。"""
        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"fake-video-data")
        output_file = tmp_path / "result.wav"

        with patch("src.asr.audio_preprocess.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = extract_audio_for_asr(video_file, output_file)

            assert isinstance(result, Path)
            assert result == output_file


class TestExtractAudioFfmpegFailure:
    """ffmpeg 执行失败场景。"""

    def test_ffmpeg_failure_raises_asr_error(self, tmp_path: Path):
        """ffmpeg 失败抛 ASRError(\"ffmpeg_failed\")。"""
        video_file = tmp_path / "corrupt.mp4"
        video_file.write_bytes(b"bad-video-data")
        output_file = tmp_path / "output.wav"

        with patch("src.asr.audio_preprocess.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=1,
                cmd=["ffmpeg", "-i", str(video_file)],
                stderr="Invalid data found",
            )

            with pytest.raises(ASRError) as exc_info:
                extract_audio_for_asr(video_file, output_file)

            assert exc_info.value.code == "ffmpeg_failed"
