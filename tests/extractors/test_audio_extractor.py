"""Test audio extractor (ffmpeg stub for M2 Whisper).

Spec ref: specs/douyin-extraction/spec.md
M1 阶段仅保留接口，不在主路径调用。
"""
from pathlib import Path

import pytest

from src.extractors.audio_extractor import extract_audio, AudioExtractionError


def test_extract_audio_success(monkeypatch, tmp_path):
    """Normal extraction: ffmpeg succeeds, returns output path."""
    video_path = tmp_path / "test.mp4"
    video_path.write_bytes(b"fake-video")
    out_path = tmp_path / "test.wav"

    def fake_run(cmd, check, capture_output, **kwargs):
        out_path.write_bytes(b"fake-wav-data")
        return type("R", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

    monkeypatch.setattr(
        "src.extractors.audio_extractor.subprocess.run", fake_run
    )
    result = extract_audio(video_path, out_path)
    assert result == out_path
    assert out_path.exists()


def test_extract_audio_ffmpeg_failure(monkeypatch, tmp_path):
    """ffmpeg non-zero exit -> AudioExtractionError."""
    video_path = tmp_path / "test.mp4"
    video_path.write_bytes(b"fake-video")
    out_path = tmp_path / "test.wav"

    def fake_run(cmd, check, capture_output, **kwargs):
        raise Exception("ffmpeg crashed")

    monkeypatch.setattr(
        "src.extractors.audio_extractor.subprocess.run", fake_run
    )
    with pytest.raises(AudioExtractionError):
        extract_audio(video_path, out_path)


def test_extract_audio_output_path_correct(monkeypatch, tmp_path):
    """Output path matches what caller passes."""
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"fake-video")
    out_path = tmp_path / "audio_16k.wav"

    def fake_run(cmd, check, capture_output, **kwargs):
        out_path.write_bytes(b"fake-wav-data")
        return type("R", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

    monkeypatch.setattr(
        "src.extractors.audio_extractor.subprocess.run", fake_run
    )
    result = extract_audio(video_path, out_path)
    assert result.name == "audio_16k.wav"
    assert result.suffix == ".wav"
