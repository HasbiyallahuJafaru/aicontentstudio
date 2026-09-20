"""Face-tracked crop: sample the clip's frames, follow the largest face's center x, and turn the moves into
steady shots the crop cuts between (falling back to a centered crop when no face is found)."""
import statistics
from pathlib import Path

import cv2

cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)

FACE_MODEL = Path(__file__).parent / "assets" / "models" / "face_detection_yunet_2026may.onnx"  # MIT, opencv_zoo


def face_xs(video, start: float, end: float, fps: float) -> tuple[int, int, list[float | None]]:
    """Sample frames at `fps`; return frame size and the largest face's center x per sample (None = no face)."""
    # ponytail: largest face = speaker; use mouth movement or diarization when two-person shots pick the wrong one
    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    detector, xs, w, h, next_t = None, [], 0, 0, start
    while cap.grab():
        t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        if t > end:
            break
        if t < next_t:
            continue
        next_t += 1 / fps
        frame = cap.retrieve()[1]
        h, w = frame.shape[:2]
        scale = 640 / w
        small = cv2.resize(frame, None, fx=scale, fy=scale)
        if detector is None:
            detector = cv2.FaceDetectorYN.create(str(FACE_MODEL), "", (small.shape[1], small.shape[0]), 0.7)
        faces = detector.detect(small)[1]
        if faces is None:
            xs.append(None)
        else:
            x, _, fw, _ = max(faces, key=lambda f: f[2] * f[3])[:4]
            xs.append(float(x + fw / 2) / scale)
    cap.release()
    return w, h, xs


def shots(xs: list[float], deadzone: float, hold: int = 3) -> list[tuple[int, float]]:
    """Split per-sample positions into steady shots: (first sample, median x). A move only counts once it
    holds for `hold` samples, so the crop cuts cleanly to a new position instead of wobbling."""
    # ponytail: hard cuts suit static podcast cameras; add eased pans if handheld/walking footage looks choppy
    starts, ref = [0], xs[0]
    for i in range(1, len(xs) - hold + 1):
        run = xs[i:i + hold]
        if abs(run[0] - ref) > deadzone and max(run) - min(run) <= deadzone:
            starts.append(i)
            ref = statistics.median(run)
    return [(s, statistics.median(xs[s:e])) for s, e in zip(starts, starts[1:] + [len(xs)])]


def crop_filter(video, start: float, end: float, ratio: tuple[int, int] = (9, 16), fps: float = 4) -> str:
    """Crop of `ratio` (w, h) that follows the speaker's face horizontally, falling back to a centered crop when no
    face is found."""
    rw, rh = ratio
    w, h, xs = face_xs(video, start, end, fps)
    cw, ch = min(w, h * rw // rh) // 2 * 2, min(h, w * rh // rw) // 2 * 2
    seen = [x for x in xs if x is not None]
    if not seen or cw == w:
        return f"crop='min(iw,ih*{rw}/{rh})':'min(ih,iw*{rh}/{rw})'"
    filled, last = [], seen[0]
    for x in xs:  # frames without a face keep the last known position
        last = last if x is None else x
        filled.append(last)
    parts = [(i / fps, round(min(max(x - cw / 2, 0), w - cw))) for i, x in shots(filled, cw * 0.2)]
    expr = str(parts[-1][1])
    for (t_next, _), (_, x) in zip(reversed(parts[1:]), reversed(parts[:-1])):
        expr = f"if(lt(t,{t_next:.2f}),{x},{expr})"
    return f"crop={cw}:{ch}:'{expr}':0"
