"""The 2026-11-08 engine overhaul: each kind of content has its own writer that stays on the topic, and stock
searches are few, cached and colour-aware."""
import asyncio
import os
import tempfile
import unittest

os.environ.setdefault("ACS_DATA_DIR", tempfile.mkdtemp())

from pydantic import ValidationError  # noqa: E402

from app import assets, visual  # noqa: E402
from app.creative import prompts  # noqa: E402
from app.creative.schemas import BatchPlan, PieceContent, VideoPieceContent  # noqa: E402

from tests.test_assets import FakeProvider2, cand, make_thumbs  # noqa: E402
from tests.test_content import BRIEF, piece_json, plan_json  # noqa: E402

QUOTES = {**BRIEF, "topic": "the beauty of man and his adventure in nature", "format": "image",
          "platforms": ["instagram_feed"]}
VIDEO = {**BRIEF, "format": "video"}


class Writers(unittest.TestCase):
    def test_quote_images_get_the_quote_writer_and_no_script(self):
        plan_msgs = prompts.plan(QUOTES, [])
        self.assertEqual(plan_msgs[0]["content"], prompts.QUOTES_SYSTEM)
        plan = BatchPlan.model_validate({**plan_json(1), "reading": "people out in the wild and the awe of it"})
        msgs = prompts.piece(QUOTES, plan, plan.pieces[0], [])
        user = msgs[1]["content"]
        self.assertIn('"the beauty of man and his adventure in nature"', user)
        self.assertIn("Reading of the topic (stay inside it): people out in the wild", user)
        shape = user.split("Return JSON shaped like:")[1]
        for absent in ('"narration"', '"hook"', '"callouts"', '"shots"'):
            self.assertNotIn(absent, shape, f"quote images ask for no {absent}")
        self.assertIn("No narration, no script.", user)

    def test_videos_get_the_video_writer_with_narration(self):
        self.assertEqual(prompts.plan(VIDEO, [])[0]["content"], prompts.VIDEO_SYSTEM)
        plan = BatchPlan.model_validate(plan_json(1))
        shape = prompts.piece(VIDEO, plan, plan.pieces[0], [])[1]["content"].split("Return JSON shaped like:")[1]
        self.assertIn('"narration"', shape)
        self.assertIn('"shots"', shape)

    def test_no_time_of_day_recipe_left_and_timestamps_banned(self):
        everything = prompts.QUOTES_SYSTEM + prompts.VIDEO_SYSTEM + str(prompts.GENRES) + \
            str(prompts.QUOTES_PLAN_SHAPE) + str(prompts.VIDEO_PLAN_SHAPE)
        for recipe in ("4:52", "4am-style", "an hour of the day", "2am"):
            self.assertNotIn(recipe, everything)
        self.assertIn("clock times and timestamps", prompts.TOPIC_RULES)
        self.assertIn("reading", prompts.QUOTES_PLAN_SHAPE)

    def test_quote_pieces_need_no_narration_but_videos_do(self):
        data = piece_json("The mountain does not care. That is why you climb it.")
        data.pop("narration")
        self.assertIsNone(PieceContent.model_validate(data).narration)
        with self.assertRaises(ValidationError):
            VideoPieceContent.model_validate(data)


class Footage(unittest.TestCase):
    def setUp(self):
        assets._CACHE.clear()
        make_thumbs("p1", "p2", "p3", "p4", "u1")

    def counting(self, name, pids, typ="image"):
        class Counting(FakeProvider2):
            def __init__(self, candidates):
                super().__init__(candidates)
                self.name = name
                self.calls = []

            async def search_images(self, query, limit, color=None):
                self.calls.append((query, color))
                return await super().search_images(query, limit)

            async def search_videos(self, query, limit):
                self.calls.append((query, None))
                return await super().search_videos(query, limit)
        return Counting([cand(p, typ) for p in pids])

    def test_one_request_when_the_first_provider_has_enough_and_the_palette_reaches_it(self):
        pexels = self.counting("pexels", ["p1", "p2", "p3"])
        unsplash = self.counting("unsplash", ["u1"])
        before = assets.SEARCHES["count"]
        found = asyncio.run(assets._search_all([pexels, unsplash], "summit ridge climber", "image", "warm"))
        self.assertEqual(len(found), 3)
        self.assertEqual(pexels.calls, [("summit ridge climber", "orange")])
        self.assertEqual(unsplash.calls, [], "Unsplash is only asked when Pexels comes up short")
        self.assertEqual(assets.SEARCHES["count"] - before, 1)

    def test_repeat_searches_come_from_the_cache(self):
        pexels = self.counting("pexels", ["p1", "p2", "p3"])
        for _ in range(3):
            asyncio.run(assets._search_all([pexels], "Summit  ridge climber", "image"))
        self.assertEqual(len(pexels.calls), 1)

    def test_short_results_fall_through_to_the_next_provider(self):
        pexels = self.counting("pexels", ["p1"])
        unsplash = self.counting("unsplash", ["u1"])
        asyncio.run(assets._search_all([pexels, unsplash], "river canyon raft", "image", "cool"))
        self.assertEqual(unsplash.calls, [("river canyon raft", "blue")])

    def test_videos_are_never_colour_filtered_at_the_source(self):
        pexels = self.counting("pexels", ["p1", "p2", "p3"], typ="video")
        asyncio.run(assets._search_all([pexels], "waves at dusk", "video", "warm"))
        self.assertEqual(pexels.calls, [("waves at dusk", None)])

    def test_palette_match_reads_the_thumbnail(self):
        warm = {"brightness": 0.5, "saturation": 0.4, "temperature": "warm", "dominant_colors": ["#D98A3A", "#F2C27A"]}
        cool = {"brightness": 0.5, "saturation": 0.4, "temperature": "cool", "dominant_colors": ["#3A6FA8", "#8FB5D9"]}
        grey = {"brightness": 0.3, "saturation": 0.03, "temperature": "neutral", "dominant_colors": ["#444444"]}
        self.assertGreater(visual.palette_match(warm, "warm"), visual.palette_match(cool, "warm"))
        self.assertGreater(visual.palette_match(cool, "cool"), visual.palette_match(warm, "cool"))
        self.assertGreater(visual.palette_match(grey, "mono"), 0.8)
        self.assertGreater(visual.palette_match(grey, "dark"), visual.palette_match(warm, "dark"))
        self.assertEqual(visual.palette_match(warm, "auto"), 0.0)


if __name__ == "__main__":
    unittest.main()
