"""MCP server — 让 openclaw agent 能调用本地 bridge API。

用法：python src/bridge/mcp_server.py
openclaw 通过 MCP 协议连接后，agent 可调用 ingest_video / get_task_status / get_health 工具。
"""
import httpx
from fastmcp import FastMCP

BRIDGE_URL = "http://127.0.0.1:8765"

mcp = FastMCP("douyin-bridge")


@mcp.tool()
def ingest_video(source_url: str) -> dict:
    """提交抖音视频 URL 到解析服务，开始归档。

    Args:
        source_url: 抖音视频 URL（支持短链/完整链/分享文案）

    Returns:
        包含 task_id 和 status 的字典
    """
    resp = httpx.post(
        f"{BRIDGE_URL}/ingest",
        json={"source_url": source_url},
        timeout=10,
    )
    return resp.json()


@mcp.tool()
def get_task_status(task_id: int) -> dict:
    """查询任务状态。

    Args:
        task_id: ingest_video 返回的 task_id

    Returns:
        包含 status, note_path, error_code 等的字典
    """
    resp = httpx.get(f"{BRIDGE_URL}/tasks/{task_id}", timeout=5)
    return resp.json()


@mcp.tool()
def get_health() -> dict:
    """查询解析服务健康状态和队列统计。"""
    resp = httpx.get(f"{BRIDGE_URL}/health", timeout=5)
    return resp.json()


if __name__ == "__main__":
    mcp.run(transport="stdio")
