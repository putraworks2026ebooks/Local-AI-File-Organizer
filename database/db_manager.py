"""
Database manager for Local AI File Organizer.
Handles all SQLite operations including connection management and queries.
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Any

from database.schema import get_schema


class DatabaseManager:
    """Manages SQLite database connections and operations."""

    def __init__(self, db_path: str | Path = "file_organizer.db"):
        self.db_path = str(db_path)
        self._connection: sqlite3.Connection | None = None
        self.connect()
        self.init_schema()

    def connect(self) -> None:
        """Establish database connection."""
        self._connection = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")

    def disconnect(self) -> None:
        """Close the database connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._connection is None:
            self.connect()
        return self._connection

    def init_schema(self) -> None:
        """Initialize database schema."""
        self.conn.executescript(get_schema())
        self.conn.commit()

    # --- File operations ---

    # Default values for integer columns that must not be NULL
    _FILE_DEFAULTS = {
        "is_deleted": 0,
        "is_duplicate": 0,
        "size_bytes": 0,
    }

    def upsert_file(self, file_data: dict, commit: bool = True) -> None:
        """Insert or update a file record."""
        columns = ["file_path", "file_name", "extension", "size_bytes", "sha256",
                    "category", "subcategory", "metadata_json", "content_summary",
                    "scanned_at", "analyzed_at", "is_duplicate", "duplicate_of", "is_deleted"]

        # Build values with defaults for critical integer columns
        values = []
        for c in columns:
            val = file_data.get(c)
            if val is None and c in self._FILE_DEFAULTS:
                val = self._FILE_DEFAULTS[c]
            values.append(val)

        placeholders = ", ".join(["?"] * len(columns))
        col_str = ", ".join(columns)
        updates = ", ".join([f"{c}=excluded.{c}" for c in columns if c != "file_path"])

        sql = f"""
            INSERT INTO files ({col_str}) VALUES ({placeholders})
            ON CONFLICT(file_path) DO UPDATE SET {updates}
        """
        self.conn.execute(sql, values)
        if commit:
            self.conn.commit()

    def get_file_by_path(self, path: str) -> Optional[dict]:
        """Get file record by path."""
        row = self.conn.execute(
            "SELECT * FROM files WHERE file_path = ?", (path,)
        ).fetchone()
        return dict(row) if row else None

    def get_file_by_hash(self, sha256: str) -> list[dict]:
        """Get all files with a given hash."""
        rows = self.conn.execute(
            "SELECT * FROM files WHERE sha256 = ? AND is_deleted = 0", (sha256,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_files_by_category(self, category: str) -> list[dict]:
        """Get all files in a category."""
        rows = self.conn.execute(
            "SELECT * FROM files WHERE category = ? AND is_deleted = 0 ORDER BY file_name",
            (category,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_files(self, limit: int = 0, offset: int = 0) -> list[dict]:
        """Get all non-deleted files."""
        sql = "SELECT * FROM files WHERE is_deleted = 0 ORDER BY file_name"
        if limit > 0:
            sql += f" LIMIT {limit} OFFSET {offset}"
        rows = self.conn.execute(sql).fetchall()
        return [dict(r) for r in rows]

    def get_file_count(self) -> int:
        """Get total file count."""
        return self.conn.execute(
            "SELECT COUNT(*) FROM files WHERE is_deleted = 0"
        ).fetchone()[0]

    def get_total_size(self) -> int:
        """Get total size of all indexed files."""
        return self.conn.execute(
            "SELECT COALESCE(SUM(size_bytes), 0) FROM files WHERE is_deleted = 0"
        ).fetchone()[0]

    def get_category_stats(self) -> list[dict]:
        """Get file counts and sizes per category."""
        rows = self.conn.execute("""
            SELECT category, COUNT(*) as count, COALESCE(SUM(size_bytes), 0) as total_size
            FROM files WHERE is_deleted = 0
            GROUP BY category ORDER BY count DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def search_files(self, query: str) -> list[dict]:
        """Search files by name or path."""
        pattern = f"%{query}%"
        rows = self.conn.execute(
            "SELECT * FROM files WHERE is_deleted = 0 AND (file_name LIKE ? OR file_path LIKE ?) ORDER BY file_name",
            (pattern, pattern),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_file_record(self, path: str) -> None:
        """Mark a file as deleted (soft delete)."""
        self.conn.execute(
            "UPDATE files SET is_deleted = 1 WHERE file_path = ?", (path,)
        )
        self.conn.commit()

    # --- Duplicate operations ---

    def insert_duplicate_group(self, sha256: str, file_path: str, group_id: int,
                               size_bytes: int, keep: bool = False) -> None:
        """Insert a duplicate group entry."""
        self.conn.execute(
            """INSERT INTO duplicate_groups (sha256, file_path, group_id, size_bytes, keep, detected_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (sha256, file_path, group_id, size_bytes, 1 if keep else 0,
             datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_duplicate_groups(self) -> list[dict]:
        """Get all duplicate groups."""
        rows = self.conn.execute("""
            SELECT dg.sha256, dg.group_id, dg.size_bytes,
                   GROUP_CONCAT(dg.file_path, '|||') as file_paths,
                   COUNT(*) as count
            FROM duplicate_groups dg
            GROUP BY dg.group_id
            ORDER BY dg.size_bytes DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def clear_duplicate_groups(self) -> None:
        """Clear all duplicate group records."""
        self.conn.execute("DELETE FROM duplicate_groups")
        self.conn.commit()

    # --- Settings operations ---

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting value."""
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        if row:
            try:
                return json.loads(row["value"])
            except (json.JSONDecodeError, TypeError):
                return row["value"]
        return default

    def set_setting(self, key: str, value: Any) -> None:
        """Set a setting value."""
        value_str = json.dumps(value) if not isinstance(value, str) else value
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value_str),
        )
        self.conn.commit()

    # --- Custom categories ---

    def add_custom_category(self, name: str, extensions: list[str], keywords: list[str]) -> None:
        """Add a custom category."""
        self.conn.execute(
            """INSERT INTO custom_categories (name, extensions_json, keywords_json, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET extensions_json = excluded.extensions_json,
                keywords_json = excluded.keywords_json""",
            (name, json.dumps(extensions), json.dumps(keywords),
             datetime.now().isoformat()),
        )
        self.conn.commit()

    def get_custom_categories(self) -> list[dict]:
        """Get all custom categories."""
        rows = self.conn.execute("SELECT * FROM custom_categories").fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["extensions"] = json.loads(d.get("extensions_json", "[]"))
            d["keywords"] = json.loads(d.get("keywords_json", "[]"))
            results.append(d)
        return results

    def delete_custom_category(self, name: str) -> None:
        """Delete a custom category."""
        self.conn.execute("DELETE FROM custom_categories WHERE name = ?", (name,))
        self.conn.commit()

    # --- Index state ---

    def update_index_state(self, scan_path: str, file_count: int, total_size: int) -> None:
        """Update or insert index state for a scan path."""
        self.conn.execute(
            """INSERT INTO index_state (scan_path, last_scanned, file_count, total_size)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(scan_path) DO UPDATE SET
                last_scanned = excluded.last_scanned,
                file_count = excluded.file_count,
                total_size = excluded.total_size""",
            (scan_path, datetime.now().isoformat(), file_count, total_size),
        )
        self.conn.commit()

    def get_index_state(self, scan_path: str) -> Optional[dict]:
        """Get index state for a scan path."""
        row = self.conn.execute(
            "SELECT * FROM index_state WHERE scan_path = ?", (scan_path,)
        ).fetchone()
        return dict(row) if row else None
