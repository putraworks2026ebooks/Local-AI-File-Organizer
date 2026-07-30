"""
Duplicates view for Local AI File Organizer.
Displays duplicate file groups with options to review and move duplicates.
All heavy operations run in worker threads.
"""

from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox, QMessageBox,
    QFileDialog, QTreeWidget, QTreeWidgetItem, QComboBox, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor

from core.duplicate_finder import DuplicateFinder
from core.organizer import FileOrganizer
from database.operations import OperationHistory
from database.db_manager import DatabaseManager
from utils.helpers import format_file_size
from utils.logger import get_logger


class DuplicateScanWorker(QThread):
    """Worker thread for duplicate detection."""

    progress = Signal(int, int)
    status_update = Signal(str)
    error = Signal(str)
    finished_scan = Signal(list, dict)

    def __init__(self, files: list[dict], duplicate_finder: DuplicateFinder):
        super().__init__()
        self.files = files
        self.duplicate_finder = duplicate_finder
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        self.status_update.emit("Detecting duplicates...")

        def cancel_check():
            return self._cancel

        def progress_cb(current, total):
            self.progress.emit(current, total)
            if current % 500 == 0:
                self.status_update.emit(f"Hashing files: {current}/{total}")

        groups = self.duplicate_finder.find_duplicates(
            self.files, progress_callback=progress_cb, cancel_check=cancel_check
        )
        summary = self.duplicate_finder.get_summary()
        self.status_update.emit(
            f"Found {summary['total_duplicates']} duplicates in "
            f"{summary['total_groups']} groups "
            f"({summary['wasted_formatted']} wasted)"
        )
        self.finished_scan.emit(groups, summary)


class MoveDuplicatesWorker(QThread):
    """Worker thread for moving duplicate files."""

    progress = Signal(int, int)
    status_update = Signal(str)
    error = Signal(str)
    finished_move = Signal(list)

    def __init__(self, groups: list[dict], output_folder: str,
                 duplicate_finder: DuplicateFinder, strategy: str):
        super().__init__()
        self.groups = groups
        self.output_folder = output_folder
        self.duplicate_finder = duplicate_finder
        self.strategy = strategy
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        import shutil
        from utils.helpers import get_unique_filename
        from database.operations import OperationType

        results = []
        base = Path(self.output_folder) / "_Duplicates"
        base.mkdir(parents=True, exist_ok=True)

        total = sum(len(g["duplicates"]) for g in self.groups)
        processed = 0

        for group in self.groups:
            if self._cancel:
                break

            for dup_path in group["duplicates"]:
                if self._cancel:
                    break

                processed += 1
                src = Path(dup_path)

                if not src.exists():
                    results.append({"file_path": dup_path, "success": False, "message": "File not found"})
                    continue

                filename = src.name
                if (base / filename).exists():
                    filename = get_unique_filename(base, filename)

                dest_path = base / filename

                try:
                    shutil.move(str(src), str(dest_path))
                    results.append({"file_path": dup_path, "success": True, "message": str(dest_path)})
                except (OSError, shutil.Error) as e:
                    results.append({"file_path": dup_path, "success": False, "message": str(e)})

                self.progress.emit(processed, total)
                if processed % 100 == 0:
                    self.status_update.emit(f"Moving duplicates: {processed}/{total}")

        self.status_update.emit(f"Moved {sum(1 for r in results if r['success'])}/{total} duplicates")
        self.finished_move.emit(results)


class DuplicatesView(QWidget):
    """Duplicate finder interface."""

    def __init__(self, config: dict, db: DatabaseManager, duplicate_finder: DuplicateFinder):
        super().__init__()
        self.config = config
        self.db = db
        self.duplicate_finder = duplicate_finder
        self.duplicate_groups: list[dict] = []
        self.scan_worker = None
        self.move_worker = None
        self.logger = get_logger()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("👥 Duplicate Finder")
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)

        # Summary cards
        summary_layout = QHBoxLayout()

        self.lbl_groups = QLabel("Groups: 0")
        self.lbl_groups.setStyleSheet("font-weight: bold; font-size: 16px; padding: 8px;")
        summary_layout.addWidget(self.lbl_groups)

        self.lbl_duplicates = QLabel("Duplicates: 0")
        self.lbl_duplicates.setStyleSheet("font-weight: bold; font-size: 16px; padding: 8px;")
        summary_layout.addWidget(self.lbl_duplicates)

        self.lbl_wasted = QLabel("Wasted: 0 B")
        self.lbl_wasted.setStyleSheet("font-weight: bold; font-size: 16px; padding: 8px;")
        summary_layout.addWidget(self.lbl_wasted)

        summary_layout.addStretch()
        layout.addLayout(summary_layout)

        # Keep strategy
        strategy_group = QGroupBox("Keep Strategy")
        strategy_layout = QHBoxLayout()

        strategy_layout.addWidget(QLabel("Keep:"))
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems([
            "First file (default)",
            "Oldest file",
            "Newest file",
            "Shortest path",
            "Longest path",
        ])
        strategy_layout.addWidget(self.strategy_combo)

        strategy_group.setLayout(strategy_layout)
        layout.addWidget(strategy_group)

        # Action buttons
        btn_layout = QHBoxLayout()

        self.find_btn = QPushButton("🔍 Find Duplicates")
        self.find_btn.setObjectName("primary")
        self.find_btn.setStyleSheet("padding: 12px 24px; font-size: 14px;")
        self.find_btn.clicked.connect(self._find_duplicates)
        btn_layout.addWidget(self.find_btn)

        self.cancel_btn = QPushButton("⏹️ Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_scan)
        btn_layout.addWidget(self.cancel_btn)

        self.move_btn = QPushButton("📁 Move Duplicates")
        self.move_btn.setEnabled(False)
        self.move_btn.clicked.connect(self._move_duplicates)
        btn_layout.addWidget(self.move_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        # Results tree
        results_group = QGroupBox("Duplicate Groups")
        results_layout = QVBoxLayout()

        self.results_tree = QTreeWidget()
        self.results_tree.setColumnCount(4)
        self.results_tree.setHeaderLabels(["File / Group", "Size", "Path", "Action"])
        self.results_tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.results_tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.results_tree.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self.results_tree.header().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        results_layout.addWidget(self.results_tree)

        results_group.setLayout(results_layout)
        layout.addWidget(results_group)

    def _find_duplicates(self):
        """Start duplicate detection."""
        files = self.db.get_all_files()
        if not files:
            QMessageBox.warning(self, "No Files", "Scan files first before finding duplicates.")
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.find_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.move_btn.setEnabled(False)
        self.results_tree.clear()

        self.scan_worker = DuplicateScanWorker(files, self.duplicate_finder)
        self.scan_worker.progress.connect(self._on_progress)
        self.scan_worker.status_update.connect(self._on_status)
        self.scan_worker.error.connect(self._on_error)
        self.scan_worker.finished_scan.connect(self._on_finished)
        self.scan_worker.start()

    def _cancel_scan(self):
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.cancel()
            self.scan_worker.wait(3000)
        if self.move_worker and self.move_worker.isRunning():
            self.move_worker.cancel()
            self.move_worker.wait(3000)

    def _on_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def _on_status(self, msg):
        self.status_label.setText(msg)

    def _on_error(self, msg):
        self.status_label.setText(f"Error: {msg}")

    def _on_finished(self, groups: list[dict], summary: dict):
        self.duplicate_groups = groups
        self.progress_bar.setVisible(False)
        self.find_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.move_btn.setEnabled(len(groups) > 0)

        self.lbl_groups.setText(f"Groups: {summary['total_groups']}")
        self.lbl_duplicates.setText(f"Duplicates: {summary['total_duplicates']}")
        self.lbl_wasted.setText(f"Wasted: {summary['wasted_formatted']}")

        # Populate tree — cap at 1000 groups for UI performance
        strategy = self.strategy_combo.currentText().lower().split()[0]
        display_groups = groups[:1000]
        for group in display_groups:
            group_item = QTreeWidgetItem([
                f"Group {group['group_id']} — {group['count']} files",
                group['size_formatted'],
                f"SHA256: {group['sha256'][:16]}...",
                "",
            ])
            group_item.setForeground(0, QColor("blue"))

            keep_path = self.duplicate_finder.select_duplicate_to_keep(group, strategy)

            for file_path in group['file_paths']:
                action = "✅ Keep" if file_path == keep_path else "📦 Duplicate"
                child = QTreeWidgetItem([
                    Path(file_path).name,
                    "",
                    file_path,
                    action,
                ])
                if file_path == keep_path:
                    child.setForeground(3, QColor("green"))
                else:
                    child.setForeground(3, QColor("orange"))
                group_item.addChild(child)

            self.results_tree.addTopLevelItem(group_item)
            group_item.setExpanded(True)

        if len(groups) > 1000:
            self.status_label.setText(f"Showing 1000 of {len(groups)} groups")

        # Save to database — BATCH commits (not per-record)
        self.db.clear_duplicate_groups()
        batch_count = 0
        for group in groups:
            for file_path in group['file_paths']:
                self.db.insert_duplicate_group(
                    sha256=group['sha256'],
                    file_path=file_path,
                    group_id=group['group_id'],
                    size_bytes=group['size_bytes'],
                    keep=(file_path == group.get('keep_file', group['file_paths'][0])),
                    commit=False,
                )
                batch_count += 1
                if batch_count % 100 == 0:
                    self.db.conn.commit()
        self.db.conn.commit()

    def _move_duplicates(self):
        """Move duplicate files to a duplicates folder — in a worker thread."""
        if not self.duplicate_groups:
            return

        folder = QFileDialog.getExistingDirectory(self, "Select Duplicates Folder")
        if not folder:
            return

        reply = QMessageBox.question(
            self, "Confirm Move",
            f"Move all duplicate files to:\n{folder}\n\n"
            "Original files are kept. Duplicates are moved (not deleted).\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        strategy = self.strategy_combo.currentText().lower().split()[0]

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.find_btn.setEnabled(False)
        self.move_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        self.move_worker = MoveDuplicatesWorker(
            self.duplicate_groups, folder, self.duplicate_finder, strategy
        )
        self.move_worker.progress.connect(self._on_progress)
        self.move_worker.status_update.connect(self._on_status)
        self.move_worker.finished_move.connect(self._on_move_finished)
        self.move_worker.start()

    def _on_move_finished(self, results: list):
        self.progress_bar.setVisible(False)
        self.find_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.move_btn.setEnabled(True)

        success = sum(1 for r in results if r["success"])
        total = len(results)
        self.status_label.setText(f"Moved {success}/{total} duplicates")
        QMessageBox.information(
            self, "Move Complete",
            f"Moved {success} of {total} duplicate files.\nUse Undo to reverse any moves.",
        )
