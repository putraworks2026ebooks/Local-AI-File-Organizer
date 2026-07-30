"""
Operation history management with undo support.
Tracks all file operations and provides full undo functionality.
"""

import json
from datetime import datetime
from typing import Optional

from database.db_manager import DatabaseManager


class OperationType:
    MOVE = "move"
    CATEGORIZE = "categorize"
    RENAME = "rename"
    DUPLICATE_MOVE = "duplicate_move"
    DELETE = "delete"


class OperationHistory:
    """Manages operation history and undo functionality."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def log_operation(self, op_type: str, file_path: str,
                      source_path: Optional[str] = None,
                      destination_path: Optional[str] = None,
                      category: Optional[str] = None,
                      details: Optional[dict] = None) -> int:
        """Log an operation and return its ID."""
        timestamp = datetime.now().isoformat()
        details_json = json.dumps(details) if details else None

        cursor = self.db.conn.execute(
            """INSERT INTO operations (operation_type, timestamp, file_path,
               source_path, destination_path, category, details_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (op_type, timestamp, file_path, source_path, destination_path,
             category, details_json),
        )
        self.db.conn.commit()
        return cursor.lastrowid

    def log_to_table(self, level: str, message: str, details: Optional[dict] = None) -> None:
        """Write to the operation_log table."""
        timestamp = datetime.now().isoformat()
        details_json = json.dumps(details) if details else None
        self.db.conn.execute(
            "INSERT INTO operation_log (timestamp, level, message, details_json) VALUES (?, ?, ?, ?)",
            (timestamp, level, message, details_json),
        )
        self.db.conn.commit()

    def get_operations(self, limit: int = 100, offset: int = 0,
                       include_undone: bool = False) -> list[dict]:
        """Get operation history."""
        if include_undone:
            sql = "SELECT * FROM operations ORDER BY id DESC LIMIT ? OFFSET ?"
        else:
            sql = "SELECT * FROM operations WHERE undone = 0 ORDER BY id DESC LIMIT ? OFFSET ?"
        rows = self.db.conn.execute(sql, (limit, offset)).fetchall()
        return [dict(r) for r in rows]

    def get_undoable_operations(self) -> list[dict]:
        """Get all operations that can be undone."""
        rows = self.db.conn.execute(
            "SELECT * FROM operations WHERE undone = 0 ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_undone(self, operation_id: int) -> None:
        """Mark an operation as undone."""
        self.db.conn.execute(
            "UPDATE operations SET undone = 1, undone_at = ? WHERE id = ?",
            (datetime.now().isoformat(), operation_id),
        )
        self.db.conn.commit()

    def undo_operation(self, operation_id: int) -> tuple[bool, str]:
        """Undo a single operation. Returns (success, message)."""
        import shutil
        from pathlib import Path

        row = self.db.conn.execute(
            "SELECT * FROM operations WHERE id = ? AND undone = 0",
            (operation_id,),
        ).fetchone()

        if not row:
            return False, "Operation not found or already undone."

        op = dict(row)

        if op["operation_type"] in (OperationType.MOVE, OperationType.DUPLICATE_MOVE):
            src = op.get("source_path")
            dst = op.get("destination_path")
            if not src or not dst:
                return False, "Missing source or destination path."

            if not Path(dst).exists():
                return False, f"Destination file no longer exists: {dst}"

            try:
                Path(src).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(src))
                self.mark_undone(operation_id)
                return True, f"Moved back: {dst} → {src}"
            except (OSError, shutil.Error) as e:
                return False, f"Undo failed: {e}"

        elif op["operation_type"] == OperationType.RENAME:
            file_path = op.get("file_path")
            details = json.loads(op.get("details_json", "{}")) if op.get("details_json") else {}
            original_name = details.get("original_name")
            if not file_path or not original_name:
                return False, "Missing rename details."

            current_path = Path(file_path)
            if not current_path.exists():
                return False, f"File no longer exists: {file_path}"

            original_path = current_path.parent / original_name
            try:
                shutil.move(str(current_path), str(original_path))
                self.mark_undone(operation_id)
                return True, f"Renamed back: {current_path.name} → {original_name}"
            except (OSError, shutil.Error) as e:
                return False, f"Undo failed: {e}"

        elif op["operation_type"] == OperationType.CATEGORIZE:
            file_path = op.get("file_path")
            if file_path:
                self.db.conn.execute(
                    "UPDATE files SET category = NULL WHERE file_path = ?",
                    (file_path,),
                )
                self.db.conn.commit()
            self.mark_undone(operation_id)
            return True, f"Uncategorized: {op.get('file_path', 'unknown')}"

        return False, f"Unknown operation type: {op['operation_type']}"

    def undo_last(self) -> tuple[bool, str]:
        """Undo the most recent undoable operation."""
        ops = self.get_undoable_operations()
        if not ops:
            return False, "No operations to undo."
        return self.undo_operation(ops[0]["id"])

    def undo_all(self) -> list[tuple[bool, str]]:
        """Undo all undoable operations (in reverse order)."""
        results = []
        ops = self.get_undoable_operations()
        for op in ops:
            results.append(self.undo_operation(op["id"]))
        return results

    def get_log_entries(self, limit: int = 200, offset: int = 0) -> list[dict]:
        """Get operation log entries."""
        rows = self.db.conn.execute(
            "SELECT * FROM operation_log ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        """Get operation history statistics."""
        total = self.db.conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
        undone = self.db.conn.execute(
            "SELECT COUNT(*) FROM operations WHERE undone = 1"
        ).fetchone()[0]
        move_ops = self.db.conn.execute(
            "SELECT COUNT(*) FROM operations WHERE operation_type = 'move' AND undone = 0"
        ).fetchone()[0]
        return {
            "total_operations": total,
            "undone_operations": undone,
            "pending_moves": move_ops,
        }
