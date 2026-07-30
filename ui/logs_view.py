"""
Logs view for Local AI File Organizer.
Displays real-time and historical operation logs.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
    QComboBox, QCheckBox, QGroupBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QTabWidget
)
from PySide6.QtCore import Qt, QTimer

from utils.logger import get_logger


class LogsView(QWidget):
    """Logs viewer interface."""

    def __init__(self):
        super().__init__()
        self.logger = get_logger()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("📋 Logs")
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)

        # Tabbed: Live logs + Operation history
        self.log_tabs = QTabWidget()

        # Live log tab
        live_tab = QWidget()
        live_layout = QVBoxLayout(live_tab)

        # Controls
        ctrl_layout = QHBoxLayout()

        ctrl_layout.addWidget(QLabel("Filter:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["All", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.filter_combo.currentTextChanged.connect(self._refresh_logs)
        ctrl_layout.addWidget(self.filter_combo)

        self.auto_scroll = QCheckBox("Auto-scroll")
        self.auto_scroll.setChecked(True)
        ctrl_layout.addWidget(self.auto_scroll)

        ctrl_layout.addStretch()

        clear_btn = QPushButton("🗑️ Clear")
        clear_btn.clicked.connect(self._clear_logs)
        ctrl_layout.addWidget(clear_btn)

        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self._refresh_logs)
        ctrl_layout.addWidget(refresh_btn)

        live_layout.addLayout(ctrl_layout)

        # Log text area
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("font-family: Consolas, monospace; font-size: 12px;")
        live_layout.addWidget(self.log_text)

        self.log_tabs.addTab(live_tab, "📡 Live Logs")

        # Operation history tab
        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(6)
        self.history_table.setHorizontalHeaderLabels(
            ["ID", "Type", "Timestamp", "File", "Category", "Undone"]
        )
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.history_table.setAlternatingRowColors(True)

        history_layout.addWidget(self.history_table)

        hist_btn_layout = QHBoxLayout()
        hist_btn_layout.addStretch()

        load_btn = QPushButton("🔄 Load History")
        load_btn.clicked.connect(self._load_history)
        hist_btn_layout.addWidget(load_btn)

        history_layout.addLayout(hist_btn_layout)

        self.log_tabs.addTab(history_tab, "📜 Operation History")

        layout.addWidget(self.log_tabs)

        # Auto-refresh timer
        self.timer = QTimer()
        self.timer.timeout.connect(self._refresh_logs)
        self.timer.start(2000)

        self._refresh_logs()

    def append_log(self, entry: str):
        """Append a log entry to the display."""
        filter_level = self.filter_combo.currentText()
        if filter_level != "All" and filter_level not in entry:
            return

        self.log_text.append(entry)

        if self.auto_scroll.isChecked():
            self.log_text.verticalScrollBar().setValue(
                self.log_text.verticalScrollBar().maximum()
            )

    def _refresh_logs(self):
        """Refresh log display from the logger."""
        filter_level = self.filter_combo.currentText()
        logs = self.logger.get_recent_logs(200)

        self.log_text.clear()
        for entry in logs:
            if filter_level == "All" or filter_level in entry:
                self.log_text.append(entry)

        if self.auto_scroll.isChecked():
            self.log_text.verticalScrollBar().setValue(
                self.log_text.verticalScrollBar().maximum()
            )

    def _clear_logs(self):
        """Clear log display."""
        self.logger.clear_logs()
        self.log_text.clear()

    def _load_history(self):
        """Load operation history from database."""
        # This is called by the main window's DB connection
        # We use a signal to request data from the parent
        try:
            parent = self.window()
            if hasattr(parent, "op_history"):
                ops = parent.op_history.get_operations(limit=200)
                self.history_table.setRowCount(len(ops))
                for i, op in enumerate(ops):
                    self.history_table.setItem(i, 0, QTableWidgetItem(str(op.get("id", ""))))
                    self.history_table.setItem(i, 1, QTableWidgetItem(op.get("operation_type", "")))
                    self.history_table.setItem(i, 2, QTableWidgetItem(op.get("timestamp", "")))
                    self.history_table.setItem(i, 3, QTableWidgetItem(op.get("file_path", "")))
                    self.history_table.setItem(i, 4, QTableWidgetItem(op.get("category", "") or ""))
                    undone = "✅ Yes" if op.get("undone") else "No"
                    self.history_table.setItem(i, 5, QTableWidgetItem(undone))
        except Exception:
            pass
