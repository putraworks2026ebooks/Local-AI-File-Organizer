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
                make_clean = sanitize_filename(str(make).strip().title())
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

    @staticmethod
    def _nominatim_lookup(lat: float, lon: float, timeout: int = 10) -> str:
        """Free reverse geocoding via OpenStreetMap Nominatim — no API key needed."""
        import requests as _req
        try:
            resp = _req.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"lat": lat, "lon": lon, "format": "json", "zoom": 14},
                headers={"User-Agent": "LocalAIFileOrganizer/1.0"},
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                addr = data.get("address", {})
                parts = []
                for key in ("country", "state", "city", "town", "village", "road", "suburb"):
                    val = addr.get(key, "").strip()
                    if val and val not in parts:
                        parts.append(val)
                return ", ".join(parts[:4]) if parts else ""
        except Exception:
            pass
        return ""

    @staticmethod
    def _google_geocode_lookup(lat: float, lon: float, api_key: str,
                                language: str = "en", timeout: int = 10) -> str:
        """Reverse geocoding via Google Maps Geocoding API — requires API key."""
        import requests as _req
        if not api_key:
            return ""
        try:
            resp = _req.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={
                    "latlng": f"{lat},{lon}",
                    "key": api_key,
                    "language": language,
                    "result_type": "street_address|route|neighborhood|locality|administrative_area_level_1|administrative_area_level_2|country",
                },
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if not results:
                    return ""
                # Build from address components (most specific to least)
                addr = {}
                for comp in results[0].get("address_components", []):
                    for t in comp.get("types", []):
                        if t not in addr:
                            addr[t] = comp.get("long_name", "")
                parts = []
                for key in ("route", "neighborhood", "locality",
                            "administrative_area_level_1", "country"):
                    val = addr.get(key, "").strip()
                    if val and val not in parts:
                        parts.append(val)
                return ", ".join(parts[:4]) if parts else ""
        except Exception:
            pass
        return ""

    @staticmethod
    def _bigdatacloud_lookup(lat: float, lon: float, language: str = "en",
                              timeout: int = 10) -> str:
        """Free reverse geocoding via BigDataCloud — no API key needed."""
        import requests as _req
        try:
            resp = _req.get(
                "https://api.bigdatacloud.net/data/reverse-geocode-client",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "localityLanguage": language,
                },
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                parts = []
                for key in ("locality", "city", "principalSubdivision",
                            "countryName"):
                    val = str(data.get(key, "")).strip()
                    if val and val != "None" and val not in parts:
                        parts.append(val)
                return ", ".join(parts[:4]) if parts else ""
        except Exception:
            pass
        return ""

    @staticmethod
    def _locationiq_lookup(lat: float, lon: float, api_key: str,
                            language: str = "en", timeout: int = 10) -> str:
        """Free reverse geocoding via LocationIQ (10k req/day free tier)."""
        import requests as _req
        if not api_key:
            return ""
        try:
            resp = _req.get(
                f"https://us1.locationiq.com/v1/reverse",
                params={
                    "key": api_key,
                    "lat": lat,
                    "lon": lon,
                    "format": "json",
                    "accept-language": language,
                },
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                addr = data.get("address", {})
                parts = []
                for key in ("road", "neighbourhood", "suburb", "city",
                            "town", "state", "country"):
                    val = addr.get(key, "").strip()
                    if val and val not in parts:
                        parts.append(val)
                return ", ".join(parts[:4]) if parts else ""
        except Exception:
            pass
        return ""

    @staticmethod
    def _geonames_lookup(lat: float, lon: float, username: str,
                          timeout: int = 10) -> str:
        """Free reverse geocoding via GeoNames (free account, 10k req/day)."""
        import requests as _req
        if not username:
            return ""
        try:
            resp = _req.get(
                "http://api.geonames.org/extendedFindNearbyJSON",
                params={
                    "lat": lat,
                    "lng": lon,
                    "username": username,
                },
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                geonames = data.get("geonames", [])
                if not geonames:
                    return ""
                # Build from hierarchy (street → city → state → country)
                parts = []
                for entry in geonames:
                    name = entry.get("name", "").strip()
                    if name and name not in parts:
                        parts.append(name)
                return ", ".join(parts[:4]) if parts else ""
        except Exception:
            pass
        return ""

    @staticmethod
    def _openstreetmap_lookup(lat: float, lon: float, timeout: int = 10) -> str:
        """Free reverse geocoding via OpenStreetMap Nominatim (alias)."""
        return FileOrganizer._nominatim_lookup(lat, lon, timeout)

    def _reverse_geocode(self, lat: float, lon: float,
                          provider: str = None, config: dict = None) -> str:
        """Reverse geocode using the configured provider.

        Args:
            lat, lon: GPS coordinates.
            provider: 'nominatim', 'google', 'bigdatacloud', 'locationiq',
                      'geonames', or 'ai'. If None, reads from config.
            config: app config dict. If None, uses self.config.
        """
        cfg = config or self.config
        geo_cfg = cfg.get("geocoding", {})
        prov = provider or geo_cfg.get("provider", "nominatim")
        timeout = geo_cfg.get("timeout", 10)
        language = geo_cfg.get("language", "en")

        if prov == "google":
            api_key = geo_cfg.get("google_api_key", "")
            if not api_key:
                self.logger.warning("Geocoding: Google selected but no API key")
                return ""
            return self._google_geocode_lookup(lat, lon, api_key, language, timeout)
        elif prov == "bigdatacloud":
            return self._bigdatacloud_lookup(lat, lon, language, timeout)
        elif prov == "locationiq":
            api_key = geo_cfg.get("locationiq_key", "")
            if not api_key:
                self.logger.warning("Geocoding: LocationIQ selected but no API key")
                return ""
            return self._locationiq_lookup(lat, lon, api_key, language, timeout)
        elif prov == "geonames":
            username = geo_cfg.get("geonames_user", "")
            if not username:
                self.logger.warning("Geocoding: GeoNames selected but no username")
                return ""
            return self._geonames_lookup(lat, lon, username, timeout)
        elif prov == "nominatim":
            return self._nominatim_lookup(lat, lon, timeout)
        else:
            return ""  # 'ai' handled by caller via Ollama

    def update_gps_with_ai(self, metadata_map: dict, ollama,
                             progress_callback: callable = None) -> int:
        """Update gps.md files with place names.

        Uses the configured geocoding provider (Nominatim, Google, BigDataCloud,
        or AI/Ollama) to reverse-geocode GPS coordinates.

        Reads gps.md files directly, extracts coordinates from table rows,
        and looks up country, state, city, and road for each entry that
        doesn't already have a place name.

        Args:
            metadata_map: kept for API compatibility (unused — reads gps.md directly).
            ollama: OllamaClient instance for AI lookups (only used if provider='ai').
            progress_callback: optional callback(filename, place_name).

        Returns:
            Number of photos that got place names.
        """
        if not ollama or not ollama.is_available():
            self.logger.warning("GPS AI: Ollama not available")
            return 0

        import json as _json
        import re as _re

        # Find all gps.md files under the output base directory
        output_base = self.config.get("organize", {}).get("output_base", "")
        if not output_base:
            self.logger.warning("GPS AI: no output_base configured")
            return 0

        base_path = Path(output_base)
        if not base_path.exists():
            self.logger.warning(f"GPS AI: output_base does not exist: {base_path}")
            return 0

        gps_files = list(base_path.rglob("gps.md"))
        if not gps_files:
            self.logger.warning(f"GPS AI: no gps.md files found under {base_path}")
            return 0

        self.logger.info(f"GPS AI: found {len(gps_files)} gps.md files")

        count = 0
        for gps_file in gps_files:
            self.logger.info(f"GPS AI: processing {gps_file}")
            try:
                lines_out = []
                rows_updated = 0
                rows_seen = 0

                for line in gps_file.read_text(encoding="utf-8").splitlines():
                    # Pass through non-table lines
                    if not line.startswith("|"):
                        lines_out.append(line)
                        continue

                    # Check for separator row (|---|---|...)
                    if _re.match(r"^\|[-|\s]+\|$", line):
                        lines_out.append(line)
                        continue

                    # Parse table row: | col1 | col2 | col3 | col4 |
                    parts = [p.strip() for p in line.split("|")[1:-1]]
                    if len(parts) < 4:
                        lines_out.append(line)
                        continue

                    rows_seen += 1

                    # Detect format: new = | lat | lon | file | place |
                    #                old = | place | lat | lon | file |
                    try:
                        lat_val = float(parts[0])
                        lon_val = float(parts[1])
                        fname = parts[2]
                        place_str = parts[3]
                    except (ValueError, IndexError):
                        # Old format: | place | lat | lon | file |
                        try:
                            place_str = parts[0]
                            lat_val = float(parts[1])
                            lon_val = float(parts[2])
                            fname = parts[3]
                        except (ValueError, IndexError):
                            lines_out.append(line)
                            continue

                    # Check if place is empty, em-dash, or coordinate placeholder
                    place_clean = place_str.strip()
                    if place_clean in ("\u2014", "-", ""):
                        place_clean = ""
                    # Detect coordinate placeholder like "1.3521, 103.8198"
                    if _re.match(r"^-?\d+\.\d+,\s*-?\d+\.\d+$", place_clean):
                        place_clean = ""

                    if place_clean:
                        # Already has a real place name, keep it
                        lines_out.append(f"| {lat_val} | {lon_val} | {fname} | {place_clean} |")
                        continue

                    # No place name — ask Ollama for coordinates
                    self.logger.info(f"GPS AI: asking Ollama for lat={lat_val}, lon={lon_val} ({fname})")
                    json_template = '{"country": "<country>", "state": "<state>", "city": "<city>", "road": "<road>"}'
                    prompt = (
                        f"Given the GPS coordinates latitude {lat_val}, longitude {lon_val}, "
                        f"what is the country, state/province, city, and nearest road or area name? "
                        f"Return JSON only: {json_template}"
                    )
                    messages = [
                        {"role": "system", "content": "You are a geocoding assistant. Given GPS coordinates, return the country, state/province, city, and nearest road or area name. Return only valid JSON with keys: country, state, city, road."},
                        {"role": "user", "content": prompt},
                    ]

                    new_place = ""
                    try:
                        response = ollama.chat(
                            messages,
                            use_json_format=False,
                            num_predict=500,
                        )
                        if response:
                            self.logger.info(f"GPS AI: Ollama response for {fname}: {response[:200]}")
                            # Strip markdown code fences if present
                            cleaned = response.strip()
                            if cleaned.startswith("```"):
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
                            new_place = ", ".join(place_parts) if place_parts else ""
                        else:
                            self.logger.warning(f"GPS AI: Ollama returned empty response for {fname} — trying Nominatim fallback")
                        new_place = self._nominatim_lookup(lat_val, lon_val)
                        if new_place:
                            self.logger.info(f"GPS AI: Nominatim fallback succeeded for {fname}: {new_place}")
                    except _json.JSONDecodeError as e:
                        self.logger.warning(f"GPS AI: JSON parse failed for {fname}: {e} — trying Nominatim fallback")
                        new_place = self._nominatim_lookup(lat_val, lon_val)
                        if new_place:
                            self.logger.info(f"GPS AI: Nominatim fallback for {fname}: {new_place}")
                    except Exception as e:
                        self.logger.warning(f"GPS AI: lookup failed for {fname}: {e}")

                    if new_place:
                        count += 1
                        rows_updated += 1
                        if progress_callback:
                            progress_callback(fname, new_place)
                    else:
                        new_place = "\u2014"

                    # Rebuild the row in new format: | lat | lon | file | place |
                    lines_out.append(f"| {lat_val} | {lon_val} | {fname} | {new_place} |")

                # Rewrite the gps.md file
                gps_file.write_text("\n".join(lines_out), encoding="utf-8")
                self.logger.info(f"GPS AI: updated {gps_file} ({rows_updated}/{rows_seen} rows got place names)")

            except Exception as e:
                self.logger.warning(f"GPS AI: failed to process {gps_file}: {e}")

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
