"""
Utility helper functions for Local AI File Organizer.
"""

import os
import re
import shutil
import json
from pathlib import Path
from datetime import datetime
from typing import Optional


def format_file_size(size_bytes: int) -> str:
    """Format bytes into human-readable string."""
    if size_bytes == 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    size = float(size_bytes)
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    return f"{size:.1f} {units[i]}"


def get_file_hash(filepath: Path | str, chunk_size: int = 8192) -> Optional[str]:
    """Get SHA-256 hash of a file. Returns None on error."""
    import hashlib
    try:
        hasher = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(chunk_size):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (OSError, PermissionError):
        return None


def is_system_folder(path: Path | str, system_folders: list[str]) -> bool:
    """Check if a path is within a system folder."""
    parts = Path(path).parts
    for folder in system_folders:
        if folder.lower() in [p.lower() for p in parts]:
            return True
    return False


def sanitize_filename(filename: str) -> str:
    """Remove invalid characters from a filename for Windows."""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, "_")
    return filename.strip().rstrip(".")


def get_unique_filename(dest: Path, filename: str) -> str:
    """Generate a unique filename if destination already exists."""
    if not (dest / filename).exists():
        return filename
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 1
    while (dest / f"{stem}_{counter}{suffix}").exists():
        counter += 1
    return f"{stem}_{counter}{suffix}"


def safe_move_file(src: Path, dest_dir: Path, overwrite: bool = False) -> tuple[bool, str]:
    """
    Safely move a file, handling conflicts.
    Returns (success, destination_path_or_error_message).
    """
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        filename = src.name

        if (dest_dir / filename).exists():
            if overwrite:
                filename = get_unique_filename(dest_dir, filename)
            else:
                filename = get_unique_filename(dest_dir, filename)

        dest_path = dest_dir / filename
        shutil.move(str(src), str(dest_path))
        return True, str(dest_path)
    except (OSError, PermissionError, shutil.Error) as e:
        return False, str(e)


def get_photo_date(filepath: Path) -> Optional[datetime]:
    """Extract date from photo metadata (EXIF) or filename."""
    # Try EXIF first
    try:
        from PIL import Image
        from PIL.ExifTags import Base as ExifBase

        with Image.open(filepath) as img:
            exif = img._getexif()
            if exif:
                for tag_id, value in exif.items():
                    if tag_id == ExifBase.DateTimeOriginal:
                        return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass

    # Try filename patterns
    name = filepath.stem
    patterns = [
        r"(\d{4})[_-](\d{2})[_-](\d{2})",
        r"IMG_(\d{4})(\d{2})(\d{2})",
        r"(\d{4})(\d{2})(\d{2})_",
    ]
    for pattern in patterns:
        match = re.search(pattern, name)
        if match:
            try:
                year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                if 1990 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
                    return datetime(year, month, day)
            except (ValueError, IndexError):
                continue

    # Fall back to file modification time
    try:
        return datetime.fromtimestamp(filepath.stat().st_mtime)
    except OSError:
        return None


def get_disk_usage(path: Path | str) -> dict:
    """Get disk usage statistics for a path."""
    total, used, free = shutil.disk_usage(str(path))
    return {
        "total": total,
        "used": used,
        "free": free,
        "percent_used": round((used / total) * 100, 1) if total > 0 else 0,
    }


def format_duration(seconds: float) -> str:
    """Format seconds into human-readable duration."""
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours}h {minutes}m"


def is_safe_path(path: Path, base: Path) -> bool:
    """Check if path is within the base directory (prevent path traversal)."""
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False
