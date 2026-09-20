# -*- mode: python ; coding: utf-8 -*-
# Freezes the stdio JSON-RPC backend into a one-folder Windows app: dist/backend/backend.exe.
# Build:  cd apps/backend && .venv/Scripts/pyinstaller backend.spec --noconfirm
# The folder (not a single file) keeps startup instant; electron-builder ships it under resources/backend.
import warnings

from PyInstaller.utils.hooks import collect_data_files

warnings.filterwarnings("ignore")

datas = [
    ("assets/fonts", "assets/fonts"),                  # Sora for drawtext (OFL)
    ("app/clipper/assets", "app/clipper/assets"),      # YuNet face model + Montserrat captions
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas + collect_data_files("kokoro_onnx"),   # espeak/jieba data the voice engine needs
    hiddenimports=[
        "yt_dlp",                                       # lazy-loads extractors from package data
        "cv2",
        "kokoro_onnx",
        "soundfile",
        "PIL._tkinter_finder",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest", "tests"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="backend",
    console=True,          # stdio JSON-RPC lives on stdout; never a windowed app
)
coll = COLLECT(exe, a.binaries, a.datas, name="backend")
