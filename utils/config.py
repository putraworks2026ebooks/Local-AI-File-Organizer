"""
Configuration management for Local AI File Organizer.
Handles loading, saving, and merging user config with defaults.
"""

import json
import os
from pathlib import Path
from copy import deepcopy


DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "default_config.json"
USER_CONFIG_PATH = Path(__file__).parent.parent / "config" / "user_config.json"


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


class ConfigManager:
    """Manages application configuration with defaults and user overrides."""

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or USER_CONFIG_PATH
        self._config: dict = {}
        self.load()

    def load(self) -> dict:
        """Load configuration by merging defaults with user config."""
        with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
            defaults = json.load(f)

        user_config = {}
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)

        self._config = _deep_merge(defaults, user_config)
        return self._config

    def save(self, config: dict | None = None) -> None:
        """Save user configuration to disk."""
        if config is not None:
            self._config = config
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self._config, f, indent=2, ensure_ascii=False)

    def get(self, *keys, default=None):
        """Get a nested config value using dot-style keys."""
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def set(self, *keys_and_value):
        """Set a nested config value. Last argument is the value."""
        if len(keys_and_value) < 2:
            raise ValueError("set requires at least one key and a value")
        *keys, value = keys_and_value
        target = self._config
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]
        target[keys[-1]] = value

    @property
    def config(self) -> dict:
        return self._config

    @property
    def ollama_settings(self) -> dict:
        return self._config.get("ollama", {})

    @property
    def scan_settings(self) -> dict:
        return self._config.get("scan", {})

    @property
    def organize_settings(self) -> dict:
        return self._config.get("organize", {})

    @property
    def ui_settings(self) -> dict:
        return self._config.get("ui", {})

    @property
    def db_settings(self) -> dict:
        return self._config.get("database", {})

    @property
    def logging_settings(self) -> dict:
        return self._config.get("logging", {})

    @property
    def ocr_settings(self) -> dict:
        return self._config.get("ocr", {})

    @property
    def advanced_settings(self) -> dict:
        return self._config.get("advanced", {})
