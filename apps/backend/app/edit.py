"""The edit grammar in code (see `.claude/edit-grammar.md`): how each genre is cut, graded and dressed.

One table so the grade cannot drift from the cadence. `renders.py` reads CUTS to build the shot plan,
`render.py` reads LOOKS to build the filter chain. Nothing here talks to ffmpeg or the database.
"""

# A colour grade plus the film dressing that rides with it.
#   grade:    filter terms applied to the whole timeline (curves/eq/colorbalance, no leading comma)
#   bloom:    halation opacity, 0 disables the blurred highlight pass
#   grain:    `noise=alls=` strength
#   vignette: corner falloff angle divisor (higher = subtler), None disables
#   unsharp:  micro-contrast amount, 0 disables
#   bars:     letterbox height as a share of the frame, 0 disables
# ponytail: 1D curves per channel, not a 3D LUT. lut3d is verified to work here and buys true cross-channel
# grading (real bleach bypass, luminance-keyed split tone); move to it when a genre needs more than this.
LOOKS = {
    "none": {"grade": "", "bloom": 0.0, "grain": 4, "vignette": 5.0, "unsharp": 0.0, "bars": 0.0},
    "warm": {"grade": "colorbalance=rm=.07:bm=-.07,eq=saturation=1.08", "bloom": 0.22, "grain": 4,
             "vignette": 5.0, "unsharp": 0.0, "bars": 0.0},
    "cool": {"grade": "colorbalance=rm=-.06:bm=.07", "bloom": 0.0, "grain": 4, "vignette": 5.0,
             "unsharp": 0.0, "bars": 0.0},
    "mono": {"grade": "hue=s=0", "bloom": 0.18, "grain": 6, "vignette": 4.0, "unsharp": 0.0, "bars": 0.0},
    "vivid": {"grade": "eq=saturation=1.32:contrast=1.05", "bloom": 0.0, "grain": 4, "vignette": 5.0,
              "unsharp": 0.0, "bars": 0.0},
    # genre grades: reached when the brief's Look is "auto"
    "hope": {"grade": "curves=r='0/0.02 0.5/0.53 1/1':g='0/0.015 0.5/0.5 1/0.99':b='0/0.03 0.5/0.48 1/0.96',"
                      "eq=saturation=1.02:contrast=1.02",
             "bloom": 0.30, "grain": 4, "vignette": 6.0, "unsharp": 0.0, "bars": 0.0},
    "speech": {"grade": "curves=r='0/0 0.5/0.52 1/1':b='0/0.02 0.5/0.48 1/0.98',"
                        "eq=saturation=0.75:contrast=1.22",
               "bloom": 0.0, "grain": 8, "vignette": 3.5, "unsharp": 0.6, "bars": 0.0},
    "stoic": {"grade": "curves=r='0/0 0.5/0.47 1/0.97':b='0/0.05 0.5/0.53 1/1',"
                       "eq=saturation=0.85:contrast=1.06",
              "bloom": 0.0, "grain": 3, "vignette": 6.0, "unsharp": 0.0, "bars": 0.0},
    "history": {"grade": "eq=saturation=0.35,colorbalance=rm=.12:gm=.04:bm=-.10,"
                         "curves=all='0/0.06 0.5/0.5 1/0.96'",
                "bloom": 0.20, "grain": 10, "vignette": 3.0, "unsharp": 0.0, "bars": 0.11},
    "books": {"grade": "curves=r='0/0.01 0.5/0.51 1/0.99':b='0/0.03 0.5/0.5 1/0.97',"
                       "eq=saturation=0.95:contrast=1.04",
              "bloom": 0.18, "grain": 5, "vignette": 5.0, "unsharp": 0.0, "bars": 0.0},
    "cinema": {"grade": "curves=r='0/0 0.45/0.47 1/1':b='0/0.06 0.5/0.52 1/0.94',"
                        "eq=saturation=1.1:contrast=1.08",
               "bloom": 0.40, "grain": 4, "vignette": 5.0, "unsharp": 0.0, "bars": 0.11},
}

# How each genre is cut.
#   cadence:    (min, max) seconds a shot holds; the planner aims at the middle and snaps to the voice
#   transition: (xfade name, seconds) or None for hard cuts
#   every:      transition on every cut, or only into the final shot
#   motion:     the camera moves a shot may take, cycled so neighbours never move the same way
#   ramp:       slow the turn shot (the beat before the last) for a pattern interrupt
#   duck:       how far music drops under the narration, in dB
DEFAULT = {"cadence": (2.6, 3.2), "transition": ("dissolve", 0.35), "every": True,
           "motion": ("push",), "ramp": False, "duck": 6.0, "look": "hope"}
CUTS = {
    "hope": DEFAULT,
    "speech": {"cadence": (1.4, 1.9), "transition": ("fadeblack", 0.2), "every": False,
               "motion": ("in", "out"), "ramp": True, "duck": 8.0, "look": "speech"},
    "stoic": {"cadence": (3.0, 4.0), "transition": ("fade", 0.3), "every": False,
              "motion": ("slow", "still"), "ramp": False, "duck": 5.0, "look": "stoic"},
    "history": {"cadence": (2.4, 3.0), "transition": ("fadeblack", 0.25), "every": True,
                "motion": ("push", "slow"), "ramp": False, "duck": 5.0, "look": "history"},
    "books": {"cadence": (2.6, 3.2), "transition": ("dissolve", 0.3), "every": False,
              "motion": ("push", "slow"), "ramp": False, "duck": 6.0, "look": "books"},
    "cinema": {"cadence": (3.5, 4.5), "transition": ("fadeblack", 0.4), "every": True,
               "motion": ("in", "pan"), "ramp": True, "duck": 4.0, "look": "cinema"},
}
MAX_SHOTS = 12     # past this the edit is strobing, not cutting
HARD = ("fade", 0.04)  # a hard cut, expressed as a one-frame blend so every join uses the same timeline maths
TAIL = 0.6         # the last shot holds this long past the final word: the screenshot frame


def cut_for(tone: str) -> dict:
    return CUTS.get(tone, DEFAULT)


def look_for(name: str, tone: str) -> dict:
    """The brief's Look, or the genre's own grade when it is left on auto."""
    return LOOKS.get(cut_for(tone)["look"] if name == "auto" else name, LOOKS["none"])


def breaths(words: list[dict]) -> list[float]:
    """Times the voice gives us to cut on: a real gap between words, or the end of a clause."""
    out = []
    for i, w in enumerate(words):
        nxt = words[i + 1]["start"] if i + 1 < len(words) else None
        gap = (nxt - w["end"]) if nxt is not None else 0.0
        if gap > 0.18 or w["word"].rstrip()[-1:] in ".?!,;:":
            out.append(round(w["end"] + min(gap / 2, 0.12), 3))
    return out


def cuts(duration: float, words: list[dict], n: int, cadence: tuple[float, float]) -> list[float]:
    """Cut times for `n` shots across `duration`, snapped to the nearest breath in the narration.

    Falls back to even spacing where the voice offers nothing usable, so a piece without word timings still
    cuts on cadence rather than not at all. Returns the n+1 boundaries, starting at 0 and ending at duration.
    """
    if n <= 1:
        return [0.0, duration]
    lo = cadence[0] * 0.6
    options = [b for b in breaths(words) if 0 < b < duration]
    edges = [0.0]
    for i in range(1, n):
        ideal = duration * i / n
        floor, ceiling = edges[-1] + lo, duration - lo * (n - i)
        near = [b for b in options if floor <= b <= ceiling]
        edges.append(min(near, key=lambda b: abs(b - ideal)) if near else max(min(ideal, ceiling), floor))
    return [*edges, duration]


def plan(assets: list[dict], duration: float, words: list[dict], tone: str) -> list[dict]:
    """The shot plan: which visual is on screen when, how it moves, and what it cuts through.

    Shots cycle the piece's pool so neighbours are never the same location, and the same asset used twice
    enters at a different point. Lengths already carry the transition overlap, so the concatenated timeline
    still lands on `duration`.
    """
    cut = cut_for(tone)
    mid = sum(cut["cadence"]) / 2
    n = max(1, min(len(assets) * 3, MAX_SHOTS, round(duration / mid) or 1))
    edges = cuts(duration, words, n, cut["cadence"])
    trans, tdur = cut["transition"] or (None, 0.0)
    moves = cut["motion"]
    turn = n - 2 if cut["ramp"] and n >= 3 else -1

    shots = []
    for i in range(n):
        asset = assets[i % len(assets)]
        uses = [j for j in range(n) if j % len(assets) == i % len(assets)]
        shot = {"asset": asset, "length": round(edges[i + 1] - edges[i], 3),
                "motion": moves[i % len(moves)], "nth": uses.index(i), "of": len(uses),
                "speed": 1.8 if i == turn else 1.0}
        if i:
            named = trans and (cut["every"] or i == n - 1)
            shot["transition"], shot["tdur"] = (trans, tdur) if named else HARD
            shot["length"] = round(shot["length"] + shot["tdur"], 3)  # the overlap xfade eats back out
        shots.append(shot)
    return shots
