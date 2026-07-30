"""
Scan view for Local AI File Organizer.
Provides folder selection, scanning controls, and results display.
"""

from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QFileDialog, QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QMessageBox, QCheckBox, QSpinBox, QComboBox, QMenu, QInputDialog,
    QStyle, QStyleFactory
)
from PySide6.QtCore import Qt, Signal, QThread

from core.scanner import ScanWorker
from utils.helpers import format_file_size


class ScanView(QWidget):
    """Scan interface for selecting folders and scanning files."""

    scan_complete = Signal(list, int)
    scan_progress = Signal(int, int)

    def __init__(self, config: dict, db):
        super().__init__()
        self.config = config
        self.db = db
        self.scan_worker = None
        self.scan_paths: list[str] = []
        self.scanned_files: list[dict] = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("🔍 Scan")
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)

        # Scan paths section
        paths_group = QGroupBox("Scan Locations")
        paths_layout = QVBoxLayout()

        # Paths list
        self.paths_list = QListWidget()
        self.paths_list.setAlternatingRowColors(True)
        paths_layout.addWidget(self.paths_list)

        # Path buttons
        path_btn_layout = QHBoxLayout()

        add_btn = QPushButton("➕ Add Folder")
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self._add_folder)
        path_btn_layout.addWidget(add_btn)

        remove_btn = QPushButton("➖ Remove")
        remove_btn.clicked.connect(self._remove_path)
        path_btn_layout.addWidget(remove_btn)

        path_btn_layout.addStretch()

        paths_group.setLayout(paths_layout)
        layout.addWidget(paths_group)

        # Scan options
        options_group = QGroupBox("Scan Options")
        options_layout = QHBoxLayout()

        self.skip_system = QCheckBox("Skip system folders")
        self.skip_system.setChecked(self.config.get("scan", {}).get("skip_system_folders", True))
        options_layout.addWidget(self.skip_system)

        options_layout.addWidget(QLabel("Workers:"))
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 16)
        self.workers_spin.setValue(self.config.get("scan", {}).get("max_workers", 4))
        options_layout.addWidget(self.workers_spin)

        options_layout.addWidget(QLabel("Max file size (MB):"))
        self.max_size_spin = QSpinBox()
        self.max_size_spin.setRange(1, 10240)
        self.max_size_spin.setValue(self.config.get("scan", {}).get("max_file_size_mb", 512))
        options_layout.addWidget(self.max_size_spin)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        # Scan buttons
        scan_btn_layout = QHBoxLayout()

        self.scan_btn = QPushButton("🔍 Start Scan")
        self.scan_btn.setObjectName("primary")
        self.scan_btn.setStyleSheet("padding: 12px 24px; font-size: 14px;")
        self.scan_btn.clicked.connect(self._start_scan)
        scan_btn_layout.addWidget(self.scan_btn)

        self.cancel_btn = QPushButton("⏹️ Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_scan)
        scan_btn_layout.addWidget(self.cancel_btn)

        scan_btn_layout.addStretch()
        layout.addLayout(scan_btn_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        # Results table
        results_group = QGroupBox("Scanned Files")
        results_layout = QVBoxLayout()

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(5)
        self.results_table.setHorizontalHeaderLabels(["File", "Path", "Size", "Extension", "Scanned"])
        self.results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.results_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.results_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.results_table.setAlternatingRowColors(True)
        results_layout.addWidget(self.results_table)

        results_group.setLayout(results_layout)
        layout.addWidget(results_group)

    def add_scan_path(self, path: str):
        """Add a scan path."""
        if path not in self.scan_paths:
            self.scan_paths.append(path)
            self.paths_list.addItem(path)

    def _add_folder(self):
        """Open folder picker and add to scan list."""
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Scan")
        if folder:
            self.add_scan_path(folder)

    def _remove_path(self):
        """Remove selected scan path."""
        row = self.paths_list.currentRow()
        if row >= 0:
            self.paths_list.takeItem(row)
            self.scan_paths.pop(row)

    def _start_scan(self):
        """Start scanning selected folders."""
        if not self.scan_paths:
            QMessageBox.warning(self, "No Paths", "Please add at least one folder to scan.")
            return

        # Update config with scan options
        scan_config = self.config.setdefault("scan", {})
        scan_config["skip_system_folders"] = self.skip_system.isChecked()
        scan_config["max_workers"] = self.workers_spin.value()
        scan_config["max_file_size_mb"] = self.max_size_spin.value()

        self.scanned_files = []
        self.results_table.setRowCount(0)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.scan_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.status_label.setText("Scanning...")

        self.scan_worker = ScanWorker(list(self.scan_paths), self.config, self.db)
        self.scan_worker.progress.connect(self._on_progress)
        self.scan_worker.file_found.connect(self._on_file_found)
        self.scan_worker.status_update.connect(self._on_status)
        self.scan_worker.error.connect(self._on_error)
        self.scan_worker.finished_scan.connect(self._on_finished)
        self.scan_worker.start()

    def _cancel_scan(self):
        """Cancel the current scan."""
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.cancel()
            self.status_label.setText("Cancelling...")
            self.scan_worker.wait(3000)

    def _on_progress(self, current, total):
        """Handle progress updates."""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.scan_progress.emit(current, total)

    def _on_file_found(self, file_data: dict):
        """Handle newly found file."""
        self.scanned_files.append(file_data)

        # Save to database
        try:
            self.db.upsert_file(file_data)
        except Exception:
            pass

        # Add to table (throttled - every 100th file)
        if len(self.scanned_files) % 10 == 0:
            self._update_results_table()

    def _update_results_table(self):
        """Update the results table with scanned files."""
        self.results_table.setRowCount(len(self.scanned_files))
        for i, f in enumerate(self.scanned_files):
            self.results_table.setItem(i, 0, QTableWidgetItem(f.get("file_name", "")))
            self.results_table.setItem(i, 1, QTableWidgetItem(f.get("file_path", "")))
            self.results_table.setItem(i, 2, QTableWidgetItem(format_file_size(f.get("size_bytes", 0))))
            self.results_table.setItem(i, 3, QTableWidgetItem(f.get("extension", "")))
            self.results_table.setItem(i, 4, QTableWidgetItem(f.get("scanned_at", "")))

        self.results_table.scrollToBottom()

    def _on_status(self, msg: str):
        """Handle status updates."""
        self.status_label.setText(msg)

    def _on_error(self, msg: str):
        """Handle scan errors."""
        self.status_label.setText(f"Error: {msg}")

    def _on_finished(self, total_files: int, total_size: int):
        """Handle scan completion."""
        self._update_results_table()
        self.progress_bar.setVisible(False)
        self.scan_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.status_label.setText(f"Scan complete: {total_files} files, {format_file_size(total_size)}")

        # Update index state
        for path in self.scan_paths:
            self.db.update_index_state(path, total_files, total_size)

        self.scan_complete.emit(self.scanned_files, total_size)
