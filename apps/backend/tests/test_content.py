"""Milestone 2: generation pipeline, jobs, dedup and the OpenRouter client. No network: fake model + httpx.MockTransport."""
import json
import os
import tempfile
import time
import unittest
from typing import get_args
from unittest import mock

os.environ.setdefault("ACS_DATA_DIR", tempfile.mkdtemp())

import httpx  # noqa: E402

from app import assets, content, database, jobs, projects  # noqa: E402
from app.creative import model as creative  # noqa: E402
from app.creative.schemas import BatchPlan, PieceContent  # noqa: E402
from app.errors import UserError  # noqa: E402

BRIEF = {"topic": "discipline", "tone": "speech", "format": "automatic", "quantity": 3, "platforms": ["tiktok"]}
SUBJECTS = ["mountain runner at dawn", "empty city street at night", "ocean waves in fog"]


def piece_json(quote: str) -> dict:
    return {
        "quote": {"text": quote, "author": "Seneca"},
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
    # content tests run without visuals: no provider hits, no fixture server needed here (test_assets covers that)
    with mock.patch.object(content, "get_model", lambda: model), \
            mock.patch.object(assets, "get_providers", lambda: []), mock.patch.object(jobs, "emit"):
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

    def test_every_ai_quote_must_name_a_real_author(self):
        def piece(author):
            return PieceContent.model_validate({**piece_json("The work is quiet. Do it anyway."),
                                                "quote": {"text": "The work is quiet. Do it anyway.", "author": author}})
        self.assertTrue(content._signed(piece("Seneca")))
        for bad in (None, "", "  ", "Unknown", "anonymous"):
            self.assertFalse(content._signed(piece(bad)), bad)

    def test_repeated_quote_is_regenerated_then_failed(self):
        first = projects.create(BRIEF)
        run_job(first["id"], FakeModel(["Rest is part of the plan.", "Nobody sees the early hours.", "Discipline is a quiet promise."]))
        again = projects.create({**BRIEF, "quantity": 2})
        # both pieces are drafted together first (batch writing); piece 1's draft repeats history, then its retry is
        # fresh; piece 2 repeats on its draft and on both retries (three tries in all, the draft included)
        job = run_job(again["id"], FakeModel(["Rest is part of the plan!", "Nobody sees the early hours",
                                              "Consistency beats intensity every day.",
                                              "nobody sees the early hours.", "Nobody sees the early hours!"]))
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
        self.assertEqual(job["error"]["message"], "Add your OpenRouter API key in Settings to generate content.")
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


def openrouter(replies: list, calls: list):
    """OpenRouterModel whose HTTP layer returns the given (status, content) replies in order."""
    it = iter(replies)

    def handler(request: httpx.Request):
        calls.append(json.loads(request.content))
        status, text = next(it)
        return httpx.Response(status, json={"choices": [{"message": {"content": text}}]})

    return creative.OpenRouterModel("k", "deepseek/deepseek-v4.1-flash", 1.0, 2000, transport=httpx.MockTransport(handler))


class OpenRouterClient(unittest.TestCase):
    def setUp(self):
        mock.patch("time.sleep").start()
        self.addCleanup(mock.patch.stopall)

    def test_invalid_json_is_repaired_once(self):
        calls = []
        m = openrouter([(200, '{"quote": "oops"}'), (200, json.dumps(piece_json("Keep going when it is boring.")))], calls)
        plan = BatchPlan.model_validate(plan_json(1))
        piece = m.write_piece(BRIEF, plan, plan.pieces[0], [])
        self.assertEqual(piece.quote.text, "Keep going when it is boring.")
        self.assertEqual(len(calls), 2)
        self.assertIn("did not match the required JSON shape", calls[1]["messages"][-1]["content"])
        self.assertEqual(calls[0]["response_format"], {"type": "json_object"})
        self.assertEqual(calls[0]["provider"], {"require_parameters": True}, "only JSON-mode providers")

    def test_a_group_of_pieces_is_one_request(self):
        """Batch writing (owner 2026-11-08): three pieces, one call; a malformed piece comes back as None (written
        alone by the caller) without costing the other two; the user's own quote is named in the request."""
        calls = []
        good = [piece_json("Keep going when it is boring."), piece_json("Nobody claps for the early hours.")]
        reply = json.dumps({"pieces": [good[0], {"quote": "oops"}, good[1]]})
        m = openrouter([(200, reply)], calls)
        plan = BatchPlan.model_validate(plan_json(3))
        got = m.write_pieces(BRIEF, plan, plan.pieces, [], [None, None, ("Be the one who stays.", "Seneca")])
        self.assertEqual(len(calls), 1)
        self.assertEqual([g.quote.text if g else None for g in got],
                         ["Keep going when it is boring.", None, "Nobody claps for the early hours."])
        self.assertIn('exactly 3 item(s) in "pieces"', calls[0]["messages"][-1]["content"])
        self.assertIn("Be the one who stays.", calls[0]["messages"][-1]["content"])

    def test_out_of_credits_is_human(self):
        with self.assertRaisesRegex(UserError, "out of credits"):
            openrouter([(402, "")], []).plan_batch(BRIEF, [])

    def test_bare_model_names_from_the_deepseek_era_map_to_openrouter_ids(self):
        from app.settings import Settings
        old = Settings(ai_model="deepseek-v4-pro", ai_model_fast="deepseek-flash")
        self.assertEqual((old.ai_model, old.ai_model_fast), ("deepseek/deepseek-v4-pro", "deepseek/deepseek-v4.1-flash"))
        self.assertEqual(Settings(ai_model="anthropic/claude-opus-5.5").ai_model, "anthropic/claude-opus-5.5")

    def test_gives_up_after_repair_and_regenerate(self):
        m = openrouter([(200, "not json")] * 3, [])
        with self.assertRaisesRegex(UserError, "wrong shape"):
            m.plan_batch({**BRIEF, "quantity": 1}, [])

    def test_auth_error_is_human(self):
        m = openrouter([(401, "")], [])
        with self.assertRaisesRegex(UserError, "OpenRouter authentication failed"):
            m.plan_batch(BRIEF, [])

    def test_empty_and_server_errors_retry(self):
        calls = []
        m = openrouter([(500, ""), (200, ""), (200, json.dumps(plan_json(3)))], calls)
        self.assertEqual(len(m.plan_batch(BRIEF, []).pieces), 3)
        self.assertEqual(len(calls), 3)

    def test_wrong_piece_count_rejected(self):
        m = openrouter([(200, json.dumps(plan_json(2)))], [])
        with self.assertRaisesRegex(UserError, "wrong number"):
            m.plan_batch(BRIEF, [])


class ToneVoices(unittest.TestCase):
    """The genre knob only does something if every genre carries a voice into the prompt."""

    def test_every_genre_has_a_voice(self):
        from app.creative import prompts
        from app.settings import Genre
        self.assertEqual(set(get_args(Genre)), set(prompts.GENRES))

    def test_voice_reaches_both_prompts(self):
        from app.creative import prompts
        from app.settings import Genre
        for genre in get_args(Genre):
            brief = {**BRIEF, "tone": genre}
            plan_msg = prompts.plan(brief, [])[1]["content"]
            self.assertIn(prompts.GENRES[genre]["voice"], plan_msg, genre)
            item = BatchPlan.model_validate(plan_json(3)).pieces[0]
            piece_msg = prompts.piece(brief, BatchPlan.model_validate(plan_json(3)), item, [])[1]["content"]
            self.assertIn(prompts.GENRES[genre]["voice"], piece_msg, genre)


if __name__ == "__main__":
    unittest.main()


class OverlongModelLines(unittest.TestCase):
    """A model that writes past a schema cap must not fail the whole generation (real case: 94-char angle)."""

    def test_plan_strings_are_trimmed_to_the_cap(self):
        from app.creative.schemas import BatchPlan
        plan = BatchPlan.model_validate({
            "batch_theme": "discipline",
            "pieces": [{"angle": "a" * 94, "visual_subject": "s" * 94, "visual_type": "video",
                        "intensity": "medium", "narration_style": "calm"},
                       {"angle": "b" * 94, "visual_subject": "t" * 94, "visual_type": "image",
                        "intensity": "low", "narration_style": "warm"}]})
        self.assertEqual(len(plan.pieces[0].angle), 80)
        self.assertEqual(len(plan.pieces[1].visual_subject), 80)


class OwnQuotes(unittest.TestCase):
    """Quote images from the user's own lines: the AI writes around them, the text is never changed."""

    @classmethod
    def setUpClass(cls):
        database.migrate()

    def test_quantity_follows_the_quotes_and_blank_lines_drop(self):
        p = projects.create({**BRIEF, "format": "image", "quantity": 9,
                             "quotes": ["  Waste no more   time arguing. — Marcus Aurelius", "", "Begin anyway."]})
        self.assertEqual((p["brief"]["quantity"], len(p["brief"]["quotes"])), (2, 2))

    def test_the_users_text_and_author_survive_whatever_the_model_writes(self):
        p = projects.create({**BRIEF, "format": "image", "quotes": ["Waste no more time arguing. — Marcus Aurelius",
                                                                     "Begin anyway."]})
        seen = []

        class Echo(FakeModel):
            def write_piece(self, brief, plan, item, avoid):
                seen.append(brief.get("given_quote"))
                return super().write_piece(brief, plan, item, avoid)

        job = run_job(p["id"], Echo(["Something the model made up entirely.", "Another invented line here."]))
        self.assertEqual(job["status"], "completed")
        quotes = [x["content"]["quote"] for x in content.pieces(p["id"])]
        self.assertEqual([q["text"] for q in quotes], ["Waste no more time arguing.", "Begin anyway."])
        self.assertEqual([q["author"] for q in quotes], ["Marcus Aurelius", None])
        self.assertEqual(seen, ["Waste no more time arguing.", "Begin anyway."], "the prompt carries the fixed line")

    def test_prompt_locks_the_quote(self):
        from app.creative import prompts
        msgs = prompts.piece({**BRIEF, "given_quote": "Begin anyway.", "given_author": None},
                             BatchPlan.model_validate(plan_json(1)), BatchPlan.model_validate(plan_json(1)).pieces[0], [])
        self.assertIn('fixed, written by the user: "Begin anyway."', msgs[1]["content"])


class BulkQuotes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        database.migrate()

    def test_own_quote_images_skip_planning(self):  # owner 2026-11-08: quote images are never planned
        quotes = [f"Line number {i} of the bulk import." for i in range(25)]
        p = projects.create({**BRIEF, "format": "image", "quotes": quotes})
        self.assertEqual(p["brief"]["quantity"], 25)
        sizes = []

        class Bulk(FakeModel):
            def plan_batch(self, brief, avoid):
                sizes.append(len(brief["quotes"]))
                return BatchPlan.model_validate({"batch_theme": "bulk", "pieces": [
                    {"angle": f"angle {i}", "visual_subject": f"subject {i}", "visual_type": "image",
                     "intensity": "low", "narration_style": "calm"} for i in range(brief["quantity"])]})

        job = run_job(p["id"], Bulk([f"model line {i}" * 2 for i in range(25)]))
        self.assertEqual(job["status"], "completed")
        self.assertEqual(sizes, [], "no planning call for quote images")
        self.assertEqual([x["content"]["quote"]["text"] for x in content.pieces(p["id"])], quotes)


class WritingFixes(unittest.TestCase):
    """2026-11-09 audit, phase 3."""
    def test_a_truncated_group_reply_falls_back_to_single_pieces(self):
        def handler(request):  # the reply ran out of room mid-JSON
            return httpx.Response(200, json={"choices": [{"message": {"content": '{"pieces": [{"quo'},
                                                          "finish_reason": "length"}]})
        m = creative.OpenRouterModel("k", "m", 1.0, 2000, transport=httpx.MockTransport(handler))
        plan = BatchPlan.model_validate(plan_json(2))
        self.assertEqual(m.write_pieces(BRIEF, plan, plan.pieces, [], [None, None]), [None, None])

    def test_a_sixty_second_narration_validates_and_keeps_its_lines(self):
        from app.creative.schemas import Narration
        from app.tts import spoken
        text = "\n\n".join(["You kept the light on   for them"] + ["and nobody asked what it cost you."] * 20)
        n = Narration(text=text, delivery="calm")  # ~150 words: the old 700-character cap refused this
        self.assertEqual(n.text.split("\n")[0], "You kept the light on for them")
        self.assertNotIn("\n\n", n.text)
        self.assertTrue(spoken(n.text).startswith("You kept the light on for them, and nobody"))

    def test_new_design_rotates_without_a_model_call(self):
        from app import design
        options = design.GENRE_DESIGNS["hope"]
        self.assertEqual(design.another(options[0], "hope", "Short line."), options[1])
        self.assertIn(design.another("not-a-design", "hope", "Short line."), options)

    def test_a_fixed_quote_with_no_author_never_asks_for_one(self):
        from app.creative import prompts
        text = prompts._brief({**BRIEF, "given_quote": "My own line about mornings.", "given_author": None})
        self.assertNotIn("REAL documented", text)
        self.assertIn("This line has no author", text)

    def test_a_quote_the_checker_calls_fake_is_failed_not_kept(self):
        class Doubting(FakeModel):
            def verify_quotes(self, quotes):
                return ["no"] + ["yes"] * (len(quotes) - 1)
        p = projects.create({**BRIEF, "quantity": 2})
        run_job(p["id"], Doubting(["A line nobody ever wrote down.", "Keep the promise you made at dawn."]))
        got = sorted((x["status"], x["content"].get("error", "")) for x in content.pieces(p["id"]))
        self.assertEqual(got[0][0], "failed")
        self.assertIn("couldn't be confirmed", got[0][1])
        self.assertNotEqual(got[1][0], "failed")
        # its fix is a new quote: regenerate is allowed on exactly this failure, and footage is proposed again
        bad = next(x for x in content.pieces(p["id"]) if x["status"] == "failed")
        with mock.patch.object(content, "get_model", lambda: FakeModel(["Rest, then rise and go again."])),                 mock.patch.object(assets, "get_providers", lambda: []):
            fixed = content.regenerate(bad["id"], "quote")
        self.assertEqual((fixed["status"], fixed["content"].get("error")), ("written", None))
