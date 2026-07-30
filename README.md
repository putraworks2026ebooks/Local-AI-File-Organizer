# 🗂️ Local AI File Organizer

A **completely local**, AI-powered file organizer for **Windows 10/11**. No cloud services required — all AI processing runs on your machine via a local [Ollama](https://ollama.ai) server.

![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue)
![PySide6](https://img.shields.io/badge/PySide6-6.6+-green)
![Ollama](https://img.shields.io/badge/Ollama-Local_AI-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

## ✨ Features

### Core
- **🔍 Multi-threaded scanning** — Scan entire drives or specific folders with background workers
- **👥 Duplicate detection** — Find duplicate files using SHA-256 hashing
- **🤖 AI classification** — Ollama-powered file categorization based on filename, metadata, and content
- **👁️ Preview before action** — See every proposed move before anything happens
- **✅ User approval required** — No file is ever moved without your confirmation
- **↩️ Full undo support** — Reverse any operation, anytime
- **📜 Complete operation history** — Every action is logged and traceable
- **🚫 Never deletes files** — Files are moved, never permanently deleted

### Categories
Pre-configured categories: Documents, Finance, Pictures, Videos, Music, Downloads, Android, GitHub, Projects, eBooks, Archives, Installers, Backups, Miscellaneous — plus the ability to **create custom categories**.

### Advanced
- **📄 OCR support** for scanned PDFs (via Tesseract)
- **📚 Document content classification** — reads PDF, DOCX, TXT, EPUB, and more
- **🖼️ Image classification** with EXIF metadata extraction
- **📅 Photo organization by year and month**
- **🗑️ Duplicate cleanup** with smart keep strategies
- **📂 Empty folder detection**
- **💾 Large file finder**
- **📊 Disk usage analysis**
- **🗜️ ZIP archive inspection**
- **⬇️ Automatic Downloads cleanup**

### Performance
- Multi-threaded scanning and hashing
- Background worker threads (non-blocking UI)
- Incremental indexing for large file sets
- Handles millions of files
- Responsive UI during long operations

## 📋 Requirements

### Required
| Component | Version | Purpose |
|-----------|---------|---------|
| **Python** | 3.12+ | Application runtime |
| **Ollama** | Latest | Local AI inference engine |
| **PySide6** | 6.6+ | Qt GUI framework |
| **SQLite** | Built-in | Database (bundled with Python) |

### Optional
| Component | Purpose |
|-----------|---------|
| **Tesseract OCR** | OCR for scanned PDFs |
| **Pillow (PIL)** | Image metadata extraction |
| **PyMuPDF (fitz)** | PDF text extraction |
| **python-docx** | DOCX content reading |
| **mutagen** | Audio/video metadata |

## 🚀 Quick Start

### 1. Install Ollama

Download and install from [ollama.ai](https://ollama.ai), then pull a model:

```bash
ollama pull llama3.1
```

### 2. Install Dependencies

```bash
git clone https://github.com/YOUR_USERNAME/Local-AI-File-Organizer.git
cd Local-AI-File-Organizer
pip install -r requirements.txt
```

### 3. Run the Application

```bash
python main.py
```

### 4. (Optional) Build a Windows EXE

```bash
python build/build.py
```

The EXE will be in `dist/LocalAIFileOrganizer/LocalAIFileOrganizer.exe`.

## 📖 Usage Guide

### Scanning Files
1. Go to the **Scan** tab
2. Add folders or drives to scan
3. Configure scan options (workers, max file size, skip system folders)
4. Click **Start Scan**
5. Wait for the scan to complete — progress is shown in real time

### AI Analysis
1. Go to the **Analyze** tab
2. Ensure Ollama is connected (green status indicator)
3. Select an AI model from the dropdown
4. Click **Analyze Files**
5. Review the category preview for each file
6. Categories are assigned by AI based on filename, extension, metadata, and content

### Organizing Files
1. Go to the **Organize** tab
2. Set the output destination folder
3. Review the proposed actions preview
4. Choose options (photo organization by date, create category folders)
5. Click **Organize Files** and confirm
6. Use **Undo** to reverse any moves

### Finding Duplicates
1. Go to the **Duplicates** tab
2. Click **Find Duplicates**
3. Review duplicate groups — the file to keep is highlighted
4. Choose a keep strategy (oldest, newest, shortest path, etc.)
5. Optionally move duplicates to a separate folder

### Settings
Configure in the **Settings** tab:
- Ollama server URL and model
- Scan locations and ignore rules
- Output folder and organization options
- Custom categories
- OCR settings
- Scheduling
- Theme (dark/light)

## 🏗️ Project Structure

```
Local-AI-File-Organizer/
├── main.py                      # Application entry point
├── requirements.txt             # Python dependencies
├── README.md                    # This file
├── STATUS.md                    # Project status
├── .gitignore
├── config/
│   ├── default_config.json      # Default configuration
│   └── categories.json          # Category definitions
├── core/                        # Core processing engine
│   ├── scanner.py               # Multi-threaded file scanner
│   ├── hasher.py                # SHA-256 file hasher
│   ├── ollama_client.py         # Ollama API client
│   ├── organizer.py             # File organization logic
│   ├── duplicate_finder.py      # Duplicate detection
│   ├── metadata.py              # Metadata extraction
│   ├── content_reader.py        # Document content reader
│   └── ocr.py                   # OCR for scanned PDFs
├── database/                    # SQLite database layer
│   ├── schema.py                # Database schema
│   ├── db_manager.py            # Database operations
│   └── operations.py            # Operation history + undo
├── ui/                          # PySide6 UI components
│   ├── main_window.py           # Main application window
│   ├── dashboard.py             # Dashboard with statistics
│   ├── scan_view.py             # Scan interface
│   ├── analyze_view.py          # AI analysis interface
│   ├── organize_view.py         # Organization interface
│   ├── duplicates_view.py       # Duplicate finder UI
│   ├── settings_view.py         # Settings configuration
│   ├── logs_view.py             # Log viewer
│   └── theme.py                 # Dark/light theme
├── utils/                       # Utilities
│   ├── config.py                # Configuration manager
│   ├── logger.py                # Logging system
│   └── helpers.py               # Helper functions
├── tests/                       # Unit tests
│   ├── test_scanner.py
│   ├── test_hasher.py
│   ├── test_ollama_client.py
│   ├── test_organizer.py
│   ├── test_duplicate_finder.py
│   └── test_database.py
└── build/                       # Build & packaging
    ├── build.py                 # Build script
    ├── build.spec               # PyInstaller spec
    └── instructions.md          # Packaging instructions
```

## 🗄️ Database Schema

| Table | Purpose |
|-------|---------|
| `files` | Indexed file metadata, categories, and hashes |
| `operations` | Operation history for undo support |
| `duplicate_groups` | Duplicate file group tracking |
| `settings` | Application key-value settings |
| `custom_categories` | User-defined categories |
| `index_state` | Incremental indexing state |
| `operation_log` | Persistent operation log |

## 🔒 Safety Rules

- ✅ **Never** deletes files automatically
- ✅ **Never** overwrites files (auto-renames on conflict)
- ✅ Detects and handles filename conflicts
- ✅ Requires confirmation before moving any file
- ✅ Full undo support for all operations
- ✅ Every action is logged
- ✅ System folders are skipped by default
- ✅ User-configurable whitelist/blacklist for folders

## 🎨 Themes

The application supports **Dark Mode** and **Light Mode** with smooth theme switching. Toggle via:
- Menu: View → Toggle Dark/Light Mode
- Keyboard: `Ctrl+T`
- Settings → Appearance

## 🧪 Running Tests

```bash
cd Local-AI-File-Organizer
python -m pytest tests/ -v
```

## 📦 Building from Source

See [build/instructions.md](build/instructions.md) for detailed packaging instructions.

Quick build:
```bash
python build/build.py
```

## 🔧 Configuration

Configuration is stored in `config/user_config.json` (created on first save). It merges with `config/default_config.json` defaults. Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `ollama.server_url` | `http://localhost:11434` | Ollama server URL |
| `ollama.model` | `llama3.1` | AI model name |
| `scan.max_workers` | `4` | Thread pool size |
| `scan.max_file_size_mb` | `512` | Skip files larger than this |
| `organize.output_base` | (empty) | Base output folder |
| `ui.theme` | `dark` | UI theme |

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push: `git push origin feature/amazing-feature`
5. Open a Pull Request

## 📄 License

MIT License — see LICENSE file for details.

## 🙏 Acknowledgments

- [Ollama](https://ollama.ai) — Local AI inference engine
- [PySide6](https://www.qt.io) — Qt for Python GUI framework
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) — OCR engine
- [PyMuPDF](https://pymupdf.readthedocs.io/) — PDF processing

---

**100% Local. 100% Private. 100% Offline (except Ollama).**
