"""The edit grammar in code (see `.claude/edit-grammar.md`): how each genre is cut, graded and dressed.

One table so the grade cannot drift from the cadence. `renders.py` reads CUTS to build the shot plan,
`render.py` reads LOOKS to build the filter chain. Nothing here talks to ffmpeg or the database.
"""

# A colour grade plus the film dressing that rides with it.
#   grade:    filter terms applied to the whole timeline (curves/eq/colorbalance, no leading comma)
#   bloom:    halation opacity, 0 disables the blurred highlight pass
#   grain:    `noise=alls=` strength, at most 5: temporal grain is noise the encoder must spend bits on (8 ran
#             24 Mbps, 10 ran 50 Mbps, 2026-11-09) and platform re-encodes turn heavy grain into blocks
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
    "mono": {"grade": "hue=s=0", "bloom": 0.18, "grain": 5, "vignette": 4.0, "unsharp": 0.0, "bars": 0.0},
    "vivid": {"grade": "eq=saturation=1.32:contrast=1.05", "bloom": 0.0, "grain": 4, "vignette": 5.0,
              "unsharp": 0.0, "bars": 0.0},
    # genre grades: reached when the brief's Look is "auto"
    # 2026-11-10: split-toned (shadows and highlights pushed apart) and about twice as strong as the first cut,
    # which nudged curves ~3% and read as ungraded; the per-shot match in render.NORMALIZE makes this safe to push
    "hope": {"grade": "colorbalance=rs=.04:bs=.05:rh=.08:gh=.03:bh=-.08,"
                      "curves=all='0/0.04 0.25/0.24 0.75/0.8 1/0.97',eq=saturation=1.05:contrast=1.04",
             "bloom": 0.30, "grain": 4, "vignette": 6.0, "unsharp": 0.0, "bars": 0.0},
    "speech": {"grade": "colorbalance=rs=-.05:bs=.07:rh=.05:bh=-.04,"
                        "curves=all='0/0 0.25/0.19 0.75/0.82 1/1',eq=saturation=0.62:contrast=1.2",
               "bloom": 0.0, "grain": 5, "vignette": 3.5, "unsharp": 0.6, "bars": 0.0},
    "stoic": {"grade": "colorbalance=rs=-.04:gs=.01:bs=.06:rh=.05:gh=.02:bh=-.03,"
                       "curves=all='0/0.05 0.25/0.22 0.75/0.78 1/0.95',eq=saturation=0.6:contrast=1.08",
              "bloom": 0.0, "grain": 3, "vignette": 6.0, "unsharp": 0.0, "bars": 0.0},
    "history": {"grade": "eq=saturation=0.42,colorbalance=rs=.03:bs=-.02:rm=.12:gm=.05:bm=-.10:rh=.06:bh=-.08,"
                         "curves=all='0/0.07 0.25/0.24 0.75/0.79 1/0.95'",
                "bloom": 0.20, "grain": 5, "vignette": 3.0, "unsharp": 0.0, "bars": 0.11},
    "books": {"grade": "colorbalance=rs=.03:gs=.01:bs=-.02:rh=.07:gh=.03:bh=-.07,"
                       "curves=all='0/0.05 0.25/0.24 0.75/0.79 1/0.96',eq=saturation=0.85:contrast=1.04",
              "bloom": 0.18, "grain": 5, "vignette": 5.0, "unsharp": 0.0, "bars": 0.0},
    "cinema": {"grade": "colorbalance=rs=-.07:gs=-.01:bs=.09:rh=.08:gh=.02:bh=-.09,"
                        "curves=all='0/0.03 0.25/0.21 0.75/0.8 1/0.97',eq=saturation=1.0:contrast=1.08",
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
MAX_SHOTS = 20     # a 60 s documentary cut every 3 s; past this the edit is strobing, not cutting
STRETCH = 1.8      # a shot may hold up to this times the cadence's longest before footage is reused
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
    # one shot per asset when the pool can cover the voice at a held cadence; footage repeats only when the pool
    # is too small for that (2026-11-10: four clips cycled three times each read as a loop, not an edit)
    ideal = max(1, round(duration / mid))
    n = min(ideal, len(assets))
    if duration / n > cut["cadence"][1] * STRETCH:
        n = min(MAX_SHOTS, len(assets) * 3, -(-int(duration * 1000) // int(cut["cadence"][1] * STRETCH * 1000)))
    n = max(1, min(n, MAX_SHOTS))
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
