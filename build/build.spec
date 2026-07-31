# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Local AI File Organizer.
"""

import os
from pathlib import Path

block_cipher = None
project_root = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    ['../main.py'],
    pathex=[project_root],
    binaries=[],
    datas=[
        ('../config/default_config.json', 'config'),
        ('../config/categories.json', 'config'),
    ],
    hiddenimports=[
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'core',
        'core.scanner',
        'core.hasher',
        'core.ollama_client',
        'core.cloud_ai_client',
        'core.organizer',
        'core.duplicate_finder',
        'core.metadata',
        'core.content_reader',
        'core.ocr',
        'database',
        'database.db_manager',
        'database.operations',
        'database.schema',
        'ui',
        'ui.main_window',
        'ui.dashboard',
        'ui.scan_view',
        'ui.analyze_view',
        'ui.organize_view',
        'ui.duplicates_view',
        'ui.settings_view',
        'ui.logs_view',
        'ui.quick_organize_view',
        'ui.theme',
        'utils',
        'utils.config',
        'utils.logger',
        'utils.helpers',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LocalAIFileOrganizer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LocalAIFileOrganizer',
)
