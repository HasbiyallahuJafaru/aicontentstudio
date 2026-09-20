"""Packs resources/icon.png into the multi-size resources/icon.ico Windows wants (taskbar, title bar, Explorer).

Run after scripts/make-icon.cjs, with the backend venv's Python (it already has Pillow):
    ..\\backend\\.venv\\Scripts\\python scripts\\make-icon-ico.py
"""
import pathlib

from PIL import Image

root = pathlib.Path(__file__).resolve().parent.parent
png = root / "resources" / "icon.png"
ico = root / "resources" / "icon.ico"

img = Image.open(png).convert("RGBA")
if img.size != (512, 512):  # the capture comes back at the display's DPI scale
    img = img.resize((512, 512), Image.LANCZOS)
    img.save(png)

# Windows picks the nearest size per surface; without the small ones it downsamples 512 badly in the taskbar.
img.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote", ico)
