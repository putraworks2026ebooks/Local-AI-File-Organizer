"""
Analyze view for Local AI File Organizer.
Uses Ollama to classify files into categories with preview before organizing.
"""

import json
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox, QMessageBox,
    QCheckBox, QComboBox, QTextEdit, QSplitter, QTabWidget
)
from PySide6.QtCore import Qt, Signal, QThread

from core.ollama_client import OllamaClient
from core.metadata import MetadataExtractor
from core.content_reader import ContentReader
from core.ocr import OCRProcessor
from database.db_manager import DatabaseManager
from utils.logger import get_logger


class AnalyzeWorker(QThread):
    """Worker thread for AI analysis."""

    progress = Signal(int, int)
    file_analyzed = Signal(str, str)  # file_path, category
    status_update = Signal(str)
    error = Signal(str)
    finished_analysis = Signal(dict)  # {file_path: category}

    def __init__(self, files: list[dict], categories: list[str],
                 ollama: OllamaClient, metadata_extractor: MetadataExtractor,
                 content_reader: ContentReader, ocr: OCRProcessor, db: DatabaseManager):
        super().__init__()
        self.files = files
        self.categories = categories
        self.ollama = ollama
        self.metadata_extractor = metadata_extractor
        self.content_reader = content_reader
        self.ocr = ocr
        self.db = db
        self._cancel = False
        self.logger = get_logger()

    def cancel(self):
        self._cancel = True

    def run(self):
        """Run AI analysis on all files."""
        results = {}
        total = len(self.files)
        processed = 0
        errors = 0

        self.status_update.emit(f"Analyzing {total} files with {self.ollama.model}...")

        for file_data in self.files:
            if self._cancel:
                break

            file_path = file_data.get("file_path", "")
            file_name = file_data.get("file_name", "unknown")

            try:
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

            except Exception as e:
                self.logger.error(f"Analysis error for {file_name}: {e}")
                results[file_path] = "Miscellaneous"
                errors += 1

            processed += 1
            self.progress.emit(processed, total)

            if processed % 100 == 0:
                self.status_update.emit(f"Analyzed {processed}/{total} files ({errors} errors)")

        self.status_update.emit(f"Analysis complete: {processed} files, {errors} errors")
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

    def _init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("🤖 AI Analysis")
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)

        # AI status
        status_group = QGroupBox("Ollama AI Engine")
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

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

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

        # Check AI on init
        QTimer_singleShot = self._check_ai_status

    def set_files(self, files: list[dict]):
        """Set the files to analyze."""
        self.files = files
        self.status_label.setText(f"{len(files)} files ready for analysis")
        self.preview_table.setRowCount(0)

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
        else:
            self.ai_status.setText("❌ Not Connected")
            self.ai_status.setStyleSheet("font-weight: bold; color: red;")
            self.model_combo.clear()
            self.model_combo.addItem("No models available")

    def _start_analysis(self):
        """Start AI analysis."""
        if not self.files:
            QMessageBox.warning(self, "No Files", "Scan files first before analyzing.")
            return

        if not self.ollama.is_available():
            QMessageBox.warning(self, "AI Not Available",
                                "Ollama server is not running.\n"
                                "Start Ollama and ensure it's reachable at the configured URL.")
            return

        # Update model from combo
        model = self.model_combo.currentText()
        if model:
            self.ollama.update_settings(model=model)

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
        self.preview_table.setRowCount(0)

        self.analyze_worker = AnalyzeWorker(
            self.files, categories, self.ollama,
            self.metadata_extractor, self.content_reader, self.ocr, self.db
        )
        self.analyze_worker.progress.connect(self._on_progress)
        self.analyze_worker.file_analyzed.connect(self._on_file_analyzed)
        self.analyze_worker.status_update.connect(self._on_status)
        self.analyze_worker.error.connect(self._on_error)
        self.analyze_worker.finished_analysis.connect(self._on_finished)
        self.analyze_worker.start()

    def _cancel_analysis(self):
        """Cancel analysis."""
        if self.analyze_worker and self.analyze_worker.isRunning():
            self.analyze_worker.cancel()
            self.analyze_worker.wait(3000)

    def _on_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def _on_file_analyzed(self, file_path: str, category: str):
        row = self.preview_table.rowCount()
        self.preview_table.setRowCount(row + 1)
        self.preview_table.setItem(row, 0, QTableWidgetItem(Path(file_path).name))
        self.preview_table.setItem(row, 1, QTableWidgetItem(file_path))
        self.preview_table.setItem(row, 2, QTableWidgetItem(category))
        self.preview_table.setItem(row, 3, QTableWidgetItem("AI"))
        self.preview_table.scrollToBottom()

    def _on_status(self, msg: str):
        self.status_label.setText(msg)

    def _on_error(self, msg: str):
        self.status_label.setText(f"Error: {msg}")

    def _on_finished(self, results: dict):
        self.progress_bar.setVisible(False)
        self.analyze_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.status_label.setText(f"Analysis complete: {len(results)} files classified")
        self.analysis_complete.emit(results)


# Import for QTimer singleShot
from PySide6.QtCore import QTimer
