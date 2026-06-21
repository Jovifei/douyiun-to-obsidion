"""OCR 客户端 — M3 Task 4。

PaddleOCR PP-OCRv5 中文文字提取。
Spec ref: D-M3-2 视觉分层（关键帧→OCR→VLM）
"""
from pathlib import Path


_ocr_engine = None


def _get_ocr_engine():
    """懒加载 PaddleOCR 引擎（首次加载，后续复用）。"""
    global _ocr_engine
    if _ocr_engine is None:
        from paddleocr import PaddleOCR
        _ocr_engine = PaddleOCR(lang="ch", device="gpu")
    return _ocr_engine


def extract_text_from_image(image_path: Path) -> str:
    """从图片提取中文文字。

    调用 PaddleOCR PP-OCRv5，失败时返回空字符串（不阻塞后续流程）。

    Args:
        image_path: 图片文件路径

    Returns:
        提取的文字字符串，失败时返回空字符串
    """
    if not image_path.exists():
        return ""

    try:
        ocr = _get_ocr_engine()
        result = ocr.predict(str(image_path))
    except ImportError:
        return ""
    except Exception:
        return ""

    texts = []
    for res in result:
        if isinstance(res, dict):
            texts.extend(res.get("rec_texts", []))
        else:
            # PaddleOCR 3.x result 对象
            rec_texts = getattr(res, "rec_texts", None)
            if rec_texts:
                texts.extend(rec_texts)
    return "\n".join(texts)
