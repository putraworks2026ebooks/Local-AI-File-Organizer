"""
Quick Organize view -- all-in-one scan + analyze + organize.
Runs the entire pipeline in a single flow with a live progress display.
"""

import os
import json
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
    QGroupBox, QMessageBox, QFileDialog, QCheckBox, QComboBox, QLineEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QSpinBox
)
from PySide6.QtCore import Qt, Signal, QThread

from core.ollama_client import OllamaClient
from utils.logger import get_logger


class QuickOrganizeWorker(QThread):
    """Runs scan -> analyze -> organize in a single worker thread."""
    progress = Signal(str, int, int)
    file_processed = Signal(str, str, str)
    status_update = Signal(str)
    finished_all = Signal(dict)

    def __init__(self, scan_paths, config, ollama, db, organizer,
                 metadata_extractor, content_reader, ocr,
                 use_ai=False, bulk_mode=True):
        super().__init__()
        self.scan_paths = scan_paths
        self.config = config
        self.ollama = ollama
        self.db = db
        self.organizer = organizer
        self.metadata_extractor = metadata_extractor
        self.content_reader = content_reader
        self.ocr = ocr
        self.use_ai = use_ai and ollama.is_available()
        self.bulk_mode = bulk_mode
        self._cancel = False
        self._filter_category = "all"
        self._metadata_map = {}
        self.logger = get_logger()

    def cancel(self):
        self._cancel = True

    def run(self):
        results = {"scanned": 0, "analyzed": 0, "organized": 0, "errors": 0, "categories": {}}
        try:
            self.status_update.emit("Stage 1/3: Scanning folders...")
            self.progress.emit("Scanning", 0, 0)
            scanned_files = self._scan_stage()
            if self._cancel:
                self.finished_all.emit(results)
                return

            results["scanned"] = len(scanned_files)
            if not scanned_files:
                self.status_update.emit("No files found to organize.")
                self.finished_all.emit(results)
                return

            self.status_update.emit(f"Found {len(scanned_files)} files. Analyzing...")

            self.progress.emit("Analyzing", 0, len(scanned_files))
            file_categories = self._analyze_stage(scanned_files, results)
            if self._cancel:
                self.finished_all.emit(results)
                return

            self.status_update.emit(f"Analyzed {len(file_categories)} files. Organizing...")

            self.progress.emit("Organizing", 0, len(file_categories))
            self._organize_stage(file_categories, results)
            if self._cancel:
                self.finished_all.emit(results)
                return

            self.status_update.emit(
                f"Done! Scanned {results['scanned']}, organized {results['organized']} files."
            )
            self.finished_all.emit(results)

        except Exception as e:
            self.logger.error(f"Quick organize error: {e}")
            self.status_update.emit(f"Error: {e}")
            self.finished_all.emit(results)

    def _scan_stage(self):
        scan_config = self.config.get("scan", {})
        ignore_exts = set(scan_config.get("ignore_extensions", []))
        max_size = scan_config.get("max_file_size_mb", 512) * 1024 * 1024
        skip_system = scan_config.get("skip_system_folders", True)
        system_folders = set(scan_config.get("system_folders", []))

        all_files = []
        for scan_path in self.scan_paths:
            if self._cancel:
                break
            root = Path(scan_path)
            if not root.exists():
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                if self._cancel:
                    break
                if skip_system:
                    dirnames[:] = [d for d in dirnames if d not in system_folders]
                # Skip -AI folders (already organized output)
                dirnames[:] = [d for d in dirnames if not d.endswith("-AI")]
                for filename in filenames:
                    if self._cancel:
                        break
                    filepath = Path(dirpath) / filename
                    ext = filepath.suffix.lower()
                    if ext in ignore_exts:
                        continue
                    try:
                        size = filepath.stat().st_size
                    except (OSError, PermissionError):
                        continue
                    if size > max_size:
                        continue
                    all_files.append({
                        "file_path": str(filepath),
                        "file_name": filepath.name,
                        "extension": ext,
                        "size_bytes": size,
                        "scanned_at": datetime.now().isoformat(),
                    })
            self.progress.emit("Scanning", len(all_files), 0)
        return all_files

    def _analyze_stage(self, files, results):
        from ui.analyze_view import RuleBasedClassifier

        categories_path = Path(__file__).parent.parent / "config" / "categories.json"
        with open(categories_path, "r") as f:
            cat_config = json.load(f)
        categories = [c["name"] for c in cat_config["categories"]]

        rule_classifier = RuleBasedClassifier(categories)
        file_categories = {}
        total = len(files)

        for i, file_data in enumerate(files):
            if self._cancel:
                break
            file_path = file_data.get("file_path", "")
            category = None

            if self.use_ai:
                file_info = {
                    "file_name": file_data.get("file_name", ""),
                    "extension": file_data.get("extension", ""),
                    "metadata": {},
                }
                try:
                    category = self.ollama.classify_file(file_info, categories)
                except Exception:
                    category = None
                if not category or category == "Miscellaneous":
                    category = rule_classifier.classify(file_data)

            if not category:
                category = rule_classifier.classify(file_data)

            file_categories[file_path] = category
            results["categories"][category] = results["categories"].get(category, 0) + 1
            results["analyzed"] += 1

            dest = str(self.organizer.get_category_path(category, file_path) / Path(file_path).name)
            self.file_processed.emit(file_data.get("file_name", ""), category, dest)
            self.progress.emit("Analyzing", i + 1, total)

        return file_categories

    def _organize_stage(self, file_categories, results):
        # Apply category filter
        filter_cat = self._filter_category
        if filter_cat and filter_cat != "all":
            file_categories = {k: v for k, v in file_categories.items() if v == filter_cat}

        total = len(file_categories)
        if total == 0:
            return

        # Extract metadata for all files (in worker thread, not UI)
        self.status_update.emit("Extracting metadata for organize...")
        for file_path in file_categories:
            if self._cancel:
                break
            try:
                meta = self.metadata_extractor.extract(file_path)
                meta["category"] = file_categories[file_path]
                self._metadata_map[file_path] = meta
            except Exception:
                self._metadata_map[file_path] = {}

        for i, (file_path, category) in enumerate(file_categories.items()):
            if self._cancel:
                break
            metadata = self._metadata_map.get(file_path, {})
            metadata["category"] = category
            success, msg, op_id = self.organizer.move_file(file_path, category, metadata)
            if success:
                results["organized"] += 1
            else:
                results["errors"] += 1
            self.progress.emit("Organizing", i + 1, total)
        self.db.conn.commit()

        # Write GPS files
        if self._metadata_map:
            try:
                self.organizer._write_gps_files(self._metadata_map)
            except Exception as e:
                self.logger.warning(f"GPS write failed: {e}")

        # Clean up empty folders if enabled
        if self.organizer.move_empty_folders:
            self.status_update.emit("Cleaning up empty folders...")
            try:
                self.organizer._cleanup_empty_folders(file_categories)
            except Exception as e:
                self.logger.warning(f"Cleanup failed: {e}")


class QuickOrganizeView(QWidget):
    """All-in-one: Scan -> Analyze -> Organize in a single flow."""

    finished_organize = Signal(dict)

    def __init__(self, config, db, ollama, organizer, metadata_extractor, content_reader, ocr):
        super().__init__()
        self.config = config
        self.db = db
        self.ollama = ollama
        self.organizer = organizer
        self.metadata_extractor = metadata_extractor
        self.content_reader = content_reader
        self.ocr = ocr
        self.scan_paths = []
        self.worker = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Quick Organize")
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)

        desc = QLabel(
            "Scan, analyze, and organize your files in one step. "
            "Pick a folder, choose your options, and click Go."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        folder_group = QGroupBox("Folders to Organize")
        folder_layout = QVBoxLayout()

        self.folder_list = QLineEdit()
        self.folder_list.setPlaceholderText("Add folders to scan...")
        self.folder_list.setReadOnly(True)
        folder_layout.addWidget(self.folder_list)

        folder_btns = QHBoxLayout()
        add_btn = QPushButton("Add Folder")
        add_btn.clicked.connect(self._add_folder)
        folder_btns.addWidget(add_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_folders)
        folder_btns.addWidget(clear_btn)
        folder_btns.addStretch()
        folder_layout.addLayout(folder_btns)

        folder_group.setLayout(folder_layout)
        layout.addWidget(folder_group)

        output_group = QGroupBox("Output Destination")
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("Organize into:"))
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Select destination folder...")
        self.output_edit.setText(self.config.get("organize", {}).get("output_base", ""))
        output_layout.addWidget(self.output_edit)

        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_output)
        output_layout.addWidget(browse_btn)
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # Options are now in Settings → Organize tab
        # Read config values at start time

        results_group = QGroupBox("Live Results")
        results_layout = QVBoxLayout()
        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(["File", "Category", "Destination", "Status"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.results_table.setAlternatingRowColors(True)
        results_layout.addWidget(self.results_table)
        results_group.setLayout(results_layout)
        layout.addWidget(results_group)

        btn_layout = QHBoxLayout()
        self.go_btn = QPushButton("Go -- Scan + Analyze + Organize")
        self.go_btn.setObjectName("primary")
        self.go_btn.setStyleSheet("padding: 14px 28px; font-size: 15px;")
        self.go_btn.clicked.connect(self._on_go_btn)
        btn_layout.addWidget(self.go_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.stage_label = QLabel("")
        layout.addWidget(self.stage_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Scan")
        if folder:
            self.scan_paths.append(folder)
            self.folder_list.setText("  |  ".join(self.scan_paths))
            # Default output path = first scan folder
            if not self.output_edit.text().strip():
                self.output_edit.setText(folder)

    def _clear_folders(self):
        self.scan_paths.clear()
        self.folder_list.setText("")

    def _populate_date_struct_table(self):
        """Populate the per-category date structure table."""
        categories_path = Path(__file__).parent.parent / "config" / "categories.json"
        with open(categories_path, "r") as f:
            cat_config = json.load(f)
        all_cats = [c["name"] for c in cat_config["categories"]]

        try:
            custom = self.db.get_custom_categories()
            all_cats.extend(c["name"] for c in custom if c["name"] not in all_cats)
        except Exception:
            pass

        saved = self.config.get("organize", {}).get("date_structures", {})

        self.date_struct_table.setRowCount(len(all_cats))
        for i, cat in enumerate(all_cats):
            name_item = QTableWidgetItem(cat)
            name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.date_struct_table.setItem(i, 0, name_item)

            combo = QComboBox()
            combo.addItem("None (flat)", "none")
            combo.addItem("Year (2024)", "year")
            combo.addItem("Year/Month (2024/01)", "year_month")
            current = saved.get(cat, "none")
            idx = combo.findData(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            self.date_struct_table.setCellWidget(i, 1, combo)

    def _get_date_structures_from_table(self):
        """Read date structures from the table."""
        structures = {}
        for i in range(self.date_struct_table.rowCount()):
            cat_item = self.date_struct_table.item(i, 0)
            combo = self.date_struct_table.cellWidget(i, 1)
            if cat_item and combo:
                struct = combo.currentData()
                if struct != "none":
                    structures[cat_item.text()] = struct
        return structures

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_edit.setText(folder)

    def add_scan_path(self, path):
        self.scan_paths.append(path)
        self.folder_list.setText("  |  ".join(self.scan_paths))

    def _on_go_btn(self):
        """Toggle between Go and Stop."""
        if self.worker and self.worker.isRunning():
            self._cancel()
        else:
            self._start()

    def _start(self):
        if not self.scan_paths:
            QMessageBox.warning(self, "No Folders", "Add at least one folder to organize.")
            return

        # Read output from the field in this tab
        organize_config = self.config.setdefault("organize", {})
        output_base = self.output_edit.text().strip()
        if not output_base:
            QMessageBox.warning(self, "No Output", "Select a destination folder.")
            return
        organize_config["output_base"] = output_base

        # Other options come from Settings → Organize tab
        self.organizer.update_config(self.config)

        use_ai = self.config.get("analyze", {}).get("use_ai", False) and self.ollama.is_available()
        bulk = organize_config.get("bulk_mode", True)

        self.results_table.setRowCount(0)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.go_btn.setText("⏹️ Stop")
        self.go_btn.setStyleSheet("padding: 14px 28px; font-size: 15px; background-color: #dc3545; color: white;")
        self.status_label.setText("Starting...")

        self.worker = QuickOrganizeWorker(
            self.scan_paths, self.config, self.ollama, self.db, self.organizer,
            self.metadata_extractor, self.content_reader, self.ocr,
            use_ai=use_ai, bulk_mode=bulk
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.file_processed.connect(self._on_file_processed)
        self.worker.status_update.connect(self._on_status)
        self.worker.finished_all.connect(self._on_finished)
        self.worker.start()

    def _cancel(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.status_label.setText("Cancelling...")
            self.worker.wait(5000)

    def _on_progress(self, stage, current, total):
        self.stage_label.setText(f"Stage: {stage}")
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
        else:
            self.progress_bar.setRange(0, 0)

    def _on_file_processed(self, file_name, category, destination):
        row = self.results_table.rowCount()
        self.results_table.insertRow(row)
        self.results_table.setItem(row, 0, QTableWidgetItem(file_name))
        self.results_table.setItem(row, 1, QTableWidgetItem(category))
        self.results_table.setItem(row, 2, QTableWidgetItem(destination))
        self.results_table.setItem(row, 3, QTableWidgetItem("Done"))
        self.results_table.scrollToBottom()

    def _on_status(self, msg):
        self.status_label.setText(msg)

    def _on_finished(self, results):
        self.progress_bar.setVisible(False)
        self.go_btn.setText("Go -- Scan + Analyze + Organize")
        self.go_btn.setStyleSheet("padding: 14px 28px; font-size: 15px;")
        self.go_btn.setObjectName("primary")
        scanned = results.get("scanned", 0)
        organized = results.get("organized", 0)
        errors = results.get("errors", 0)
        summary = f"Done! Scanned {scanned} files, organized {organized}"
        if errors:
            summary += f", {errors} errors"
        self.status_label.setText(summary)
        self.finished_organize.emit(results)
