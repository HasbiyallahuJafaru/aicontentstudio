"""Motion graphics (HyperFrames): animated layers rendered with alpha and composited over the edit by ffmpeg.

A layer is a template in app/motion_assets/ (hook title, callout) filled with data; the AI only ever supplies the data,
never markup. Rendering runs apps/desktop/motion/render.mjs on the app's own Electron binary as Node, with the
Edge that ships with Windows (or Chrome) as the browser. Rendered layers are cached by content, so a re-render with
the same hook is free. Motion is a nicety: no browser, the setting off or a failed render means the video ships
without it, never a failed job."""
import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from app import config, settings
from app.clipper.tighten import bare

log = logging.getLogger("motion")

HERE = Path(__file__).parent / "motion_assets"
FONT = Path(__file__).parent / "clipper" / "assets" / "fonts" / "Montserrat-ExtraBold.ttf"
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")]
# per genre: accent colour and whether the hook shouts. Clips use the caption emphasis orange.
LOOKS = {"hope": ("#FFB86B", False), "speech": ("#FF3B3B", True), "stoic": ("#D9D9D9", True),
         "history": ("#E8C48A", False), "books": ("#F2D49B", False), "cinema": ("#4FD1C5", True),
         "clip": ("#FF7A3D", True)}
HOOK_SECS, CALLOUT_SECS = 2.6, 1.6
MAX_HOOK_WORDS = 9
TIMEOUT = 300  # a 3 s layer takes ~30 s on a laptop; this is the wedged-browser backstop


def browser() -> str | None:
    env = os.environ.get("HYPERFRAMES_BROWSER_PATH")
    return next((b for b in ([env] if env else []) + BROWSERS if b and Path(b).exists()), None)


def _runner() -> tuple[str, str] | None:
    """(node binary, runner script). The app passes its Electron exe + the packaged script; dev falls back."""
    script = os.environ.get("ACS_MOTION_RUNNER") or str(config.REPO_ROOT / "apps" / "desktop" / "motion" / "render.mjs")
    node = os.environ.get("ACS_NODE") or shutil.which("node")
    return (node, script) if node and Path(script).exists() else None


def enabled() -> bool:
    return (settings.get()["motion_graphics"] and not os.environ.get("ACS_NO_MOTION")
            and browser() is not None and _runner() is not None)


def hook_words(text: str) -> list[dict]:
    """Hook text to template words. *Starred* words (the model marks 1-2) are the keywords: accent colour, bounce."""
    words, inside = [], False
    for token in text.split():
        starts, ends = token.startswith("*"), token.rstrip(".,!?:;").endswith("*")
        word = token.replace("*", "")
        if word:
            words.append({"t": word, "key": inside or starts or ends})
        inside = (inside or starts) and not ends
    return words[:MAX_HOOK_WORDS]


def _render(template: str, params: dict, w: int, h: int, duration: float) -> Path | None:
    html = ((HERE / f"{template}.html").read_text(encoding="utf-8")
            .replace("__W__", str(w)).replace("__H__", str(h)).replace("__DUR__", f"{duration:g}")
            .replace("/*PARAMS*/null", json.dumps(params | {"w": w, "h": h, "duration": duration})))
    out = config.MEDIA_DIR / "motion" / f"{template}-{hashlib.sha256(html.encode()).hexdigest()[:16]}.webm"
    if out.exists():
        return out
    node, script = _runner()
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(out.stem + ".part.webm")
    env = {**os.environ, "ELECTRON_RUN_AS_NODE": "1", "HYPERFRAMES_BROWSER_PATH": browser()}
    for name, binary in (("HYPERFRAMES_FFMPEG_PATH", config.FFMPEG), ("HYPERFRAMES_FFPROBE_PATH", config.FFPROBE)):
        if Path(binary).is_file():  # the bundled ffmpeg; on PATH the engine finds its own
            env[name] = binary
    work = config.MEDIA_DIR / "tmp"
    work.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as d:
        (Path(d) / "index.html").write_text(html, encoding="utf-8")
        shutil.copy(HERE / "gsap.min.js", d)
        shutil.copy(FONT, Path(d) / "font.ttf")
        try:
            proc = subprocess.run([node, script, d, str(part)], env=env, cwd=d, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            log.warning("motion layer %s timed out after %ss", template, TIMEOUT)
            return None
    result = next((line for line in reversed(proc.stdout.splitlines()) if line.startswith("{")), "{}")
    if proc.returncode != 0 or not part.exists():
        log.warning("motion layer %s failed: %s %s", template, result[:500], proc.stderr[-500:])
        part.unlink(missing_ok=True)
        return None
    part.replace(out)
    return out


def layers(genre: str, w: int, h: int, hook: str = "", callouts: list[tuple[str, float]] = ()) -> list[dict]:
    """[{path, start}] for the overlays this video gets: the hook title at 0, each callout at its time.
    Empty when motion is off or unavailable, so callers composite nothing and ship the plain edit."""
    if not enabled() or not (hook or callouts):
        return []
    accent, upper = LOOKS.get(genre, LOOKS["clip"])
    wanted = []
    if words := hook_words(hook):
        wanted.append(("hook", {"words": words, "accent": accent, "upper": upper}, HOOK_SECS, 0.0))
    for text, at in callouts:
        wanted.append(("callout", {"text": text[:24], "accent": accent}, CALLOUT_SECS, max(at, HOOK_SECS + 0.2)))
    out = []
    for template, params, secs, start in wanted:
        if path := _render(template, params, w, h, secs):
            out.append({"path": path, "start": start})
    return out


def overlay_graph(base: str, layers_: list[dict], first_input: int) -> tuple[list[str], list[str], str]:
    """ffmpeg pieces to composite `layers_` over the `base` stream: (input args, filter chains, output label).
    Each layer is decoded with libvpx (the native vp9 decoder drops alpha) and shifted to its start time."""
    args, chain, prev = [], [], base
    for i, layer in enumerate(layers_):
        idx = first_input + i
        args += ["-c:v", "libvpx-vp9", "-i", str(layer["path"])]
        chain.append(f"[{idx}:v]setpts=PTS+{layer['start']:.3f}/TB[ml{i}]")
        chain.append(f"[{prev}][ml{i}]overlay=0:0:eof_action=pass:format=auto[mo{i}]")
        prev = f"mo{i}"
    return args, chain, prev


def anchor_time(words: list[dict], anchor: str) -> float | None:
    """When the narration says `anchor` (first match): that's where its callout lands. A multi-word anchor
    ("human being", seen from the real writer) lands on its first word."""
    want = bare(anchor.split()[0]) if anchor.split() else ""
    return next((w["start"] for w in words if bare(w["word"]) == want), None)
