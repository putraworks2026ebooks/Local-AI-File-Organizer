"""
Unit tests for the file organizer.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock

from database.db_manager import DatabaseManager
from database.operations import OperationHistory, OperationType
from core.organizer import FileOrganizer


@pytest.fixture
def temp_db():
    """Create a temporary database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")
        db = DatabaseManager(db_path)
        yield db
        db.disconnect()


@pytest.fixture
def organizer(temp_db):
    """Create an organizer with a temp database."""
    op_history = OperationHistory(temp_db)
    config = {
        "organize": {
            "output_base": "",
            "create_category_folders": True,
            "photo_organize_by_date": True,
            "duplicates_folder": "_Duplicates",
        }
    }
    return FileOrganizer(temp_db, op_history, config)


@pytest.fixture
def temp_source_dir():
    """Create temporary source files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "doc1.txt").write_text("test content")
        (Path(tmpdir) / "image1.jpg").write_text("image data")
        yield tmpdir


class TestFileOrganizer:

    def test_get_category_path(self, organizer, tmp_path):
        """Test category path generation."""
        organizer.output_base = str(tmp_path)
        path = organizer.get_category_path("Documents")
        assert path == tmp_path / "Documents"

    def test_get_category_path_with_photos(self, organizer, tmp_path):
        """Test photo path includes year/month structure."""
        organizer.output_base = str(tmp_path)
        organizer.photo_by_date = True

        # Create a test image file
        img_path = tmp_path / "source" / "photo.jpg"
        img_path.parent.mkdir()
        img_path.write_text("image")

        path = organizer.get_category_path("Pictures", str(img_path))
        # Should include year/month subdirectories
        parts = path.parts
        assert "Pictures" in parts

    def test_move_file(self, organizer, temp_source_dir, tmp_path):
        """Test moving a file to a category folder."""
        organizer.output_base = str(tmp_path / "output")
        src = Path(temp_source_dir) / "doc1.txt"

        success, message, op_id = organizer.move_file(str(src), "Documents")

        assert success is True
        assert op_id is not None
        assert Path(message).exists()
        assert not src.exists()  # File should be moved

    def test_move_file_not_found(self, organizer, tmp_path):
        """Test moving a non-existent file."""
        organizer.output_base = str(tmp_path)
        success, message, op_id = organizer.move_file("/nonexistent/file.txt", "Documents")

        assert success is False
        assert "not found" in message.lower()

    def test_move_file_creates_category_folder(self, organizer, temp_source_dir, tmp_path):
        """Test that category folders are created."""
        organizer.output_base = str(tmp_path / "output")
        src = Path(temp_source_dir) / "doc1.txt"

        organizer.move_file(str(src), "Finance")

        assert (tmp_path / "output" / "Finance").exists()

    def test_find_empty_folders(self, organizer, tmp_path):
        """Test finding empty folders."""
        (tmp_path / "empty1").mkdir()
        (tmp_path / "empty2").mkdir()
        (tmp_path / "nonempty").mkdir()
        (tmp_path / "nonempty" / "file.txt").write_text("content")

        empty = organizer.find_empty_folders(str(tmp_path))
        assert str(tmp_path / "empty1") in empty
        assert str(tmp_path / "empty2") in empty
        assert str(tmp_path / "nonempty") not in empty

    def test_find_large_files(self, organizer):
        """Test finding large files."""
        files = [
            {"file_path": "/a/small.txt", "size_bytes": 100},
            {"file_path": "/b/medium.bin", "size_bytes": 500 * 1024 * 1024},
            {"file_path": "/c/large.bin", "size_bytes": 2000 * 1024 * 1024},
        ]
        large = organizer.find_large_files(files, threshold_mb=1000)

        assert len(large) == 1
        assert large[0]["file_path"] == "/c/large.bin"

    def test_organize_files(self, organizer, temp_source_dir, tmp_path):
        """Test organizing multiple files."""
        organizer.output_base = str(tmp_path / "output")

        file_categories = {
            str(Path(temp_source_dir) / "doc1.txt"): "Documents",
            str(Path(temp_source_dir) / "image1.jpg"): "Pictures",
        }

        results = organizer.organize_files(file_categories)

        assert len(results) == 2
        assert all(r["success"] for r in results)
        assert (tmp_path / "output" / "Documents" / "doc1.txt").exists()
        assert (tmp_path / "output" / "Pictures" / "image1.jpg").exists()
