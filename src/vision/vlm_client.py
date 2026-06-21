"""VLM Client — M3 Task 5。

通过 mimo-v2-omni API 理解关键帧画面。
API 格式：chat/completions + image_url（data URL）。
"""
import base64
from pathlib import Path

import httpx

_DEFAULT_PROMPT = "这是一段抖音知识视频的关键帧，请用一句话描述画面中的关键信息"


def describe_image(
    image_path: Path,
    prompt: str | None = None,
    api_key: str = "",
    base_url: str = "https://token-plan-cn.xiaomimimo.com/v1",
) -> str:
    """调用 VLM API 描述图片内容。

    Args:
        image_path: 图片文件路径。
        prompt: 用户 prompt，None 时使用默认 prompt。
        api_key: API 密钥。
        base_url: API 基础 URL。

    Returns:
        描述文本，失败时返回降级文本（不抛异常）。
    """
    # 图片不存在 → 空字符串
    if not image_path.exists():
        return ""

    effective_prompt = prompt if prompt is not None else _DEFAULT_PROMPT

    # 读图片 → base64 data URL
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    data_url = f"data:image/jpeg;base64,{img_b64}"

    # 调 mimo-v2-omni API
    try:
        resp = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "mimo-v2-omni",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": effective_prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
            },
            timeout=30,
        )
    except httpx.TimeoutException:
        return "VLM 超时，画面内容未提取"
    except httpx.RequestError as e:
        return f"VLM 调用失败：{e}"

    if resp.status_code != 200:
        return f"VLM 调用失败：{resp.status_code}"

    result = resp.json()
    return result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
