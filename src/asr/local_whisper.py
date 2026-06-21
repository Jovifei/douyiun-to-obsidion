"""WhisperLocalClient — M2 Task 4: 本地 faster-whisper + Belle 模型。

通过 faster-whisper 在本地 GPU (4070S) 运行 ASR 转写，
使用 Belle-whisper-large-v3-turbo-zh 模型，int8_float16 量化。
"""
from pathlib import Path

import torch

from src.asr import ASRClient, ASRError, ASRResult

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None  # type: ignore[assignment,misc]

# Belle 模型名称
_MODEL_NAME = "Belle/Belle-whisper-large-v3-turbo-zh"


class WhisperLocalClient(ASRClient):
    """Whisper 本地客户端 — 基于 faster-whisper + Belle 模型。"""

    def __init__(self) -> None:
        self._model = None

    def _get_model(self):
        """懒加载 faster-whisper 模型。

        首次调用时加载模型到 GPU，后续复用同一实例。

        Returns:
            faster_whisper.WhisperModel 实例。

        Raises:
            ASRError: GPU 不可用时抛出，code 为 "gpu_unavailable"。
        """
        if self._model is not None:
            return self._model

        if not torch.cuda.is_available():
            raise ASRError("gpu_unavailable")

        if WhisperModel is None:
            raise ImportError("faster_whisper not installed")

        self._model = WhisperModel(
            _MODEL_NAME,
            device="cuda",
            compute_type="int8_float16",
        )
        return self._model

    def transcribe(self, audio_path: Path) -> ASRResult:
        """转录音频文件。

        使用 faster-whisper VAD 切片 + 批量推理，
        拼接所有 segment 文本返回完整转写结果。

        Args:
            audio_path: 音频文件路径（16kHz mono WAV）。

        Returns:
            ASRResult 实例，source 为 "whisper_local"。

        Raises:
            ASRError: GPU 不可用时抛出，code 为 "gpu_unavailable"。
        """
        model = self._get_model()

        segments_iterator, _info = model.transcribe(
            str(audio_path),
            language="zh",
            vad_filter=True,
        )

        segments: list[dict] = []
        texts: list[str] = []
        for seg in segments_iterator:
            segment_dict = {
                "start": getattr(seg, "start", seg.get("start", 0.0)),
                "end": getattr(seg, "end", seg.get("end", 0.0)),
                "text": getattr(seg, "text", seg.get("text", "")),
            }
            segments.append(segment_dict)
            texts.append(segment_dict["text"])

        text = "".join(texts)

        return ASRResult(
            text=text,
            segments=segments,
            source="whisper_local",
            confidence=0.0,
        )

    def unload(self) -> None:
        """释放模型和 GPU 显存。"""
        self._model = None
        torch.cuda.empty_cache()
