# -*- mode: python ; coding: utf-8 -*-
# Freezes the stdio JSON-RPC backend into a one-folder Windows app: dist/backend/<ENGINE>.exe.
# Build:  cd apps/backend && .venv/Scripts/pyinstaller backend.spec --noconfirm
# The folder (not a single file) keeps startup instant; electron-builder ships it under resources/backend.
# The exe carries the app's name, icon and version so Windows and antivirus see it as part of the product,
# not an anonymous helper (Avast AutoSandbox targets unknown, unsigned exes). Keep ENGINE in sync with
# apps/desktop/electron/backend.ts and apps/desktop/scripts/smoke-packaged.mjs.
import json
import warnings

from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

warnings.filterwarnings("ignore")

ENGINE = "AI Social Content Studio Engine"
APP = json.load(open("../desktop/package.json", encoding="utf-8"))
nums = tuple(int(n) for n in APP["version"].split("-")[0].split(".")) + (0,)
version = VSVersionInfo(
    ffi=FixedFileInfo(filevers=nums, prodvers=nums),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", APP["author"]["name"]),
            StringStruct("FileDescription", ENGINE),
            StringStruct("FileVersion", APP["version"]),
            StringStruct("InternalName", ENGINE),
            StringStruct("LegalCopyright", APP["build"]["copyright"]),
            StringStruct("OriginalFilename", ENGINE + ".exe"),
            StringStruct("ProductName", APP["productName"]),
            StringStruct("ProductVersion", APP["version"]),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

datas = [
    ("assets/fonts", "assets/fonts"),                  # Sora for drawtext (OFL)
    ("assets/music", "assets/music"),                  # bundled public-domain / CC0 music beds
    ("app/clipper/assets", "app/clipper/assets"),      # YuNet face model
    ("app/migrations", "app/migrations"),              # schema: without these the first run has no tables
    ("app/motion_assets", "app/motion_assets"),        # HyperFrames templates + GSAP for motion layers
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "yt_dlp",                                       # lazy-loads extractors from package data
        "curl_cffi",                                    # yt-dlp imports it lazily for browser impersonation
        "cv2",
        "PIL._tkinter_finder",
    ],
    hookspath=[],
    runtime_hooks=[],
    # narration is Gemini TTS over HTTP now: keep the old local voice engine out even if the venv still has it
    excludes=["tkinter", "matplotlib", "pytest", "tests", "kokoro_onnx", "onnxruntime", "soundfile", "phonemizer"],
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=ENGINE,
    icon="../desktop/resources/icon.ico",
    version=version,
    upx=False,             # UPX-packed PEs are a top antivirus heuristic trigger
    console=True,          # stdio JSON-RPC lives on stdout; never a windowed app
)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="backend")
