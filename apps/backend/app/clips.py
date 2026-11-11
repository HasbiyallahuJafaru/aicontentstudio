"""Clip orchestration: runs the engine over a clip project's source video, records rows in `clips`, keeps the
transcript cached on disk by source key. Rides the shared job system (generation_jobs.kind = 'clip')."""
import json
import shutil
import uuid
from pathlib import Path

from pydantic import BaseModel, Field

from app import config, motion, music, projects, settings
from app.clipper import acquire, select, tighten, transcribe
from app.clipper.ff import silences
from app.clipper.render_clip import ORIENTATIONS, render as render_clip
from app.clipper.select import snap
from app.database import connect
from app.errors import UserError

WORK = "clipwork"  # under media/: downloaded sources + cached transcripts
MIN_CLIP = config.MIN_CLIP  # seconds, of the FINISHED clip (the floor: 60 s, owner 2026-11-10)
PER_CLIP = 150  # seconds of speech per auto clip: a 60 min talk gives ~24 (owner: as many as the source holds)


def _at_least(video, words, start, end, cold, min_len, spoken):
    """Plan the cut, then make sure what's left after dead air and fillers come out still runs min_len: grow the
    clip EARLIER, into its setup, snapped to sentences. Never later: the end is the payoff, and talk added after it
    killed the ending and the loop (2026-11-09). Only when nothing earlier is left does it run on, sentence by
    sentence, past the end: the minute is a hard floor (owner 2026-11-10)."""
    ranges, zooms = tighten.plan(words, start, end, cold, silences(video, start, end))
    for attempt in range(8):
        short = min_len - sum(b - a for a, b in ranges)
        if short <= 0 or start <= 0:
            break
        new_start, _ = snap(max(0.0, start - short - 2.0 - 2.0 * attempt), end, words)
        if new_start >= start:
            break  # no earlier sentence to take in
        start = max(0.0, new_start - 0.1)
        ranges, zooms = tighten.plan(words, start, end, cold, silences(video, start, end))
    last = words[-1]["end"] if words else end
    for attempt in range(8):  # still short: take in the following sentences
        short = min_len - sum(b - a for a, b in ranges)
        if short <= 0 or end >= last:
            break
        _, new_end = snap(start, min(last, end + short + 2.0 + 2.0 * attempt), words)
        if new_end <= end:
            break
        end = new_end
        ranges, zooms = tighten.plan(words, start, end, cold, silences(video, start, end))
    return start, end, ranges, zooms


def load_transcript(key: str) -> dict | None:
    p = config.MEDIA_DIR / WORK / key / "transcript.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def save_transcript(key: str, transcript: dict) -> None:
    p = config.MEDIA_DIR / WORK / key / "transcript.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(transcript, ensure_ascii=False), encoding="utf-8")


def run(project_id: str, report) -> None:
    """Same (project_id, report) runner shape as content.generate / renders.render_project (jobs.py dispatch)."""
    from app.publish import posts
    b = projects.get(project_id)["brief"]
    # posts are keyed by clip number: new clips would inherit the old ones' "Scheduled" chips and slots
    if left := posts.waiting(project_id, clips=True):
        raise UserError(f"{len(left)} of this project's clip posts are still scheduled. Unschedule them (or wait "
                        "until they've gone out), then clip again.")
    # a re-clip renders into a staging folder and replaces the previous take only once it has succeeded: a
    # failure (a 429 bot check, a bad model reply) used to leave the project with nothing (2026-11-09)
    final = config.MEDIA_DIR / "clips" / project_id
    out = final.with_name(f"{project_id}.next")
    if out.exists():
        shutil.rmtree(out)

    meta: dict = {}
    video, work = acquire.acquire(b["source"], config.MEDIA_DIR / WORK,
                                  lambda pct: report("Downloading", round(0.02 + 0.23 * pct / 100, 3)), meta,
                                  cookies=settings.get()["ytdlp_cookies"])
    if meta.get("title"):  # the source's own title is the honest project name
        with connect() as conn:
            conn.execute("UPDATE projects SET name = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
                         "WHERE id = ?", (meta["title"][:80], project_id))
    report("Transcribing", 0.25)
    transcript = load_transcript(work.name)
    if transcript is None:
        transcript = transcribe.transcribe(video, work)
        save_transcript(work.name, transcript)
    if not transcript["segments"]:
        raise UserError("No speech found in this video, so there is nothing to clip.")

    report("Finding the best moments", 0.5)
    # projects saved before the one-minute floor may hold shorter lengths: the floor wins
    min_len = max(float(b["min_len"]), MIN_CLIP)
    max_len = max(float(b["max_len"]), min_len + 15)
    spoken = transcript["words"][-1]["end"] if transcript["words"] else transcript["segments"][-1]["end"]
    # as many as the source holds (owner 2026-11-10: an hour-long talk is not 10 clips): one per PER_CLIP seconds
    # of speech, never more than fit without overlapping. One per minute (2026-11-09) tiled the whole transcript
    # into filler; one per 2.5 min leaves the model room to choose.
    fits = max(1, int(spoken // (min_len * 1.1)))
    n = min(b["n"] or max(3, round(spoken / PER_CLIP)), fits)
    if spoken < min_len:
        raise UserError(f"This video has about {round(spoken)} seconds of speech, and every clip runs at least "
                        f"{round(min_len)} seconds. Try a longer video.")
    found = select.find_clips(transcript, n, min_len, max_len)

    out.mkdir(parents=True, exist_ok=True)
    total = len(found)
    rows = []
    for i, clip in enumerate(found, 1):
        report(f"Rendering clip {i} of {total}", round(0.55 + 0.45 * (i - 1) / total, 3))
        words = transcript["words"]
        clip.start, clip.end = snap(clip.start, clip.end, words)
        start, end = max(0, clip.start - 0.1), clip.end + 0.2  # the 0.2 s is air, not room for the next word
        words = [w for w in words if w["start"] < clip.end]  # "...is patience. So" ended clips on the next sentence
        cold = tighten.to_words(words, *clip.cold_open) if clip.cold_open else None
        path = out / f"clip{i:02}.mp4"
        layers = motion.layers("clip", *ORIENTATIONS[b["orientation"]][1], hook=clip.hook)  # animated title
        start, end, ranges, zooms = _at_least(video, words, start, end, cold, min_len, spoken)
        clip.start, clip.end = start, end
        render_clip(video, start, end, path, words, b["burn_captions"], b["orientation"], fps=b["fps"],
                    ranges=ranges, zooms=zooms, emphasis=clip.emphasis, layers=layers,
                    caption_style=b.get("captions"),
                    music=music.for_clip(i) if settings.get().get("bundled_music", True) else None)
        clip.hook = clip.hook.replace("*", "")  # the keyword marks are for the animation, not the stored copy
        landed = final / path.name  # where the file lives once the take is swapped in
        rows.append((uuid.uuid4().hex[:12], project_id, i, clip.start, clip.end, clip.score, clip.reason,
                     clip.hook, clip.title, clip.description, json.dumps(clip.hashtags, ensure_ascii=False),
                     clip.posts.model_dump_json(), _rel(landed), _rel(landed.with_suffix(".jpg"))))
    report("Saving the clips", 0.99)
    if final.exists():
        shutil.rmtree(final)
    out.rename(final)
    with connect() as conn:  # the new take replaces the old in one transaction, old clips' post history with it
        conn.execute("DELETE FROM clips WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM publications WHERE project_id = ? AND piece_id IS NULL", (project_id,))
        conn.executemany("INSERT INTO clips (id, project_id, idx, start_at, end_at, score, reason, hook, title, "
                         "description, hashtags, posts, video_path, cover_path) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         rows)
    report("Done", 1.0)


def _rel(path: Path) -> str:
    return path.relative_to(config.MEDIA_DIR).as_posix()


def delete(clip_id: str) -> dict:
    """Delete one clip: its video, cover frame and caption file."""
    from app import jobs
    with connect() as conn:
        row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    if row is None:
        raise UserError("This clip no longer exists.", f"clip id {clip_id}")
    jobs.ensure_idle(row["project_id"])
    from app.publish import posts
    posts.release(row["project_id"], clip_idx=row["idx"])
    with connect() as conn:
        conn.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
    video = config.MEDIA_DIR / row["video_path"]
    for f in (video, video.with_suffix(".ass"), config.MEDIA_DIR / row["cover_path"]):
        f.unlink(missing_ok=True)
    return {"deleted": clip_id}


def list_(project_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM clips WHERE project_id = ? ORDER BY idx", (project_id,)).fetchall()
    return [_present(r) for r in rows]


def _present(r) -> dict:
    return {**dict(r), "hashtags": json.loads(r["hashtags"]), "posts": json.loads(r["posts"])}


class ClipEdit(BaseModel):
    """A person's own copy for a clip (ported from ClipperAi's ClipEdit). Omitted fields stay as they are."""
    title: str | None = Field(None, min_length=1, max_length=300)
    hook: str | None = Field(None, max_length=300)
    description: str | None = Field(None, max_length=5000)
    hashtags: list[str] | None = Field(None, max_length=30)
    posts: dict[str, str] | None = None


def update(id: str, **fields) -> dict:
    """Replace a clip's copy. A post over its network's limit is refused with the numbers, never shortened:
    select.Posts trims the model's copy, not a person's words."""
    edit = ClipEdit.model_validate(fields)
    for network, text in (edit.posts or {}).items():
        if network not in select.LIMITS:
            raise UserError("Unknown platform in the post copy.", network)
        if len(text) > select.LIMITS[network]:
            raise UserError(f"The {label(network)} post is {len(text)} characters long; {label(network)} allows "
                            f"{select.LIMITS[network]}. Shorten it and save again.")
    with connect() as conn:
        row = conn.execute("SELECT posts FROM clips WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise UserError("This clip no longer exists.", id)
        changes = edit.model_dump(exclude_none=True, exclude={"posts", "hashtags"})
        if edit.hashtags is not None:
            changes["hashtags"] = json.dumps([t.strip() for t in edit.hashtags if t.strip()], ensure_ascii=False)
        if edit.posts is not None:  # merge: a platform left out keeps its copy
            changes["posts"] = json.dumps(json.loads(row["posts"]) | edit.posts, ensure_ascii=False)
        if changes:
            conn.execute(f"UPDATE clips SET {', '.join(f'{k} = ?' for k in changes)} WHERE id = ?",  # keys: model fields
                         (*changes.values(), id))
        return _present(conn.execute("SELECT * FROM clips WHERE id = ?", (id,)).fetchone())


def label(network: str) -> str:
    return {"tiktok": "TikTok", "youtube": "YouTube", "linkedin": "LinkedIn", "x": "X"}.get(network, network.title())


def review(id: str, status: str) -> dict:
    if status not in ("ready", "rejected"):  # no approve step (owner 2026-11-08)
        raise UserError("Unknown clip status.", status)
    with connect() as conn:
        if conn.execute("UPDATE clips SET status = ? WHERE id = ?", (status, id)).rowcount == 0:
            raise UserError("This clip no longer exists.", id)
    return {"id": id, "status": status}
