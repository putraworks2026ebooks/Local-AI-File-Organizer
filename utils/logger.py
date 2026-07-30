"""
Logging system for Local AI File Organizer.
Provides rotating file logging and console output.
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime


class AppLogger:
    """Application logger with file rotation and optional Qt signal handler."""

    _instance: "AppLogger | None" = None

    def __init__(self, config: dict | None = None):
        if AppLogger._instance is not None:
            return
        AppLogger._instance = self

        self._log_queue: list[str] = []
        self._signal_callback = None

        log_config = (config or {}).get("logging", {})
        level_str = log_config.get("level", "INFO").upper()
        level = getattr(logging, level_str, logging.INFO)
        log_file = log_config.get("file", "logs/organizer.log")
        max_bytes = log_config.get("max_size_mb", 10) * 1024 * 1024
        backup_count = log_config.get("backup_count", 5)

        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger("file_organizer")
        self.logger.setLevel(level)
        self.logger.handlers.clear()

        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        file_handler = RotatingFileHandler(
            str(log_path), maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        self.logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(fmt)
        self.logger.addHandler(console_handler)

    @classmethod
    def get_instance(cls) -> "AppLogger":
        if cls._instance is None:
            cls()
        return cls._instance

    def set_signal_callback(self, callback):
        """Set a callback for real-time log forwarding (e.g., to UI)."""
        self._signal_callback = callback

    def debug(self, msg: str, *args, **kwargs):
        self.logger.debug(msg, *args, **kwargs)
        self._forward("DEBUG", msg % args if args else msg)

    def info(self, msg: str, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)
        self._forward("INFO", msg % args if args else msg)

    def warning(self, msg: str, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)
        self._forward("WARNING", msg % args if args else msg)

    def error(self, msg: str, *args, **kwargs):
        self.logger.error(msg, *args, **kwargs)
        self._forward("ERROR", msg % args if args else msg)

    def critical(self, msg: str, *args, **kwargs):
        self.logger.critical(msg, *args, **kwargs)
        self._forward("CRITICAL", msg % args if args else msg)

    def _forward(self, level: str, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"[{timestamp}] {level}: {msg}"
        self._log_queue.append(entry)
        if len(self._log_queue) > 1000:
            self._log_queue = self._log_queue[-500:]
        if self._signal_callback:
            try:
                self._signal_callback(entry)
            except Exception:
                pass

    def get_recent_logs(self, count: int = 100) -> list[str]:
        return self._log_queue[-count:]

    def clear_logs(self):
        self._log_queue.clear()


def get_logger(config: dict | None = None) -> AppLogger:
    """Get or create the singleton AppLogger."""
    return AppLogger.get_instance()
