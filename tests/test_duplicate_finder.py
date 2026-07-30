"""
Unit tests for the duplicate finder.
"""

import pytest
import tempfile
from pathlib import Path

from core.duplicate_finder import DuplicateFinder
from core.hasher import Hasher


@pytest.fixture
def duplicate_finder():
    return DuplicateFinder(Hasher(max_workers=2))


@pytest.fixture
def temp_files():
    """Create temporary files with some duplicates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Identical files (duplicates)
        (Path(tmpdir) / "dup1.txt").write_text("identical content here")
        (Path(tmpdir) / "dup2.txt").write_text("identical content here")
        (Path(tmpdir) / "dup3.txt").write_text("identical content here")

        # Unique file
        (Path(tmpdir) / "unique.txt").write_text("totally different content")

        # Another duplicate pair
        (Path(tmpdir) / "img1.jpg").write_text("image data 123")
        (Path(tmpdir) / "img2.jpg").write_text("image data 123")

        yield tmpdir


class TestDuplicateFinder:

    def test_find_duplicates(self, duplicate_finder, temp_files):
        """Test finding duplicate files."""
        files = []
        for f in Path(temp_files).iterdir():
            files.append({
                "file_path": str(f),
                "file_name": f.name,
                "size_bytes": f.stat().st_size,
            })

        groups = duplicate_finder.find_duplicates(files)

        # Should find 2 groups: the 3 identical text files and the 2 identical images
        assert len(groups) == 2

        # One group should have 3 files, the other 2
        counts = sorted([g["count"] for g in groups])
        assert counts == [2, 3]

    def test_no_duplicates(self, duplicate_finder, tmp_path):
        """Test that unique files return no duplicates."""
        (tmp_path / "file1.txt").write_text("content 1")
        (tmp_path / "file2.txt").write_text("content 2")
        (tmp_path / "file3.txt").write_text("content 3")

        files = [
            {"file_path": str(tmp_path / "file1.txt"), "size_bytes": 9},
            {"file_path": str(tmp_path / "file2.txt"), "size_bytes": 9},
            {"file_path": str(tmp_path / "file3.txt"), "size_bytes": 9},
        ]

        groups = duplicate_finder.find_duplicates(files)
        assert len(groups) == 0

    def test_empty_input(self, duplicate_finder):
        """Test with empty file list."""
        groups = duplicate_finder.find_duplicates([])
        assert groups == []

    def test_skip_empty_files(self, duplicate_finder, tmp_path):
        """Test that empty files are skipped."""
        (tmp_path / "empty1.txt").write_text("")
        (tmp_path / "empty2.txt").write_text("")

        files = [
            {"file_path": str(tmp_path / "empty1.txt"), "size_bytes": 0},
            {"file_path": str(tmp_path / "empty2.txt"), "size_bytes": 0},
        ]

        groups = duplicate_finder.find_duplicates(files)
        assert len(groups) == 0

    def test_wasted_space_calculation(self, duplicate_finder, temp_files):
        """Test wasted space is calculated correctly."""
        files = []
        for f in Path(temp_files).iterdir():
            files.append({
                "file_path": str(f),
                "file_name": f.name,
                "size_bytes": f.stat().st_size,
            })

        duplicate_finder.find_duplicates(files)
        summary = duplicate_finder.get_summary()

        # Wasted space = (3-1)*text_size + (2-1)*image_size
        text_size = len(b"identical content here")
        img_size = len(b"image data 123")
        expected_wasted = 2 * text_size + 1 * img_size

        assert summary["wasted_space"] == expected_wasted

    def test_summary_stats(self, duplicate_finder, temp_files):
        """Test summary statistics."""
        files = []
        for f in Path(temp_files).iterdir():
            files.append({
                "file_path": str(f),
                "file_name": f.name,
                "size_bytes": f.stat().st_size,
            })

        duplicate_finder.find_duplicates(files)
        summary = duplicate_finder.get_summary()

        assert summary["total_groups"] == 2
        # 2 duplicates from text group + 1 from image group = 3 total duplicates
        assert summary["total_duplicates"] == 3

    def test_select_duplicate_to_keep(self, duplicate_finder):
        """Test keeping the first file."""
        group = {
            "file_paths": ["/a/file.txt", "/b/file.txt", "/c/file.txt"],
            "sha256": "abc123",
            "count": 3,
        }
        keep = duplicate_finder.select_duplicate_to_keep(group, "first")
        assert keep == "/a/file.txt"

    def test_select_shortest_path(self, duplicate_finder):
        """Test keeping the file with the shortest path."""
        group = {
            "file_paths": ["/very/long/path/to/file.txt", "/short/file.txt"],
            "sha256": "abc123",
            "count": 2,
        }
        keep = duplicate_finder.select_duplicate_to_keep(group, "shortest_path")
        assert keep == "/short/file.txt"
