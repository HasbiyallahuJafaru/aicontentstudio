"""Copies the site's images out of the app (real renders, real UI screenshots, the app icon) into src/assets and
public/, as WebP/PNG at web sizes, and composes the 1200x630 social card. Re-run after the app's look changes:

    apps\\backend\\.venv\\Scripts\\python apps\\site\\scripts\\prepare-assets.py <folder with the screenshots>

The screenshot folder holds the app captures named below (the smoke run writes most of them to %TEMP%\\acs-smoke)."""
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[3]
SITE = ROOT / "apps" / "site"
APP = ROOT / "apps" / "desktop"
ASSETS, PUBLIC = SITE / "src" / "assets", SITE / "public"
SHOTS = {"dashboard": "look-dashboard.png", "create": "look-create.png", "clip": "look-clip.png",
         "quotes": "1b-quote-images.png"}


def main(shots: Path) -> None:
    (ASSETS / "renders").mkdir(parents=True, exist_ok=True)
    (ASSETS / "shots").mkdir(exist_ok=True)
    (ASSETS / "fonts").mkdir(exist_ok=True)
    PUBLIC.mkdir(exist_ok=True)
    for f in sorted((APP / "src" / "assets" / "splash").glob("card-*.webp")):  # the design engine's own output
        shutil.copy(f, ASSETS / "renders" / f.name)
    for name, file in SHOTS.items():
        img = Image.open(shots / file).convert("RGB")
        img = img.resize((1440, round(img.height * 1440 / img.width)), Image.LANCZOS) if img.width > 1440 else img
        img.save(ASSETS / "shots" / f"{name}.webp", quality=84, method=6)
    for f in (APP / "src" / "assets" / "fonts").glob("BricolageGrotesque-*"):
        shutil.copy(f, ASSETS / "fonts" / f.name)
    icon = Image.open(APP / "resources" / "icon.png").convert("RGBA")
    icon.resize((180, 180), Image.LANCZOS).save(PUBLIC / "apple-touch-icon.png")
    icon.resize((64, 64), Image.LANCZOS).save(PUBLIC / "favicon.png")

    # social card: off-white, the headline left, three real renders fanned right
    card = Image.new("RGB", (1200, 630), "#f2f3f5")
    draw = ImageDraw.Draw(card)
    bold = ImageFont.truetype(str(APP / "src" / "assets" / "fonts" / "BricolageGrotesque-Bold.ttf"), 76)
    regular = ImageFont.truetype(str(APP / "src" / "assets" / "fonts" / "BricolageGrotesque-Regular.ttf"), 30)
    draw.text((72, 200), "Long videos in.", font=bold, fill="#111214")
    draw.rounded_rectangle((66, 298, 66 + draw.textlength("Shorts", font=bold) + 14, 392), 14, fill="#c6f432")
    draw.text((72, 292), "Shorts", font=bold, fill="#111214")
    draw.text((72 + draw.textlength("Shorts ", font=bold) + 10, 292), "out.", font=bold, fill="#111214")
    draw.text((72, 500), "YT Clipper  |  AI Content Studio for Windows", font=regular, fill="#4a4d55")
    for i, (name, angle, x) in enumerate([("card-2.webp", 8, 660), ("card-6.webp", -6, 880), ("card-4.webp", 0, 770)]):
        tile = ImageOps.fit(Image.open(ASSETS / "renders" / name).convert("RGBA"), (250, 312))
        mask = Image.new("L", tile.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, *tile.size), 22, fill=255)
        tile.putalpha(mask)
        tile = tile.rotate(angle, expand=True, resample=Image.BICUBIC)
        card.paste(tile, (x - tile.width // 2 + 125, 150 + (20 if i < 2 else 0)), tile)
    card.save(PUBLIC / "og.png", optimize=True)
    print("assets ready")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
