"""Builds the background dome's moving tiles (owner request 2026-11-08): short free Pexels clips cut into seamless
loops of DIFFERENT lengths (3.2-5.4 s, so the tiles never restart together) and encoded as small animated WebP
(behaves like a GIF, a fraction of the size). Seamless: the loop's last FADE seconds crossfade into its own start. Writes src/assets/dome/clip-NN.webp
and CREDITS.json (Pexels id, page, author). Run with the backend venv from the repo root:

    apps\\backend\\.venv\\Scripts\\python apps\\desktop\\scripts\\make-dome-clips.py

Reads PEXELS_API_KEY from the repo .env (never printed). Pexels license: free use, no attribution required; the clips
are shipped as decoration inside the app, not resold as stock. ffmpeg runs as an argument list with a timeout."""
import json
import ssl
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "apps" / "desktop" / "src" / "assets" / "dome"
# cinematic subjects in the spirit of the genres; one clip per query
QUERIES = ["ocean waves", "city night traffic", "rain street night", "campfire", "mountain clouds", "people walking street",
           "neon lights city", "forest sunlight", "running athlete", "train window", "coffee pouring", "waterfall"]
SIZE, FPS, FADE = 240, 12, 0.6
# one length per clip, none equal and none a simple multiple of another, so loop points almost never coincide
LENGTHS = [3.2, 4.1, 3.6, 4.7, 3.9, 5.3, 4.4, 3.4, 5.0, 4.0, 5.4, 3.7]


def key() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "PEXELS_API_KEY" and value.strip():
            return value.strip().strip("\"'")
    sys.exit("PEXELS_API_KEY is missing from .env")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    credits = []
    with httpx.Client(verify=ssl.create_default_context(), timeout=60, headers={"Authorization": key()},
                      follow_redirects=True) as http, tempfile.TemporaryDirectory() as tmp:
        for n, query in enumerate(QUERIES, 1):
            found = http.get("https://api.pexels.com/videos/search",
                             params={"query": query, "per_page": 5, "size": "small"}).raise_for_status().json()
            length = LENGTHS[(n - 1) % len(LENGTHS)]
            video = next((v for v in found.get("videos", []) if v.get("duration", 0) >= length + FADE + 2), None)
            if video is None:
                print(f"skip {query}: nothing long enough")
                continue
            # the smallest rendition that still covers a tile comfortably
            files = sorted((f for f in video["video_files"] if (f.get("width") or 0) >= 360 and f.get("link")),
                           key=lambda f: f["width"])
            if not files:
                print(f"skip {query}: no usable file")
                continue
            src = Path(tmp) / f"{n}.mp4"
            src.write_bytes(http.get(files[0]["link"]).raise_for_status().content)
            out = OUT / f"clip-{n:02}.webp"
            # out(t) = clip(t + FADE), and over its last FADE seconds it fades into clip(0..FADE): the frame after the
            # last one is the first one, so the loop has no seam
            look = f"fps={FPS},scale={SIZE}:{SIZE}:force_original_aspect_ratio=increase,crop={SIZE}:{SIZE},format=yuv420p"
            graph = (f"[0:v]{look},split[x][y];"
                     f"[x]trim=start={FADE}:end={length + FADE},setpts=PTS-STARTPTS[a];"
                     f"[y]trim=start=0:end={FADE},setpts=PTS-STARTPTS[b];"
                     f"[a][b]xfade=transition=fade:duration={FADE}:offset={length - FADE}[v]")
            subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-ss", "1",
                            "-t", str(length + FADE + 0.5), "-i", str(src), "-an",
                            "-filter_complex", graph, "-map", "[v]",
                            "-loop", "0", "-c:v", "libwebp_anim", "-q:v", "55", "-compression_level", "6",
                            str(out)], check=True, timeout=120, stdin=subprocess.DEVNULL)
            credits.append({"file": out.name, "query": query, "seconds": length, "pexels_id": video["id"], "page": video["url"],
                            "author": video.get("user", {}).get("name", "")})
            print(f"{out.name}: {query}, {length}s loop ({out.stat().st_size // 1024} KB)")
    (OUT / "CREDITS.json").write_text(json.dumps(credits, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
