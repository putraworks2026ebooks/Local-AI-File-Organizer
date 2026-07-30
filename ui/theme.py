"""
Theme management for Local AI File Organizer.
Provides dark and light mode themes with smooth switching.
"""

from PySide6.QtGui import QColor, QPalette, QFont
from PySide6.QtCore import QObject, Signal


DARK_QSS = """
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-size: 13px;
}
QMainWindow, QDialog {
    background-color: #1e1e2e;
}
QTabWidget::pane {
    border: 1px solid #313244;
    background: #181825;
}
QTabWidget::tab-bar {
    alignment: center;
}
QTabBar::tab {
    background: #313244;
    color: #cdd6f4;
    padding: 8px 20px;
    border: 1px solid #1e1e2e;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #89b4fa;
    color: #1e1e2e;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    background: #45475a;
}
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    padding: 8px 16px;
    border-radius: 6px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #45475a;
    border-color: #89b4fa;
}
QPushButton:pressed {
    background-color: #1e1e2e;
}
QPushButton#primary {
    background-color: #89b4fa;
    color: #1e1e2e;
    font-weight: bold;
}
QPushButton#primary:hover {
    background-color: #b4befe;
}
QPushButton#danger {
    background-color: #f38ba8;
    color: #1e1e2e;
}
QPushButton#danger:hover {
    background-color: #eba0ac;
}
QProgressBar {
    border: 1px solid #45475a;
    border-radius: 4px;
    text-align: center;
    background-color: #181825;
    height: 20px;
}
QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 3px;
}
QTreeView, QTableView, QListView {
    background-color: #181825;
    border: 1px solid #313244;
    alternate-background-color: #1e1e2e;
    gridline-color: #313244;
}
QTreeView::item:selected, QTableView::item:selected {
    background-color: #89b4fa;
    color: #1e1e2e;
}
QHeaderView::section {
    background-color: #313244;
    color: #cdd6f4;
    padding: 6px;
    border: 1px solid #1e1e2e;
    font-weight: bold;
}
QLineEdit, QSpinBox, QComboBox, QTextEdit {
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #45475a;
    padding: 6px 10px;
    border-radius: 4px;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
    border-color: #89b4fa;
}
QGroupBox {
    border: 1px solid #313244;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QScrollBar:vertical {
    background: #181825;
    width: 12px;
    border: none;
}
QScrollBar::handle:vertical {
    background: #45475a;
    border-radius: 6px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #89b4fa;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QStatusBar {
    background-color: #181825;
    color: #a6adc8;
}
QLabel#stat_value {
    font-size: 28px;
    font-weight: bold;
    color: #89b4fa;
}
QLabel#stat_label {
    font-size: 12px;
    color: #a6adc8;
}
QCheckBox {
    spacing: 8px;
}
"""

LIGHT_QSS = """
QWidget {
    background-color: #f5f5f5;
    color: #1e1e2e;
    font-size: 13px;
}
QMainWindow, QDialog {
    background-color: #f5f5f5;
}
QTabWidget::pane {
    border: 1px solid #d1d5db;
    background: #ffffff;
}
QTabBar::tab {
    background: #e5e7eb;
    color: #1e1e2e;
    padding: 8px 20px;
    border: 1px solid #d1d5db;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #3b82f6;
    color: white;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    background: #d1d5db;
}
QPushButton {
    background-color: #e5e7eb;
    color: #1e1e2e;
    border: 1px solid #d1d5db;
    padding: 8px 16px;
    border-radius: 6px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #d1d5db;
    border-color: #3b82f6;
}
QPushButton:pressed {
    background-color: #f5f5f5;
}
QPushButton#primary {
    background-color: #3b82f6;
    color: white;
    font-weight: bold;
}
QPushButton#primary:hover {
    background-color: #2563eb;
}
QPushButton#danger {
    background-color: #ef4444;
    color: white;
}
QPushButton#danger:hover {
    background-color: #dc2626;
}
QProgressBar {
    border: 1px solid #d1d5db;
    border-radius: 4px;
    text-align: center;
    background-color: #ffffff;
    height: 20px;
}
QProgressBar::chunk {
    background-color: #3b82f6;
    border-radius: 3px;
}
QTreeView, QTableView, QListView {
    background-color: #ffffff;
    border: 1px solid #d1d5db;
    alternate-background-color: #f5f5f5;
    gridline-color: #d1d5db;
}
QTreeView::item:selected, QTableView::item:selected {
    background-color: #3b82f6;
    color: white;
}
QHeaderView::section {
    background-color: #e5e7eb;
    color: #1e1e2e;
    padding: 6px;
    border: 1px solid #d1d5db;
    font-weight: bold;
}
QLineEdit, QSpinBox, QComboBox, QTextEdit {
    background-color: #ffffff;
    color: #1e1e2e;
    border: 1px solid #d1d5db;
    padding: 6px 10px;
    border-radius: 4px;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
    border-color: #3b82f6;
}
QGroupBox {
    border: 1px solid #d1d5db;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QScrollBar:vertical {
    background: #ffffff;
    width: 12px;
    border: none;
}
QScrollBar::handle:vertical {
    background: #d1d5db;
    border-radius: 6px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #3b82f6;
}
QStatusBar {
    background-color: #e5e7eb;
    color: #4b5563;
}
QLabel#stat_value {
    font-size: 28px;
    font-weight: bold;
    color: #3b82f6;
}
QLabel#stat_label {
    font-size: 12px;
    color: #6b7280;
}
QCheckBox {
    spacing: 8px;
}
"""


class ThemeManager(QObject):
    """Manages application themes (dark/light)."""

    theme_changed = Signal(str)

    DARK = "dark"
    LIGHT = "light"

    def __init__(self):
        super().__init__()
        self._theme = self.DARK

    @property
    def theme(self) -> str:
        return self._theme

    def get_stylesheet(self, theme: str = None) -> str:
        """Get QSS stylesheet for a theme."""
        theme = theme or self._theme
        return DARK_QSS if theme == self.DARK else LIGHT_QSS

    def set_theme(self, theme: str) -> None:
        """Set the current theme."""
        if theme in (self.DARK, self.LIGHT):
            self._theme = theme
            self.theme_changed.emit(theme)

    def toggle(self) -> str:
        """Toggle between dark and light themes."""
        new_theme = self.LIGHT if self._theme == self.DARK else self.DARK
        self.set_theme(new_theme)
        return new_theme
