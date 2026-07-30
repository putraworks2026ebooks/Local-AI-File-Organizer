"""
Multi-threaded file scanner for Local AI File Organizer.
Scans directories and collects file metadata efficiently.
"""

import os
import json
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from PySide6.QtCore import QThread, Signal


class ScanWorker(QThread):
    """Worker thread for multi-threaded directory scanning."""

    progress = Signal(int, int)          # current, total
    file_found = Signal(dict)            # file data dict
    status_update = Signal(str)          # status message
    error = Signal(str)                 # error message
    finished_scan = Signal(int, int)      # total_files, total_size

    def __init__(self, paths: list[str], config: dict, db=None):
        super().__init__()
        self.paths = paths
        self.config = config
        self.db = db
        self._cancel = False
        self._pause = False

        scan_config = config.get("scan", {})
        self.max_workers = scan_config.get("max_workers", 4)
        self.max_file_size = scan_config.get("max_file_size_mb", 512) * 1024 * 1024
        self.skip_system = scan_config.get("skip_system_folders", True)
        self.system_folders = scan_config.get("system_folders", [])
        self.whitelist = scan_config.get("whitelist", [])
        self.blacklist = scan_config.get("blacklist", [])
        self.ignore_extensions = set(
            ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            for ext in scan_config.get("ignore_extensions", [])
        )
        self.incremental = scan_config.get("incremental_indexing", True)

    def cancel(self):
        self._cancel = True

    def pause(self):
        self._pause = True

    def resume(self):
        self._pause = False

    def _should_skip(self, path: Path) -> bool:
        """Determine if a path should be skipped."""
        name = path.name

        if self.blacklist and any(name.lower() == b.lower() for b in self.blacklist):
            return True

        if self.whitelist and not any(name.lower() == w.lower() for w in self.whitelist):
            return True

        if self.skip_system and any(name.lower() in sf.lower() for sf in self.system_folders):
            return True

        return False

    def _collect_files(self) -> list[Path]:
        """Walk directories and collect all file paths."""
        all_files = []
        for scan_path in self.paths:
            self.status_update.emit(f"Collecting files from {scan_path}...")
            root = Path(scan_path)
            if not root.exists():
                self.error.emit(f"Path does not exist: {scan_path}")
                continue

            collected = 0
            for dirpath, dirnames, filenames in os.walk(root):
                if self._cancel:
                    break

                # Filter directories in-place for efficiency
                dirnames[:] = [d for d in dirnames if not self._should_skip(Path(dirpath) / d)]

                for filename in filenames:
                    if self._cancel:
                        break

                    filepath = Path(dirpath) / filename

                    ext = filepath.suffix.lower()
                    if ext in self.ignore_extensions:
                        continue

                    try:
                        size = filepath.stat().st_size
                    except (OSError, PermissionError):
                        continue

                    if size > self.max_file_size:
                        continue

                    all_files.append(filepath)
                    collected += 1
                    if collected % 5000 == 0:
                        self.status_update.emit(f"Collecting: {collected} files found...")

            self.status_update.emit(f"Collected {collected} files from {scan_path}")

        return all_files

    def _scan_file(self, filepath: Path) -> dict:
        """Scan a single file and return metadata."""
        try:
            stat = filepath.stat()
            return {
                "file_path": str(filepath),
                "file_name": filepath.name,
                "extension": filepath.suffix.lower(),
                "size_bytes": stat.st_size,
                "scanned_at": datetime.now().isoformat(),
                "metadata_json": None,
                "is_deleted": 0,
            }
        except (OSError, PermissionError) as e:
            return {
                "file_path": str(filepath),
                "file_name": filepath.name,
                "extension": filepath.suffix.lower(),
                "size_bytes": 0,
                "scanned_at": datetime.now().isoformat(),
                "metadata_json": json.dumps({"error": str(e)}),
                "is_deleted": 0,
            }

    def run(self):
        """Main scan loop."""
        self.status_update.emit("Starting scan...")
        all_files = self._collect_files()

        if self._cancel:
            self.finished_scan.emit(0, 0)
            return

        total = len(all_files)
        self.status_update.emit(f"Found {total} files. Processing...")
        self.progress.emit(0, total)

        total_size = 0
        processed = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self._scan_file, f): f for f in all_files}

            for future in as_completed(futures):
                if self._cancel:
                    break

                while self._pause:
                    self.msleep(100)

                try:
                    file_data = future.result()
                    total_size += file_data.get("size_bytes", 0)
                    self.file_found.emit(file_data)
                    processed += 1
                    self.progress.emit(processed, total)

                    if processed % 500 == 0:
                        self.status_update.emit(f"Processed {processed}/{total} files...")
                except Exception as e:
                    self.error.emit(f"Error scanning file: {e}")

        self.status_update.emit(f"Scan complete: {processed} files, {total_size} bytes")
        self.finished_scan.emit(processed, total_size)


