"""
File organizer for Local AI File Organizer.
Handles safe file moves, category-based organization, and photo organization by date.
"""

import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

from database.db_manager import DatabaseManager
from database.operations import OperationHistory, OperationType
from utils.helpers import safe_move_file, get_unique_filename, get_photo_date, sanitize_filename
from utils.logger import get_logger


class FileOrganizer:
    """Organizes files into category folders with undo support."""

    def __init__(self, db: DatabaseManager, op_history: OperationHistory, config: dict):
        self.db = db
        self.op_history = op_history
        self.config = config
        self.logger = get_logger()

        self._load_organize_config(config)

    def _load_organize_config(self, config: dict) -> None:
        organize = config.get("organize", {})
        self.output_base = organize.get("output_base", "")
        self.create_category_folders = organize.get("create_category_folders", True)
        self.photo_by_date = organize.get("photo_organize_by_date", True)
        self.duplicates_folder = organize.get("duplicates_folder", "_Duplicates")
        # Max file size for organizing (skip super big files), 0 = no limit
        self.max_organize_size_mb = organize.get("max_organize_size_mb", 0)
        # Empty folder cleanup after organize
        self.move_empty_folders = organize.get("move_empty_folders", True)
        self.empty_folder_dest = organize.get("empty_folder_dest", "ToBeDeleted")
        # Per-category date structure: {category: "none"|"year"|"year_month"}
        self.date_structures = organize.get("date_structures", {})
        # Legacy fallback for old single-setting config
        if not self.date_structures:
            old_cats = organize.get("date_organize_categories", [])
            old_struct = organize.get("date_structure", "year_month")
            for cat in old_cats:
                self.date_structures[cat] = old_struct
            if self.photo_by_date:
                self.date_structures["Pictures"] = self.date_structures.get("Pictures", "year_month")

    def update_config(self, config: dict) -> None:
        self.config = config
        self._load_organize_config(config)

    def get_category_path(self, category: str, file_path: str = None,
                           metadata: dict = None) -> Path:
        if not self.output_base:
            return Path(file_path).parent if file_path else Path.cwd()

        base = Path(self.output_base) / (sanitize_filename(category) + "-AI")

        # Camera maker/model subfolders (for images with EXIF data)
        # Path: Pictures-AI/Canon/EOS_R5/2024/01/photo.jpg
        if metadata and category in ("Pictures", "Videos"):
            make = metadata.get("Make")
            model = metadata.get("Model")
            if make:
                make_clean = sanitize_filename(str(make).strip())
                if make_clean:
                    base = base / make_clean
            if model:
                model_clean = sanitize_filename(str(model).strip())
                if model_clean:
                    base = base / model_clean

        # Per-category date structure
        struct = self.date_structures.get(category, "none")

        if struct != "none" and file_path:
            file_date = get_photo_date(Path(file_path))
            if file_date:
                year = str(file_date.year)
                if struct == "year":
                    base = base / year
                elif struct == "year_month":
                    month = f"{file_date.month:02d}"
                    base = base / year / month

        return base

    def move_file(self, src_path: str, category: str,
                  metadata: dict = None) -> tuple[bool, str, Optional[int]]:
        """
        Move a single file to its category folder.
        Returns: (success, message, operation_id)
        """
        src = Path(src_path)
        if not src.exists():
            return False, f"Source file not found: {src_path}", None

        # Get file size BEFORE moving (source won't exist after)
        try:
            file_size = src.stat().st_size
        except (OSError, PermissionError):
            file_size = 0

        # Skip super big files if max_organize_size is set
        if self.max_organize_size_mb > 0 and file_size > self.max_organize_size_mb * 1024 * 1024:
            self.logger.info(f"Skipping large file ({file_size/1024/1024:.0f}MB): {src_path}")
            return False, f"Skipped: file too large ({file_size/1024/1024:.0f}MB)", None

        dest_dir = self.get_category_path(category, src_path, metadata)
        filename = src.name

        if (dest_dir / filename).exists():
            if str(dest_dir / filename) == str(src):
                return True, "File already in correct location", None
            filename = get_unique_filename(dest_dir, filename)

        dest_path = dest_dir / filename

        # Log the operation before moving (no auto-commit — caller batches)
        op_id = self.op_history.log_operation(
            op_type=OperationType.MOVE,
            file_path=str(src),
            source_path=str(src),
            destination_path=str(dest_path),
            category=category,
            details={"original_name": src.name, "new_name": filename},
            commit=False,
        )

        success, result = safe_move_file(src, dest_dir, overwrite=False)

        if success:
            self.logger.info(f"Moved: {src_path} → {result} (category: {category})")

            # Update database — use the size we captured BEFORE the move
            self.db.upsert_file({
                "file_path": str(result),
                "file_name": Path(result).name,
                "extension": Path(result).suffix.lower(),
                "size_bytes": file_size,
                "category": category,
                "scanned_at": datetime.now().isoformat(),
            }, commit=False)  # Batch: don't commit per file

            return True, result, op_id
        else:
            self.logger.error(f"Move failed: {src_path} → {result}")
            return False, result, op_id

    def organize_files(self, file_categories: dict[str, str],
                       metadata_map: dict = None,
                       progress_callback: callable = None) -> list[dict]:
        """Organize multiple files. Batches DB commits for performance."""
        metadata_map = metadata_map or {}
        results = []
        total = len(file_categories)
        processed = 0
        success_count = 0

        for file_path, category in file_categories.items():
            processed += 1
            metadata = metadata_map.get(file_path, {})
            success, message, op_id = self.move_file(file_path, category, metadata)

            results.append({
                "file_path": file_path,
                "category": category,
                "success": success,
                "message": message,
                "operation_id": op_id,
            })

            if success:
                success_count += 1

            # Batch commit every 50 files
            if processed % 50 == 0:
                self.db.conn.commit()

            if progress_callback:
                progress_callback(processed, total, success_count)

        # Final flush
        self.db.conn.commit()

        self.logger.info(f"Organized {success_count}/{total} files successfully")

        # Clean up empty folders after organizing
        if self.move_empty_folders:
            self._cleanup_empty_folders(file_categories)

        return results

    def _cleanup_empty_folders(self, file_categories: dict) -> None:
        """Move empty source folders to ToBeDeleted after organizing."""
        import shutil
        try:
            # Collect all parent directories of organized files
            source_dirs = set()
            for file_path in file_categories:
                source_dirs.add(Path(file_path).parent)

            # Walk up from each parent and find empty directories
            # Sort by depth (deepest first) so we don't miss nested empties
            dirs_to_check = set()
            for d in source_dirs:
                # Add the dir itself and all its ancestors up to a reasonable point
                # But only check dirs that are UNDER the scan paths, not the scan roots themselves
                current = d
                dirs_to_check.add(current)
                # Also add subdirectories that might now be empty
                for child in d.iterdir():
                    if child.is_dir():
                        dirs_to_check.add(child)

            # Check each directory recursively for empty dirs
            empty_dirs = []
            checked = set()

            def check_dir_recursive(d: Path, depth: int = 0):
                if depth > 15 or d in checked:
                    return
                checked.add(d)

                if not d.exists() or not d.is_dir():
                    return

                try:
                    children = list(d.iterdir())
                except (OSError, PermissionError):
                    return

                if not children:
                    # Directory is empty
                    empty_dirs.append(d)
                    return

                # Check children that are directories
                for child in children:
                    if child.is_dir():
                        check_dir_recursive(child, depth + 1)

            for d in dirs_to_check:
                check_dir_recursive(d)

            # Also check all parent dirs recursively for emptiness
            # Re-scan parent directories that may have become empty
            all_parents = set()
            for d in source_dirs:
                p = d
                for _ in range(15):
                    p = p.parent
                    all_parents.add(p)
                    if p == p.parent:
                        break

            # Sort deepest first
            empty_dirs.sort(key=lambda p: len(str(p)), reverse=True)

            if not empty_dirs:
                return

            # Move empty dirs to ToBeDeleted
            dest_base = Path(self.output_base) / self.empty_folder_dest

            # Skip -AI folders (they are our own output, not source folders)
            empty_dirs = [d for d in empty_dirs if not d.name.endswith("-AI")]
            dest_base.mkdir(parents=True, exist_ok=True)

            moved_count = 0
            for empty_dir in empty_dirs:
                if not empty_dir.exists():
                    continue
                # Don't move the output base itself or the scan root
                try:
                    empty_dir.relative_to(dest_base)
                    continue  # Skip if inside ToBeDeleted already
                except ValueError:
                    pass

                try:
                    dest = dest_base / empty_dir.name
                    if dest.exists():
                        dest = dest.with_name(get_unique_filename(dest_base, empty_dir.name))
                    shutil.move(str(empty_dir), str(dest))
                    moved_count += 1
                    self.logger.info(f"Moved empty folder: {empty_dir} -> {dest}")
                except (OSError, PermissionError, shutil.Error) as e:
                    self.logger.warning(f"Could not move empty folder {empty_dir}: {e}")

            if moved_count:
                self.logger.info(f"Moved {moved_count} empty folders to {dest_base}")

        except Exception as e:
            self.logger.warning(f"Empty folder cleanup error: {e}")

    def move_duplicates(self, duplicate_groups: list[dict],
                        output_base: str = None,
                        progress_callback: callable = None) -> list[dict]:
        """Move duplicate files to a dedicated duplicates folder."""
        results = []
        base = Path(output_base or self.output_base) / self.duplicates_folder
        total = sum(len(g["duplicates"]) for g in duplicate_groups)
        processed = 0

        for group in duplicate_groups:
            for dup_path in group["duplicates"]:
                processed += 1
                src = Path(dup_path)

                if not src.exists():
                    results.append({"file_path": dup_path, "success": False, "message": "File not found"})
                    continue

                filename = src.name
                if (base / filename).exists():
                    filename = get_unique_filename(base, filename)

                dest_path = base / filename

                op_id = self.op_history.log_operation(
                    op_type=OperationType.DUPLICATE_MOVE,
                    file_path=str(src),
                    source_path=str(src),
                    destination_path=str(dest_path),
                    details={"sha256": group["sha256"]},
                    commit=False,
                )

                success, result = safe_move_file(src, base, overwrite=False)
                results.append({
                    "file_path": dup_path,
                    "success": success,
                    "message": result,
                    "operation_id": op_id if success else None,
                })

                if processed % 50 == 0:
                    self.db.conn.commit()

                if progress_callback:
                    progress_callback(processed, total)

        self.db.conn.commit()
        return results

    def find_empty_folders(self, root_path: str) -> list[str]:
        """Find all empty folders within a path."""
        import os
        empty = []
        for dirpath, dirnames, filenames in os.walk(root_path):
            if not dirnames and not filenames:
                empty.append(dirpath)
        return empty

    def find_large_files(self, files: list[dict], threshold_mb: int = 1000) -> list[dict]:
        threshold = threshold_mb * 1024 * 1024
        large = [f for f in files if f.get("size_bytes", 0) > threshold]
        large.sort(key=lambda f: f.get("size_bytes", 0), reverse=True)
        return large

    def get_disk_usage_analysis(self, path: str) -> dict:
        files = self.db.get_all_files()
        category_sizes = {}

        for f in files:
            category = f.get("category", "Uncategorized")
            size = f.get("size_bytes", 0)
            category_sizes[category] = category_sizes.get(category, 0) + size

        from utils.helpers import get_disk_usage, format_file_size
        disk = get_disk_usage(path)

        return {
            "disk_total": disk["total"],
            "disk_used": disk["used"],
            "disk_free": disk["free"],
            "percent_used": disk["percent_used"],
            "by_category": {
                cat: {"size": sz, "formatted": format_file_size(sz)}
                for cat, sz in sorted(category_sizes.items(), key=lambda x: x[1], reverse=True)
            },
        }
