"""
Main application window for Local AI File Organizer.
Provides tabbed interface with all views and global controls.
"""

import json
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStatusBar, QToolBar, QFileDialog, QMessageBox,
    QProgressBar, QLineEdit, QComboBox, QMenu, QMenuBar, QDialog, QFormLayout,
    QSpinBox, QCheckBox, QInputDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QRadioButton, QButtonGroup, QSplitter, QFrame
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread, QObject, QSize
from PySide6.QtGui import QAction, QIcon, QFont, QColor

from ui.theme import ThemeManager
from ui.dashboard import DashboardWidget
from ui.scan_view import ScanView
from ui.analyze_view import AnalyzeView
from ui.organize_view import OrganizeView
from ui.quick_organize_view import QuickOrganizeView
from ui.duplicates_view import DuplicatesView
from ui.settings_view import SettingsView
from ui.logs_view import LogsView

from utils.config import ConfigManager
from utils.logger import get_logger
from database.db_manager import DatabaseManager
from database.operations import OperationHistory
from core.ollama_client import OllamaClient
from core.organizer import FileOrganizer
from core.duplicate_finder import DuplicateFinder
from core.metadata import MetadataExtractor
from core.content_reader import ContentReader
from core.ocr import OCRProcessor


class MainWindow(QMainWindow):
    """Main application window with tabbed interface."""

    def __init__(self):
        super().__init__()
        self.config_manager = ConfigManager()
        self.config = self.config_manager.config

        # Initialize database
        db_path = self.config_manager.db_settings.get("path", "file_organizer.db")
        self.db = DatabaseManager(db_path)
        self.op_history = OperationHistory(self.db)

        # Initialize core services
        self.ollama = OllamaClient(
            server_url=self.config_manager.ollama_settings.get("server_url", "http://localhost:11434"),
            model=self.config_manager.ollama_settings.get("model", "llama3.1"),
            timeout=self.config_manager.ollama_settings.get("timeout", 60),
            temperature=self.config_manager.ollama_settings.get("temperature", 0.1),
            max_tokens=self.config_manager.ollama_settings.get("max_tokens", 100),
        )
        self.organizer = FileOrganizer(self.db, self.op_history, self.config)
        self.duplicate_finder = DuplicateFinder()
        self.metadata_extractor = MetadataExtractor()
        self.content_reader = ContentReader()
        self.ocr = OCRProcessor(
            enabled=self.config_manager.ocr_settings.get("enabled", False),
            language=self.config_manager.ocr_settings.get("language", "eng"),
            max_pages=self.config_manager.ocr_settings.get("max_pages", 10),
        )
        self.logger = get_logger(self.config)
        self.logger.set_signal_callback(self._on_log_message)

        # Theme
        self.theme_manager = ThemeManager()
        self.theme_manager.set_theme(self.config_manager.ui_settings.get("theme", "dark"))

        # State
        self.scanned_files: list[dict] = []
        self.file_categories: dict[str, str] = {}
        self.scanned_file_hashes: dict[str, str] = {}

        # UI setup
        self._init_ui()
        self._init_menu()
        self._init_toolbar()
        self._init_statusbar()
        self._apply_theme()

        self.logger.info("Application initialized successfully")

    def _init_ui(self):
        """Initialize the main UI with tabs."""
        self.setWindowTitle("Local AI File Organizer")
        ui_config = self.config_manager.ui_settings
        self.resize(ui_config.get("window_width", 1400), ui_config.get("window_height", 900))

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        # Create views
        self.dashboard = DashboardWidget(self.db, self.config)
        self.scan_view = ScanView(self.config, self.db, self.ollama)
        self.analyze_view = AnalyzeView(self.config, self.db, self.ollama,
                                         self.metadata_extractor, self.content_reader, self.ocr)
        self.organize_view = OrganizeView(self.config, self.db, self.organizer)
        self.duplicates_view = DuplicatesView(self.config, self.db, self.duplicate_finder)
        self.settings_view = SettingsView(self.config_manager, self.ollama, self.db)
        self.logs_view = LogsView()

        # Quick Organize tab
        self.quick_organize_view = QuickOrganizeView(
            self.config, self.db, self.ollama, self.organizer,
            self.metadata_extractor, self.content_reader, self.ocr
        )

        # Add tabs
        self.tabs.addTab(self.dashboard, "📊 Dashboard")
        self.tabs.addTab(self.quick_organize_view, "⚡ Quick Organize")
        self.tabs.addTab(self.scan_view, "🔍 Scan")
        self.tabs.addTab(self.analyze_view, "🤖 Analyze")
        self.tabs.addTab(self.organize_view, "📁 Organize")
        self.tabs.addTab(self.duplicates_view, "👥 Duplicates")
        self.tabs.addTab(self.settings_view, "⚙️ Settings")
        self.tabs.addTab(self.logs_view, "📋 Logs")

        # Connect signals
        self.scan_view.scan_complete.connect(self._on_scan_complete)
        self.analyze_view.analysis_complete.connect(self._on_analysis_complete)
        self.scan_view.scan_progress.connect(self._update_progress)
        self.quick_organize_view.finished_organize.connect(self._on_quick_organize_finished)

        layout.addWidget(self.tabs)
        self.setCentralWidget(central)

    def _init_menu(self):
        """Initialize the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        open_action = QAction("Add Scan Folder...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._add_scan_folder)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        export_action = QAction("Export Results...", self)
        export_action.triggered.connect(self._export_results)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        undo_action = QAction("Undo Last Operation", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.triggered.connect(self._undo_last)
        edit_menu.addAction(undo_action)

        redo_action = QAction("Undo All Operations", self)
        redo_action.triggered.connect(self._undo_all)
        edit_menu.addAction(redo_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        theme_action = QAction("Toggle Dark/Light Mode", self)
        theme_action.setShortcut("Ctrl+T")
        theme_action.triggered.connect(self._toggle_theme)
        view_menu.addAction(theme_action)

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")

        empty_folders = QAction("Find Empty Folders...", self)
        empty_folders.triggered.connect(self._find_empty_folders)
        tools_menu.addAction(empty_folders)

        large_files = QAction("Find Large Files...", self)
        large_files.triggered.connect(self._find_large_files)
        tools_menu.addAction(large_files)

        disk_analysis = QAction("Disk Usage Analysis...", self)
        disk_analysis.triggered.connect(self._disk_analysis)
        tools_menu.addAction(disk_analysis)

        # Help menu
        help_menu = menubar.addMenu("&Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _init_toolbar(self):
        """Initialize the toolbar."""
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))

        scan_btn = QAction("🔍 Scan", self)
        scan_btn.triggered.connect(lambda: self.tabs.setCurrentIndex(1))
        toolbar.addAction(scan_btn)

        analyze_btn = QAction("🤖 Analyze", self)
        analyze_btn.triggered.connect(lambda: self.tabs.setCurrentIndex(2))
        toolbar.addAction(analyze_btn)

        organize_btn = QAction("📁 Organize", self)
        organize_btn.triggered.connect(lambda: self.tabs.setCurrentIndex(3))
        toolbar.addAction(organize_btn)

        duplicates_btn = QAction("👥 Duplicates", self)
        duplicates_btn.triggered.connect(lambda: self.tabs.setCurrentIndex(4))
        toolbar.addAction(duplicates_btn)

        toolbar.addSeparator()

        undo_btn = QAction("↩️ Undo", self)
        undo_btn.setShortcut("Ctrl+Z")
        undo_btn.triggered.connect(self._undo_last)
        toolbar.addAction(undo_btn)

        toolbar.addSeparator()

        theme_btn = QAction("🌗 Toggle Theme", self)
        theme_btn.triggered.connect(self._toggle_theme)
        toolbar.addAction(theme_btn)

    def _init_statusbar(self):
        """Initialize the status bar."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_label = QLabel("Ready")
        self.status_bar.addWidget(self.status_label, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(300)
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)

        self.file_count_label = QLabel("0 files")
        self.status_bar.addPermanentWidget(self.file_count_label)

    def _apply_theme(self):
        """Apply the current theme stylesheet."""
        self.setStyleSheet(self.theme_manager.get_stylesheet())

    def _toggle_theme(self):
        """Toggle between dark and light themes."""
        new_theme = self.theme_manager.toggle()
        self._apply_theme()
        self.config_manager.set("ui", "theme", new_theme)
        self.config_manager.save()
        self.status_bar.showMessage(f"Theme: {new_theme.capitalize()}", 2000)

    def _add_scan_folder(self):
        """Add a folder to scan."""
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Scan")
        if folder:
            self.scan_view.add_scan_path(folder)
            self.status_bar.showMessage(f"Added: {folder}", 2000)

    def _on_scan_complete(self, files: list[dict], total_size: int):
        """Handle scan completion."""
        self.scanned_files = files
        self.file_count_label.setText(f"{len(files)} files")
        self.dashboard.update_stats()
        self.status_bar.showMessage(f"Scan complete: {len(files)} files found", 3000)
        self.progress_bar.setVisible(False)

        # Pass files to analyze view
        self.analyze_view.set_files(files)

    def _on_analysis_complete(self, file_categories: dict):
        """Handle analysis completion."""
        self.file_categories = file_categories
        self.organize_view.set_file_categories(file_categories)
        self.dashboard.update_stats()

    def _on_quick_organize_finished(self, results: dict):
        """Handle quick organize completion."""
        scanned = results.get("scanned", 0)
        organized = results.get("organized", 0)
        self.file_count_label.setText(f"{organized} files organized")
        self.dashboard.update_stats()
        self.status_bar.showMessage(
            f"Quick organize done: {scanned} scanned, {organized} organized", 5000
        )

    def _update_progress(self, current: int, total: int):
        """Update progress bar."""
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def _on_log_message(self, entry: str):
        """Forward log messages to the logs view."""
        self.logs_view.append_log(entry)

    def _undo_last(self):
        """Undo the last operation."""
        success, message = self.op_history.undo_last()
        if success:
            QMessageBox.information(self, "Undo", message)
            self.dashboard.update_stats()
        else:
            QMessageBox.warning(self, "Undo", message)

    def _undo_all(self):
        """Undo all operations — run in worker thread to avoid UI freeze."""
        reply = QMessageBox.question(
            self, "Undo All",
            "This will undo ALL operations. This may take a moment.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.status_bar.showMessage("Undoing all operations...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate

        class UndoWorker(QThread):
            from PySide6.QtCore import Signal
            finished_undo = Signal(list)
            def __init__(self, op_history):
                super().__init__()
                self.op_history = op_history
            def run(self):
                results = self.op_history.undo_all()
                self.finished_undo.emit(results)

        self._undo_worker = UndoWorker(self.op_history)
        self._undo_worker.finished_undo.connect(lambda results: self._on_undo_all_complete(results))
        self._undo_worker.start()

    def _on_undo_all_complete(self, results):
        self.progress_bar.setVisible(False)
        success = sum(1 for s, _ in results if s)
        total = len(results)
        QMessageBox.information(self, "Undo All", f"Undone {success}/{total} operations.")
        self.dashboard.update_stats()
        self.status_bar.showMessage("", 3000)

    def _find_empty_folders(self):
        """Find empty folders — run in a worker thread to avoid UI freeze."""
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Check")
        if not folder:
            return

        self.status_bar.showMessage("Scanning for empty folders...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        from PySide6.QtCore import QThread

        class EmptyFolderWorker(QThread):
            from PySide6.QtCore import Signal
            finished_scan = Signal(list)
            def __init__(self, path):
                super().__init__()
                self.path = path
            def run(self):
                import os
                empty = []
                for dirpath, dirnames, filenames in os.walk(self.path):
                    if not dirnames and not filenames:
                        empty.append(dirpath)
                self.finished_scan.emit(empty)

        self._empty_worker = EmptyFolderWorker(folder)
        self._empty_worker.finished_scan.connect(lambda empty: self._on_empty_folders_found(empty))
        self._empty_worker.start()

    def _on_empty_folders_found(self, empty: list):
        self.progress_bar.setVisible(False)
        if empty:
            self.logs_view.append_log(f"Found {len(empty)} empty folders:")
            for f in empty[:200]:
                self.logs_view.append_log(f"  {f}")
        else:
            QMessageBox.information(self, "Empty Folders", "No empty folders found.")
        self.status_bar.showMessage("", 3000)

    def _find_large_files(self):
        """Find large files — instant (just a DB query, no threading needed)."""
        threshold, ok = QInputDialog.getInt(
            self, "Large File Finder",
            "Minimum file size (MB):", 1000, 1, 100000,
        )
        if not ok:
            return

        self.status_bar.showMessage("Finding large files...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate

        from PySide6.QtCore import QTimer

        class LargeFilesWorker(QThread):
            from PySide6.QtCore import Signal
            finished_search = Signal(list, int)
            def __init__(self, db, organizer, threshold):
                super().__init__()
                self.db = db
                self.organizer = organizer
                self.threshold = threshold
            def run(self):
                files = self.db.get_all_files()
                large = self.organizer.find_large_files(files, self.threshold)
                self.finished_search.emit(large, self.threshold)

        self._large_worker = LargeFilesWorker(self.db, self.organizer, threshold)
        self._large_worker.finished_search.connect(lambda large, t: self._on_large_files_found(large, t))
        self._large_worker.start()

    def _on_large_files_found(self, large: list, threshold: int):
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("", 3000)
        if large:
            from utils.helpers import format_file_size
            self.logs_view.append_log(f"Found {len(large)} files > {threshold}MB:")
            for f in large[:50]:
                size = format_file_size(f.get("size_bytes", 0))
                self.logs_view.append_log(f"  {size}  {f.get('file_path', '')}")
        else:
            QMessageBox.information(self, "Large Files", "No large files found.")

    def _disk_analysis(self):
        """Show disk usage analysis."""
        folder = QFileDialog.getExistingDirectory(self, "Select Drive/Folder to Analyze")
        if folder:
            analysis = self.organizer.get_disk_usage_analysis(folder)
            from utils.helpers import format_file_size
            msg = f"Disk Usage: {analysis['percent_used']}% used\n\n"
            msg += f"Total: {format_file_size(analysis['disk_total'])}\n"
            msg += f"Used: {format_file_size(analysis['disk_used'])}\n"
            msg += f"Free: {format_file_size(analysis['disk_free'])}\n\nBy Category:\n"
            for cat, info in analysis["by_category"].items():
                msg += f"  {cat}: {info['formatted']}\n"
            QMessageBox.information(self, "Disk Usage Analysis", msg)

    def _export_results(self):
        """Export results — run in worker thread for large datasets."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Results", "organizer_results.json", "JSON Files (*.json)"
        )
        if not path:
            return

        self.status_bar.showMessage("Exporting...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate

        class ExportWorker(QThread):
            from PySide6.QtCore import Signal
            finished_export = Signal(bool, str)
            def __init__(self, filepath, scanned_files, file_categories, db):
                super().__init__()
                self.filepath = filepath
                self.scanned_files = scanned_files
                self.file_categories = file_categories
                self.db = db
            def run(self):
                try:
                    data = {
                        "files": self.scanned_files,
                        "categories": self.file_categories,
                        "stats": {
                            "total_files": self.db.get_file_count(),
                            "total_size": self.db.get_total_size(),
                            "category_stats": self.db.get_category_stats(),
                        },
                    }
                    with open(self.filepath, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, default=str)
                    self.finished_export.emit(True, self.filepath)
                except Exception as e:
                    self.finished_export.emit(False, str(e))

        self._export_worker = ExportWorker(path, self.scanned_files, self.file_categories, self.db)
        self._export_worker.finished_export.connect(lambda ok, msg: self._on_export_complete(ok, msg))
        self._export_worker.start()

    def _on_export_complete(self, ok: bool, msg: str):
        self.progress_bar.setVisible(False)
        if ok:
            self.status_bar.showMessage(f"Exported to {msg}", 3000)
        else:
            QMessageBox.warning(self, "Export Failed", msg)
            self.status_bar.showMessage("", 3000)

    def _show_about(self):
        """Show about dialog."""
        QMessageBox.about(
            self, "About Local AI File Organizer",
            "<h3>Local AI File Organizer</h3>"
            "<p>Version 1.2 — Full Performance Optimization</p>"
            "<p>A completely local AI-powered file organizer for Windows 10/11.</p>"
            "<p>Powered by Ollama for AI classification. No cloud services required.</p>"
            "<p>All processing happens on your machine.</p>",
        )

    def closeEvent(self, event):
        """Save state on close."""
        # Save window size
        self.config_manager.set("ui", "window_width", self.width())
        self.config_manager.set("ui", "window_height", self.height())
        self.config_manager.save()

        # Disconnect database
        self.db.disconnect()
        event.accept()


def main():
    """Application entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName("Local AI File Organizer")
    app.setOrganizationName("LocalAI")

    # Set application-wide font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
