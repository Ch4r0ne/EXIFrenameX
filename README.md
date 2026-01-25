[![Release](https://img.shields.io/github/v/release/Ch4r0ne/date-renamer)](https://github.com/Ch4r0ne/date-renamer/releases)
[![License](https://img.shields.io/github/license/Ch4r0ne/date-renamer)](LICENSE)
![Platforms](https://img.shields.io/badge/platform-windows%20%7C%20macOS-blue)

# Date Renamer 

Renames photos and videos based on the best available capture timestamp.

> Deterministic timestamp resolution with explicit source visibility in the preview.

![Date Renamer preview](preview/date-renamer.png)

Preview of the current UI and timestamp source visibility.

## Quick start

### Download (recommended)

1. Download the latest release from the GitHub Releases page.
2. Start the app (Windows: `.exe`, macOS: `.app`).
3. No Python installation is required for the release builds.

## Features

- Live preview with planned target names.
- Undo for the last rename operation.
- Timestamp extraction via ExifTool (preferred).
- Deep mode: filename patterns and sidecars (XMP/Takeout JSON).
- Safe conflict handling with auto-unique suffixes.
- Parallel scan for large folders.
- Transparent diagnostics with tooltip source labels.

## How it works (timestamp resolution)

Date Renamer selects the best available timestamp per file.
The chosen timestamp source is visible in the preview tooltip.

Order of precedence (mirrors the code path):

1. ExifTool tags (QuickTime/EXIF/XMP/Composite/PNG).
2. Takeout JSON sidecar.
3. XMP sidecar.
4. Classic EXIF parsing via `exifread` (images).
5. HEIC embedded XMP (Pillow + pillow-heif).
6. MediaInfo for videos.
7. Filename parsing (Deep mode).
8. Filesystem fallback (Created/Modified), when selected.
9. Otherwise: skip the file.

<details>
<summary>ExifTool tags checked</summary>

- EXIF:DateTimeOriginal
- EXIF:CreateDate
- XMP:CreateDate
- XMP:DateCreated
- QuickTime:CreateDate
- QuickTime:MediaCreateDate
- QuickTime:TrackCreateDate
- QuickTime:ModifyDate
- QuickTime:ContentCreateDate
- Composite:SubSecDateTimeOriginal
- Composite:DateTimeCreated
- PNG:CreationTime
- DateTimeOriginal (fallback)
- CreateDate (fallback)
- MediaCreateDate (fallback)
</details>

## Deep mode

Deep mode extends timestamp resolution beyond embedded metadata:

- Filename parsing for known capture patterns.
- XMP sidecar reads (`.xmp` next to the media file).
- Takeout JSON sidecar reads (`.json` next to the media file).

Recognized filename patterns (examples):

```
DJI_FLY_YYYYMMDD_HHMMSS_*
DJI_YYYYMMDD_HHMMSS_*
IMG_YYYYMMDD_HHMMSS* / VID_YYYYMMDD_HHMMSS*
YYYYMMDD_HHMMSS*
YYYY-MM-DD_HH-MM-SS*
IMG-YYYYMMDD-WA####* / VID-YYYYMMDD-WA####*
```

Date-only patterns produce midnight time if no time is present.

## Known limitations

### Messenger and transcoded exports

Some exports remove capture metadata entirely. In these cases ExifTool can return
`0000:00:00` or no usable tag. The capture date is not recoverable without a
sidecar or filename pattern. Use skip or filesystem fallback if needed.

### UUID filenames

UUID-style filenames often indicate exported or transcoded media. Without a
sidecar or intact metadata, only filesystem fallback is available, which usually
reflects import or download time rather than capture time.

### Run from source

```bash
python -m venv .venv
```

```bash
# Windows
.venv\Scripts\activate
```

```bash
# macOS/Linux
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

```bash
python date-renamer.py
```


## Troubleshooting

1. Open Logs from the app menu.
2. Copy the log output.
3. Attach it to a GitHub issue.

Common cases:

- ExifTool not found or wrong mode selection.
- No timestamp available (use fallback or Deep mode).
- Permission or rename failure (Windows file locks).

The preview tooltip always shows the selected timestamp source.

## Build (PyInstaller)

Prerequisites:

- Python 3.10+
- PyInstaller (`pip install pyinstaller`)

Build commands:

```bash
# Windows
py -m PyInstaller date-renamer.spec
```

```bash
# macOS
python3 -m PyInstaller date-renamer.spec
```

Output is written to `dist/DateRenamer`.

Bundled assets are taken from `assets/` and `tools/` (if present).
ExifTool resolution order is bundled first, then system PATH.

## Credits

- Built with PyQt6 and community-maintained Python packages.

## Support

Open an issue at https://github.com/Ch4r0ne/date-renamer/issues with logs and a sample
file list if you need help reproducing a timestamp issue.


## License

[MIT License](LICENSE)
