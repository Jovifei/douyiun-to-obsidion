"""MCP tool server — M2 Task 2。

注册 asr_transcribe 工具，供 openclaw MCP 调用。
"""
import json
import subprocess
from typing import Any


def _asr_transcribe(audio_path: str) -> dict[str, Any]:
    """asr_transcribe MCP 工具实现。

    内部调用 openclaw CLI 调用 mimo-v2.5-asr API。

    Args:
        audio_path: 音频文件路径。

    Returns:
        dict 含 text / segments / source / confidence。
    """
    result = subprocess.run(
        ["openclaw", "tool", "call", "mimo-v2.5-asr", "--audio_path", audio_path],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        raise RuntimeError(f"mimo-v2.5-asr call failed: {result.stderr}")

    return json.loads(result.stdout)


asr_transcribe_tool: dict[str, Any] = {
    "name": "asr_transcribe",
    "description": "通过 mimo-v2.5-asr API 转录音频文件",
    "parameters": {
        "type": "object",
        "properties": {
            "audio_path": {
                "type": "string",
                "description": "音频文件路径",
            },
        },
        "required": ["audio_path"],
    },
    "function": _asr_transcribe,
}


class MCPToolServer:
    """MCP 工具服务器，管理已注册的工具。"""

    def __init__(self) -> None:
        self.tools: dict[str, dict[str, Any]] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """注册默认工具集。"""
        self.register(asr_transcribe_tool)

    def register(self, tool: dict[str, Any]) -> None:
        """注册一个 MCP 工具。"""
        self.tools[tool["name"]] = tool

    def call(self, tool_name: str, **kwargs: str) -> dict[str, Any]:
        """调用已注册的 MCP 工具。"""
        if tool_name not in self.tools:
            raise ValueError(f"unknown tool: {tool_name}")
        return self.tools[tool_name]["function"](**kwargs)
