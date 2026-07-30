"""
Duplicate file finder for Local AI File Organizer.
Detects duplicates using SHA-256 hashing with multi-threaded support.
"""

from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from core.hasher import Hasher
from utils.helpers import format_file_size


class DuplicateFinder:
    """Finds duplicate files using SHA-256 hashing."""

    def __init__(self, hasher: Hasher | None = None, max_workers: int = 4):
        self.hasher = hasher or Hasher(max_workers=max_workers)
        self.duplicate_groups: list[dict] = []
        self.total_duplicates: int = 0
        self.wasted_space: int = 0

    def find_duplicates(self, files: list[dict],
                        progress_callback: Optional[Callable] = None,
                        cancel_check: Optional[Callable] = None) -> list[dict]:
        """
        Find duplicate files from a list of file records.
        Uses multi-threaded hashing for speed.
        """
        if not files:
            return []

        # Step 1: Group by size (fast pre-filter)
        size_groups = defaultdict(list)
        for f in files:
            size = f.get("size_bytes", 0)
            if size > 0:
                size_groups[size].append(f)

        # Only hash files that share a size with at least one other file
        candidates = []
        for size, group in size_groups.items():
            if len(group) > 1:
                candidates.extend(group)

        if not candidates:
            self.duplicate_groups = []
            self.total_duplicates = 0
            self.wasted_space = 0
            return []

        # Step 2: Hash all candidates in PARALLEL (not sequential)
        total = len(candidates)
        processed = 0
        hash_map = defaultdict(list)

        with ThreadPoolExecutor(max_workers=self.hasher.max_workers) as executor:
            futures = {}
            for f in candidates:
                if cancel_check and cancel_check():
                    break
                filepath = f.get("file_path", f.get("file_name", ""))
                futures[executor.submit(self.hasher.hash_file, filepath)] = f

            for future in as_completed(futures):
                if cancel_check and cancel_check():
                    break

                f = futures[future]
                try:
                    file_hash = future.result()
                    if file_hash:
                        f["sha256"] = file_hash
                        hash_map[file_hash].append(f)
                except Exception:
                    pass

                processed += 1
                if progress_callback:
                    progress_callback(processed, total)

        # Step 3: Build duplicate groups (only groups with > 1 file)
        groups = []
        group_id = 0
        total_wasted = 0
        total_dupes = 0

        for hash_val, group_files in hash_map.items():
            if len(group_files) < 2:
                continue

            group_id += 1
            group_files.sort(key=lambda x: x.get("file_path", ""))
            keep_file = group_files[0]
            duplicates = group_files[1:]

            size = keep_file.get("size_bytes", 0)
            wasted = size * len(duplicates)
            total_wasted += wasted
            total_dupes += len(duplicates)

            group_entry = {
                "group_id": group_id,
                "sha256": hash_val,
                "file_paths": [f.get("file_path", "") for f in group_files],
                "file_names": [f.get("file_name", "") for f in group_files],
                "size_bytes": size,
                "size_formatted": format_file_size(size),
                "count": len(group_files),
                "wasted_space": wasted,
                "wasted_formatted": format_file_size(wasted),
                "keep_file": keep_file.get("file_path", ""),
                "duplicates": [f.get("file_path", "") for f in duplicates],
            }
            groups.append(group_entry)

        groups.sort(key=lambda g: g["wasted_space"], reverse=True)

        self.duplicate_groups = groups
        self.total_duplicates = total_dupes
        self.wasted_space = total_wasted

        return groups

    def get_summary(self) -> dict:
        return {
            "total_groups": len(self.duplicate_groups),
            "total_duplicates": self.total_duplicates,
            "wasted_space": self.wasted_space,
            "wasted_formatted": format_file_size(self.wasted_space),
        }

    def select_duplicate_to_keep(self, group: dict, strategy: str = "oldest") -> str:
        paths = group.get("file_paths", [])
        if not paths:
            return ""

        if strategy == "first":
            return paths[0]
        elif strategy == "shortest_path":
            return min(paths, key=len)
        elif strategy == "largest_path":
            return max(paths, key=len)

        # oldest / newest require file system access
        try:
            if strategy == "oldest":
                return min(paths, key=lambda p: Path(p).stat().st_mtime)
            elif strategy == "newest":
                return max(paths, key=lambda p: Path(p).stat().st_mtime)
        except (OSError, PermissionError):
            pass

        return paths[0]
