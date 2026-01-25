# EXIFrenameX (Date Renamer Toolkit)

**EXIFrenameX** is a cross-platform **PyQt6 GUI** that renames photos and videos **in-place** using the **best available capture/creation timestamp**.  
It prioritizes **ExifTool** (most reliable across formats), then falls back to sidecars (XMP / Google Takeout JSON), classic EXIF readers, MediaInfo, filename parsing, and optionally filesystem timestamps.

---

## What this app solves

When you combine files from phones, cameras, WhatsApp exports, DJI drones, Google Photos Takeout, and edited media, timestamps end up inconsistent. This tool standardizes filenames deterministically:

- **Stable naming format** (strftime-based)
- **Predictable timestamp resolution order**
- **Collision-safe** renaming (auto-appends `_1`, `_2`, …)
- **Preview-first workflow** + **Undo for the last run (same session)**

---

## Features

- **Auto-preview**: changing options triggers rescans (debounced).
- **Rename patterns**
  - `Date only` → `2026-01-25_14-03-09.jpg`
  - `Date + Original` → `2026-01-25_14-03-09_IMG_1234.jpg`
  - `Original only` → `IMG_1234.jpg` (prefix/suffix optional)
  - `Original + Date` → `IMG_1234_2026-01-25_14-03-09.jpg`
- **Deep analysis (optional toggles)**
  - Parse date from filename (WhatsApp / IMG / DJI patterns)
  - Read `.xmp` sidecar (Adobe/Lightroom/exports)
  - Read Google Takeout `.json` sidecar (timestamp-based)
- **Fallback modes** (optional)
  - File created time
  - File modified time
  - OFF (skip files without a timestamp)
- **Recursive scanning** (include subfolders)
- **Logs viewer** for troubleshooting
- **Dark UI theme** + platform-neutral checkbox rendering

---

## How timestamps are chosen (deterministic order)

For each file, the tool resolves a timestamp in this order:

1. **ExifTool** (preferred, if available)
   - It checks these tags (in order):
     - `EXIF:DateTimeOriginal`, `EXIF:CreateDate`, `XMP:CreateDate`, `XMP:DateCreated`,
       QuickTime creation tags, file dates, composite tags, PNG creation time, …
2. **Google Takeout JSON sidecar** (`<file>.<ext>.json`)
3. **XMP sidecar** (`<file>.xmp` or `<file>.<ext>.xmp`)
4. **Classic EXIF parsing** via `exifread` (images)
5. **HEIC embedded XMP** via Pillow + pillow-heif (if present)
6. **MediaInfo** (`pymediainfo`) for videos
7. **Filename parsing** (if enabled)
8. **Filesystem fallback** (created/modified) if enabled  
9. Otherwise → **SKIP (missing timestamp)**

In the Preview table you can hover rows to see the **source** and timestamp used.

---

## Filename patterns recognized (deep filename mode)

- `IMG_YYYYMMDD_HHMMSS` / `VID_YYYYMMDD_HHMMSS`  
- `YYYY-MM-DD_HH-MM-SS`
- WhatsApp style: `IMG-YYYYMMDD-WA####`
- DJI style: `DJI_YYYYMMDD_HHMMSS`

---

## Requirements

- Python **3.10+** (recommended)
- PyQt6
- Optional (recommended for best results):
  - **ExifTool** available as `exiftool` in PATH **or** via `exiftool_wrapper`
  - `exifread` (classic EXIF)
  - `pymediainfo` (videos)
  - `Pillow` + `pillow-heif` (HEIC support)

---

## Installation (from source)

### 1) Create venv + install
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -U pip
pip install PyQt6
pip install exifread pillow pillow-heif pymediainfo exiftool-wrapper
```
---

## Development

Want to contribute?  
- Code style: [PEP8](https://www.python.org/dev/peps/pep-0008/), modular, clear docstrings.
- See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setup, code guidelines, and feature requests.

**Key dependencies:**  
```powershell
# Windows (onefile) – EXIFrenameX + Assets inkl. exiftool.exe (mit Subordnern)
py -m PyInstaller --noconfirm --clean --windowed --onefile `
  --name "EXIFrenameX" `
  --icon ".\assets\EXIFrenameX.ico" `
  --add-data ".\assets;assets" `
  --add-data ".\assets\exiftool;assets\exiftool" `
  --collect-all "PyQt6" `
  --hidden-import "PyQt6.QtCore" `
  --hidden-import "PyQt6.QtGui" `
  --hidden-import "PyQt6.QtWidgets" `
  --hidden-import "PyQt6.sip" `
  --hidden-import "PIL._imaging" `
  --hidden-import "pillow_heif" `
  --hidden-import "pymediainfo" `
  --hidden-import "exifread" `
  --hidden-import "exiftool_wrapper" `
  ".\EXIFrenameX.py"
```

---

## License

[MIT License](LICENSE)

---

## Credits

- Inspired by real-world batch photo organizing challenges.
- Powered by open-source Python packages.
- UI built with [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter).

---

**Questions, feedback, or feature requests?**  
Open an [issue](https://github.com/Ch4r0ne/EXIFrenameX/issues) or start a discussion!
