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

        # Camera maker+model combined subfolder (for images with EXIF data)
        # Path: Pictures-AI/Canon EOS_R5/2024/01/photo.jpg
        if metadata and category in ("Pictures", "Videos"):
            make = metadata.get("Make")
            model = metadata.get("Model")
            parts = []
            if make:
                make_clean = sanitize_filename(str(make).strip())
                if make_clean:
                    parts.append(make_clean)
            if model:
                model_clean = sanitize_filename(str(model).strip())
                if model_clean:
                    parts.append(model_clean)
            if parts:
                base = base / " ".join(parts)

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
            metadata["category"] = category
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

        # Write GPS data to date folders
        self._write_gps_files(metadata_map)

        self.logger.info(f"Organized {success_count}/{total} files successfully")

        # Clean up empty folders after organizing
        if self.move_empty_folders:
            self._cleanup_empty_folders(file_categories)

        return results

    def _write_gps_files(self, metadata_map: dict = None):
        """Write gps.md in each date folder with GPS coordinates and places.

        Table format: | Latitude | Longitude | File | Place |
        Place column starts as '—' and is filled by update_gps_with_ai.
        """
        if not metadata_map:
            return

        # Collect GPS data per folder
        folder_gps: dict = {}
        for file_path, meta in metadata_map.items():
            lat = meta.get("GPSLatitude")
            lon = meta.get("GPSLongitude")
            if lat is None or lon is None:
                continue
            category = meta.get("category", "Pictures")
            dest_dir = self.get_category_path(category, file_path, meta)
            # Only write gps.md in date folders (has year subfolder)
            if dest_dir.name.isdigit() or dest_dir.parent.name.isdigit():
                folder_gps.setdefault(str(dest_dir), []).append({
                    "file": Path(file_path).name,
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                })

        from datetime import datetime
        for folder_str, entries in folder_gps.items():
            folder = Path(folder_str)
            try:
                folder.mkdir(parents=True, exist_ok=True)
                gps_file = folder / "gps.md"

                # Load existing entries (merge so re-organize keeps AI place names)
                existing = {}
                if gps_file.exists():
                    for line in gps_file.read_text(encoding="utf-8").splitlines():
                        if line.startswith("| ") and "|" in line[2:]:
                            parts = [p.strip() for p in line.split("|")[1:-1]]
                            if len(parts) >= 4:
                                try:
                                    # New format: | lat | lon | file | place |
                                    # Old format: | place | lat | lon | file |
                                    # Detect: if parts[0] parses as float, it's new format
                                    lat_val = float(parts[0])
                                    lon_val = float(parts[1])
                                    fname = parts[2]
                                    place = parts[3] if parts[3] != "—" else ""
                                    existing[fname] = {
                                        "lat": lat_val, "lon": lon_val, "place": place,
                                    }
                                except (ValueError, IndexError):
                                    # Old format fallback: | place | lat | lon | file |
                                    try:
                                        existing[parts[3]] = {
                                            "lat": float(parts[1]),
                                            "lon": float(parts[2]),
                                            "place": parts[0] if parts[0] != "—" else "",
                                        }
                                    except (ValueError, IndexError):
                                        pass

                # Merge new entries (keep existing place names)
                for e in entries:
                    key = e["file"]
                    if key not in existing:
                        existing[key] = {"lat": e["lat"], "lon": e["lon"], "place": ""}

                # Write gps.md — new format: coords first, place last
                lines = ["# GPS Data", ""]
                lines.append(f"**Folder:** `{folder.name}`")
                lines.append(f"**Total photos with GPS:** {len(existing)}")
                lines.append("")
                lines.append("| Latitude | Longitude | File | Place |")
                lines.append("|----------|-----------|------|-------|")
                for fname, data in sorted(existing.items()):
                    place = data.get("place") or "—"
                    lines.append(f"| {data['lat']} | {data['lon']} | {fname} | {place} |")
                lines.append("")
                lines.append(f"---\n*Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

                gps_file.write_text("\n".join(lines), encoding="utf-8")
                self.logger.info(f"GPS data written: {gps_file} ({len(existing)} entries)")
            except Exception as e:
                self.logger.warning(f"Failed to write GPS for {folder}: {e}")

    def update_gps_with_ai(self, metadata_map: dict, ollama,
                             progress_callback: callable = None) -> int:
        """Update gps.md files with AI-generated place names.

        Uses Ollama to convert GPS coordinates into country, state, city,
        and road names. Updates the Place column (last column) in gps.md
        without touching the coordinate columns.

        Args:
            metadata_map: {file_path: metadata_dict} from organize stage.
            ollama: OllamaClient instance for AI lookups.
            progress_callback: optional callback(filename, place_name).

        Returns:
            Number of photos that got place names.
        """
        if not metadata_map or not ollama or not ollama.is_available():
            return 0

        import json as _json
        import re as _re

        # Collect GPS data per folder (same grouping as _write_gps_files)
        folder_gps: dict = {}
        for file_path, meta in metadata_map.items():
            lat = meta.get("GPSLatitude")
            lon = meta.get("GPSLongitude")
            if lat is None or lon is None:
                continue
            category = meta.get("category", "Pictures")
            dest_dir = self.get_category_path(category, file_path, meta)
            if dest_dir.name.isdigit() or dest_dir.parent.name.isdigit():
                folder_gps.setdefault(str(dest_dir), []).append({
                    "file": Path(file_path).name,
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                })

        if not folder_gps:
            return 0

        count = 0
        for folder_str, entries in folder_gps.items():
            folder = Path(folder_str)
            gps_file = folder / "gps.md"
            if not gps_file.exists():
                continue

            # Load existing entries from gps.md (new format: | lat | lon | file | place |)
            existing = {}
            if gps_file.exists():
                for line in gps_file.read_text(encoding="utf-8").splitlines():
                    if line.startswith("| ") and "|" in line[2:]:
                        parts = [p.strip() for p in line.split("|")[1:-1]]
                        if len(parts) >= 4:
                            try:
                                lat_val = float(parts[0])
                                lon_val = float(parts[1])
                                fname = parts[2]
                                place = parts[3] if parts[3] != "—" else ""
                                existing[fname] = {
                                    "lat": lat_val, "lon": lon_val, "place": place,
                                }
                            except (ValueError, IndexError):
                                # Old format fallback: | place | lat | lon | file |
                                try:
                                    existing[parts[3]] = {
                                        "lat": float(parts[1]),
                                        "lon": float(parts[2]),
                                        "place": parts[0] if parts[0] != "—" else "",
                                    }
                                except (ValueError, IndexError):
                                    pass

            # Ask Ollama for place names for entries that don't have one
            for e in entries:
                fname = e["file"]
                if fname not in existing:
                    existing[fname] = {"lat": e["lat"], "lon": e["lon"], "place": ""}

                entry = existing[fname]
                if entry.get("place"):
                    continue  # Already has a place name

                # Ask Ollama: given lat/lon, what country, state, city, road?
                json_template = '{"country": "<country>", "state": "<state>", "city": "<city>", "road": "<road>"}'
                prompt = (
                    f"Given the GPS coordinates latitude {entry['lat']}, longitude {entry['lon']}, "
                    f"what is the country, state/province, city, and nearest road or area name? "
                    f"Return JSON only: {json_template}"
                )
                messages = [
                    {"role": "system", "content": "You are a geocoding assistant. Given GPS coordinates, return the country, state/province, city, and nearest road or area name. Return only valid JSON with keys: country, state, city, road."},
                    {"role": "user", "content": prompt},
                ]

                try:
                    response = ollama.chat(messages)
                    if response:
                        # Strip markdown code fences if present
                        cleaned = response.strip()
                        if cleaned.startswith("```"):
                            # Remove ```json or ``` wrapper
                            cleaned = _re.sub(r"^```(?:json)?\s*", "", cleaned)
                            cleaned = _re.sub(r"\s*```$", "", cleaned)
                            cleaned = cleaned.strip()
                        # Try to find JSON object in the response
                        json_match = _re.search(r"\{[^{}]*\}", cleaned)
                        if json_match:
                            cleaned = json_match.group(0)

                        result = _json.loads(cleaned)
                        # Build place name from components
                        place_parts = []
                        for key in ("country", "state", "city", "road"):
                            val = result.get(key, "").strip()
                            if val and val.lower() not in ("unknown", "n/a", "none", "null"):
                                place_parts.append(val)
                        place = ", ".join(place_parts) if place_parts else ""
                        if place:
                            entry["place"] = place
                            count += 1
                            if progress_callback:
                                progress_callback(fname, place)
                        else:
                            self.logger.warning(f"AI returned empty place for {fname}: {response[:200]}")
                    else:
                        self.logger.warning(f"AI returned empty response for {fname}")
                except _json.JSONDecodeError as e:
                    self.logger.warning(f"AI GPS JSON parse failed for {fname}: {e} — response: {response[:200] if response else 'None'}")
                except Exception as e:
                    self.logger.warning(f"AI GPS lookup failed for {fname}: {e}")

            # Rewrite gps.md with place names (new format: coords first, place last)
            from datetime import datetime
            lines = ["# GPS Data", ""]
            lines.append(f"**Folder:** `{folder.name}`")
            lines.append(f"**Total photos with GPS:** {len(existing)}")
            lines.append("")
            lines.append("| Latitude | Longitude | File | Place |")
            lines.append("|----------|-----------|------|-------|")
            for fname, data in sorted(existing.items()):
                place = data.get("place") or "—"
                lines.append(f"| {data['lat']} | {data['lon']} | {fname} | {place} |")
            lines.append("")
            lines.append(f"---\n*Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

            try:
                gps_file.write_text("\n".join(lines), encoding="utf-8")
                self.logger.info(f"GPS AI update written: {gps_file} ({count} places added)")
            except Exception as e:
                self.logger.warning(f"Failed to write GPS AI update for {folder}: {e}")

        return count

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
