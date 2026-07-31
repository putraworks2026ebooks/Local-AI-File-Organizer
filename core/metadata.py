"""
File metadata extraction for Local AI File Organizer.
Extracts metadata from various file types (images, videos, documents, audio).
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional


class MetadataExtractor:
    """Extracts metadata from various file types."""

    IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".heic", ".raw"}
    VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"}
    AUDIO_EXTS = {".mp3", ".flac", ".wav", ".aac", ".ogg", ".wma", ".m4a", ".aiff"}
    DOC_EXTS = {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".md", ".tex"}
    ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"}

    def extract(self, filepath: Path | str) -> dict:
        """Extract metadata from a file. Returns dict of metadata."""
        filepath = Path(filepath)
        ext = filepath.suffix.lower()
        metadata = {}

        # Basic file system metadata
        try:
            stat = filepath.stat()
            metadata["size_bytes"] = stat.st_size
            metadata["created"] = datetime.fromtimestamp(stat.st_ctime).isoformat()
            metadata["modified"] = datetime.fromtimestamp(stat.st_mtime).isoformat()
            metadata["accessed"] = datetime.fromtimestamp(stat.st_atime).isoformat()
        except (OSError, PermissionError):
            pass

        metadata["extension"] = ext
        metadata["parent_dir"] = filepath.parent.name

        # Type-specific metadata
        if ext in self.IMAGE_EXTS:
            metadata.update(self._extract_image_metadata(filepath))
        elif ext in self.VIDEO_EXTS:
            metadata.update(self._extract_video_metadata(filepath))
        elif ext in self.AUDIO_EXTS:
            metadata.update(self._extract_audio_metadata(filepath))
        elif ext in self.DOC_EXTS:
            metadata.update(self._extract_document_metadata(filepath))
        elif ext in self.ARCHIVE_EXTS:
            metadata.update(self._extract_archive_metadata(filepath))

        return metadata

    def _extract_image_metadata(self, filepath: Path) -> dict:
        """Extract image metadata using PIL."""
        meta = {}
        try:
            from PIL import Image
            from PIL.ExifTags import Base as ExifBase

            with Image.open(filepath) as img:
                meta["width"] = img.width
                meta["height"] = img.height
                meta["format"] = img.format
                meta["mode"] = img.mode

                exif = img._getexif() if hasattr(img, "_getexif") else None
                if exif:
                    for tag_id, value in exif.items():
                        tag = ExifBase(tag_id).name if hasattr(ExifBase, tag_id) else str(tag_id)
                        if tag in ("DateTimeOriginal", "DateTimeDigitized", "Make", "Model",
                                    "GPSInfo", "ExposureTime", "FNumber", "ISOSpeedRatings",
                                    "FocalLength", "LensModel"):
                            # Clean up EXIF values — strip null bytes and whitespace
                            if isinstance(value, bytes):
                                value = value.decode("ascii", errors="ignore").replace("\x00", "").strip()
                            elif isinstance(value, str):
                                value = value.replace("\x00", "").strip()
                            meta[tag] = str(value) if not isinstance(value, (str, int, float)) else value

                    # Parse GPS data into lat/lon
                    gps_data = self._parse_gps(exif)
                    if gps_data:
                        meta["GPSLatitude"] = gps_data[0]
                        meta["GPSLongitude"] = gps_data[1]
        except Exception:
            pass
        return meta

    @staticmethod
    def _parse_gps(exif: dict) -> tuple[float, float] | None:
        """Parse EXIF GPSInfo into (latitude, longitude) decimals."""
        try:
            from PIL.ExifTags import Base as ExifBase
            gps_id = None
            for tag_id, _ in exif.items():
                tag = ExifBase(tag_id).name if hasattr(ExifBase, tag_id) else str(tag_id)
                if tag == "GPSInfo":
                    gps_id = tag_id
                    break
            if gps_id is None:
                return None
            gps_raw = exif.get(gps_id)
            if not gps_raw:
                return None

            def _convert(value):
                """Convert EXIF rational to float."""
                if isinstance(value, tuple) and len(value) == 3:
                    def _ratio(v):
                        if isinstance(v, tuple) and len(v) == 2 and v[1] != 0:
                            return v[0] / v[1]
                        return float(v) if not isinstance(v, tuple) else 0.0
                    d, m, s = value
                    return _ratio(d) + _ratio(m) / 60 + _ratio(s) / 3600
                if isinstance(value, tuple) and len(value) == 2 and value[1] != 0:
                    return value[0] / value[1]
                return float(value)

            from PIL.ExifTags import Base as ExifBase
            gps_tags = {ExifBase(k).name: v for k, v in gps_raw.items()
                        if hasattr(ExifBase, k)}
            lat = _convert(gps_tags.get("GPSLatitude"))
            lon = _convert(gps_tags.get("GPSLongitude"))
            lat_ref = gps_tags.get("GPSLatitudeRef", "N")
            lon_ref = gps_tags.get("GPSLongitudeRef", "E")
            if lat_ref == "S":
                lat = -lat
            if lon_ref == "W":
                lon = -lon
            return (lat, lon)
        except Exception:
            return None

    def _extract_video_metadata(self, filepath: Path) -> dict:
        """Extract video metadata."""
        meta = {}
        # Try mutagen for video tags
        try:
            from mutagen import File as MutagenFile
            mf = MutagenFile(str(filepath))
            if mf and hasattr(mf, "info"):
                info = mf.info
                if hasattr(info, "length"):
                    meta["duration_seconds"] = round(info.length, 1)
        except Exception:
            pass
        return meta

    def _extract_audio_metadata(self, filepath: Path) -> dict:
        """Extract audio metadata using mutagen."""
        meta = {}
        try:
            from mutagen import File as MutagenFile
            mf = MutagenFile(str(filepath))
            if mf:
                if hasattr(mf, "info") and hasattr(mf.info, "length"):
                    meta["duration_seconds"] = round(mf.info.length, 1)
                if hasattr(mf, "info") and hasattr(mf.info, "bitrate"):
                    meta["bitrate"] = mf.info.bitrate

                for key, value in (mf.tags or {}).items():
                    if key in ("TIT2", "TPE1", "TALB", "TDRC", "TCON", "TPE2",
                                "title", "artist", "album", "date", "genre"):
                        meta[key] = str(value)
        except Exception:
            pass
        return meta

    def _extract_document_metadata(self, filepath: Path) -> dict:
        """Extract document metadata."""
        meta = {}
        ext = filepath.suffix.lower()

        if ext == ".pdf":
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(str(filepath))
                meta["page_count"] = doc.page_count
                if doc.metadata:
                    for key in ("title", "author", "subject", "keywords", "creator", "producer"):
                        val = doc.metadata.get(key)
                        if val:
                            meta[key] = val
                doc.close()
            except Exception:
                pass

        elif ext in (".docx", ".odt"):
            try:
                from docx import Document
                doc = Document(str(filepath))
                core_props = doc.core_properties
                for attr in ("author", "title", "subject", "created", "modified"):
                    val = getattr(core_props, attr, None)
                    if val:
                        meta[attr] = str(val)
            except Exception:
                pass

        return meta

    def _extract_archive_metadata(self, filepath: Path) -> dict:
        """Extract archive metadata."""
        meta = {}
        ext = filepath.suffix.lower()

        try:
            if ext == ".zip":
                import zipfile
                with zipfile.ZipFile(str(filepath), "r") as zf:
                    meta["file_count"] = len(zf.namelist())
                    meta["contains"] = zf.namelist()[:20]  # First 20 files
            elif ext == ".tar":
                import tarfile
                with tarfile.open(str(filepath), "r") as tf:
                    members = tf.getnames()
                    meta["file_count"] = len(members)
                    meta["contains"] = members[:20]
        except Exception:
            pass

        return meta

    def to_json(self, metadata: dict) -> str:
        """Serialize metadata to JSON string."""
        return json.dumps(metadata, default=str, ensure_ascii=False)
