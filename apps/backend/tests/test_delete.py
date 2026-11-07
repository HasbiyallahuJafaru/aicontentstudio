"""Individual deletes (owner ask 2026-11-07): each one removes exactly its own rows and files, nothing else."""
import json
import os
import tempfile
import unittest

os.environ.setdefault("ACS_DATA_DIR", tempfile.mkdtemp())

from app import assets, clips, config, content, database, export, jobs, projects, renders  # noqa: E402
from app.errors import UserError  # noqa: E402

from tests.test_content import BRIEF  # noqa: E402


def touch(rel: str, base=None) -> str:
    path = (base or config.MEDIA_DIR) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return rel


def piece(project_id: str, idx: int, asset_ids=()) -> str:
    c = {"plan": {"visual_type": "video"}, "visual": {"search_query": "q"}, "quote": {"text": f"line {idx}"}}
    if asset_ids:
        c["assets"] = [{"id": a, "provider": "pexels", "asset_type": "video"} for a in asset_ids]
        c["asset"] = c["assets"][0]
    return content._insert(project_id, idx, f"angle {idx}", f"line {idx}", c)


def render(project_id: str, piece_id: str, kind: str) -> tuple[str, str]:
    rid = f"r-{piece_id}-{kind}"
    rel = touch(f"renders/{rid}.{'mp4' if kind == 'video' else 'jpg'}")
    with database.connect() as conn:
        conn.execute("INSERT INTO renders (id, project_id, piece_id, kind, local_path) VALUES (?,?,?,?,?)",
                     (rid, project_id, piece_id, kind, rel))
    return rid, rel


class Deletes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.migrate()

    def test_render_delete_removes_only_that_file(self):
        p = projects.create(BRIEF)
        pid = piece(p["id"], 1)
        (vid, vrel), (_, irel) = render(p["id"], pid, "video"), render(p["id"], pid, "image")
        renders.delete(vid)
        self.assertFalse((config.MEDIA_DIR / vrel).exists())
        self.assertTrue((config.MEDIA_DIR / irel).exists(), "the sibling render stays")
        self.assertEqual([r["kind"] for r in renders.list_(p["id"])], ["image"])

    def test_piece_delete_takes_its_renders_and_leaves_siblings(self):
        p = projects.create(BRIEF)
        a, b = piece(p["id"], 1), piece(p["id"], 2)
        _, arel = render(p["id"], a, "video")
        _, brel = render(p["id"], b, "video")
        content.delete_piece(a)
        self.assertEqual([x["id"] for x in content.pieces(p["id"])], [b])
        self.assertFalse((config.MEDIA_DIR / arel).exists())
        self.assertTrue((config.MEDIA_DIR / brel).exists())

    def test_asset_delete_drops_the_shot_and_flags_an_empty_piece(self):
        p = projects.create(BRIEF)
        with database.connect() as conn:
            for aid in ("del1", "del2"):
                conn.execute("INSERT INTO assets (id, provider, provider_asset_id, asset_type, local_path, thumb_path) "
                             "VALUES (?, 'pexels', ?, 'video', ?, ?)",
                             (aid, aid, touch(f"assets/{aid}.mp4"), touch(f"thumbs/{aid}.jpg")))
        two, one = piece(p["id"], 1, ("del1", "del2")), piece(p["id"], 2, ("del1",))
        with database.connect() as conn:
            for pc, aid in ((two, "del1"), (two, "del2"), (one, "del1")):
                conn.execute("INSERT INTO asset_usage (asset_id, piece_id) VALUES (?, ?)", (aid, pc))
        assets.delete_asset("del1")
        self.assertFalse((config.MEDIA_DIR / "assets/del1.mp4").exists())
        self.assertFalse((config.MEDIA_DIR / "thumbs/del1.jpg").exists())
        by_id = {x["id"]: x["content"] for x in content.pieces(p["id"])}
        self.assertEqual([a["id"] for a in by_id[two]["assets"]], ["del2"], "the other shot stays")
        self.assertEqual(by_id[two]["asset"]["id"], "del2")
        self.assertNotIn("asset", by_id[one])
        self.assertIn("Find another visual", by_id[one]["visual_error"])

    def test_clip_delete_removes_video_cover_and_captions(self):
        p = projects.create({"kind": "clip", "source": "https://www.youtube.com/watch?v=test"})
        files = [touch("clips/x/clip01.mp4"), touch("clips/x/clip01.ass"), touch("clips/x/clip01.jpg")]
        with database.connect() as conn:
            conn.execute("INSERT INTO clips (id, project_id, idx, start_at, end_at, score, reason, hook, title, description, "
                         "hashtags, posts, video_path, cover_path) VALUES ('c1', ?, 1, 0, 30, 90, 'r', 'h', 'Title', 'd', "
                         "'[]', '{}', ?, ?)", (p["id"], files[0], files[2]))
        clips.delete("c1")
        self.assertFalse(any((config.MEDIA_DIR / f).exists() for f in files))
        self.assertEqual(clips.list_(p["id"]), [])

    def test_export_delete_keeps_other_projects_from_the_same_day(self):
        mine, theirs = projects.create({**BRIEF, "topic": "Mine"}), projects.create({**BRIEF, "topic": "Theirs"})
        mine_name, theirs_name = projects.get(mine["id"])["name"], projects.get(theirs["id"])["name"]
        day = "exports/2000-01-01"  # sorts first: other tests pick the newest export folder
        touch(f"{day}/001_{export._slug(mine_name)}/video_9x16.mp4", config.DATA_DIR)
        touch(f"{day}/001_{export._slug(theirs_name)}/video_9x16.mp4", config.DATA_DIR)
        with database.connect() as conn:
            for eid, pid in (("e-mine", mine["id"]), ("e-theirs", theirs["id"])):
                conn.execute("INSERT INTO exports (id, project_id, dir, pieces) VALUES (?, ?, ?, 1)", (eid, pid, day))
        export.delete("e-mine")
        self.assertFalse((config.DATA_DIR / day / f"001_{export._slug(mine_name)}").exists())
        self.assertTrue((config.DATA_DIR / day / f"001_{export._slug(theirs_name)}").exists())
        self.assertEqual([e["id"] for e in export.list_() if e["dir"] == day], ["e-theirs"])
        export.delete("e-theirs")
        self.assertFalse((config.DATA_DIR / day).exists(), "an emptied date folder goes too")

    def test_deletes_wait_for_a_running_job(self):
        p = projects.create(BRIEF)
        pid = piece(p["id"], 1)
        rid, _ = render(p["id"], pid, "video")
        with database.connect() as conn:
            conn.execute("INSERT INTO generation_jobs (id, project_id, kind, status) VALUES ('del-busy', ?, 'render', 'running')",
                         (p["id"],))
        try:
            with self.assertRaisesRegex(UserError, "job running"):
                renders.delete(rid)
            with self.assertRaisesRegex(UserError, "job running"):
                content.delete_piece(pid)
        finally:
            with database.connect() as conn:
                conn.execute("UPDATE generation_jobs SET status = 'completed' WHERE id = 'del-busy'")
        self.assertTrue(jobs.latest(p["id"]))


if __name__ == "__main__":
    unittest.main()
