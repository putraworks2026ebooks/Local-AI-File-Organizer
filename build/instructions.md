# Build & Packaging Instructions

## Prerequisites

1. **Python 3.12+** installed on Windows 10/11
2. **Ollama** installed and running locally
3. Build dependencies: `pip install -r requirements.txt`
4. PyInstaller: `pip install pyinstaller`

## Quick Build

```bash
python build/build.py
```

This will:
1. Clean previous build artifacts
2. Install all dependencies
3. Run PyInstaller to create the EXE
4. Verify the output

## Manual Build

### Step 1: Install Dependencies

```bash
pip install -r requirements.txt
pip install pyinstaller
```

### Step 2: Run PyInstaller

```bash
pyinstaller build/build.spec --noconfirm --clean
```

### Step 3: Find Your EXE

The built application will be in:
```
dist/LocalAIFileOrganizer/LocalAIFileOrganizer.exe
```

## Creating a Single-File EXE (Optional)

For a single-file executable, modify the spec file:

1. Replace the `COLLECT` section with `EXE` that includes `a.binaries` and `a.datas`:

```python
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='LocalAIFileOrganizer',
    console=False,
    icon=None,
)
```

2. Run: `pyinstaller build/build.spec --onefile --noconfirm`

> ⚠️ Single-file mode has slower startup but is easier to distribute.

## Including an Icon

To add an application icon:

1. Place an `.ico` file in the `assets/` directory
2. Update the spec file: `icon='../assets/app_icon.ico'`
3. Rebuild

## Tesseract OCR (Optional)

To include OCR support in the build:

1. Install Tesseract OCR: https://github.com/UB-Mannheim/tesseract/wiki
2. Add the Tesseract path to the spec's `datas`:
   ```python
   datas=[
       ('../config/default_config.json', 'config'),
       ('../config/categories.json', 'config'),
       ('C:/Program Files/Tesseract-OCR/tessdata', 'tessdata'),
   ],
   ```
3. In settings, set the Tesseract path accordingly

## Distribution

### Portable Distribution

1. Zip the entire `dist/LocalAIFileOrganizer/` folder
2. The zip is self-contained — users just extract and run the EXE

### Installer (with Inno Setup)

1. Download [Inno Setup](https://jrsoftware.org/isinfo.php)
2. Create a script that copies `dist/LocalAIFileOrganizer/` to `C:\Program Files\LocalAIFileOrganizer\`
3. Create desktop and start menu shortcuts
4. Build the installer

### Requirements for End Users

- Windows 10 or 11 (64-bit)
- [Ollama](https://ollama.ai) installed and running
- At least one model pulled (e.g., `ollama pull llama3.1`)
- No other dependencies needed — everything is bundled

## Troubleshooting

### Missing Module Error
Add the module to `hiddenimports` in `build.spec`.

### Large EXE Size
- Add more modules to `excludes` in the spec file
- Use `--strip` and `--upx` options

### Anti-Virus False Positive
- This is common with PyInstaller builds
- Sign the executable with a code signing certificate
- Or instruct users to add an exception

### Console Window Appears
- Ensure `console=False` in the spec file
- For debugging, set `console=True` temporarily
