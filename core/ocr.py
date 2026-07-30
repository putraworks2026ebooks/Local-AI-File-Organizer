"""
OCR support for scanned PDFs and images.
Uses Tesseract OCR via pytesseract for text extraction.
"""

import os
from pathlib import Path
from typing import Optional


class OCRProcessor:
    """Handles OCR processing for scanned PDFs and images."""

    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".gif", ".webp"}

    def __init__(self, enabled: bool = False, language: str = "eng", max_pages: int = 10):
        self.enabled = enabled
        self.language = language
        self.max_pages = max_pages
        self._tesseract_available = self._check_tesseract()

    def _check_tesseract(self) -> bool:
        """Check if Tesseract is installed."""
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def is_available(self) -> bool:
        """Check if OCR is available."""
        return self.enabled and self._tesseract_available

    def extract_text(self, filepath: Path | str, max_length: int = 2000) -> Optional[str]:
        """
        Extract text from image or scanned PDF using OCR.

        Args:
            filepath: Path to image or PDF file.
            max_length: Maximum characters to extract.

        Returns:
            Extracted text or None.
        """
        filepath = Path(filepath)
        ext = filepath.suffix.lower()

        if not self.is_available():
            return None

        try:
            if ext in self.IMAGE_EXTS:
                return self._ocr_image(filepath, max_length)
            elif ext == ".pdf":
                return self._ocr_pdf(filepath, max_length)
        except Exception:
            return None

        return None

    def _ocr_image(self, filepath: Path, max_length: int) -> Optional[str]:
        """Extract text from an image using OCR."""
        try:
            import pytesseract
            from PIL import Image

            with Image.open(str(filepath)) as img:
                text = pytesseract.image_to_string(img, lang=self.language)
                return text[:max_length].strip() or None
        except Exception:
            return None

    def _ocr_pdf(self, filepath: Path, max_length: int) -> Optional[str]:
        """Extract text from a scanned PDF using OCR."""
        try:
            import fitz  # PyMuPDF
            from PIL import Image
            import pytesseract
            import io

            doc = fitz.open(str(filepath))
            text_parts = []
            pages_to_process = min(doc.page_count, self.max_pages)

            for i in range(pages_to_process):
                page = doc[i]
                # Try regular text extraction first
                text = page.get_text()
                if text and text.strip():
                    text_parts.append(text.strip())
                    continue

                # Fall back to OCR
                pix = page.get_pixmap(dpi=200)
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))
                ocr_text = pytesseract.image_to_string(img, lang=self.language)
                if ocr_text and ocr_text.strip():
                    text_parts.append(ocr_text.strip())

                if sum(len(t) for t in text_parts) >= max_length:
                    break

            doc.close()
            result = " ".join(text_parts)[:max_length]
            return result if result else None
        except Exception:
            return None

    def install_instructions(self) -> str:
        """Return installation instructions for Tesseract."""
        return (
            "To enable OCR support, install Tesseract OCR:\n\n"
            "Windows:\n"
            "  Download from: https://github.com/UB-Mannheim/tesseract/wiki\n"
            "  Install to default path (C:\\Program Files\\Tesseract-OCR)\n"
            "  Add to PATH or set TESSERACT_PATH in settings\n\n"
            "Then install Python package:\n"
            "  pip install pytesseract Pillow PyMuPDF\n\n"
            "After installation, enable OCR in Settings."
        )
