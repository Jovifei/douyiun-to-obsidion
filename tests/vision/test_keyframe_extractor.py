"""Test keyframe extractor — 按语音重点位置抽帧（不限帧不限时）。

Spec ref: D-M3-2 视觉分层（关键帧→OCR→VLM）
"""
from pathlib import Path
from unittest.mock import patch

import pytest

from src.vision.keyframe_extractor import (
    extract_keyframes,
    extract_keyframes_by_segments,
    extract_keyframes_fallback,
    VisionError,
    _extract_frame,
)


# ── extract_keyframes 统一入口 ──────────────────────────────────────────


def test_extract_keyframes_signature():
    """函数存在且参数签名匹配 spec。"""
    import inspect
    sig = inspect.signature(extract_keyframes)
    params = list(sig.parameters.keys())
    assert "video_path" in params
    assert "output_dir" in params
    assert "asr_segments" in params
    assert "max_frames" in params


def test_extract_keyframes_with_segments(monkeypatch, tmp_path):
    """有 ASR segments 时走 extract_keyframes_by_segments。"""
    video = tmp_path / "test.mp4"
    video.write_bytes(b"fake")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    segments = [{"start": 0.0, "end": 2.0, "text": "hi"},
                {"start": 5.0, "end": 7.0, "text": "world"}]

    def fake_run(cmd, check, capture_output, **kwargs):
        if "-ss" in cmd:
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"fake-img")
        return type("R", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

    monkeypatch.setattr("src.vision.keyframe_extractor.subprocess.run", fake_run)

    result = extract_keyframes(video, output_dir, asr_segments=segments)
    assert len(result) == 2


def test_extract_keyframes_fallback(monkeypatch, tmp_path):
    """无 ASR segments 时走均匀采样 fallback。"""
    video = tmp_path / "test.mp4"
    video.write_bytes(b"fake")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    def fake_run(cmd, check, capture_output, **kwargs):
        joined = " ".join(cmd)
        if "fps=" in joined:
            out_dir = Path([a for a in cmd if a.endswith(".jpg") and "%" in a][0]).parent
            for i in range(3):
                (out_dir / f"fallback_{i:04d}.jpg").write_bytes(b"fake-img")
        return type("R", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

    monkeypatch.setattr("src.vision.keyframe_extractor.subprocess.run", fake_run)

    result = extract_keyframes(video, output_dir)
    assert len(result) == 3


def test_extract_keyframes_max_frames(monkeypatch, tmp_path):
    """显式 max_frames 时截断。"""
    video = tmp_path / "test.mp4"
    video.write_bytes(b"fake")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    segments = [{"start": i * 2, "end": i * 2 + 1, "text": f"seg{i}"} for i in range(20)]

    def fake_run(cmd, check, capture_output, **kwargs):
        if "-ss" in cmd:
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"fake-img")
        return type("R", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

    monkeypatch.setattr("src.vision.keyframe_extractor.subprocess.run", fake_run)

    result = extract_keyframes(video, output_dir, asr_segments=segments, max_frames=5)
    assert len(result) == 5


# ── extract_keyframes_by_segments ──────────────────────────────────────


def test_segments_extract_frames_at_start_times(monkeypatch, tmp_path):
    """每个 segment 起始点抽一帧。"""
    video = tmp_path / "test.mp4"
    video.write_bytes(b"fake")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    segments = [{"start": 3.5, "end": 6.0, "text": "important"},
                {"start": 10.0, "end": 12.0, "text": "key point"}]

    captured_times = []
    def fake_run(cmd, check, capture_output, **kwargs):
        if "-ss" in cmd:
            idx = cmd.index("-ss")
            captured_times.append(cmd[idx + 1])
            # ffmpeg 最后一个参数是输出路径
            out_path = cmd[-1]
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            Path(out_path).write_bytes(b"fake-img")
        return type("R", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

    monkeypatch.setattr("src.vision.keyframe_extractor.subprocess.run", fake_run)

    result = extract_keyframes_by_segments(video, output_dir, segments)
    assert len(result) == 2
    assert "3.5" in captured_times
    assert "10.0" in captured_times


def test_segments_output_dir_naming(monkeypatch, tmp_path):
    """输出目录格式: {video_id}_keyframes/。"""
    video = tmp_path / "abc123.mp4"
    video.write_bytes(b"fake")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    def fake_run(cmd, check, capture_output, **kwargs):
        if "-ss" in cmd:
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"fake-img")
        return type("R", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

    monkeypatch.setattr("src.vision.keyframe_extractor.subprocess.run", fake_run)

    result = extract_keyframes_by_segments(video, output_dir, [{"start": 1.0, "end": 2.0, "text": "x"}])
    assert len(result) > 0
    assert "abc123_keyframes" in str(result[0].parent)


def test_segments_no_limit(monkeypatch, tmp_path):
    """不限帧数——100 个 segment 得到 100 帧。"""
    video = tmp_path / "test.mp4"
    video.write_bytes(b"fake")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    segments = [{"start": i, "end": i + 1, "text": f"seg{i}"} for i in range(100)]

    def fake_run(cmd, check, capture_output, **kwargs):
        if "-ss" in cmd:
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"fake-img")
        return type("R", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

    monkeypatch.setattr("src.vision.keyframe_extractor.subprocess.run", fake_run)

    result = extract_keyframes_by_segments(video, output_dir, segments)
    assert len(result) == 100  # 不限帧


# ── extract_keyframes_fallback ──────────────────────────────────────────


def test_fallback_uniform_sampling(monkeypatch, tmp_path):
    """无 segments 时均匀采样每 10 秒一帧。"""
    video = tmp_path / "test.mp4"
    video.write_bytes(b"fake")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    def fake_run(cmd, check, capture_output, **kwargs):
        joined = " ".join(cmd)
        if "fps=" in joined:
            out_dir = Path([a for a in cmd if a.endswith(".jpg") and "%" in a][0]).parent
            for i in range(3):
                (out_dir / f"fallback_{i:04d}.jpg").write_bytes(b"fake-img")
        return type("R", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

    monkeypatch.setattr("src.vision.keyframe_extractor.subprocess.run", fake_run)

    result = extract_keyframes_fallback(video, output_dir)
    assert len(result) == 3
    assert all("fallback_" in f.name for f in result)


def test_fallback_raises_on_ffmpeg_failure(monkeypatch, tmp_path):
    """ffmpeg 失败抛 VisionError。"""
    video = tmp_path / "test.mp4"
    video.write_bytes(b"fake")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    def fake_run(cmd, check, capture_output, **kwargs):
        raise Exception("ffmpeg crashed")

    monkeypatch.setattr("src.vision.keyframe_extractor.subprocess.run", fake_run)

    with pytest.raises(VisionError):
        extract_keyframes_fallback(video, output_dir)


# ── _extract_frame ──────────────────────────────────────────────────────


def test_extract_frame_params(monkeypatch, tmp_path):
    """_extract_frame 用 -ss + -frames:v 1 参数。"""
    video = tmp_path / "test.mp4"
    video.write_bytes(b"fake")
    out = tmp_path / "frame.jpg"

    captured_cmd = []
    def fake_run(cmd, check, capture_output, **kwargs):
        captured_cmd.extend(cmd)
        out.write_bytes(b"fake-img")
        return type("R", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

    monkeypatch.setattr("src.vision.keyframe_extractor.subprocess.run", fake_run)

    _extract_frame(video, 5.5, out)
    assert "-ss" in captured_cmd
    assert "5.5" in captured_cmd
    assert "-frames:v" in captured_cmd


def test_extract_frame_raises_on_failure(monkeypatch, tmp_path):
    """ffmpeg 失败抛 VisionError。"""
    video = tmp_path / "test.mp4"
    video.write_bytes(b"fake")
    out = tmp_path / "frame.jpg"

    def fake_run(cmd, check, capture_output, **kwargs):
        raise Exception("ffmpeg failed at 5.5s")

    monkeypatch.setattr("src.vision.keyframe_extractor.subprocess.run", fake_run)

    with pytest.raises(VisionError):
        _extract_frame(video, 5.5, out)


def test_vision_error_is_exception():
    """VisionError 继承自 Exception。"""
    assert issubclass(VisionError, Exception)
