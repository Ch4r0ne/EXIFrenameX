# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

def collect_dir_as_datas(src_dir: str, dest_root: str):
    """
    PyInstaller expects: [(source_file, destination_dir), ...]
    destination_dir is relative inside the packaged app.
    """
    src = Path(src_dir)
    if not src.exists():
        raise SystemExit(f"Missing directory: {src_dir}")

    datas = []
    for p in src.rglob("*"):
        if not p.is_file():
            continue

        rel_posix = p.as_posix()

        # --- Hard excludes (macOS: ExifTool tests contain problematic Mach-O samples) ---
        if IS_MAC:
            if "assets/exiftool/macos/t/" in rel_posix:
                continue
            if rel_posix.endswith(".macho"):
                continue

        # Normal mapping
        rel = p.relative_to(src)
        dest_dir = str(Path(dest_root) / rel.parent).replace("\\", "/")
        datas.append((str(p), dest_dir))

    return datas

# Bundle all assets, but with hard excludes above on macOS
datas = collect_dir_as_datas("assets", "assets")

# Icon selection (embed for Windows exe, use for macOS .app)
icon = None
if IS_WIN:
    ico = Path("assets/EXIFrenameX.ico")
    icon = str(ico) if ico.exists() else None
elif IS_MAC:
    icns = Path("assets/EXIFrenameX.icns")
    icon = str(icns) if icns.exists() else None

a = Analysis(
    ["date-renamer-toolkit.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PyQt6",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.sip",
        "PIL._imaging",
        "pillow_heif",
        "pymediainfo",
        "exifread",
        "exiftool_wrapper",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DateRenamerToolkit",
    console=False,
    icon=icon,
    upx=True if IS_WIN else False,
)

# Onedir output (robuster für Qt + Assets)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True if IS_WIN else False,
    name="DateRenamerToolkit",
)

# macOS: build .app bundle with proper icon
if IS_MAC:
    app = BUNDLE(
        coll,
        name="DateRenamerToolkit.app",
        icon=icon,
        bundle_identifier="de.technetpro.daterenamertoolkit",
    )
