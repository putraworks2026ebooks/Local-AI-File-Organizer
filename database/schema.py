"""
SQLite database schema for Local AI File Organizer.
"""

SCHEMA_SQL = """
-- Files table: stores scanned file information
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    file_name TEXT NOT NULL,
    extension TEXT,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    sha256 TEXT,
    category TEXT,
    subcategory TEXT,
    metadata_json TEXT,
    content_summary TEXT,
    scanned_at TEXT,
    analyzed_at TEXT,
    is_duplicate INTEGER DEFAULT 0,
    duplicate_of TEXT,
    is_deleted INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_files_sha256 ON files(sha256);
CREATE INDEX IF NOT EXISTS idx_files_category ON files(category);
CREATE INDEX IF NOT EXISTS idx_files_extension ON files(extension);
CREATE INDEX IF NOT EXISTS idx_files_path ON files(file_path);

-- Operations table: complete operation history for undo support
CREATE TABLE IF NOT EXISTS operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    file_path TEXT NOT NULL,
    source_path TEXT,
    destination_path TEXT,
    category TEXT,
    details_json TEXT,
    undone INTEGER DEFAULT 0,
    undone_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_operations_timestamp ON operations(timestamp);
CREATE INDEX IF NOT EXISTS idx_operations_undone ON operations(undone);

-- Duplicates table: tracks duplicate file groups
CREATE TABLE IF NOT EXISTS duplicate_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256 TEXT NOT NULL,
    file_path TEXT NOT NULL,
    group_id INTEGER NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    keep INTEGER DEFAULT 0,
    detected_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_dup_groups_sha256 ON duplicate_groups(sha256);
CREATE INDEX IF NOT EXISTS idx_dup_groups_group ON duplicate_groups(group_id);

-- Settings table: stores key-value application settings
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Custom categories table
CREATE TABLE IF NOT EXISTS custom_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    extensions_json TEXT,
    keywords_json TEXT,
    created_at TEXT NOT NULL
);

-- Index state table: for incremental indexing
CREATE TABLE IF NOT EXISTS index_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_path TEXT NOT NULL,
    last_scanned TEXT,
    file_count INTEGER DEFAULT 0,
    total_size INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_index_state_path ON index_state(scan_path);

-- Log table: persistent operation log
CREATE TABLE IF NOT EXISTS operation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    details_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_op_log_timestamp ON operation_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_op_log_level ON operation_log(level);
"""


def get_schema() -> str:
    """Return the full SQL schema."""
    return SCHEMA_SQL
