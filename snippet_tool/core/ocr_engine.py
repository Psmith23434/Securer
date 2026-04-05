# COMPILE_TO_PYD
"""
OCR pipeline wrapper.
Supports pytesseract and EasyOCR as backends.
Compile to .pyd before distribution.

Requires:
  - pytesseract + Tesseract binary in PATH, OR
  - easyocr (heavier, no external binary needed)
"""
from __future__ import annotations
from typing import Optional
from pathlib import Path
import tempfile


def extract_text_from_file(image_path: str | Path, backend: str = "tesseract") -> str:
    """
    Extract text from an image file.
    backend: 'tesseract' or 'easyocr'
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    if backend == "easyocr":
        return _easyocr_extract(str(image_path))
    return _tesseract_extract(str(image_path))


def extract_text_from_clipboard() -> Optional[str]:
    """
    Grab an image from the clipboard (Windows) and run OCR on it.
    Returns None if clipboard contains no image.
    """
    try:
        from PIL import ImageGrab
        img = ImageGrab.grabclipboard()
        if img is None:
            return None
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name
        img.save(tmp_path)
        text = _tesseract_extract(tmp_path)
        Path(tmp_path).unlink(missing_ok=True)
        return text
    except Exception as e:
        return f"[OCR Error: {e}]"


def extract_text_from_screenshot(region: tuple = None) -> str:
    """
    Take a screenshot (optionally of a region) and run OCR.
    region: (x, y, width, height) in screen coordinates, or None for full screen.
    """
    try:
        from PIL import ImageGrab
        bbox = None
        if region:
            x, y, w, h = region
            bbox = (x, y, x + w, y + h)
        img = ImageGrab.grab(bbox=bbox)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name
        img.save(tmp_path)
        text = _tesseract_extract(tmp_path)
        Path(tmp_path).unlink(missing_ok=True)
        return text
    except Exception as e:
        return f"[OCR Error: {e}]"


def _tesseract_extract(image_path: str) -> str:
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(image_path)
        return pytesseract.image_to_string(img).strip()
    except ImportError:
        return "[Error: pytesseract not installed. Run: pip install pytesseract]"
    except Exception as e:
        return f"[Tesseract error: {e}]"


def _easyocr_extract(image_path: str) -> str:
    try:
        import easyocr
        reader = easyocr.Reader(["en"], gpu=False)
        results = reader.readtext(image_path, detail=0)
        return "\n".join(results).strip()
    except ImportError:
        return "[Error: easyocr not installed. Run: pip install easyocr]"
    except Exception as e:
        return f"[EasyOCR error: {e}]"
