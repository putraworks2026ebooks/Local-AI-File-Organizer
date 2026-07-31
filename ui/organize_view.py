"""
Organize view for Local AI File Organizer.
Shows proposed actions, requires user approval, and executes file moves.
All file operations run in a worker thread to keep UI responsive.
"""

from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox, QMessageBox,
    QCheckBox, QFileDialog, QLineEdit, QComboBox, QButtonGroup, QRadioButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QSpinBox
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor

from core.organizer import FileOrganizer
from database.db_manager import DatabaseManager
from utils.helpers import format_file_size
from utils.logger import get_logger


class OrganizeWorker(QThread):
    """Worker thread for file organization — keeps UI responsive."""

    progress = Signal(int, int, int)  # processed, total, success_count
    status_update = Signal(str)
    error = Signal(str)
    finished_organize = Signal(list)  # results list

    def __init__(self, file_categories: dict[str, str], organizer: FileOrganizer,
                 metadata_map: dict = None):
        super().__init__()
        self.file_categories = file_categories
        self.organizer = organizer
        self.metadata_map = metadata_map or {}
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        results = []
        total = len(self.file_categories)
        processed = 0
        success_count = 0

        for file_path, category in self.file_categories.items():
            if self._cancel:
                break

            processed += 1
            metadata = self.metadata_map.get(file_path, {})
            success, message, op_id = self.organizer.move_file(file_path, category, metadata)

            results.append({
                "file_path": file_path,
                "category": category,
                "success": success,
                "message": message,
                "operation_id": op_id,
            })

            if success:
                success_count += 1

            self.progress.emit(processed, total, success_count)

            if processed % 100 == 0:
                self.status_update.emit(f"Organizing: {processed}/{total} ({success_count} moved)")

        self.status_update.emit(f"Done: {success_count}/{total} files moved")
        self.finished_organize.emit(results)


class OrganizeView(QWidget):
    """Organize interface."""

    analysis_complete = Signal(dict)

    def __init__(self, config: dict, db: DatabaseManager, organizer: FileOrganizer):
        super().__init__()
        self.config = config
        self.db = db
        self.organizer = organizer
        self.file_categories: dict[str, str] = {}
        self.organize_worker = None
        self.logger = get_logger()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("📁 Organize")
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)

        # Output path
        path_group = QGroupBox("Output Destination")
        path_layout = QHBoxLayout()

        path_layout.addWidget(QLabel("Base folder:"))
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Select destination folder...")
        output_base = self.config.get("organize", {}).get("output_base", "")
        self.output_edit.setText(output_base)
        path_layout.addWidget(self.output_edit)

        browse_btn = QPushButton("📁 Browse")
        browse_btn.clicked.connect(self._browse_output)
        path_layout.addWidget(browse_btn)

        path_group.setLayout(path_layout)
        layout.addWidget(path_group)

        # Options
        opts_group = QGroupBox("Organization Options")
        opts_layout = QVBoxLayout()

        # Row 1: checkboxes
        row1 = QHBoxLayout()
        self.photos_by_date = QCheckBox("Organize photos by date")
        self.photos_by_date.setChecked(self.config.get("organize", {}).get("photo_organize_by_date", True))
        row1.addWidget(self.photos_by_date)

        self.create_folders = QCheckBox("Create category folders")
        self.create_folders.setChecked(self.config.get("organize", {}).get("create_category_folders", True))
        row1.addWidget(self.create_folders)

        self.move_empty_check = QCheckBox("Move empty folders to ToBeDeleted")
        self.move_empty_check.setChecked(self.config.get("organize", {}).get("move_empty_folders", True))
        self.move_empty_check.setToolTip("After organizing, move empty source folders to a ToBeDeleted folder")
        row1.addWidget(self.move_empty_check)

        row1.addStretch()
        opts_layout.addLayout(row1)

        # Row 2: max file size for organizing
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Max file size to organize (MB):"))
        self.max_size_spin = QSpinBox()
        self.max_size_spin.setRange(0, 999999)
        self.max_size_spin.setValue(self.config.get("organize", {}).get("max_organize_size_mb", 0))
        self.max_size_spin.setSpecialValueText("No limit")
        self.max_size_spin.setToolTip("0 = no limit. Files larger than this are skipped during organize.")
        row2.addWidget(self.max_size_spin)
        row2.addStretch()
        opts_layout.addLayout(row2)

        # Row 3: per-category date structure table
        row3_label = QLabel("Date structure per category (set once, applies to all):")
        opts_layout.addWidget(row3_label)

        self.date_struct_table = QTableWidget()
        self.date_struct_table.setColumnCount(2)
        self.date_struct_table.setHorizontalHeaderLabels(["Category", "Date Structure"])
        self.date_struct_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.date_struct_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.date_struct_table.setMaximumHeight(200)
        self._populate_date_struct_table()
        opts_layout.addWidget(self.date_struct_table)

        opts_group.setLayout(opts_layout)
        layout.addWidget(opts_group)

        # Category filter
        filter_group = QGroupBox("Category Filter")
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Organize only:"))
        self.category_filter = QComboBox()
        self.category_filter.addItem("All categories", "all")
        import json as _json
        from pathlib import Path as _Path
        _cat_path = _Path(__file__).parent.parent / "config" / "categories.json"
        with open(_cat_path, "r") as _f:
            _cats = [c["name"] for c in _json.load(_f)["categories"]]
        try:
            _custom = self.db.get_custom_categories()
            _cats.extend(c["name"] for c in _custom if c["name"] not in _cats)
        except Exception:
            pass
        for _c in _cats:
            self.category_filter.addItem(_c, _c)
        self.category_filter.currentIndexChanged.connect(self._apply_category_filter)
        filter_layout.addWidget(self.category_filter)
        filter_layout.addStretch()
        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)

        # Preview table
        preview_group = QGroupBox("Proposed Actions (Review before applying)")
        preview_layout = QVBoxLayout()

        self.preview_table = QTableWidget()
        self.preview_table.setColumnCount(5)
        self.preview_table.setHorizontalHeaderLabels(["File", "Source", "Category", "Destination", "Status"])
        self.preview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.preview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.preview_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.preview_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.preview_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.preview_table.setAlternatingRowColors(True)
        preview_layout.addWidget(self.preview_table)

        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)

        # Action buttons
        btn_layout = QHBoxLayout()

        self.preview_btn = QPushButton("👁️ Preview Actions")
        self.preview_btn.clicked.connect(self._generate_preview)
        btn_layout.addWidget(self.preview_btn)

        self.organize_btn = QPushButton("📁 Organize Files")
        self.organize_btn.setObjectName("primary")
        self.organize_btn.setStyleSheet("padding: 12px 24px; font-size: 14px;")
        self.organize_btn.clicked.connect(self._on_organize_btn)
        btn_layout.addWidget(self.organize_btn)

        self.undo_btn = QPushButton("↩️ Undo Last")
        self.undo_btn.clicked.connect(self._undo_last)
        btn_layout.addWidget(self.undo_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

    def set_file_categories(self, file_categories: dict):
        self.file_categories = file_categories
        self._all_file_categories = dict(file_categories)
        self.status_label.setText(f"{len(file_categories)} files ready for organization")
        self._generate_preview()

    def _populate_date_struct_table(self):
        """Populate the per-category date structure table with all categories."""
        import json
        from pathlib import Path

        categories_path = Path(__file__).parent.parent / "config" / "categories.json"
        with open(categories_path, "r") as f:
            cat_config = json.load(f)
        all_cats = [c["name"] for c in cat_config["categories"]]

        # Add custom categories from DB if available
        try:
            custom = self.db.get_custom_categories()
            all_cats.extend(c["name"] for c in custom if c["name"] not in all_cats)
        except Exception:
            pass

        saved_structures = self.config.get("organize", {}).get("date_structures", {})

        self.date_struct_table.setRowCount(len(all_cats))
        for i, cat in enumerate(all_cats):
            # Category name (read-only)
            name_item = QTableWidgetItem(cat)
            name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.date_struct_table.setItem(i, 0, name_item)

            # Date structure dropdown
            combo = QComboBox()
            combo.addItem("None (flat folder)", "none")
            combo.addItem("Year (2024)", "year")
            combo.addItem("Year/Month (2024/01)", "year_month")

            current = saved_structures.get(cat, "none")
            idx = combo.findData(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)

            self.date_struct_table.setCellWidget(i, 1, combo)

    def _get_date_structures_from_table(self) -> dict:
        """Read the per-category date structures from the table."""
        structures = {}
        for i in range(self.date_struct_table.rowCount()):
            cat_item = self.date_struct_table.item(i, 0)
            combo = self.date_struct_table.cellWidget(i, 1)
            if cat_item and combo:
                cat = cat_item.text()
                struct = combo.currentData()
                if struct != "none":
                    structures[cat] = struct
        return structures

    def _apply_category_filter(self):
        """Filter file_categories to only show selected category."""
        if not self.file_categories:
            return
        selected = self.category_filter.currentData()
        if selected == "all":
            # Restore full list
            if hasattr(self, "_all_file_categories") and self._all_file_categories:
                self.file_categories = dict(self._all_file_categories)
        else:
            # Save full list if not already saved
            if not hasattr(self, "_all_file_categories"):
                self._all_file_categories = dict(self.file_categories)
            else:
                self._all_file_categories = dict(self.file_categories)
            # Filter to only selected category
            self.file_categories = {
                k: v for k, v in self._all_file_categories.items() if v == selected
            }
        self.status_label.setText(f"{len(self.file_categories)} files ready for organization")
        self._generate_preview()

    def set_config(self, config: dict):
        self.config = config
        self.organizer.update_config(config)
        self.output_edit.setText(config.get("organize", {}).get("output_base", ""))
        self.photos_by_date.setChecked(config.get("organize", {}).get("photo_organize_by_date", True))
        self.create_folders.setChecked(config.get("organize", {}).get("create_category_folders", True))
        self.move_empty_check.setChecked(config.get("organize", {}).get("move_empty_folders", True))
        self.max_size_spin.setValue(config.get("organize", {}).get("max_organize_size_mb", 0))
        self._populate_date_struct_table()

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_edit.setText(folder)

    def _generate_preview(self):
        """Generate a preview — throttled for large file sets."""
        if not self.file_categories:
            self.status_label.setText("No files to organize. Run analysis first.")
            return

        output_base = self.output_edit.text().strip()
        if not output_base:
            self.status_label.setText("Please select an output folder first.")
            return

        organize_config = self.config.setdefault("organize", {})
        organize_config["output_base"] = output_base
        organize_config["photo_organize_by_date"] = self.photos_by_date.isChecked()
        organize_config["create_category_folders"] = self.create_folders.isChecked()
        organize_config["move_empty_folders"] = self.move_empty_check.isChecked()
        organize_config["max_organize_size_mb"] = self.max_size_spin.value()
        organize_config["date_structures"] = self._get_date_structures_from_table()
        self.organizer.update_config(self.config)

        # Cap preview at 500 rows for performance; show count in status
        items = list(self.file_categories.items())
        preview_count = min(len(items), 500)
        self.preview_table.setRowCount(preview_count)

        for i in range(preview_count):
            file_path, category = items[i]
            # Quick metadata for preview path (camera maker/model)
            preview_meta = {}
            try:
                from core.metadata import MetadataExtractor
                meta_ext = MetadataExtractor(self.config)
                preview_meta = meta_ext.extract(Path(file_path))
            except Exception:
                pass
            dest_dir = self.organizer.get_category_path(category, file_path, preview_meta)
            dest_path = dest_dir / Path(file_path).name

            self.preview_table.setItem(i, 0, QTableWidgetItem(Path(file_path).name))
            self.preview_table.setItem(i, 1, QTableWidgetItem(str(Path(file_path).parent)))
            self.preview_table.setItem(i, 2, QTableWidgetItem(category))
            self.preview_table.setItem(i, 3, QTableWidgetItem(str(dest_path)))
            self.preview_table.setItem(i, 4, QTableWidgetItem("Pending"))

        suffix = f" (showing first {preview_count})" if preview_count < len(items) else ""
        self.status_label.setText(f"Preview: {len(self.file_categories)} files to organize{suffix}")

    def _on_organize_btn(self):
        """Toggle between Organize and Stop."""
        if self.organize_worker and self.organize_worker.isRunning():
            self._cancel_organize()
        else:
            self._organize_files()

    def _organize_files(self):
        """Execute file organization in a WORKER THREAD — no UI freeze."""
        if not self.file_categories:
            QMessageBox.warning(self, "No Files", "No files to organize.")
            return

        output_base = self.output_edit.text().strip()
        if not output_base:
            QMessageBox.warning(self, "No Output", "Please select an output folder.")
            return

        reply = QMessageBox.question(
            self, "Confirm Organization",
            f"Move {len(self.file_categories)} files to category folders in:\n{output_base}\n\n"
            "No files will be deleted. You can undo any move later.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        organize_config = self.config.setdefault("organize", {})
        organize_config["output_base"] = output_base
        organize_config["photo_organize_by_date"] = self.photos_by_date.isChecked()
        organize_config["create_category_folders"] = self.create_folders.isChecked()
        organize_config["move_empty_folders"] = self.move_empty_check.isChecked()
        organize_config["max_organize_size_mb"] = self.max_size_spin.value()
        organize_config["date_structures"] = self._get_date_structures_from_table()
        self.organizer.update_config(self.config)

        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(self.file_categories))
        self.progress_bar.setValue(0)
        self.organize_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.status_label.setText("Extracting metadata...")

        # Extract metadata for camera maker/model folders
        metadata_map = {}
        try:
            from core.metadata import MetadataExtractor
            meta_ext = MetadataExtractor(self.config)
            for file_path in self.file_categories:
                try:
                    metadata_map[file_path] = meta_ext.extract(Path(file_path))
                except Exception:
                    metadata_map[file_path] = {}
        except Exception:
            pass

        self.status_label.setText("Organizing...")

        self.organize_worker = OrganizeWorker(self.file_categories, self.organizer, metadata_map)
        self.organize_worker.progress.connect(self._on_progress)
        self.organize_worker.status_update.connect(self._on_status)
        self.organize_worker.finished_organize.connect(self._on_finished)
        self.organize_worker.start()

    def _cancel_organize(self):
        if self.organize_worker and self.organize_worker.isRunning():
            self.organize_worker.cancel()
            self.organize_btn.setText("📁 Organize Files")
            self.organize_btn.setStyleSheet("padding: 12px 24px; font-size: 14px;")
            self.organize_btn.setObjectName("primary")
            self.status_label.setText("Cancelling...")
            self.organize_worker.wait(5000)

    def _on_progress(self, processed, total, success_count):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(processed)
        self.status_label.setText(f"Processing {processed}/{total} ({success_count} moved)")

    def _on_status(self, msg: str):
        self.status_label.setText(msg)

    def _on_finished(self, results: list):
        """Handle organize completion."""
        self.progress_bar.setVisible(False)
        self.organize_btn.setText("📁 Organize Files")
        self.organize_btn.setStyleSheet("padding: 12px 24px; font-size: 14px;")
        self.organize_btn.setObjectName("primary")

        success_count = sum(1 for r in results if r["success"])
        total = len(results)

        # Update preview table (only the rows we showed)
        preview_count = min(len(results), self.preview_table.rowCount())
        for i in range(preview_count):
            result = results[i]
            status = "✅ Moved" if result["success"] else "❌ Failed"
            item = QTableWidgetItem(status)
            item.setForeground(QColor("green") if result["success"] else QColor("red"))
            self.preview_table.setItem(i, 4, item)

        self.status_label.setText(f"Organized: {success_count}/{total} files moved successfully")
        QMessageBox.information(
            self, "Organization Complete",
            f"Successfully moved {success_count} of {total} files.\n"
            "Use Undo to reverse any moves.",
        )

    def _undo_last(self):
        success, message = self.organizer.op_history.undo_last()
        if success:
            QMessageBox.information(self, "Undo", message)
            self.status_label.setText(f"Undone: {message}")
        else:
            QMessageBox.warning(self, "Undo", message)
