"""Build the bundled music library (owner pick 2026-11-10): public-domain / CC0 recordings from Wikimedia Commons,
each cut to its steadiest 75 s (so it sits under a voice without swelling over it), faded, loudness-matched and
saved as small AAC files in assets/music/<genre>-<n>.m4a, with CREDITS.md naming every source and its licence.

Run once from apps/backend: python scripts/make_music.py  (needs ffmpeg on PATH and internet). Not run by the app.
"""
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "assets" / "music"
WINDOW = 75.0
UA = {"User-Agent": "AiContentStudio/0.1 (music library build; https://ytclipper.xyz)"}
C = "https://upload.wikimedia.org/wikipedia/commons/transcoded/"

# (file name, Commons file page, licence on Commons, mp3 transcode)
TRACKS = [
    ("hope-1", "Erik Satie - gymnopedies - la 1 ere. lent et douloureux.ogg", "Public domain",
     C + "9/90/Erik_Satie_-_gymnopedies_-_la_1_ere._lent_et_douloureux.ogg/Erik_Satie_-_gymnopedies_-_la_1_ere._lent_et_douloureux.ogg.mp3"),
    ("hope-2", "Grieg - Peer Gynt Suite No. 1, Op. 46 - I. Morning Mood (Musopen Symphony).flac", "Public domain",
     C + "c/c2/Grieg_-_Peer_Gynt_Suite_No._1%2C_Op._46_-_I._Morning_Mood_%28Musopen_Symphony%29.flac/Grieg_-_Peer_Gynt_Suite_No._1%2C_Op._46_-_I._Morning_Mood_%28Musopen_Symphony%29.flac.mp3"),
    ("speech-1", "Beethoven EgmontOvertureOp.84 LudwigVanBeethoven-EgmontOvertureOp.84.ogg", "CC0",
     C + "2/20/Beethoven_EgmontOvertureOp.84_LudwigVanBeethoven-EgmontOvertureOp.84.ogg/Beethoven_EgmontOvertureOp.84_LudwigVanBeethoven-EgmontOvertureOp.84.ogg.mp3"),
    ("speech-2", "Grieg - Peer Gynt Suite No. 1, Op. 46 - IV. In the Hall of the Mountain King (Musopen Symphony).flac",
     "Public domain",
     C + "8/84/Grieg_-_Peer_Gynt_Suite_No._1%2C_Op._46_-_IV._In_the_Hall_of_the_Mountain_King_%28Musopen_Symphony%29.flac/Grieg_-_Peer_Gynt_Suite_No._1%2C_Op._46_-_IV._In_the_Hall_of_the_Mountain_King_%28Musopen_Symphony%29.flac.mp3"),
    ("stoic-1", "Bach, Goldberg Variations, Aria (Musopen version).ogg", "CC0",
     C + "a/af/Bach%2C_Goldberg_Variations%2C_Aria_%28Musopen_version%29.ogg/Bach%2C_Goldberg_Variations%2C_Aria_%28Musopen_version%29.ogg.mp3"),
    ("stoic-2", "Josef Suk - Meditation Op 35a.ogg", "Public domain",
     C + "f/f5/Josef_Suk_-_Meditation_Op_35a.ogg/Josef_Suk_-_Meditation_Op_35a.ogg.mp3"),
    ("history-1", "Alexander Borodin - In The Steppes Of Central Asia.ogg", "CC0",
     C + "b/be/Alexander_Borodin_-_In_The_Steppes_Of_Central_Asia.ogg/Alexander_Borodin_-_In_The_Steppes_Of_Central_Asia.ogg.mp3"),
    ("history-2", "Mendelssohn - Symphony No. 3 in A minor, Op. 56 'Scottish' - III. Adagio (Musopen Symphony).flac",
     "Public domain",
     C + "8/8e/Mendelssohn_-_Symphony_No._3_in_A_minor%2C_Op._56_%27Scottish%27_-_III._Adagio_%28Musopen_Symphony%29.flac/Mendelssohn_-_Symphony_No._3_in_A_minor%2C_Op._56_%27Scottish%27_-_III._Adagio_%28Musopen_Symphony%29.flac.mp3"),
    ("books-1", "Chopin- Nocturne op. 37 no. 1.ogg", "CC0",
     C + "6/6d/Chopin-_Nocturne_op._37_no._1.ogg/Chopin-_Nocturne_op._37_no._1.ogg.mp3"),
    ("books-2", "Frederic Chopin - nocturne no. 1 in b major, op. 62.oga", "CC0",
     C + "1/1a/Frederic_Chopin_-_nocturne_no._1_in_b_major%2C_op._62.oga/Frederic_Chopin_-_nocturne_no._1_in_b_major%2C_op._62.oga.mp3"),
    ("cinema-1", "Grieg - Peer Gynt Suite No. 1, Op. 46 - II. The Death of Aase (Musopen Symphony).flac",
     "Public domain",
     C + "3/35/Grieg_-_Peer_Gynt_Suite_No._1%2C_Op._46_-_II._The_Death_of_Aase_%28Musopen_Symphony%29.flac/Grieg_-_Peer_Gynt_Suite_No._1%2C_Op._46_-_II._The_Death_of_Aase_%28Musopen_Symphony%29.flac.mp3"),
    ("cinema-2", "Suk - Meditation on the Old Czech Chorale Saint Wenceslas, Op. 35a (Musopen String Quartet).flac",
     "Public domain",
     C + "1/1f/Suk_-_Meditation_on_the_Old_Czech_Chorale_Saint_Wenceslas%2C_Op._35a_%28Musopen_String_Quartet%29.flac/Suk_-_Meditation_on_the_Old_Czech_Chorale_Saint_Wenceslas%2C_Op._35a_%28Musopen_String_Quartet%29.flac.mp3"),
]


def steadiest(src: Path) -> float:
    """Start of the WINDOW whose momentary loudness swings least (and is not near-silent)."""
    err = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-i", str(src), "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    m = [(float(t), float(v)) for t, v in re.findall(r"t:\s*([\d.]+).*?M:\s*(-?[\d.]+)", err)]
    step = 10  # ebur128 reports every 0.1 s
    n = int(WINDOW * 10)
    if len(m) <= n:
        return 0.0
    best, at = None, 0.0
    for i in range(0, len(m) - n, step * 5):  # try a start every 5 s
        vals = [v for _, v in m[i:i + n] if v > -70]
        if len(vals) < n * 0.9:
            continue
        mean = sum(vals) / len(vals)
        spread = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
        cost = spread + max(0.0, -32 - mean)  # quiet passages are fine, near-silent ones are not
        if best is None or cost < best:
            best, at = cost, m[i][0]
    return at


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    credits = ["# Bundled music", "",
               "Every track is a public-domain or CC0 recording from Wikimedia Commons, cut to a 75-second excerpt by",
               "`scripts/make_music.py`. Free for any use, commercial included, no credit required.", "",
               "| File | Recording | Licence |", "|---|---|---|"]
    with tempfile.TemporaryDirectory() as tmp:
        for name, page, lic, url in TRACKS:
            out = OUT / f"{name}.m4a"
            done = OUT / f"{name}.start"  # a rerun after a dropped download skips what is already built
            if out.exists() and done.exists():
                start = float(done.read_text())
                credits.append(f"| {out.name} | [{page}](https://commons.wikimedia.org/wiki/File:"
                               f"{page.replace(' ', '_')}) from {start:.0f} s | {lic} |")
                continue
            # an .ogg original is smaller than its mp3 transcode and served from cache (transcodes are made on demand
            # and crawl); FLAC originals are 40-160 MB, so those keep the transcode
            if not page.endswith(".flac"):
                url = url.replace("/transcoded/", "/").rsplit("/", 1)[0]
            raw = Path(tmp) / f"{name}.{url.rsplit('.', 1)[1]}"
            time.sleep(15)  # Wikimedia answers 429 (10 min cooldown) to back-to-back fetches
            # curl, not urllib: a long Commons transcode stalled urllib for good (2026-11-10)
            subprocess.run(["curl", "-sSfL", "--ssl-no-revoke", "--retry", "4", "--speed-limit", "20000",
                            "--speed-time", "30", "-A", UA["User-Agent"], "-o", str(raw), url], check=True)
            start = steadiest(raw)
            subprocess.run(["ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{start:.1f}",
                            "-t", f"{WINDOW}", "-i", str(raw), "-af",
                            f"afade=t=in:d=2,afade=t=out:st={WINDOW - 3}:d=3,loudnorm=I=-20:TP=-2:LRA=7",
                            "-ar", "44100", "-ac", "2", "-c:a", "aac", "-b:a", "112k", str(out)], check=True)
            credits.append(f"| {out.name} | [{page}](https://commons.wikimedia.org/wiki/File:"
                           f"{page.replace(' ', '_')}) from {start:.0f} s | {lic} |")
            done.write_text(f"{start:.1f}")
            print(name, f"{start:.0f}s", out.stat().st_size // 1024, "KiB", file=sys.stderr)
    (OUT / "CREDITS.md").write_text("\n".join(credits) + "\n", encoding="utf-8")
    for marker in OUT.glob("*.start"):  # every track built: the resume markers are done
        marker.unlink()


if __name__ == "__main__":
    main()
