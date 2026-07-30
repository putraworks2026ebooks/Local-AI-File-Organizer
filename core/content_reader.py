"""
Document content reader for Local AI File Organizer.
Reads and summarizes text content from various document formats.
"""

from pathlib import Path
from typing import Optional


class ContentReader:
    """Reads text content from various file formats for AI classification."""

    TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml", ".ini",
                 ".cfg", ".conf", ".log", ".py", ".js", ".ts", ".java", ".cpp", ".c",
                 ".h", ".sh", ".bat", ".ps1", ".sql", ".html", ".css", ".rst", ".tex"}
    PDF_EXTS = {".pdf"}
    DOCX_EXTS = {".docx"}
    DOC_EXTS = {".doc"}
    ODT_EXTS = {".odt"}
    RTF_EXTS = {".rtf"}
    EPUB_EXTS = {".epub"}

    MAX_CONTENT_LENGTH = 5000  # Max characters to read for classification

    def read(self, filepath: Path | str) -> Optional[str]:
        """Read text content from a file. Returns None if unsupported."""
        filepath = Path(filepath)
        ext = filepath.suffix.lower()

        if ext in self.TEXT_EXTS:
            return self._read_text(filepath)
        elif ext in self.PDF_EXTS:
            return self._read_pdf(filepath)
        elif ext in self.DOCX_EXTS:
            return self._read_docx(filepath)
        elif ext in self.ODT_EXTS:
            return self._read_odt(filepath)
        elif ext in self.EPUB_EXTS:
            return self._read_epub(filepath)
        elif ext in self.RTF_EXTS:
            return self._read_rtf(filepath)

        return None

    def read_summary(self, filepath: Path | str, max_length: int = 1000) -> Optional[str]:
        """Read a brief summary of file content."""
        content = self.read(filepath)
        if content:
            # Take first N characters and clean up
            summary = content[:max_length]
            summary = " ".join(summary.split())  # Normalize whitespace
            return summary
        return None

    def _read_text(self, filepath: Path) -> Optional[str]:
        """Read plain text files."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(self.MAX_CONTENT_LENGTH)
        except (OSError, PermissionError):
            return None

    def _read_pdf(self, filepath: Path) -> Optional[str]:
        """Read text from PDF files."""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(str(filepath))
            text_parts = []
            for page in doc:
                text = page.get_text()
                if text:
                    text_parts.append(text.strip())
                if sum(len(t) for t in text_parts) >= self.MAX_CONTENT_LENGTH:
                    break
            doc.close()
            return "\n".join(text_parts)[:self.MAX_CONTENT_LENGTH]
        except Exception:
            return None

    def _read_docx(self, filepath: Path) -> Optional[str]:
        """Read text from DOCX files."""
        try:
            from docx import Document
            doc = Document(str(filepath))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            text = "\n".join(paragraphs)
            return text[:self.MAX_CONTENT_LENGTH]
        except Exception:
            return None

    def _read_odt(self, filepath: Path) -> Optional[str]:
        """Read text from ODT files."""
        try:
            import zipfile
            from xml.etree import ElementTree

            with zipfile.ZipFile(str(filepath), "r") as zf:
                with zf.open("content.xml") as content:
                    tree = ElementTree.parse(content)
                    root = tree.getroot()
                    # Extract text from namespace
                    ns = {"text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0"}
                    texts = []
                    for t in root.iter():
                        if t.text and t.text.strip():
                            texts.append(t.text.strip())
                    return " ".join(texts)[:self.MAX_CONTENT_LENGTH]
        except Exception:
            return None

    def _read_rtf(self, filepath: Path) -> Optional[str]:
        """Read text from RTF files (basic stripping)."""
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(self.MAX_CONTENT_LENGTH)
            # Basic RTF tag stripping
            import re
            clean = re.sub(r"\\[a-z]+-?\d* ?|{|}", "", content)
            clean = re.sub(r"\\\*|\\par\b|\\line\b", "\n", clean)
            return clean.strip()[:self.MAX_CONTENT_LENGTH]
        except (OSError, PermissionError):
            return None

    def _read_epub(self, filepath: Path) -> Optional[str]:
        """Read text from EPUB files."""
        try:
            import zipfile
            from xml.etree import ElementTree

            text_parts = []
            with zipfile.ZipFile(str(filepath), "r") as zf:
                for name in zf.namelist():
                    if name.endswith((".html", ".xhtml", ".htm")):
                        with zf.open(name) as html_file:
                            tree = ElementTree.parse(html_file)
                            for elem in tree.iter():
                                if elem.text and elem.text.strip():
                                    text_parts.append(elem.text.strip())
                            if sum(len(t) for t in text_parts) >= self.MAX_CONTENT_LENGTH:
                                break
            return " ".join(text_parts)[:self.MAX_CONTENT_LENGTH]
        except Exception:
            return None
