"""
Unit tests for the file hasher.
"""

import pytest
import tempfile
import hashlib
from pathlib import Path

from core.hasher import Hasher


@pytest.fixture
def hasher():
    return Hasher(max_workers=2)


@pytest.fixture
def temp_files():
    """Create temporary test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "file1.txt").write_text("identical content")
        (Path(tmpdir) / "file2.txt").write_text("identical content")
        (Path(tmpdir) / "file3.txt").write_text("different content")
        yield tmpdir


class TestHasher:

    def test_hash_file(self, hasher, temp_files):
        """Test hashing a single file."""
        filepath = Path(temp_files) / "file1.txt"
        result = hasher.hash_file(filepath)

        expected = hashlib.sha256(b"identical content").hexdigest()
        assert result == expected

    def test_identical_files_same_hash(self, hasher, temp_files):
        """Test that identical files produce the same hash."""
        f1 = Path(temp_files) / "file1.txt"
        f2 = Path(temp_files) / "file2.txt"
        assert hasher.hash_file(f1) == hasher.hash_file(f2)

    def test_different_files_different_hash(self, hasher, temp_files):
        """Test that different files produce different hashes."""
        f1 = Path(temp_files) / "file1.txt"
        f3 = Path(temp_files) / "file3.txt"
        assert hasher.hash_file(f1) != hasher.hash_file(f3)

    def test_hash_nonexistent_file(self, hasher):
        """Test hashing a non-existent file returns None."""
        assert hasher.hash_file("/nonexistent/file.txt") is None

    def test_hash_empty_file(self, hasher, temp_files):
        """Test hashing an empty file."""
        filepath = Path(temp_files) / "empty.txt"
        filepath.write_text("")
        result = hasher.hash_file(filepath)
        expected = hashlib.sha256(b"").hexdigest()
        assert result == expected

    def test_hash_files_batch(self, hasher, temp_files):
        """Test batch hashing multiple files."""
        paths = [
            str(Path(temp_files) / "file1.txt"),
            str(Path(temp_files) / "file2.txt"),
            str(Path(temp_files) / "file3.txt"),
        ]
        results = hasher.hash_files(paths)

        assert len(results) == 3
        assert results[paths[0]] == results[paths[1]]  # Identical files
        assert results[paths[0]] != results[paths[2]]  # Different file

    def test_quick_hash(self, hasher, temp_files):
        """Test quick hashing (partial read)."""
        filepath = Path(temp_files) / "file1.txt"
        result = hasher.quick_hash(filepath)
        assert result is not None
        assert len(result) == 64  # SHA-256 hex length

    def test_quick_hash_small_file(self, hasher, temp_files):
        """Test quick hash on a small file."""
        filepath = Path(temp_files) / "file1.txt"
        result = hasher.quick_hash(filepath, size_bytes=17)
        assert result is not None
