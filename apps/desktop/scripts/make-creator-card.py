"""Draws the creator ID card that hangs from the Lanyard pop-up (components/CreatorCard.tsx): front, back and strap,
in the app's look (white panel, black ink, one lime accent, no gradients). Run once from the repo root with the
backend venv: apps/backend/.venv/Scripts/python apps/desktop/scripts/make-creator-card.py
Writes src/assets/lanyard/{front,back,strap}.webp. Fonts are the backend's bundled OFL cuts."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
DESKTOP = HERE.parent
FONTS = DESKTOP.parent / "backend" / "assets" / "fonts"
OUT = DESKTOP / "src" / "assets" / "lanyard"
INK, PAPER, LIME, MUTED, LINE = "#111214", "#ffffff", "#c6f432", "#6b6f79", "#e4e6ea"
W, H = 1024, 1440  # the Lanyard's portrait card is 1.6 x 2.25; its strap slot sits in the top ~9%


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def front() -> Image.Image:
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    m = 84
    # a lime band across the top carries the strap slot, like a real badge
    d.rectangle([0, 0, W, 210], fill=LIME)
    # the app's mark sits in the band, left of the strap slot (the slot is centred, ~220 px wide)
    icon = Image.open(DESKTOP / "resources" / "icon.png").convert("RGBA").resize((132, 132), Image.LANCZOS)
    img.paste(icon, (m - 10, 40), icon)
    d.text((W - m - 150, 84), "YT Clipper", font=font("InstrumentSans-Bold.ttf", 30), fill=INK, anchor="lm")
    # the owner's portrait (scripts/creator-photo.png, 2026-11-09) on a panel of its own background colour, so the
    # photo has no visible edge; the panel's corners are rounded like the app's media frames
    photo = Image.open(HERE / "creator-photo.png").convert("RGB")
    bg = photo.getpixel((4, 4))
    top, ph = 240, 450
    panel = Image.new("RGB", (W - 2 * m, ph), bg)
    panel.paste(photo.resize((ph, ph), Image.LANCZOS), ((W - 2 * m - ph) // 2, 0))
    mask = Image.new("L", panel.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, panel.width - 1, ph - 1], radius=36, fill=255)
    img.paste(panel, (m, top), mask)
    # text runs top to bottom from a cursor, so nothing can overlap whatever the font sizes
    y = top + ph + 30
    d.text((m, y), "SOFTWARE DEVELOPER", font=font("InstrumentSans-Bold.ttf", 28), fill=MUTED)
    y += 44
    name = font("BricolageGrotesque-Bold.ttf", 104)
    while d.textlength("Hasbiyallahu", font=name) > W - 2 * m:  # fit the long first name inside the margins
        name = font("BricolageGrotesque-Bold.ttf", name.size - 4)
    for line in ("Hasbiyallahu", "Jafaru"):
        d.text((m - 4, y), line, font=name, fill=INK)
        y += round(name.size * 0.98)
    y += 30
    # the pitch (owner 2026-11-09: the card is a marketing tool), then the socials only
    pitch = font("InstrumentSans-Bold.ttf", 34)
    d.text((m, y), "I build websites, mobile apps and desktop apps.", font=pitch, fill=INK)
    assert d.textlength("I build websites, mobile apps and desktop apps.", font=pitch) <= W - 2 * m
    y += 46
    d.text((m, y), "YT Clipper is one of them.", font=font("InstrumentSans-Regular.ttf", 34), fill=MUTED)
    y += 70
    label, value = font("InstrumentSans-Bold.ttf", 26), font("InstrumentSans-Regular.ttf", 32)
    for k, v in (("GITHUB", "HasbiyallahuJafaru"), ("LINKEDIN", "hasbiyallahu-jafaru")):
        d.text((m, y + 5), k, font=label, fill=MUTED)
        d.text((m + 170, y), v, font=value, fill=INK)
        y += 46
    assert y < H - 150 - 20, f"front text runs into the foot ({y})"
    # the foot: a solid black strip with the card number, so the card reads as an ID
    d.rectangle([0, H - 150, W, H], fill=INK)
    d.text((m, H - 104), "ID 0001", font=font("InstrumentSans-Bold.ttf", 40), fill=LIME)
    tag = "Open for work"
    tf = font("InstrumentSans-Regular.ttf", 36)
    d.text((W - m - d.textlength(tag, font=tf), H - 100), tag, font=tf, fill=PAPER)
    return img


def back() -> Image.Image:
    """The ask: what he builds, and that hiring him is how the free app is supported."""
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)
    icon = Image.open(DESKTOP / "resources" / "icon.png").convert("RGBA").resize((170, 170), Image.LANCZOS)
    img.paste(icon, ((W - 170) // 2, 250), icon)
    centre = lambda text, y, f, fill: d.text(((W - d.textlength(text, font=f)) / 2, y), text, font=f, fill=fill)
    big = font("BricolageGrotesque-Bold.ttf", 118)
    centre("Let's work", 500, big, PAPER)
    centre("together", 618, big, LIME)
    sub = font("InstrumentSans-Regular.ttf", 42)
    centre("Need a website, a mobile app", 820, sub, "#c9ccd4")
    centre("or a desktop app? I build all three.", 876, sub, "#c9ccd4")
    pill = "Hiring me keeps YT Clipper free"
    pf = font("InstrumentSans-Bold.ttf", 38)
    pw = d.textlength(pill, font=pf)
    d.rounded_rectangle([(W - pw) / 2 - 40, 1040, (W + pw) / 2 + 40, 1118], radius=39, fill=LIME)
    d.text(((W - pw) / 2, 1057), pill, font=pf, fill=INK)
    return img


def strap() -> Image.Image:
    """A wide tile: its height spans the band's width and it repeats along the band."""
    text = "WEBSITES   ·   MOBILE APPS   ·   DESKTOP APPS   ·   OPEN FOR WORK   ·   "
    f = font("InstrumentSans-Bold.ttf", 64)
    tw = int(ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(text, font=f))
    img = Image.new("RGB", (tw, 160), INK)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, tw, 10], fill=LIME)
    d.rectangle([0, 150, tw, 160], fill=LIME)
    d.text((0, 42), text, font=f, fill=PAPER)
    return img


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, make in (("front", front), ("back", back), ("strap", strap)):
        make().save(OUT / f"{name}.webp", "WEBP", quality=90, method=6)
        print(name, (OUT / f"{name}.webp").stat().st_size // 1024, "KB")
