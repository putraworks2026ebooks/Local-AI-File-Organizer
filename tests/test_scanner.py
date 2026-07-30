"""
Unit tests for the file scanner.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch

from core.scanner import ScanWorker


@pytest.fixture
def temp_scan_dir():
    """Create a temporary directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some test files
        (Path(tmpdir) / "test1.txt").write_text("hello")
        (Path(tmpdir) / "test2.pdf").write_text("pdf content")
        (Path(tmpdir) / "subdir").mkdir()
        (Path(tmpdir) / "subdir" / "test3.jpg").write_text("image data")
        yield tmpdir


class TestScanWorker:
    """Test the ScanWorker class."""

    def test_collect_files(self, temp_scan_dir):
        """Test file collection from a directory."""
        config = {
            "scan": {
                "max_workers": 2,
                "max_file_size_mb": 512,
                "skip_system_folders": False,
                "system_folders": [],
                "whitelist": [],
                "blacklist": [],
                "ignore_extensions": [],
                "incremental_indexing": True,
            }
        }
        worker = ScanWorker([temp_scan_dir], config)
        files = worker._collect_files()

        assert len(files) == 3
        names = [f.name for f in files]
        assert "test1.txt" in names
        assert "test2.pdf" in names
        assert "test3.jpg" in names

    def test_skip_ignored_extensions(self, temp_scan_dir):
        """Test that ignored extensions are skipped."""
        (Path(temp_scan_dir) / "ignore.tmp").write_text("ignore me")
        config = {
            "scan": {
                "max_workers": 2,
                "max_file_size_mb": 512,
                "skip_system_folders": False,
                "system_folders": [],
                "whitelist": [],
                "blacklist": [],
                "ignore_extensions": [".tmp"],
                "incremental_indexing": True,
            }
        }
        worker = ScanWorker([temp_scan_dir], config)
        files = worker._collect_files()

        names = [f.name for f in files]
        assert "ignore.tmp" not in names
        assert len(files) == 3  # Original 3 files

    def test_scan_single_file(self, temp_scan_dir):
        """Test scanning a single file returns correct metadata."""
        config = {"scan": {}}
        worker = ScanWorker([], config)
        filepath = Path(temp_scan_dir) / "test1.txt"
        result = worker._scan_file(filepath)

        assert result["file_name"] == "test1.txt"
        assert result["extension"] == ".txt"
        assert result["size_bytes"] == 5  # "hello"
        assert result["file_path"] == str(filepath)

    def test_max_file_size_filter(self, temp_scan_dir):
        """Test that files larger than max size are filtered."""
        (Path(temp_scan_dir) / "large.bin").write_bytes(b"x" * 1024)
        config = {
            "scan": {
                "max_workers": 2,
                "max_file_size_mb": 0,  # 0 MB = filter everything with content
                "skip_system_folders": False,
                "system_folders": [],
                "whitelist": [],
                "blacklist": [],
                "ignore_extensions": [],
                "incremental_indexing": True,
            }
        }
        worker = ScanWorker([temp_scan_dir], config)
        files = worker._collect_files()
        # All files with content should be filtered
        assert all(f.stat().st_size == 0 for f in files)
