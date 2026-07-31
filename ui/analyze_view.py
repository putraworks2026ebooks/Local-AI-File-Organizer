"""
Analyze view for Local AI File Organizer.
Uses Ollama to classify files into categories with preview before organizing.
Falls back to rule-based classification when Ollama is not available.
"""

import json
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox, QMessageBox,
    QCheckBox, QComboBox, QTextEdit, QSplitter, QTabWidget
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer

from core.ollama_client import OllamaClient
from core.metadata import MetadataExtractor
from core.content_reader import ContentReader
from core.ocr import OCRProcessor
from database.db_manager import DatabaseManager
from utils.logger import get_logger


class RuleBasedClassifier:
    """Fallback classifier that uses file extensions and keywords when Ollama is not available."""

    # Extension -> category mapping (must match config/categories.json names)
    EXTENSION_MAP = {
        # Documents
        ".pdf": "Documents", ".doc": "Documents", ".docx": "Documents",
        ".txt": "Documents", ".rtf": "Documents", ".odt": "Documents",
        ".pages": "Documents", ".md": "Documents", ".tex": "Documents", ".wps": "Documents",
        # Finance (spreadsheets, financial)
        ".xls": "Finance", ".xlsx": "Finance", ".csv": "Finance",
        ".qfx": "Finance", ".qbo": "Finance", ".ofx": "Finance",
        ".tax": "Finance", ".money": "Finance",
        # Pictures (images, photos)
        ".jpg": "Pictures", ".jpeg": "Pictures", ".png": "Pictures", ".gif": "Pictures",
        ".bmp": "Pictures", ".tiff": "Pictures", ".tif": "Pictures", ".svg": "Pictures",
        ".webp": "Pictures", ".heic": "Pictures", ".raw": "Pictures", ".ico": "Pictures",
        ".cr2": "Pictures", ".nef": "Pictures", ".arw": "Pictures", ".dng": "Pictures",
        # Videos
        ".mp4": "Videos", ".avi": "Videos", ".mkv": "Videos", ".mov": "Videos",
        ".wmv": "Videos", ".flv": "Videos", ".webm": "Videos", ".m4v": "Videos",
        ".mpg": "Videos", ".mpeg": "Videos", ".3gp": "Videos", ".ts": "Videos",
        ".vob": "Videos",
        # Music (audio)
        ".mp3": "Music", ".wav": "Music", ".flac": "Music", ".aac": "Music",
        ".ogg": "Music", ".m4a": "Music", ".wma": "Music", ".alac": "Music",
        ".aiff": "Music", ".opus": "Music",
        # Downloads
        ".crdownload": "Downloads", ".part": "Downloads", ".download": "Downloads",
        # Android
        ".apk": "Android", ".xapk": "Android", ".apks": "Android",
        ".aab": "Android", ".dex": "Android",
        # Projects (code, scripts)
        ".py": "Projects", ".js": "Projects", ".ts": "Projects", ".html": "Projects",
        ".css": "Projects", ".scss": "Projects", ".less": "Projects", ".vue": "Projects",
        ".jsx": "Projects", ".tsx": "Projects",
        ".java": "Projects", ".cpp": "Projects", ".c": "Projects", ".h": "Projects",
        ".hpp": "Projects", ".cs": "Projects", ".go": "Projects", ".rs": "Projects",
        ".rb": "Projects", ".php": "Projects", ".swift": "Projects", ".kt": "Projects",
        ".dart": "Projects", ".lua": "Projects", ".r": "Projects",
        ".sh": "Projects", ".bat": "Projects", ".ps1": "Projects", ".sql": "Projects",
        ".json": "Projects", ".xml": "Projects", ".yaml": "Projects", ".yml": "Projects",
        ".toml": "Projects", ".ini": "Projects", ".cfg": "Projects", ".conf": "Projects",
        # eBooks
        ".epub": "eBooks", ".mobi": "eBooks", ".azw": "eBooks", ".azw3": "eBooks",
        ".kf8": "eBooks", ".pdb": "eBooks", ".fb2": "eBooks", ".lit": "eBooks", ".lrf": "eBooks",
        # Archives
        ".zip": "Archives", ".rar": "Archives", ".7z": "Archives", ".tar": "Archives",
        ".gz": "Archives", ".bz2": "Archives", ".xz": "Archives", ".lzma": "Archives",
        ".cab": "Archives", ".iso": "Archives", ".dmg": "Archives", ".pkg": "Archives",
        ".tgz": "Archives",
        # Installers
        ".exe": "Installers", ".msi": "Installers", ".msp": "Installers", ".msu": "Installers",
        ".appx": "Installers", ".deb": "Installers", ".rpm": "Installers", ".snap": "Installers",
        ".flatpak": "Installers",
        # Backups
        ".bak": "Backups", ".old": "Backups", ".orig": "Backups", ".backup": "Backups",
        ".dump": "Backups", ".save": "Backups", ".swp": "Backups", ".tmp": "Backups",
    }

    def __init__(self, categories: list[str]):
        self.categories = [c for c in categories if c != "Miscellaneous"]

    def classify(self, file_data: dict, content_summary: str = None) -> str:
        """Classify a file based on its extension."""
        ext = file_data.get("extension", "").lower()
        category = self.EXTENSION_MAP.get(ext)
        if category and category in self.categories:
            return category
        return "Miscellaneous"


class AnalyzeWorker(QThread):
    """Worker thread for AI analysis (or rule-based fallback)."""

    progress = Signal(int, int)
    file_analyzed = Signal(str, str)  # file_path, category
    status_update = Signal(str)
    error = Signal(str)
    finished_analysis = Signal(dict)  # {file_path: category}

    def __init__(self, files: list[dict], categories: list[str],
                 ollama: OllamaClient, metadata_extractor: MetadataExtractor,
                 content_reader: ContentReader, ocr: OCRProcessor, db: DatabaseManager,
                 use_ai: bool = True):
        super().__init__()
        self.files = files
        self.categories = categories
        self.ollama = ollama
        self.metadata_extractor = metadata_extractor
        self.content_reader = content_reader
        self.ocr = ocr
        self.db = db
        self.use_ai = use_ai and ollama.is_available()
        self._cancel = False
        self.logger = get_logger()

    def cancel(self):
        self._cancel = True

    def run(self):
        """Run AI or rule-based analysis on all files."""
        results = {}
        total = len(self.files)
        processed = 0
        errors = 0

        if self.use_ai:
            self.status_update.emit(f"Analyzing {total} files with {self.ollama.model}...")
        else:
            self.status_update.emit(f"Analyzing {total} files (rule-based, no AI)...")

        # Use rule-based classifier as fallback
        # Always create rule_classifier — used as fallback even in AI mode
        rule_classifier = RuleBasedClassifier(self.categories)

        for file_data in self.files:
            if self._cancel:
                break

            file_path = file_data.get("file_path", "")
            file_name = file_data.get("file_name", "unknown")

            try:
                if self.use_ai:
                    # Extract metadata
                    metadata = {}
                    try:
                        metadata = self.metadata_extractor.extract(file_path)
                    except Exception:
                        pass

                    # Read content for documents
                    content_summary = None
                    try:
                        content_summary = self.content_reader.read_summary(file_path, max_length=500)
                    except Exception:
                        pass

                    # OCR for scanned PDFs (if enabled)
                    if not content_summary and self.ocr.is_available():
                        try:
                            content_summary = self.ocr.extract_text(file_path, max_length=500)
                        except Exception:
                            pass

                    # Classify with Ollama
                    file_info = {
                        "file_name": file_name,
                        "extension": file_data.get("extension", ""),
                        "metadata": metadata,
                    }

                    category = self.ollama.classify_file(file_info, self.categories, content_summary)

                    # If AI fails or returns Miscellaneous, try rule-based as fallback
                    if not category or category == "Miscellaneous":
                        rule_category = rule_classifier.classify(file_data)
                        if rule_category and rule_category != "Miscellaneous":
                            category = rule_category

                    if category:
                        results[file_path] = category
                        self.file_analyzed.emit(file_path, category)

                        # Update database
                        file_data["category"] = category
                        file_data["metadata_json"] = json.dumps(metadata, default=str) if metadata else None
                        file_data["content_summary"] = content_summary
                        file_data["analyzed_at"] = json.dumps({"timestamp": None})
                        self.db.upsert_file(file_data)
                    else:
                        results[file_path] = "Miscellaneous"
                        errors += 1
                else:
                    # Rule-based fallback
                    category = rule_classifier.classify(file_data)
                    results[file_path] = category
                    self.file_analyzed.emit(file_path, category)

                    file_data["category"] = category
                    file_data["analyzed_at"] = json.dumps({"timestamp": None, "method": "rule-based"})
                    self.db.upsert_file(file_data)

            except Exception as e:
                self.logger.error(f"Analysis error for {file_name}: {e}")
                results[file_path] = "Miscellaneous"
                errors += 1

            processed += 1
            self.progress.emit(processed, total)

            if processed % 100 == 0:
                method = "AI" if self.use_ai else "rule-based"
                self.status_update.emit(f"Analyzed {processed}/{total} files ({errors} errors) [{method}]")

        method = "AI" if self.use_ai else "rule-based"
        self.status_update.emit(f"Analysis complete: {processed} files, {errors} errors [{method}]")
        self.finished_analysis.emit(results)


class AnalyzeView(QWidget):
    """Analyze interface for AI file classification."""

    analysis_complete = Signal(dict)

    def __init__(self, config: dict, db: DatabaseManager, ollama: OllamaClient,
                 metadata_extractor: MetadataExtractor, content_reader: ContentReader,
                 ocr: OCRProcessor):
        super().__init__()
        self.config = config
        self.db = db
        self.ollama = ollama
        self.metadata_extractor = metadata_extractor
        self.content_reader = content_reader
        self.ocr = ocr
        self.files: list[dict] = []
        self.analyze_worker = None
        self.logger = get_logger()
        self._init_ui()

        # Check AI status on init (deferred to avoid blocking UI)
        QTimer.singleShot(500, self._check_ai_status)

    def _init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("📂 File Analysis")
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)

        # AI status + mode toggle
        status_group = QGroupBox("Classification Mode")
        status_layout = QHBoxLayout()

        self.ai_status = QLabel("Checking...")
        self.ai_status.setStyleSheet("font-weight: bold;")
        status_layout.addWidget(self.ai_status)

        status_layout.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(200)
        status_layout.addWidget(self.model_combo)

        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self._check_ai_status)
        status_layout.addWidget(refresh_btn)

        status_layout.addStretch()

        # Mode toggle: AI vs Rule-based
        self.ai_mode_toggle = QCheckBox("Use AI (requires Ollama)")
        self.ai_mode_toggle.setToolTip(
            "Checked: use Ollama AI for smart classification.\n"
            "Unchecked: use rule-based classification by file extension (no AI needed)."
        )
        self.ai_mode_toggle.setChecked(self.config.get("analyze", {}).get("use_ai", True))
        self.ai_mode_toggle.toggled.connect(self._on_mode_toggled)
        status_layout.addWidget(self.ai_mode_toggle)

        status_layout.addWidget(QLabel("│"))
        # Processing mode: bulk vs 1-by-1
        self.bulk_mode_check = QCheckBox("Bulk mode")
        self.bulk_mode_check.setToolTip(
            "Bulk: process all files at once.\n"
            "1-by-1: show each file in the table as it is processed."
        )
        self.bulk_mode_check.setChecked(True)
        status_layout.addWidget(self.bulk_mode_check)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Info banner for no-AI mode
        self.no_ai_banner = QLabel(
            "ℹ️ Rule-based mode active. Files are classified by extension — no AI needed.\n"
            "Enable 'Use AI' above and install Ollama for smarter content-based classification."
        )
        self.no_ai_banner.setStyleSheet(
            "background-color: #fff3cd; color: #856404; padding: 10px; "
            "border-radius: 5px; border: 1px solid #ffeaa7;"
        )
        self.no_ai_banner.setWordWrap(True)
        self.no_ai_banner.setVisible(False)
        layout.addWidget(self.no_ai_banner)

        # Category preview
        preview_group = QGroupBox("Category Preview")
        preview_layout = QVBoxLayout()

        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(4)
        self.preview_table.setHorizontalHeaderLabels(["File", "Path", "Category", "Confidence"])
        self.preview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.preview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.preview_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.preview_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.preview_table.setAlternatingRowColors(True)
        preview_layout.addWidget(self.preview_table)

        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)

        # Controls
        ctrl_layout = QHBoxLayout()

        self.analyze_btn = QPushButton("🤖 Analyze Files")
        self.analyze_btn.setObjectName("primary")
        self.analyze_btn.setStyleSheet("padding: 12px 24px; font-size: 14px;")
        self.analyze_btn.clicked.connect(self._start_analysis)
        ctrl_layout.addWidget(self.analyze_btn)

        self.cancel_btn = QPushButton("⏹️ Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_analysis)
        ctrl_layout.addWidget(self.cancel_btn)

        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

    def set_files(self, files: list[dict]):
        """Set the files to analyze."""
        self.files = files
        self.status_label.setText(f"{len(files)} files ready for analysis")
        self.preview_table.setRowCount(0)

    def _on_mode_toggled(self, checked: bool):
        """Handle AI mode toggle."""
        if checked and not self.ollama.is_available():
            # User wants AI but Ollama isn't running — uncheck and inform
            self.ai_mode_toggle.setChecked(False)
            QMessageBox.information(
                self, "Ollama Not Available",
                "Ollama is not running. Please install and start Ollama first.\n\n"
                "Continuing in rule-based mode.",
            )
            return

        if checked:
            self.no_ai_banner.setVisible(False)
            self.analyze_btn.setText("🤖 Analyze Files")
        else:
            self.no_ai_banner.setVisible(True)
            self.analyze_btn.setText("📁 Analyze Files")

    def _check_ai_status(self):
        """Check Ollama availability and populate models."""
        if self.ollama.is_available():
            self.ai_status.setText("✅ Connected")
            self.ai_status.setStyleSheet("font-weight: bold; color: green;")

            models = self.ollama.list_models()
            self.model_combo.clear()
            self.model_combo.addItems(models)

            current_model = self.ollama.model
            if current_model in models:
                self.model_combo.setCurrentText(current_model)

            # Auto-enable AI toggle if Ollama is available
            if self.ai_mode_toggle.isChecked():
                self.no_ai_banner.setVisible(False)
        else:
            self.ai_status.setText("❌ Not Connected")
            self.ai_status.setStyleSheet("font-weight: bold; color: red;")
            self.model_combo.clear()
            self.model_combo.addItem("No models available")

            # Auto-disable AI toggle if Ollama isn't available
            if self.ai_mode_toggle.isChecked():
                self.ai_mode_toggle.setChecked(False)
            self.no_ai_banner.setVisible(True)

    def _start_analysis(self):
        """Start AI or rule-based analysis."""
        if not self.files:
            QMessageBox.warning(self, "No Files", "Scan files first before analyzing.")
            return

        # Use toggle to decide AI vs rule-based — no confirmation dialog needed
        use_ai = self.ai_mode_toggle.isChecked() and self.ollama.is_available()

        if use_ai:
            # Update model from combo
            model = self.model_combo.currentText()
            if model and model != "No models available":
                self.ollama.update_settings(model=model)

        # 1-by-1 mode: only analyze files not yet categorized
        bulk_mode = self.bulk_mode_check.isChecked()
        if not bulk_mode:
            unanalyzed = []
            for f in self.files:
                cat = f.get("category", "")
                if not cat or cat == "Uncategorized" or cat == "Miscellaneous":
                    unanalyzed.append(f)
            if not unanalyzed:
                self.status_label.setText("All files already analyzed. Toggle Bulk mode to re-analyze all.")
                return
            self.files_to_analyze = unanalyzed
            self.status_label.setText(f"1-by-1 mode: analyzing {len(unanalyzed)}/{len(self.files)} unanalyzed files...")
        else:
            self.files_to_analyze = self.files
            self.status_label.setText(f"Bulk mode: analyzing all {len(self.files)} files...")

        # Get categories from config
        categories_path = Path(__file__).parent.parent / "config" / "categories.json"
        with open(categories_path, "r") as f:
            cat_config = json.load(f)
        categories = [c["name"] for c in cat_config["categories"]]

        # Add custom categories from DB
        custom = self.db.get_custom_categories()
        categories.extend(c["name"] for c in custom)

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.analyze_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        method_label = "AI" if use_ai else "rule-based"
        self.status_label.setText(f"Analyzing {len(self.files_to_analyze)} files ({method_label})...")

        self.analyze_worker = AnalyzeWorker(
            self.files_to_analyze, categories, self.ollama,
            self.metadata_extractor, self.content_reader, self.ocr,
            self.db, use_ai=use_ai
        )
        self.analyze_worker.progress.connect(self._on_progress)
        self.analyze_worker.file_analyzed.connect(self._on_file_analyzed)
        self.analyze_worker.status_update.connect(self._on_status)
        self.analyze_worker.finished_analysis.connect(self._on_finished)
        self.analyze_worker.start()

    def _cancel_analysis(self):
        """Cancel ongoing analysis."""
        if self.analyze_worker and self.analyze_worker.isRunning():
            self.analyze_worker.cancel()
            self.status_label.setText("Cancelling...")
            self.analyze_worker.wait(3000)

    def _on_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def _on_file_analyzed(self, file_path: str, category: str):
        """Add a result to the preview table."""
        row = self.preview_table.rowCount()
        self.preview_table.insertRow(row)
        self.preview_table.setItem(row, 0, QTableWidgetItem(Path(file_path).name))
        self.preview_table.setItem(row, 1, QTableWidgetItem(file_path))
        self.preview_table.setItem(row, 2, QTableWidgetItem(category))
        self.preview_table.setItem(row, 3, QTableWidgetItem("—"))

    def _on_status(self, msg: str):
        self.status_label.setText(msg)

    def _on_finished(self, results: dict):
        """Handle analysis completion."""
        self.progress_bar.setVisible(False)
        self.analyze_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.status_label.setText(f"Analysis complete: {len(results)} files classified")

        self.analysis_complete.emit(results)
