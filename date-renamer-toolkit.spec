# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

block_cipher = None

def collect_dir_as_datas(src_dir: str, dest_root: str):
    """
    Return datas in the format PyInstaller expects:
    [(source_file, destination_dir), ...]
    destination_dir is relative inside the packaged app.
    """
    src = Path(src_dir)
    if not src.exists():
        raise SystemExit(f"Missing directory: {src_dir}")

    datas = []
    for p in src.rglob("*"):
        if p.is_file():
            rel = p.relative_to(src)
            dest_dir = str(Path(dest_root) / rel.parent).replace("\\", "/")
            datas.append((str(p), dest_dir))
    return datas

datas = collect_dir_as_datas("assets", "assets")

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
    upx=True,
)
