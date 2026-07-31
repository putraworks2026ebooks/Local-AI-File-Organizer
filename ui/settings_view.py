"""
Settings view for Local AI File Organizer.
Allows configuration of all application settings.
"""

import json
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QSpinBox, QDoubleSpinBox, QCheckBox, QComboBox, QGroupBox, QFormLayout,
    QTabWidget, QFileDialog, QListWidget, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QInputDialog, QTextEdit
)
from PySide6.QtCore import Qt, Signal

from utils.config import ConfigManager
from core.ollama_client import OllamaClient
from database.db_manager import DatabaseManager


class SettingsView(QWidget):
    """Settings configuration interface."""

    settings_changed = Signal(dict)

    def __init__(self, config_manager: ConfigManager, ollama: OllamaClient,
                 db: DatabaseManager):
        super().__init__()
        self.config_manager = config_manager
        self.ollama = ollama
        self.db = db
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("⚙️ Settings")
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)

        # Tabbed settings
        self.settings_tabs = QTabWidget()

        self.settings_tabs.addTab(self._build_ai_tab(), "🤖 AI / Ollama")
        self.settings_tabs.addTab(self._build_scan_tab(), "🔍 Scan")
        self.settings_tabs.addTab(self._build_organize_tab(), "📁 Organize")
        self.settings_tabs.addTab(self._build_categories_tab(), "📂 Categories")
        self.settings_tabs.addTab(self._build_advanced_tab(), "🔧 Advanced")
        self.settings_tabs.addTab(self._build_scheduling_tab(), "⏰ Scheduling")
        self.settings_tabs.addTab(self._build_appearance_tab(), "🎨 Appearance")

        layout.addWidget(self.settings_tabs)

        # Save / Reset buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        reset_btn = QPushButton("↩️ Reset to Defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        btn_layout.addWidget(reset_btn)

        save_btn = QPushButton("💾 Save Settings")
        save_btn.setObjectName("primary")
        save_btn.setStyleSheet("padding: 10px 24px; font-size: 14px;")
        save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def _build_ai_tab(self) -> QWidget:
        """Build AI / Ollama settings tab."""
        tab = QWidget()
        layout = QFormLayout(tab)
        ai_config = self.config_manager.ollama_settings

        self.ai_url = QLineEdit(ai_config.get("server_url", "http://localhost:11434"))
        layout.addRow("Ollama Server URL:", self.ai_url)

        self.ai_model = QLineEdit(ai_config.get("model", "qwen2.5:3b"))
        layout.addRow("AI Model:", self.ai_model)

        test_btn = QPushButton("Test Connection")
        test_btn.clicked.connect(self._test_ollama)
        layout.addRow("", test_btn)

        self.ai_timeout = QSpinBox()
        self.ai_timeout.setRange(5, 600)
        self.ai_timeout.setValue(ai_config.get("timeout", 60))
        layout.addRow("Timeout (seconds):", self.ai_timeout)

        self.ai_temp = QDoubleSpinBox()
        self.ai_temp.setRange(0.0, 2.0)
        self.ai_temp.setSingleStep(0.1)
        self.ai_temp.setValue(ai_config.get("temperature", 0.1))
        layout.addRow("Temperature:", self.ai_temp)

        self.ai_max_tokens = QSpinBox()
        self.ai_max_tokens.setRange(10, 4096)
        self.ai_max_tokens.setValue(ai_config.get("max_tokens", 100))
        layout.addRow("Max Tokens:", self.ai_max_tokens)

        return tab

    def _build_scan_tab(self) -> QWidget:
        """Build scan settings tab."""
        tab = QWidget()
        layout = QFormLayout(tab)
        scan_config = self.config_manager.scan_settings

        self.scan_workers = QSpinBox()
        self.scan_workers.setRange(1, 32)
        self.scan_workers.setValue(scan_config.get("max_workers", 4))
        layout.addRow("Max Workers:", self.scan_workers)

        self.scan_max_size = QSpinBox()
        self.scan_max_size.setRange(1, 102400)
        self.scan_max_size.setValue(scan_config.get("max_file_size_mb", 512))
        layout.addRow("Max File Size (MB):", self.scan_max_size)

        self.scan_skip_system = QCheckBox("Skip system folders")
        self.scan_skip_system.setChecked(scan_config.get("skip_system_folders", True))
        layout.addRow("", self.scan_skip_system)

        self.scan_system_folders = QLineEdit(
            ", ".join(scan_config.get("system_folders", []))
        )
        layout.addRow("System folders (comma-separated):", self.scan_system_folders)

        self.scan_ignore_ext = QLineEdit(
            ", ".join(scan_config.get("ignore_extensions", []))
        )
        layout.addRow("Ignore extensions (comma-separated):", self.scan_ignore_ext)

        self.scan_incremental = QCheckBox("Enable incremental indexing")
        self.scan_incremental.setChecked(scan_config.get("incremental_indexing", True))
        layout.addRow("", self.scan_incremental)

        return tab

    def _build_organize_tab(self) -> QWidget:
        """Build organize settings tab — all organize options live here."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        org_config = self.config_manager.organize_settings

        # Output base folder
        out_group = QGroupBox("Output")
        out_layout = QFormLayout(out_group)
        self.org_output = QLineEdit(org_config.get("output_base", ""))
        out_layout.addRow("Output Base Folder:", self.org_output)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(lambda: self._browse_folder(self.org_output))
        out_layout.addRow("", browse_btn)
        layout.addWidget(out_group)

        # General options
        opts_group = QGroupBox("Options")
        opts_layout = QVBoxLayout(opts_group)

        self.org_photos_date = QCheckBox("Organize photos by year/month")
        self.org_photos_date.setChecked(org_config.get("photo_organize_by_date", True))
        opts_layout.addWidget(self.org_photos_date)

        self.org_create_folders = QCheckBox("Create category folders")
        self.org_create_folders.setChecked(org_config.get("create_category_folders", True))
        opts_layout.addWidget(self.org_create_folders)

        self.org_move_empty = QCheckBox("Move empty folders to ToBeDeleted")
        self.org_move_empty.setChecked(org_config.get("move_empty_folders", True))
        self.org_move_empty.setToolTip("After organizing, move empty source folders to a ToBeDeleted folder")
        opts_layout.addWidget(self.org_move_empty)

        # Max file size
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Max file size to organize (MB):"))
        self.org_max_size = QSpinBox()
        self.org_max_size.setRange(0, 999999)
        self.org_max_size.setValue(org_config.get("max_organize_size_mb", 0))
        self.org_max_size.setSpecialValueText("No limit")
        self.org_max_size.setToolTip("0 = no limit. Files larger than this are skipped during organize.")
        size_row.addWidget(self.org_max_size)
        size_row.addStretch()
        opts_layout.addLayout(size_row)

        # Bulk / 1-by-1 mode
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Processing mode:"))
        self.org_bulk_mode = QCheckBox("Bulk (all at once)")
        self.org_bulk_mode.setChecked(org_config.get("organize", {}).get("bulk_mode", True))
        mode_row.addWidget(self.org_bulk_mode)
        self.org_onebyone_mode = QCheckBox("1-by-1 (step through)")
        self.org_onebyone_mode.setChecked(not self.org_bulk_mode.isChecked())
        self.org_bulk_mode.toggled.connect(
            lambda checked: self.org_onebyone_mode.setChecked(not checked)
        )
        self.org_onebyone_mode.toggled.connect(
            lambda checked: self.org_bulk_mode.setChecked(not checked)
        )
        mode_row.addWidget(self.org_onebyone_mode)
        mode_row.addStretch()
        opts_layout.addLayout(mode_row)

        layout.addWidget(opts_group)

        # Duplicates folder name
        dup_row = QHBoxLayout()
        dup_row.addWidget(QLabel("Duplicates folder name:"))
        self.org_dup_folder = QLineEdit(org_config.get("duplicates_folder", "_Duplicates"))
        dup_row.addWidget(self.org_dup_folder)
        dup_row.addStretch()
        layout.addLayout(dup_row)

        # Date structure per category
        layout.addWidget(QLabel("Date structure per category:"))
        self.org_date_struct_table = QTableWidget()
        self.org_date_struct_table.setColumnCount(2)
        self.org_date_struct_table.setHorizontalHeaderLabels(["Category", "Date Structure"])
        self.org_date_struct_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.org_date_struct_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.org_date_struct_table.setMaximumHeight(250)
        self._populate_org_date_struct_table()
        layout.addWidget(self.org_date_struct_table)

        layout.addStretch()
        return tab

    def _populate_org_date_struct_table(self):
        """Populate date structure table in Settings."""
        import json as _json
        from pathlib import Path as _Path
        cat_path = _Path(__file__).parent.parent / "config" / "categories.json"
        with open(cat_path, "r") as _f:
            cats = [c["name"] for c in _json.load(_f)["categories"]]
        try:
            custom = self.db.get_custom_categories()
            cats.extend(c["name"] for c in custom if c["name"] not in cats)
        except Exception:
            pass

        saved = self.config_manager.config.get("organize", {}).get("date_structures", {})
        self.org_date_struct_table.setRowCount(len(cats))
        for i, cat in enumerate(cats):
            name_item = QTableWidgetItem(cat)
            name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.org_date_struct_table.setItem(i, 0, name_item)

            combo = QComboBox()
            combo.addItem("None (flat)", "none")
            combo.addItem("Year (2024)", "year")
            combo.addItem("Year/Month (2024/01)", "year_month")
            current = saved.get(cat, "none")
            idx = combo.findData(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            self.org_date_struct_table.setCellWidget(i, 1, combo)

    def _get_org_date_structures(self):
        """Read date structures from the Settings table."""
        structures = {}
        for i in range(self.org_date_struct_table.rowCount()):
            cat_item = self.org_date_struct_table.item(i, 0)
            combo = self.org_date_struct_table.cellWidget(i, 1)
            if cat_item and combo:
                struct = combo.currentData()
                if struct != "none":
                    structures[cat_item.text()] = struct
        return structures

    def _build_categories_tab(self) -> QWidget:
        """Build categories management tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Existing categories
        layout.addWidget(QLabel("Configured Categories:"))

        self.categories_table = QTableWidget()
        self.categories_table.setColumnCount(3)
        self.categories_table.setHorizontalHeaderLabels(["Category", "Extensions", "Keywords"])
        self.categories_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.categories_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.categories_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        layout.addWidget(self.categories_table)

        self._load_categories()

        # Custom category buttons
        btn_layout = QHBoxLayout()

        add_btn = QPushButton("➕ Add Custom Category")
        add_btn.clicked.connect(self._add_custom_category)
        btn_layout.addWidget(add_btn)

        del_btn = QPushButton("➖ Delete Custom")
        del_btn.clicked.connect(self._delete_custom_category)
        btn_layout.addWidget(del_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return tab

    def _build_advanced_tab(self) -> QWidget:
        """Build advanced settings tab."""
        tab = QWidget()
        layout = QFormLayout(tab)
        adv = self.config_manager.advanced_settings
        ocr = self.config_manager.ocr_settings

        self.ocr_enabled = QCheckBox("Enable OCR for scanned PDFs")
        self.ocr_enabled.setChecked(ocr.get("enabled", False))
        layout.addRow("", self.ocr_enabled)

        self.ocr_lang = QLineEdit(ocr.get("language", "eng"))
        layout.addRow("OCR Language:", self.ocr_lang)

        self.ocr_pages = QSpinBox()
        self.ocr_pages.setRange(1, 100)
        self.ocr_pages.setValue(ocr.get("max_pages", 10))
        layout.addRow("OCR Max Pages:", self.ocr_pages)

        self.empty_folders = QCheckBox("Empty folder detection")
        self.empty_folders.setChecked(adv.get("empty_folder_detection", True))
        layout.addRow("", self.empty_folders)

        self.large_threshold = QSpinBox()
        self.large_threshold.setRange(1, 102400)
        self.large_threshold.setValue(adv.get("large_file_threshold_mb", 1000))
        layout.addRow("Large file threshold (MB):", self.large_threshold)

        self.disk_analysis = QCheckBox("Disk usage analysis")
        self.disk_analysis.setChecked(adv.get("disk_usage_analysis", True))
        layout.addRow("", self.disk_analysis)

        self.zip_inspect = QCheckBox("ZIP archive inspection")
        self.zip_inspect.setChecked(adv.get("zip_inspection", True))
        layout.addRow("", self.zip_inspect)

        self.auto_downloads = QCheckBox("Automatic Downloads cleanup")
        self.auto_downloads.setChecked(adv.get("auto_downloads_cleanup", False))
        layout.addRow("", self.auto_downloads)

        self.downloads_path = QLineEdit(adv.get("downloads_path", ""))
        layout.addRow("Downloads path:", self.downloads_path)

        return tab

    def _build_scheduling_tab(self) -> QWidget:
        """Build scheduling settings tab."""
        tab = QWidget()
        layout = QFormLayout(tab)
        sched = self.config_manager.config.get("scheduling", {})

        self.sched_enabled = QCheckBox("Enable automatic scheduling")
        self.sched_enabled.setChecked(sched.get("enabled", False))
        layout.addRow("", self.sched_enabled)

        self.sched_interval = QSpinBox()
        self.sched_interval.setRange(1, 168)
        self.sched_interval.setValue(sched.get("interval_hours", 24))
        layout.addRow("Interval (hours):", self.sched_interval)

        self.sched_paths = QTextEdit()
        self.sched_paths.setPlainText("\n".join(sched.get("scan_paths", [])))
        self.sched_paths.setMaximumHeight(100)
        layout.addRow("Scan paths (one per line):", self.sched_paths)

        return tab

    def _build_appearance_tab(self) -> QWidget:
        """Build appearance settings tab."""
        tab = QWidget()
        layout = QFormLayout(tab)
        ui = self.config_manager.ui_settings

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["dark", "light"])
        self.theme_combo.setCurrentText(ui.get("theme", "dark"))
        layout.addRow("Theme:", self.theme_combo)

        self.win_width = QSpinBox()
        self.win_width.setRange(800, 3840)
        self.win_width.setValue(ui.get("window_width", 1400))
        layout.addRow("Window Width:", self.win_width)

        self.win_height = QSpinBox()
        self.win_height.setRange(600, 2160)
        self.win_height.setValue(ui.get("window_height", 900))
        layout.addRow("Window Height:", self.win_height)

        return tab

    def _load_categories(self):
        """Load categories into the table."""
        cat_path = Path(__file__).parent.parent / "config" / "categories.json"
        with open(cat_path, "r") as f:
            cat_config = json.load(f)

        categories = cat_config["categories"]
        custom = self.db.get_custom_categories()
        for c in custom:
            categories.append({"name": c["name"], "extensions": c.get("extensions", []),
                               "keywords": c.get("keywords", [])})

        self.categories_table.setRowCount(len(categories))
        for i, cat in enumerate(categories):
            self.categories_table.setItem(i, 0, QTableWidgetItem(cat["name"]))
            self.categories_table.setItem(i, 1, QTableWidgetItem(", ".join(cat["extensions"])))
            self.categories_table.setItem(i, 2, QTableWidgetItem(", ".join(cat["keywords"])))

    def _add_custom_category(self):
        """Add a custom category."""
        name, ok = QInputDialog.getText(self, "Custom Category", "Category name:")
        if not ok or not name:
            return

        exts, ok = QInputDialog.getText(
            self, "Extensions", "Extensions (comma-separated, e.g. .xyz,.abc):"
        )
        if not ok:
            return

        keywords, ok = QInputDialog.getText(
            self, "Keywords", "Keywords (comma-separated):"
        )
        if not ok:
            return

        ext_list = [e.strip() for e in exts.split(",") if e.strip()]
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()]

        self.db.add_custom_category(name, ext_list, kw_list)
        self._load_categories()

    def _delete_custom_category(self):
        """Delete a custom category."""
        row = self.categories_table.currentRow()
        if row < 0:
            return
        name = self.categories_table.item(row, 0).text()
        self.db.delete_custom_category(name)
        self._load_categories()

    def _browse_folder(self, line_edit: QLineEdit):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            line_edit.setText(folder)

    def _test_ollama(self):
        """Test Ollama connection."""
        url = self.ai_url.text().strip()
        self.ollama.update_settings(server_url=url)
        if self.ollama.is_available():
            models = self.ollama.list_models()
            QMessageBox.information(
                self, "Connection OK",
                f"Connected to Ollama at {url}\nAvailable models: {', '.join(models)}",
            )
        else:
            QMessageBox.warning(
                self, "Connection Failed",
                f"Could not connect to Ollama at {url}\n"
                "Make sure Ollama is running.",
            )

    def _save_settings(self):
        """Save all settings."""
        config = self.config_manager.config

        # AI settings
        config["ollama"]["server_url"] = self.ai_url.text().strip()
        config["ollama"]["model"] = self.ai_model.text().strip()
        config["ollama"]["timeout"] = self.ai_timeout.value()
        config["ollama"]["temperature"] = self.ai_temp.value()
        config["ollama"]["max_tokens"] = self.ai_max_tokens.value()

        # Scan settings
        config["scan"]["max_workers"] = self.scan_workers.value()
        config["scan"]["max_file_size_mb"] = self.scan_max_size.value()
        config["scan"]["skip_system_folders"] = self.scan_skip_system.isChecked()
        config["scan"]["system_folders"] = [
            s.strip() for s in self.scan_system_folders.text().split(",") if s.strip()
        ]
        config["scan"]["ignore_extensions"] = [
            s.strip() for s in self.scan_ignore_ext.text().split(",") if s.strip()
        ]
        config["scan"]["incremental_indexing"] = self.scan_incremental.isChecked()

        # Organize settings
        config["organize"]["output_base"] = self.org_output.text().strip()
        config["organize"]["photo_organize_by_date"] = self.org_photos_date.isChecked()
        config["organize"]["create_category_folders"] = self.org_create_folders.isChecked()
        config["organize"]["duplicates_folder"] = self.org_dup_folder.text().strip()
        config["organize"]["move_empty_folders"] = self.org_move_empty.isChecked()
        config["organize"]["max_organize_size_mb"] = self.org_max_size.value()
        config["organize"]["bulk_mode"] = self.org_bulk_mode.isChecked()
        config["organize"]["date_structures"] = self._get_org_date_structures()

        # Advanced settings
        config["ocr"]["enabled"] = self.ocr_enabled.isChecked()
        config["ocr"]["language"] = self.ocr_lang.text().strip()
        config["ocr"]["max_pages"] = self.ocr_pages.value()
        config["advanced"]["empty_folder_detection"] = self.empty_folders.isChecked()
        config["advanced"]["large_file_threshold_mb"] = self.large_threshold.value()
        config["advanced"]["disk_usage_analysis"] = self.disk_analysis.isChecked()
        config["advanced"]["zip_inspection"] = self.zip_inspect.isChecked()
        config["advanced"]["auto_downloads_cleanup"] = self.auto_downloads.isChecked()
        config["advanced"]["downloads_path"] = self.downloads_path.text().strip()

        # Scheduling
        config["scheduling"]["enabled"] = self.sched_enabled.isChecked()
        config["scheduling"]["interval_hours"] = self.sched_interval.value()
        config["scheduling"]["scan_paths"] = [
            p.strip() for p in self.sched_paths.toPlainText().split("\n") if p.strip()
        ]

        # UI settings
        config["ui"]["theme"] = self.theme_combo.currentText()
        config["ui"]["window_width"] = self.win_width.value()
        config["ui"]["window_height"] = self.win_height.value()

        # Update Ollama client
        self.ollama.update_settings(
            server_url=config["ollama"]["server_url"],
            model=config["ollama"]["model"],
            timeout=config["ollama"]["timeout"],
            temperature=config["ollama"]["temperature"],
            max_tokens=config["ollama"]["max_tokens"],
        )

        self.config_manager.save(config)
        self.settings_changed.emit(config)
        QMessageBox.information(self, "Settings Saved", "All settings have been saved.")

    def _reset_defaults(self):
        """Reset to default configuration."""
        reply = QMessageBox.question(
            self, "Reset Settings",
            "Reset all settings to defaults? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            import os
            user_config = Path(__file__).parent.parent / "config" / "user_config.json"
            if user_config.exists():
                os.remove(str(user_config))
            self.config_manager.load()
            QMessageBox.information(self, "Reset Complete", "Settings reset to defaults.")
