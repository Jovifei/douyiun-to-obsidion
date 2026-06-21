"""MimoASRClient — M2 Task 2。

通过 openclaw MCP 工具 asr_transcribe 调用 mimo-v2.5-asr API。
"""
from pathlib import Path

from src.asr import ASRClient, ASRError, ASRResult


class MimoASRClient(ASRClient):
    """MiMo ASR 客户端 — 走 openclaw MCP 工具层。"""

    def transcribe(self, audio_path: Path) -> ASRResult:
        """转录音频文件。

        Args:
            audio_path: 音频文件路径。

        Returns:
            ASRResult 实例。

        Raises:
            ASRError: MCP 调用超时或返回空结果。
        """
        try:
            response = self._call_mcp_tool(
                "asr_transcribe",
                audio_path=str(audio_path),
            )
        except TimeoutError:
            raise ASRError("asr_timeout")

        text = response.get("text", "").strip()
        if not text:
            raise ASRError("empty_result")

        return ASRResult(
            text=response["text"],
            segments=response.get("segments", []),
            source=response.get("source", "mimo_asr"),
            confidence=response.get("confidence", 0.0),
        )

    def _call_mcp_tool(self, tool_name: str, **kwargs: str) -> dict:
        """调用 openclaw MCP 工具。

        Args:
            tool_name: MCP 工具名称。
            **kwargs: 工具参数。

        Returns:
            工具返回的 dict。

        Raises:
            TimeoutError: MCP 调用超时。
        """
        import json
        import subprocess

        # Build MCP tool call via openclaw CLI
        args = ["openclaw", "tool", "call", tool_name]
        for key, value in kwargs.items():
            args.extend([f"--{key}", value])

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError("MCP call timed out")

        if result.returncode != 0:
            raise RuntimeError(f"MCP tool call failed: {result.stderr}")

        return json.loads(result.stdout)
