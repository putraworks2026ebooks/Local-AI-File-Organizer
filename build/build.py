#!/usr/bin/env python3
"""
Build script for Local AI File Organizer.
Uses PyInstaller to create a Windows EXE package.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"
WORK_DIR = PROJECT_ROOT / "build" / "work"


def clean_build():
    """Clean previous build artifacts."""
    print("Cleaning build directories...")
    for d in [BUILD_DIR / "work", DIST_DIR]:
        if d.exists():
            shutil.rmtree(d)
    print("✅ Clean complete")


def install_dependencies():
    """Install build dependencies."""
    print("Installing dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r",
                     str(PROJECT_ROOT / "requirements.txt")], check=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
    print("✅ Dependencies installed")


def run_pyinstaller():
    """Run PyInstaller to build the EXE."""
    print("Building EXE with PyInstaller...")
    spec_file = PROJECT_ROOT / "build" / "build.spec"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(spec_file),
        "--noconfirm",
        "--clean",
        "--distpath", str(DIST_DIR),
        "--workpath", str(WORK_DIR),
    ]

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    if result.returncode == 0:
        print("✅ Build successful!")
        print(f"   EXE location: {DIST_DIR / 'LocalAIFileOrganizer' / 'LocalAIFileOrganizer.exe'}")
    else:
        print("❌ Build failed!")
        sys.exit(1)


def verify_build():
    """Verify the build output."""
    exe_path = DIST_DIR / "LocalAIFileOrganizer" / "LocalAIFileOrganizer.exe"
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"✅ EXE created: {exe_path}")
        print(f"   Size: {size_mb:.1f} MB")
    else:
        print("❌ EXE not found!")
        sys.exit(1)


def main():
    """Main build entry point."""
    print("=" * 60)
    print("  Local AI File Organizer - Build Script")
    print("=" * 60)
    print()

    steps = [
        ("Clean", clean_build),
        ("Install Dependencies", install_dependencies),
        ("Build EXE", run_pyinstaller),
        ("Verify", verify_build),
    ]

    for name, func in steps:
        print(f"\n--- {name} ---")
        func()

    print("\n" + "=" * 60)
    print("  Build Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
