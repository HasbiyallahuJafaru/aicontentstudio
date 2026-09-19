"""Milestone 2: generation pipeline, jobs, dedup and the DeepSeek client. No network: fake model + httpx.MockTransport."""
import json
import os
import tempfile
import time
import unittest
from unittest import mock

os.environ.setdefault("ACS_DATA_DIR", tempfile.mkdtemp())

import httpx  # noqa: E402

from app import content, database, jobs, projects  # noqa: E402
from app.creative import model as creative  # noqa: E402
from app.creative.schemas import BatchPlan, PieceContent  # noqa: E402
from app.errors import UserError  # noqa: E402

BRIEF = {"topic": "discipline", "tone": "cinematic", "format": "automatic", "quantity": 3, "platforms": ["tiktok"]}
SUBJECTS = ["mountain runner at dawn", "empty city street at night", "ocean waves in fog"]


def piece_json(quote: str) -> dict:
    return {
        "quote": {"text": quote, "author": None},
        "narration": {"text": f"Nobody sees the early hours. {quote}", "delivery": "calm_reflective"},
        "visual": {"preferred_type": "video", "search_query": "runner mountain sunrise", "secondary_query": "trail dawn", "mood": "quiet"},
        "design": {"text_density": "low", "animation": "slow", "composition": "editorial"},
        "metadata": {"title": "Keep moving", "description": "A short reflection on discipline.", "caption": "Keep going anyway.",
                     "hashtags": ["discipline", "#mindset", "#motivation"], "keywords": ["discipline", "habits", "focus"],
                     "alt_text": "A runner on a mountain trail at sunrise."},
    }


def plan_json(n: int) -> dict:
    return {"batch_theme": "discipline", "pieces": [
        {"angle": f"angle {i}", "visual_subject": SUBJECTS[i], "visual_type": "video", "intensity": "low", "narration_style": "calm"}
        for i in range(n)]}


class FakeModel(creative.CreativeModel):
    def __init__(self, quotes):
        self.quotes = iter(quotes)

    def plan_batch(self, brief, avoid):
        return BatchPlan.model_validate(plan_json(brief["quantity"]))

    def write_piece(self, brief, plan, item, avoid):
        return PieceContent.model_validate(piece_json(next(self.quotes)))


def run_job(project_id: str, model) -> dict:
    with mock.patch.object(content, "get_model", lambda: model), mock.patch.object(jobs, "emit"):
        job = jobs.start(project_id)
        for _ in range(200):
            job = jobs.get(job["id"])
            if job["status"] not in ("queued", "running"):
                return job
            time.sleep(0.02)
    raise AssertionError("job did not finish")


class Generation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.migrate()

    def test_batch_generates_distinct_pieces(self):
        p = projects.create(BRIEF)
        job = run_job(p["id"], FakeModel(["Show up when nobody claps.", "Small steps still count as moving.",
                                           "The work is quiet. Do it anyway."]))
        self.assertEqual((job["status"], job["progress"]), ("completed", 1.0))
        pieces = content.pieces(p["id"])
        self.assertEqual([x["idx"] for x in pieces], [1, 2, 3])
        self.assertEqual(pieces[0]["content"]["metadata"]["hashtags"][0], "#discipline")
        self.assertEqual(projects.get(p["id"])["status"], "ready")
        self.assertEqual(content.recent(1)[0]["quote"], "The work is quiet. Do it anyway.")
        self.assertGreaterEqual(content.stats()["today"], 3)

    def test_repeated_quote_is_regenerated_then_failed(self):
        first = projects.create(BRIEF)
        run_job(first["id"], FakeModel(["Rest is part of the plan.", "Nobody sees the early hours.", "Discipline is a quiet promise."]))
        again = projects.create({**BRIEF, "quantity": 2})
        # piece 1: repeats history, then a fresh line; piece 2: repeats every attempt
        job = run_job(again["id"], FakeModel(["Rest is part of the plan!", "Consistency beats intensity every day.",
                                              "Nobody sees the early hours", "nobody sees the early hours.", "Nobody sees the early hours!"]))
        self.assertEqual(job["status"], "completed")
        a, b = content.pieces(again["id"])
        self.assertEqual((a["status"], a["quote"]), ("written", "Consistency beats intensity every day."))
        self.assertEqual(b["status"], "failed")
        self.assertIn("repeated an earlier line", b["content"]["error"])

    def test_missing_key_fails_job_with_readable_error(self):
        p = projects.create(BRIEF)
        with mock.patch.dict(creative.config.SECRETS, {}, clear=True), mock.patch.object(jobs, "emit"):
            job = jobs.start(p["id"])
            for _ in range(100):
                job = jobs.get(job["id"])
                if job["status"] == "failed":
                    break
                time.sleep(0.02)
        self.assertEqual(job["error"]["message"], "Add your DeepSeek API key in Settings to generate content.")
        self.assertEqual(projects.get(p["id"])["status"], "failed")

    def test_recover_marks_interrupted_jobs(self):
        p = projects.create(BRIEF)
        with database.connect() as conn:
            conn.execute("INSERT INTO generation_jobs (id, project_id, status) VALUES ('j1', ?, 'running')", (p["id"],))
            conn.execute("UPDATE projects SET status = 'generating' WHERE id = ?", (p["id"],))
        jobs.recover()
        self.assertEqual(jobs.get("j1")["status"], "failed")
        self.assertEqual(projects.get(p["id"])["status"], "failed")

    def test_plan_rejects_duplicate_subjects(self):
        bad = plan_json(2)
        bad["pieces"][1]["visual_subject"] = bad["pieces"][0]["visual_subject"].upper()
        with self.assertRaises(ValueError):
            BatchPlan.model_validate(bad)


def deepseek(replies: list, calls: list):
    """DeepSeekModel whose HTTP layer returns the given (status, content) replies in order."""
    it = iter(replies)

    def handler(request: httpx.Request):
        calls.append(json.loads(request.content))
        status, text = next(it)
        return httpx.Response(status, json={"choices": [{"message": {"content": text}}]})

    return creative.DeepSeekModel("k", "deepseek-flash", 1.0, 2000, transport=httpx.MockTransport(handler))


class DeepSeekClient(unittest.TestCase):
    def setUp(self):
        mock.patch("time.sleep").start()
        self.addCleanup(mock.patch.stopall)

    def test_invalid_json_is_repaired_once(self):
        calls = []
        m = deepseek([(200, '{"quote": "oops"}'), (200, json.dumps(piece_json("Keep going when it is boring.")))], calls)
        plan = BatchPlan.model_validate(plan_json(1))
        piece = m.write_piece(BRIEF, plan, plan.pieces[0], [])
        self.assertEqual(piece.quote.text, "Keep going when it is boring.")
        self.assertEqual(len(calls), 2)
        self.assertIn("did not match the required JSON shape", calls[1]["messages"][-1]["content"])
        self.assertEqual(calls[0]["response_format"], {"type": "json_object"})

    def test_gives_up_after_repair_and_regenerate(self):
        m = deepseek([(200, "not json")] * 3, [])
        with self.assertRaisesRegex(UserError, "wrong shape"):
            m.plan_batch({**BRIEF, "quantity": 1}, [])

    def test_auth_error_is_human(self):
        m = deepseek([(401, "")], [])
        with self.assertRaisesRegex(UserError, "DeepSeek authentication failed"):
            m.plan_batch(BRIEF, [])

    def test_empty_and_server_errors_retry(self):
        calls = []
        m = deepseek([(500, ""), (200, ""), (200, json.dumps(plan_json(3)))], calls)
        self.assertEqual(len(m.plan_batch(BRIEF, []).pieces), 3)
        self.assertEqual(len(calls), 3)

    def test_wrong_piece_count_rejected(self):
        m = deepseek([(200, json.dumps(plan_json(2)))], [])
        with self.assertRaisesRegex(UserError, "wrong number"):
            m.plan_batch(BRIEF, [])


if __name__ == "__main__":
    unittest.main()
