"""MimoASRClient — M2 Task 2。

通过 mimo-v2.5-asr API 转录音频。
API 格式：chat/completions + input_audio（data URL）。
"""
import base64
from pathlib import Path

import httpx

from src.asr import ASRClient, ASRError, ASRResult


class MimoASRClient(ASRClient):
    """MiMo ASR 客户端 — 直接调 mimo-v2.5-asr API。"""

    def __init__(self, api_key: str, base_url: str = "https://token-plan-cn.xiaomimimo.com/v1"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def transcribe(self, audio_path: Path) -> ASRResult:
        """转录音频文件。

        Args:
            audio_path: 音频文件路径（WAV 格式）。

        Returns:
            ASRResult 实例。

        Raises:
            ASRError: API 调用失败或返回空结果。
        """
        # 读音频 → base64 data URL
        with open(audio_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()
        data_url = f"data:audio/wav;base64,{audio_b64}"

        # 调 mimo-v2.5-asr API（chat/completions + input_audio）
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "mimo-v2.5-asr",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_audio",
                                    "input_audio": {
                                        "data": data_url,
                                        "format": "wav",
                                    },
                                }
                            ],
                        }
                    ],
                },
                timeout=30,
            )
        except httpx.TimeoutException:
            raise ASRError("asr_timeout")
        except httpx.RequestError as e:
            raise ASRError(f"asr_network_error: {e}")

        if resp.status_code != 200:
            raise ASRError(f"asr_api_error_{resp.status_code}: {resp.text[:200]}")

        result = resp.json()
        text = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

        if not text:
            raise ASRError("empty_result")

        # 构造 ASRResult（mimo-asr 不返回 segments，用单段占位）
        usage = result.get("usage", {})
        audio_tokens = usage.get("prompt_tokens_details", {}).get("audio_tokens", 0)
        total_tokens = usage.get("prompt_tokens", 0)
        confidence = min(1.0, audio_tokens / max(total_tokens, 1)) if total_tokens > 0 else 0.8

        return ASRResult(
            text=text,
            segments=[{"start": 0, "end": 0, "text": text}],
            source="mimo_asr",
            confidence=confidence,
        )
