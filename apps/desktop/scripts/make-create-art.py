"""Builds the three photos on Create's "What are you making?" cards (owner request 2026-11-08): one free Pexels photo
per kind, fetched once, cropped to the card and saved as a small WebP in src/assets/create/ with CREDITS.json, so the
app never fetches anything at runtime. Run with the backend venv from the repo root:

    apps\\backend\\.venv\\Scripts\\python apps\\desktop\\scripts\\make-create-art.py --preview   # contact sheets to pick from
    apps\\backend\\.venv\\Scripts\\python apps\\desktop\\scripts\\make-create-art.py images=123 videos=456 clips=789

Reads PEXELS_API_KEY from the repo .env (never printed). Pexels license: free use, no attribution required."""
import io
import json
import ssl
import sys
import tempfile
from pathlib import Path

import httpx
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "apps" / "desktop" / "src" / "assets" / "create"
QUERIES = {"images": "minimal desk notebook coffee", "videos": "cinematic mountain sunrise silhouette",
           "clips": "podcast microphone studio"}
SIZE = (960, 1200)  # 4:5, twice the card's on-screen size for sharp high-DPI screens


def key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "PEXELS_API_KEY" and value.strip():
            return value.strip().strip("\"'")
    sys.exit("PEXELS_API_KEY is missing from .env")


def main() -> None:
    with httpx.Client(verify=ssl.create_default_context(), timeout=60, headers={"Authorization": key()},
                      follow_redirects=True) as client:
        if sys.argv[1:] == ["--preview"]:
            sheets = Path(tempfile.gettempdir()) / "acs-create-art"
            sheets.mkdir(exist_ok=True)
            for kind, query in QUERIES.items():
                photos = client.get("https://api.pexels.com/v1/search",
                                    params={"query": query, "orientation": "portrait", "per_page": 8}).json()["photos"]
                sheet = Image.new("RGB", (4 * 240, 2 * 330), "white")
                for i, p in enumerate(photos):
                    thumb = Image.open(io.BytesIO(client.get(p["src"]["medium"]).content)).convert("RGB")
                    sheet.paste(ImageOps.fit(thumb, (236, 300)), ((i % 4) * 240 + 2, (i // 4) * 330 + 2))
                    print(f"{kind} #{i}: id={p['id']} by {p['photographer']}")
                sheet.save(sheets / f"{kind}.jpg", quality=85)
            print(f"contact sheets in {sheets}")
            return
        OUT.mkdir(parents=True, exist_ok=True)
        credits = []
        for arg in sys.argv[1:]:
            kind, _, pid = arg.partition("=")
            p = client.get(f"https://api.pexels.com/v1/photos/{pid}").json()
            img = Image.open(io.BytesIO(client.get(p["src"]["original"]).content)).convert("RGB")
            ImageOps.fit(img, SIZE, Image.LANCZOS).save(OUT / f"{kind}.webp", quality=80, method=6)
            credits.append({"file": f"{kind}.webp", "pexels_id": p["id"], "page": p["url"], "author": p["photographer"]})
        (OUT / "CREDITS.json").write_text(json.dumps(credits, indent=2, ensure_ascii=False), encoding="utf-8")
        print("wrote", [c["file"] for c in credits])


if __name__ == "__main__":
    main()
