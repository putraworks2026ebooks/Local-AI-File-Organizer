"""
Dashboard widget for Local AI File Organizer.
Shows overview statistics and category breakdowns.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QGridLayout,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView, QFrame
)
from PySide6.QtCore import Qt
from utils.helpers import format_file_size


class StatCard(QFrame):
    """A stat display card."""

    def __init__(self, label: str, value: str = "0", parent=None):
        super().__init__(parent)
        self.setObjectName("stat_card")
        self.setStyleSheet("""
            QFrame#stat_card {
                background-color: palette(base);
                border: 1px solid palette(mid);
                border-radius: 8px;
                padding: 16px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setSpacing(4)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("stat_value")
        self.value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.value_label)

        self.label = QLabel(label)
        self.label.setObjectName("stat_label")
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

    def set_value(self, value: str):
        self.value_label.setText(value)


class DashboardWidget(QWidget):
    """Dashboard view showing overall statistics and category breakdown."""

    def __init__(self, db, config: dict):
        super().__init__()
        self.db = db
        self.config = config
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("Dashboard")
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)

        # Stat cards row
        stats_layout = QHBoxLayout()

        self.card_total_files = StatCard("Total Files")
        self.card_total_size = StatCard("Total Size")
        self.card_categories = StatCard("Categories Used")
        self.card_duplicates = StatCard("Duplicates Found")

        stats_layout.addWidget(self.card_total_files)
        stats_layout.addWidget(self.card_total_size)
        stats_layout.addWidget(self.card_categories)
        stats_layout.addWidget(self.card_duplicates)

        layout.addLayout(stats_layout)

        # Category breakdown table
        cat_group = QGroupBox("Files by Category")
        cat_layout = QVBoxLayout()

        self.category_table = QTableWidget()
        self.category_table.setColumnCount(4)
        self.category_table.setHorizontalHeaderLabels(["Category", "Files", "Total Size", "%"])
        self.category_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.category_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.category_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.category_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.category_table.setAlternatingRowColors(True)
        cat_layout.addWidget(self.category_table)

        cat_group.setLayout(cat_layout)
        layout.addWidget(cat_group)

        # AI status
        ai_group = QGroupBox("AI Engine Status")
        ai_layout = QHBoxLayout()

        self.ai_status_label = QLabel("Checking Ollama...")
        self.ai_status_label.setStyleSheet("font-weight: bold;")
        ai_layout.addWidget(self.ai_status_label)

        ai_layout.addStretch()

        self.model_label = QLabel("Model: --")
        ai_layout.addWidget(self.model_label)

        ai_group.setLayout(ai_layout)
        layout.addWidget(ai_group)

        layout.addStretch()

    def update_stats(self):
        """Refresh dashboard statistics."""
        total_files = self.db.get_file_count()
        total_size = self.db.get_total_size()
        category_stats = self.db.get_category_stats()

        self.card_total_files.set_value(str(total_files))
        self.card_total_size.set_value(format_file_size(total_size))
        self.card_categories.set_value(str(len(category_stats)))

        # Count duplicates
        dup_groups = self.db.get_duplicate_groups()
        self.card_duplicates.set_value(str(len(dup_groups)))

        # Update category table
        self.category_table.setRowCount(len(category_stats))
        for i, stat in enumerate(category_stats):
            category = stat.get("category", "Uncategorized") or "Uncategorized"
            count = stat.get("count", 0)
            size = stat.get("total_size", 0)

            self.category_table.setItem(i, 0, QTableWidgetItem(category))
            self.category_table.setItem(i, 1, QTableWidgetItem(str(count)))
            self.category_table.setItem(i, 2, QTableWidgetItem(format_file_size(size)))

            pct = f"{round((size / total_size) * 100, 1)}%" if total_size > 0 else "0%"
            self.category_table.setItem(i, 3, QTableWidgetItem(pct))

    def update_ai_status(self, available: bool, model: str = ""):
        """Update AI engine status display."""
        if available:
            self.ai_status_label.setText("✅ Ollama Connected")
            self.ai_status_label.setStyleSheet("font-weight: bold; color: green;")
            self.model_label.setText(f"Model: {model}")
        else:
            self.ai_status_label.setText("❌ Ollama Not Connected")
            self.ai_status_label.setStyleSheet("font-weight: bold; color: red;")
            self.model_label.setText("Model: --")
