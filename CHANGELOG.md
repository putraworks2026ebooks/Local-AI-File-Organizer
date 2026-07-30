# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] — 2026-07-30

### Added

#### Core Engine
- **Multi-threaded file scanner** (`core/scanner.py`) with configurable thread pool, system folder skipping, extension filtering, and incremental indexing support
- **SHA-256 file hasher** (`core/hasher.py`) with full and quick (partial read) hashing modes for duplicate detection
- **Ollama AI client** (`core/ollama_client.py`) for local AI file classification — supports chat API, JSON response parsing, batch classification, model listing, and connection testing
- **File organizer** (`core/organizer.py`) with safe file moves, category-based folder creation, photo organization by year/month, duplicate relocation, empty folder detection, large file finder, and disk usage analysis
- **Duplicate finder** (`core/duplicate_finder.py`) using SHA-256 hashing with size-based pre-filtering, wasted space calculation, and configurable keep strategies (oldest, newest, shortest path, etc.)
- **Metadata extractor** (`core/metadata.py`) supporting images (EXIF), videos, audio (ID3 tags), documents (PDF/DOCX), and archives (ZIP/TAR)
- **Content reader** (`core/content_reader.py`) for extracting text from PDF, DOCX, ODT, RTF, EPUB, and plain text files for AI classification
- **OCR processor** (`core/ocr.py`) for scanned PDFs and images via Tesseract with configurable language and page limits

#### Database Layer
- **SQLite database** with WAL mode for concurrent access
- **7 tables**: `files`, `operations`, `duplicate_groups`, `settings`, `custom_categories`, `index_state`, `operation_log`
- **Database manager** (`database/db_manager.py`) with full CRUD, upsert, search, category statistics, duplicate group management, custom category CRUD, and incremental index state tracking
- **Operation history** (`database/operations.py`) with complete undo support — tracks all file moves, categorizations, renames, and duplicate relocations with full reversal capability

#### User Interface
- **Main application window** (`ui/main_window.py`) with tabbed interface, menu bar (File/Edit/View/Tools/Help), toolbar, status bar with progress, and comprehensive keyboard shortcuts
- **Dashboard** (`ui/dashboard.py`) with stat cards (total files, total size, categories, duplicates), category breakdown table, and AI engine status
- **Scan view** (`ui/scan_view.py`) with folder picker, scan path list, configurable options (workers, max file size, system folder skipping), live results table, and cancel support
- **Analyze view** (`ui/analyze_view.py`) with Ollama connection status, model selector, AI classification with progress, category preview table, and cancel support
- **Organize view** (`ui/organize_view.py`) with output folder selection, organization options, proposed actions preview, confirmation dialog, and undo button
- **Duplicates view** (`ui/duplicates_view.py`) with summary stats, keep strategy selector, duplicate group tree with keep/duplicate indicators, and move duplicates functionality
- **Settings view** (`ui/settings_view.py`) with 7 tabs: AI/Ollama, Scan, Organize, Categories (with custom category CRUD), Advanced (OCR, empty folders, large files, disk analysis, ZIP inspection, downloads cleanup), Scheduling, Appearance
- **Logs view** (`ui/logs_view.py`) with live log stream (filterable by level), auto-scroll, operation history table, and clear/refresh controls
- **Theme system** (`ui/theme.py`) with full dark mode and light mode QSS stylesheets, smooth toggle via menu/keyboard

#### Utilities
- **Config manager** (`utils/config.py`) with deep merge of defaults and user overrides, JSON serialization, and nested key access
- **Logger** (`utils/logger.py`) with rotating file handler, console output, real-time signal callback for UI forwarding, and log queue management
- **Helpers** (`utils/helpers.py`) including file size formatting, safe file moves with conflict resolution, unique filename generation, photo date extraction (EXIF + filename patterns), disk usage analysis, path sanitization, and duration formatting

#### Configuration
- **Default config** (`config/default_config.json`) with all settings pre-configured
- **Category definitions** (`config/categories.json`) with 14 pre-configured categories including extensions and keywords

#### Testing
- **42 unit tests** across 6 test files:
  - `test_database.py` — 11 tests (CRUD, search, settings, custom categories, duplicate groups, operation history, undo)
  - `test_duplicate_finder.py` — 7 tests (detection, no duplicates, empty files, wasted space, summary, keep strategies)
  - `test_hasher.py` — 7 tests (hashing, identical/different files, empty files, batch hashing, quick hash)
  - `test_ollama_client.py` — 7 tests (init, settings, availability, model listing, chat, classification, fallback)
  - `test_organizer.py` — 6 tests (category paths, file moves, folder creation, empty folders, large files, batch organize)
  - `test_scanner.py` — 4 tests (file collection, extension filtering, single file scan, max size filter)

#### Build System
- **PyInstaller spec** (`build/build.spec`) with all hidden imports, data files, and UPX compression
- **Build script** (`build/build.py`) with clean, install, build, and verify steps
- **Packaging instructions** (`build/instructions.md`) covering quick build, manual build, single-file EXE, icon, Tesseract OCR, distribution, and troubleshooting

#### Documentation
- **README.md** with full usage guide, project structure, database schema, safety rules, themes, test instructions, build instructions, and configuration reference
- **STATUS.md** with complete module status, feature checklist, test summary, known limitations, and roadmap

### Security
- Files are **never** automatically deleted — only moved
- Files are **never** overwritten — conflicts auto-resolved with unique filenames
- User confirmation required before any file move
- Full undo support for all operations
- Every action is logged to both database and file log
- System folders skipped by default
- User-configurable whitelist/blacklist for folders
- All processing is 100% local — no data leaves the machine (except Ollama API calls to localhost)

---

## Versioning Scheme

- **Major** (x.0.0): Breaking changes, major feature removals
- **Minor** (0.x.0): New features, backward-compatible
- **Patch** (0.0.x): Bug fixes, minor improvements

---

## Future Releases

### [1.1.0] — Planned
- Background scheduler service (Windows Task Scheduler integration)
- Real-time file watcher for auto-organize on file creation
- File preview pane (image thumbnails, document previews)
- Batch undo with selection

### [1.2.0] — Planned
- Plugin system for custom classifiers
- Category rules editor with regex support
- Network drive support with caching
- Advanced duplicate management (auto-resolve, link instead of move)

### [2.0.0] — Future
- Cloud backup integration (optional, opt-in)
- Cross-platform support (macOS, Linux)
- Multi-language UI
- Web interface for remote management
