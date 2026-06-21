"""Test keyframe extractor — M3 Task 3.

Spec ref: D-M3-2 视觉分层（关键帧→OCR→VLM）
ffmpeg scene detect: -vf "select='gt(scene,0.4)'" -vsync vframe
"""
from pathlib import Path
from unittest.mock import patch, call

import pytest

from src.vision.keyframe_extractor import extract_keyframes, VisionError


def _make_fake_run(scene_frames=5, duration="30.0"):
    """构造 fake_run，区分 ffprobe / scene detect / uniform sampling。"""
    calls_captured = []

    def fake_run(cmd, check, capture_output, **kwargs):
        calls_captured.append(cmd)
        joined = " ".join(cmd)

        if "ffprobe" in joined:
            return type("R", (), {
                "returncode": 0,
                "stdout": f'{{"format": {{"duration": "{duration}"}}}}'.encode(),
                "stderr": b""
            })()

        # ffmpeg 命令 — 需要知道输出目录
        # 从命令末尾的 pattern 参数解析输出目录
        out_dir = None
        for arg in reversed(cmd):
            p = Path(arg)
            if p.suffix == ".jpg" and "%" in p.name:
                out_dir = p.parent
                break

        if out_dir is None:
            return type("R", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

        if "select=" in joined:
            # scene detect
            for i in range(scene_frames):
                (out_dir / f"frame_{i:04d}.jpg").write_bytes(b"fake-img")
        elif "fps=" in joined:
            # uniform sampling
            for i in range(3):
                (out_dir / f"uniform_{i:04d}.jpg").write_bytes(b"fake-img")

        return type("R", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

    return fake_run, calls_captured


# ---------------------------------------------------------------------------
# 1. extract_keyframes 函数存在，签名正确
# ---------------------------------------------------------------------------

def test_extract_keyframes_signature():
    """函数存在且参数签名匹配 spec。"""
    import inspect
    sig = inspect.signature(extract_keyframes)
    params = list(sig.parameters.keys())
    assert "video_path" in params
    assert "output_dir" in params
    assert "max_frames" in params


# ---------------------------------------------------------------------------
# 2. ffmpeg scene detect 参数正确
# ---------------------------------------------------------------------------

def test_scene_detect_params_correct(monkeypatch, tmp_path):
    """ffmpeg 命令包含正确的 scene detect 参数。"""
    video_path = tmp_path / "test.mp4"
    video_path.write_bytes(b"fake-video")
    output_dir = tmp_path / "keyframes"
    output_dir.mkdir()

    fake_run, captured = _make_fake_run(scene_frames=5)
    monkeypatch.setattr(
        "src.vision.keyframe_extractor.subprocess.run", fake_run
    )

    result = extract_keyframes(video_path, output_dir)

    # 找到包含 scene detect 参数的命令
    scene_cmd = None
    for cmd in captured:
        joined = " ".join(cmd)
        if "select=" in joined:
            scene_cmd = cmd
            break

    assert scene_cmd is not None, "未找到包含 scene detect 参数的 ffmpeg 命令"
    assert "-vf" in scene_cmd
    assert "select=" in " ".join(scene_cmd)
    assert "scene,0.4" in " ".join(scene_cmd)
    assert "-vsync" in scene_cmd
    assert "vframe" in scene_cmd


# ---------------------------------------------------------------------------
# 3. scene detect 帧 < 3 时，均匀采样补抽（每 10 秒一帧）
# ---------------------------------------------------------------------------

def test_fallback_uniform_sampling_when_few_frames(monkeypatch, tmp_path):
    """scene detect 帧数 < 3 时，使用均匀采样兜底。"""
    video_path = tmp_path / "test.mp4"
    video_path.write_bytes(b"fake-video")
    output_dir = tmp_path / "keyframes"
    output_dir.mkdir()

    fake_run, captured = _make_fake_run(scene_frames=1, duration="60.0")
    monkeypatch.setattr(
        "src.vision.keyframe_extractor.subprocess.run", fake_run
    )

    result = extract_keyframes(video_path, output_dir)

    # 验证 fallback 命令包含 fps 参数
    fallback_cmd = None
    for cmd in captured:
        joined = " ".join(cmd)
        if "fps=" in joined and "ffprobe" not in joined:
            fallback_cmd = cmd
            break

    assert fallback_cmd is not None, "未找到包含均匀采样的 ffmpeg 命令"
    assert "fps=" in " ".join(fallback_cmd)


# ---------------------------------------------------------------------------
# 4. 返回关键帧路径列表
# ---------------------------------------------------------------------------

def test_returns_keyframe_paths(monkeypatch, tmp_path):
    """返回值为关键帧路径列表。"""
    video_path = tmp_path / "test.mp4"
    video_path.write_bytes(b"fake-video")
    output_dir = tmp_path / "keyframes"
    output_dir.mkdir()

    fake_run, _ = _make_fake_run(scene_frames=5)
    monkeypatch.setattr(
        "src.vision.keyframe_extractor.subprocess.run", fake_run
    )

    result = extract_keyframes(video_path, output_dir)

    assert isinstance(result, list)
    assert len(result) == 5
    for p in result:
        assert isinstance(p, Path)
        assert p.suffix == ".jpg"


# ---------------------------------------------------------------------------
# 5. 返回最多 max_frames 帧
# ---------------------------------------------------------------------------

def test_max_frames_limit(monkeypatch, tmp_path):
    """超过 max_frames 时截断。"""
    video_path = tmp_path / "test.mp4"
    video_path.write_bytes(b"fake-video")
    output_dir = tmp_path / "keyframes"
    output_dir.mkdir()

    fake_run, _ = _make_fake_run(scene_frames=50)
    monkeypatch.setattr(
        "src.vision.keyframe_extractor.subprocess.run", fake_run
    )

    result = extract_keyframes(video_path, output_dir, max_frames=10)

    assert len(result) <= 10


# ---------------------------------------------------------------------------
# 6. ffmpeg 失败抛 VisionError
# ---------------------------------------------------------------------------

def test_ffmpeg_failure_raises_vision_error(monkeypatch, tmp_path):
    """ffmpeg 非零退出 -> VisionError。"""
    video_path = tmp_path / "test.mp4"
    video_path.write_bytes(b"fake-video")
    output_dir = tmp_path / "keyframes"
    output_dir.mkdir()

    def fake_run(cmd, check, capture_output, **kwargs):
        joined = " ".join(cmd)
        if "ffprobe" in joined:
            return type("R", (), {
                "returncode": 0,
                "stdout": b'{"format": {"duration": "30.0"}}',
                "stderr": b""
            })()
        raise Exception("ffmpeg crashed")

    monkeypatch.setattr(
        "src.vision.keyframe_extractor.subprocess.run", fake_run
    )

    with pytest.raises(VisionError):
        extract_keyframes(video_path, output_dir)


# ---------------------------------------------------------------------------
# 7. VisionError 是 Exception 子类
# ---------------------------------------------------------------------------

def test_vision_error_is_exception():
    """VisionError 继承自 Exception。"""
    assert issubclass(VisionError, Exception)


# ---------------------------------------------------------------------------
# 8. 输出目录命名规范
# ---------------------------------------------------------------------------

def test_output_dir_naming_convention(monkeypatch, tmp_path):
    """输出目录格式: {output_dir}/{video_id}_keyframes/。"""
    video_path = tmp_path / "abc123.mp4"
    video_path.write_bytes(b"fake-video")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    fake_run, _ = _make_fake_run(scene_frames=1)
    monkeypatch.setattr(
        "src.vision.keyframe_extractor.subprocess.run", fake_run
    )

    result = extract_keyframes(video_path, output_dir)

    assert len(result) > 0
    frame_dir = result[0].parent
    assert frame_dir.name == "abc123_keyframes"
