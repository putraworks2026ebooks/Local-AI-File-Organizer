"""
Unit tests for the database manager.
"""

import pytest
import tempfile
from pathlib import Path

from database.db_manager import DatabaseManager
from database.operations import OperationHistory, OperationType


@pytest.fixture
def db():
    """Create a temporary database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        db = DatabaseManager(db_path)
        yield db
        db.disconnect()


class TestDatabaseManager:

    def test_connection(self, db):
        """Test database connection."""
        assert db.conn is not None

    def test_schema_initialized(self, db):
        """Test that schema tables exist."""
        tables = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [t["name"] for t in tables]
        assert "files" in table_names
        assert "operations" in table_names
        assert "duplicate_groups" in table_names
        assert "settings" in table_names
        assert "custom_categories" in table_names
        assert "index_state" in table_names
        assert "operation_log" in table_names

    def test_upsert_and_get_file(self, db):
        """Test inserting and retrieving a file."""
        file_data = {
            "file_path": "/test/file.txt",
            "file_name": "file.txt",
            "extension": ".txt",
            "size_bytes": 1024,
            "sha256": "abc123",
            "category": "Documents",
        }
        db.upsert_file(file_data)

        retrieved = db.get_file_by_path("/test/file.txt")
        assert retrieved is not None
        assert retrieved["file_name"] == "file.txt"
        assert retrieved["category"] == "Documents"

    def test_upsert_update_existing(self, db):
        """Test updating an existing file record."""
        db.upsert_file({
            "file_path": "/test/file.txt",
            "file_name": "file.txt",
            "extension": ".txt",
            "size_bytes": 1024,
            "category": "Documents",
        })
        db.upsert_file({
            "file_path": "/test/file.txt",
            "file_name": "file.txt",
            "extension": ".txt",
            "size_bytes": 1024,
            "category": "Finance",
        })

        retrieved = db.get_file_by_path("/test/file.txt")
        assert retrieved["category"] == "Finance"

    def test_get_files_by_category(self, db):
        """Test retrieving files by category."""
        for i in range(5):
            db.upsert_file({
                "file_path": f"/test/doc{i}.txt",
                "file_name": f"doc{i}.txt",
                "extension": ".txt",
                "size_bytes": 100,
                "category": "Documents",
            })
        for i in range(3):
            db.upsert_file({
                "file_path": f"/test/img{i}.jpg",
                "file_name": f"img{i}.jpg",
                "extension": ".jpg",
                "size_bytes": 200,
                "category": "Pictures",
            })

        docs = db.get_files_by_category("Documents")
        pics = db.get_files_by_category("Pictures")

        assert len(docs) == 5
        assert len(pics) == 3

    def test_file_count(self, db):
        """Test file count."""
        for i in range(10):
            db.upsert_file({
                "file_path": f"/test/file{i}.txt",
                "file_name": f"file{i}.txt",
                "extension": ".txt",
                "size_bytes": 100,
            })
        assert db.get_file_count() == 10

    def test_category_stats(self, db):
        """Test category statistics."""
        db.upsert_file({
            "file_path": "/test/doc1.txt", "file_name": "doc1.txt",
            "extension": ".txt", "size_bytes": 500, "category": "Documents",
        })
        db.upsert_file({
            "file_path": "/test/doc2.txt", "file_name": "doc2.txt",
            "extension": ".txt", "size_bytes": 300, "category": "Documents",
        })
        db.upsert_file({
            "file_path": "/test/img1.jpg", "file_name": "img1.jpg",
            "extension": ".jpg", "size_bytes": 200, "category": "Pictures",
        })

        stats = db.get_category_stats()
        assert len(stats) == 2

        doc_stat = next(s for s in stats if s["category"] == "Documents")
        assert doc_stat["count"] == 2
        assert doc_stat["total_size"] == 800

    def test_search_files(self, db):
        """Test file search."""
        db.upsert_file({
            "file_path": "/docs/report.pdf", "file_name": "report.pdf",
            "extension": ".pdf", "size_bytes": 1000,
        })
        db.upsert_file({
            "file_path": "/pics/photo.jpg", "file_name": "photo.jpg",
            "extension": ".jpg", "size_bytes": 2000,
        })

        results = db.search_files("report")
        assert len(results) == 1
        assert results[0]["file_name"] == "report.pdf"

    def test_settings(self, db):
        """Test setting and getting settings."""
        db.set_setting("test_key", {"nested": "value"})
        result = db.get_setting("test_key")
        assert result == {"nested": "value"}

        db.set_setting("simple", "string_value")
        assert db.get_setting("simple") == "string_value"

        assert db.get_setting("nonexistent", "default") == "default"

    def test_custom_categories(self, db):
        """Test custom category CRUD."""
        db.add_custom_category("MyCategory", [".xyz", ".abc"], ["custom", "test"])
        cats = db.get_custom_categories()
        assert len(cats) == 1
        assert cats[0]["name"] == "MyCategory"
        assert ".xyz" in cats[0]["extensions"]

        db.delete_custom_category("MyCategory")
        assert len(db.get_custom_categories()) == 0

    def test_duplicate_groups(self, db):
        """Test duplicate group operations."""
        db.insert_duplicate_group("hash1", "/file1.txt", 1, 100, keep=True)
        db.insert_duplicate_group("hash1", "/file2.txt", 1, 100, keep=False)

        groups = db.get_duplicate_groups()
        assert len(groups) == 1
        assert groups[0]["count"] == 2

        db.clear_duplicate_groups()
        assert len(db.get_duplicate_groups()) == 0


class TestOperationHistory:

    def test_log_and_get_operations(self, db):
        """Test logging and retrieving operations."""
        history = OperationHistory(db)
        op_id = history.log_operation(
            OperationType.MOVE, "/src/file.txt",
            source_path="/src/file.txt",
            destination_path="/dest/file.txt",
            category="Documents",
        )

        ops = history.get_operations()
        assert len(ops) == 1
        assert ops[0]["id"] == op_id
        assert ops[0]["operation_type"] == "move"

    def test_undo_move(self, db, tmp_path):
        """Test undoing a move operation."""
        history = OperationHistory(db)

        # Create source file and move it
        src = tmp_path / "source.txt"
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        dest = dest_dir / "source.txt"
        src.write_text("content")
        import shutil
        shutil.move(str(src), str(dest))

        op_id = history.log_operation(
            OperationType.MOVE, str(src),
            source_path=str(src),
            destination_path=str(dest),
            category="Documents",
        )

        # Undo the move
        success, message = history.undo_operation(op_id)
        assert success is True
        assert src.exists()  # File should be back
        assert not dest.exists()  # Dest should be gone

    def test_get_stats(self, db):
        """Test operation statistics."""
        history = OperationHistory(db)
        for i in range(5):
            history.log_operation(
                OperationType.MOVE, f"/file{i}.txt",
                source_path=f"/src/file{i}.txt",
                destination_path=f"/dest/file{i}.txt",
            )

        stats = history.get_stats()
        assert stats["total_operations"] == 5
        assert stats["undone_operations"] == 0
        assert stats["pending_moves"] == 5

    def test_log_to_table(self, db):
        """Test logging to the operation log table."""
        history = OperationHistory(db)
        history.log_to_table("INFO", "Test log message", {"key": "value"})

        entries = history.get_log_entries()
        assert len(entries) == 1
        assert entries[0]["message"] == "Test log message"
