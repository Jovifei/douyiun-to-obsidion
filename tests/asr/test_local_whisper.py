"""WhisperLocalClient 单元测试 — M2 Task 4 TDD (RED phase).

验证 WhisperLocalClient 通过 faster-whisper + Belle 模型在本地 GPU 运行 ASR。
"""
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.asr import ASRClient, ASRResult
from src.asr.local_whisper import WhisperLocalClient, ASRError


# ── 继承 & 实例化 ──────────────────────────────────────────


class TestWhisperLocalClientInheritance:
    """WhisperLocalClient 继承 ASRClient ABC。"""

    def test_inherits_asr_client(self):
        """WhisperLocalClient 是 ASRClient 的子类。"""
        assert issubclass(WhisperLocalClient, ASRClient)

    def test_can_instantiate(self):
        """可以正常实例化 WhisperLocalClient。"""
        client = WhisperLocalClient()
        assert isinstance(client, ASRClient)


# ── transcribe 正常场景 ────────────────────────────────────


class TestTranscribeNormal:
    """正常转写场景。"""

    def test_transcribe_returns_asr_result(self, tmp_path: Path):
        """transcribe 返回 ASRResult，source 为 whisper_local。"""
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake-wav-data")

        mock_segments = [
            {"start": 0.0, "end": 2.5, "text": "你好世界"},
            {"start": 2.5, "end": 5.0, "text": "这是测试"},
        ]

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (
            mock_segments,  # segments generator
            {"language": "zh"},  # info
        )

        client = WhisperLocalClient()
        with patch.object(client, "_get_model", return_value=mock_model):
            result = client.transcribe(audio_file)

            assert isinstance(result, ASRResult)
            assert result.source == "whisper_local"
            assert "你好世界" in result.text
            assert "这是测试" in result.text
            assert len(result.segments) == 2
            assert result.segments[0]["text"] == "你好世界"

    def test_transcribe_concatenates_segment_texts(self, tmp_path: Path):
        """transcribe 拼接所有 segment 的 text。"""
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake-wav-data")

        mock_segments = [
            {"start": 0.0, "end": 1.0, "text": "第一段"},
            {"start": 1.0, "end": 2.0, "text": "第二段"},
            {"start": 2.0, "end": 3.0, "text": "第三段"},
        ]

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter(mock_segments), {"language": "zh"})

        client = WhisperLocalClient()
        with patch.object(client, "_get_model", return_value=mock_model):
            result = client.transcribe(audio_file)

            assert result.text == "第一段第二段第三段"
            assert len(result.segments) == 3


# ── 懒加载模型 ─────────────────────────────────────────────


class TestLazyModelLoading:
    """模型懒加载：首次加载，后续复用。"""

    def test_model_loaded_lazily(self, tmp_path: Path):
        """首次 transcribe 时才加载模型。"""
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake-wav-data")

        mock_segments = [{"start": 0.0, "end": 1.0, "text": "测试"}]
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter(mock_segments), {"language": "zh"})

        client = WhisperLocalClient()
        assert client._model is None  # 初始未加载

        with patch("src.asr.local_whisper.WhisperModel", return_value=mock_model) as mock_cls, \
             patch("src.asr.local_whisper.torch.cuda.is_available", return_value=True):
            client.transcribe(audio_file)
            mock_cls.assert_called_once()

            # 第二次调用不再加载
            mock_model.transcribe.return_value = (iter(mock_segments), {"language": "zh"})
            client.transcribe(audio_file)
            assert mock_cls.call_count == 1  # 仍然只调用一次


# ── unload 释放显存 ────────────────────────────────────────


class TestUnload:
    """unload() 释放模型和 GPU 显存。"""

    def test_unload_clears_model(self):
        """unload 将 _model 设为 None。"""
        client = WhisperLocalClient()
        client._model = MagicMock()

        with patch("src.asr.local_whisper.torch") as mock_torch:
            client.unload()
            assert client._model is None
            mock_torch.cuda.empty_cache.assert_called_once()

    def test_unload_when_no_model(self):
        """unload 在模型未加载时不报错。"""
        client = WhisperLocalClient()
        client.unload()  # 不应抛异常


# ── GPU 不可用 ──────────────────────────────────────────────


class TestGPUUnavailable:
    """GPU 不可用时的错误处理。"""

    def test_no_gpu_raises_asr_error(self, tmp_path: Path):
        """GPU 不可用时 transcribe 抛 ASRError(\"gpu_unavailable\")。"""
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"fake-wav-data")

        client = WhisperLocalClient()
        with patch("src.asr.local_whisper.torch") as mock_torch:
            mock_torch.cuda.is_available.return_value = False
            with pytest.raises(ASRError) as exc_info:
                client.transcribe(audio_file)
            assert exc_info.value.code == "gpu_unavailable"
