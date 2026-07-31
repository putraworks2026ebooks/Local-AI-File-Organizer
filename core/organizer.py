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
        # Date-organize settings for any category
        self.date_organize_categories = organize.get("date_organize_categories", ["Pictures"])
        self.date_structure = organize.get("date_structure", "year_month")  # "year_month" or "year"

    def update_config(self, config: dict) -> None:
        self.config = config
        self._load_organize_config(config)

    def get_category_path(self, category: str, file_path: str = None,
                           metadata: dict = None) -> Path:
        if not self.output_base:
            return Path(file_path).parent if file_path else Path.cwd()

        base = Path(self.output_base) / sanitize_filename(category)

        # Build effective list of categories to date-organize
        effective_date_cats = set(self.date_organize_categories)
        if self.photo_by_date:
            effective_date_cats.add("Pictures")
        else:
            effective_date_cats.discard("Pictures")

        should_date_organize = category in effective_date_cats

        if should_date_organize and file_path:
            file_date = get_photo_date(Path(file_path))
            if file_date:
                year = str(file_date.year)
                if self.date_structure == "year":
                    base = base / year
                else:
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
        return results

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
