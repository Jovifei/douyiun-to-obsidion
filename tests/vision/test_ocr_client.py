"""Test OCR client — M3 Task 4.

Spec ref: D-M3-2 视觉分层（关键帧→OCR→VLM）
PaddleOCR PP-OCRv5 中文文字提取
"""
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.vision.ocr_client import extract_text_from_image


# ---------------------------------------------------------------------------
# 1. extract_text_from_image 函数存在，签名正确
# ---------------------------------------------------------------------------

def test_extract_text_from_image_signature():
    """函数存在且参数签名匹配 spec。"""
    import inspect
    sig = inspect.signature(extract_text_from_image)
    params = list(sig.parameters.keys())
    assert "image_path" in params


# ---------------------------------------------------------------------------
# 2. 正常中文图片返回文字字符串
# ---------------------------------------------------------------------------

def test_returns_string_for_valid_image(monkeypatch, tmp_path):
    """正常图片返回字符串。"""
    fake_img = tmp_path / "test.jpg"
    fake_img.write_bytes(b"fake-jpeg-data")

    # Mock PaddleOCR
    fake_ocr = MagicMock()
    fake_ocr.predict.return_value = [
        {"rec_texts": ["你好世界"]}
    ]
    monkeypatch.setattr(
        "src.vision.ocr_client._get_ocr_engine", lambda: fake_ocr
    )

    result = extract_text_from_image(fake_img)
    assert isinstance(result, str)
    assert "你好世界" in result


# ---------------------------------------------------------------------------
# 3. OCR 失败返回空字符串（不阻塞后续流程）
# ---------------------------------------------------------------------------

def test_ocr_failure_returns_empty_string(monkeypatch, tmp_path):
    """OCR 异常时返回空字符串，不抛异常。"""
    fake_img = tmp_path / "test.jpg"
    fake_img.write_bytes(b"fake-jpeg-data")

    fake_ocr = MagicMock()
    fake_ocr.predict.side_effect = Exception("OCR crashed")
    monkeypatch.setattr(
        "src.vision.ocr_client._get_ocr_engine", lambda: fake_ocr
    )

    result = extract_text_from_image(fake_img)
    assert result == ""


# ---------------------------------------------------------------------------
# 4. PaddleOCR 未装时降级返回空字符串
# ---------------------------------------------------------------------------

def test_paddleocr_not_installed_returns_empty_string(monkeypatch, tmp_path):
    """PaddleOCR 未安装时返回空字符串。"""
    fake_img = tmp_path / "test.jpg"
    fake_img.write_bytes(b"fake-jpeg-data")

    def raise_import_error():
        raise ImportError("No module named 'paddleocr'")

    monkeypatch.setattr(
        "src.vision.ocr_client._get_ocr_engine", raise_import_error
    )

    result = extract_text_from_image(fake_img)
    assert result == ""


# ---------------------------------------------------------------------------
# 5. 图片文件不存在时返回空字符串
# ---------------------------------------------------------------------------

def test_nonexistent_image_returns_empty_string():
    """不存在的图片路径返回空字符串。"""
    fake_img = Path("/nonexistent/path/image.jpg")
    result = extract_text_from_image(fake_img)
    assert result == ""
