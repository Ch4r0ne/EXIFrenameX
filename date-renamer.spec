# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

def collect_tree(root_dir: str):
    """
    ONEFILE: datas must be (source_file, dest_dir_in_meipass).
    We include:
      - assets/ (icons, UI assets)
      - tools/  (bundled ExifTool)
    """
    src = Path(root_dir)
    if not src.exists():
        return []

    datas = []
    for p in src.rglob("*"):
        if not p.is_file():
            continue

        rel_posix = p.as_posix()

        if IS_MAC:
            # Defensive: do not ever bundle ExifTool tests if present
            if "/t/" in rel_posix and ("tools/exiftool/" in rel_posix or "assets/exiftool/" in rel_posix):
                continue
            if rel_posix.endswith(".macho"):
                continue

        rel = p.relative_to(src)
        dest_dir = str(Path(root_dir) / rel.parent).replace("\\", "/")
        datas.append((str(p), dest_dir))
    return datas


datas = []
datas += collect_tree("assets")
datas += collect_tree("tools")

# Icons (new branding)
icon = None
if IS_WIN:
    ico = Path("assets/DateRenamer.ico")
    if ico.exists():
        icon = str(ico)
elif IS_MAC:
    icns = Path("assets/DateRenamer.icns")
    if icns.exists():
        icon = str(icns)

a = Analysis(
    ["date-renamer.py"],
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

# ONEFILE: no COLLECT. EXE creates a single-file artifact.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DateRenamer",
    console=False,
    icon=icon,
    upx=True if IS_WIN else False,
)
