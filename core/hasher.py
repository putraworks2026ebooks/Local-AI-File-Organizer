"""
SHA-256 file hasher for duplicate detection.
Supports incremental hashing for large files and multi-threaded operation.
"""

import hashlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional


class Hasher:
    """Computes SHA-256 hashes for files."""

    CHUNK_SIZE = 65536  # 64KB chunks

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers

    def hash_file(self, filepath: Path | str) -> Optional[str]:
        """Compute SHA-256 hash of a file. Returns None on error."""
        filepath = Path(filepath)
        try:
            sha256 = hashlib.sha256()
            with open(filepath, "rb") as f:
                while True:
                    chunk = f.read(self.CHUNK_SIZE)
                    if not chunk:
                        break
                    sha256.update(chunk)
            return sha256.hexdigest()
        except (OSError, PermissionError):
            return None

    def hash_files(self, filepaths: list[str | Path],
                   progress_callback: Optional[callable] = None) -> dict[str, str]:
        """Hash multiple files in parallel. Returns {filepath: hash}."""
        results = {}
        total = len(filepaths)
        processed = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self.hash_file, Path(fp)): str(fp)
                for fp in filepaths
            }
            for future in as_completed(futures):
                filepath = futures[future]
                try:
                    hash_val = future.result()
                    if hash_val:
                        results[filepath] = hash_val
                except Exception:
                    pass

                processed += 1
                if progress_callback:
                    progress_callback(processed, total)

        return results

    @staticmethod
    def quick_hash(filepath: Path | str, size_bytes: int = None) -> Optional[str]:
        """Quick hash using first and last 1KB + file size. For fast duplicate pre-check."""
        filepath = Path(filepath)
        try:
            if size_bytes is None:
                size_bytes = filepath.stat().st_size

            if size_bytes == 0:
                return hashlib.sha256(b"").hexdigest()

            sha256 = hashlib.sha256()
            with open(filepath, "rb") as f:
                # First 1KB
                head = f.read(1024)
                sha256.update(head)

                if size_bytes > 2048:
                    # Last 1KB
                    f.seek(-1024, 2)
                    tail = f.read(1024)
                    sha256.update(tail)

                # Include size in quick hash
                sha256.update(str(size_bytes).encode())

            return sha256.hexdigest()
        except (OSError, PermissionError):
            return None
