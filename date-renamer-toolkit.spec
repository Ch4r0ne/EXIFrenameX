# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import Tree

block_cipher = None

datas = [
    Tree("assets", prefix="assets"),
]

a = Analysis(
    ["EXIFrenameX.py"],   # <- wenn dein Entry anders heißt, hier anpassen
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=[],
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
