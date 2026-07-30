#!/usr/bin/env python3
"""
Local AI File Organizer - Main Entry Point
A completely local AI-powered file organizer for Windows 10/11.
No cloud services required. Uses a locally running Ollama server.
"""

import sys
import os
from pathlib import Path

# Ensure the project root is on the Python path
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Create necessary directories
(PROJECT_ROOT / "logs").mkdir(exist_ok=True)
(PROJECT_ROOT / "config").mkdir(exist_ok=True)


def main():
    """Application entry point."""
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QFont
        from ui.main_window import MainWindow
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("\nInstall dependencies with:")
        print("    pip install -r requirements.txt")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("Local AI File Organizer")
    app.setOrganizationName("LocalAI")

    # Set application font (Segoe UI for Windows)
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
