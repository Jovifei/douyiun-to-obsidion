"""Vision module -- 关键帧提取、OCR、VLM 分析。"""
from src.vision.vlm_client import (
    VLMClient,
    VLMClientError,
    OllamaVLMClient,
    CloudVLMClient,
    get_vlm_client,
    describe_image,
)

__all__ = [
    "VLMClient",
    "VLMClientError",
    "OllamaVLMClient",
    "CloudVLMClient",
    "get_vlm_client",
    "describe_image",
]
