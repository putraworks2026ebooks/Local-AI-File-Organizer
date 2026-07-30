"""
Organize view for Local AI File Organizer.
Shows proposed actions, requires user approval, and executes file moves.
"""

from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox, QMessageBox,
    QCheckBox, QFileDialog, QLineEdit, QComboBox
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor

from core.organizer import FileOrganizer
from database.db_manager import DatabaseManager
from utils.helpers import format_file_size
from utils.logger import get_logger


class OrganizeView(QWidget):
    """Organize interface for moving files to category folders."""

    def __init__(self, config: dict, db: DatabaseManager, organizer: FileOrganizer):
        super().__init__()
        self.config = config
        self.db = db
        self.organizer = organizer
        self.file_categories: dict[str, str] = {}
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
        opts_layout = QHBoxLayout()

        self.photos_by_date = QCheckBox("Organize photos by year/month")
        self.photos_by_date.setChecked(self.config.get("organize", {}).get("photo_organize_by_date", True))
        opts_layout.addWidget(self.photos_by_date)

        self.create_folders = QCheckBox("Create category folders")
        self.create_folders.setChecked(self.config.get("organize", {}).get("create_category_folders", True))
        opts_layout.addWidget(self.create_folders)

        opts_group.setLayout(opts_layout)
        layout.addWidget(opts_group)

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
        self.organize_btn.clicked.connect(self._organize_files)
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
        """Set the file-to-category mapping."""
        self.file_categories = file_categories
        self.status_label.setText(f"{len(file_categories)} files ready for organization")
        self._generate_preview()

    def set_config(self, config: dict):
        """Update config and organizer settings."""
        self.config = config
        self.organizer.update_config(config)
        self.output_edit.setText(config.get("organize", {}).get("output_base", ""))
        self.photos_by_date.setChecked(config.get("organize", {}).get("photo_organize_by_date", True))
        self.create_folders.setChecked(config.get("organize", {}).get("create_category_folders", True))

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder")
        if folder:
            self.output_edit.setText(folder)

    def _generate_preview(self):
        """Generate a preview of proposed actions."""
        if not self.file_categories:
            self.status_label.setText("No files to organize. Run analysis first.")
            return

        output_base = self.output_edit.text().strip()
        if not output_base:
            self.status_label.setText("Please select an output folder first.")
            return

        # Update config
        organize_config = self.config.setdefault("organize", {})
        organize_config["output_base"] = output_base
        organize_config["photo_organize_by_date"] = self.photos_by_date.isChecked()
        organize_config["create_category_folders"] = self.create_folders.isChecked()
        self.organizer.update_config(self.config)

        self.preview_table.setRowCount(len(self.file_categories))

        for i, (file_path, category) in enumerate(self.file_categories.items()):
            dest_dir = self.organizer.get_category_path(category, file_path)
            dest_path = dest_dir / Path(file_path).name

            self.preview_table.setItem(i, 0, QTableWidgetItem(Path(file_path).name))
            self.preview_table.setItem(i, 1, QTableWidgetItem(str(Path(file_path).parent)))
            self.preview_table.setItem(i, 2, QTableWidgetItem(category))
            self.preview_table.setItem(i, 3, QTableWidgetItem(str(dest_path)))
            self.preview_table.setItem(i, 4, QTableWidgetItem("Pending"))

        self.status_label.setText(f"Preview: {len(self.file_categories)} files to organize")

    def _organize_files(self):
        """Execute file organization with user confirmation."""
        if not self.file_categories:
            QMessageBox.warning(self, "No Files", "No files to organize.")
            return

        output_base = self.output_edit.text().strip()
        if not output_base:
            QMessageBox.warning(self, "No Output", "Please select an output folder.")
            return

        # Confirmation
        reply = QMessageBox.question(
            self, "Confirm Organization",
            f"Move {len(self.file_categories)} files to category folders in:\n{output_base}\n\n"
            "No files will be deleted. You can undo any move later.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # Update config
        organize_config = self.config.setdefault("organize", {})
        organize_config["output_base"] = output_base
        organize_config["photo_organize_by_date"] = self.photos_by_date.isChecked()
        organize_config["create_category_folders"] = self.create_folders.isChecked()
        self.organizer.update_config(self.config)

        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(self.file_categories))
        self.progress_bar.setValue(0)
        self.organize_btn.setEnabled(False)

        results = self.organizer.organize_files(
            self.file_categories,
            progress_callback=self._on_progress,
        )

        # Update table with results
        success_count = 0
        for i, result in enumerate(results):
            status = "✅ Moved" if result["success"] else "❌ Failed"
            item = QTableWidgetItem(status)
            if result["success"]:
                item.setForeground(QColor("green"))
                success_count += 1
            else:
                item.setForeground(QColor("red"))
            self.preview_table.setItem(i, 4, item)

        self.progress_bar.setVisible(False)
        self.organize_btn.setEnabled(True)
        self.status_label.setText(
            f"Organized: {success_count}/{len(results)} files moved successfully"
        )
        QMessageBox.information(
            self, "Organization Complete",
            f"Successfully moved {success_count} of {len(results)} files.\n"
            "Use Undo to reverse any moves.",
        )

    def _on_progress(self, processed, total, success_count):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(processed)
        self.status_label.setText(
            f"Processing {processed}/{total} ({success_count} succeeded)"
        )

    def _undo_last(self):
        """Undo the last move operation."""
        success, message = self.organizer.op_history.undo_last()
        if success:
            QMessageBox.information(self, "Undo", message)
            self.status_label.setText(f"Undone: {message}")
        else:
            QMessageBox.warning(self, "Undo", message)
