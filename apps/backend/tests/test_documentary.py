"""2026-11-10: fact-based videos, no looping footage, directed narrators, bundled music."""
import unittest

from app import edit, music, research, tts
from app.creative import prompts


class Documentary(unittest.TestCase):
    def test_topic_matches_its_article_in_any_order(self):
        self.assertTrue(research.matches("Musa Mansa", "Mansa Musa"))
        self.assertTrue(research.matches("the life of Alexander the Great", "Alexander the Great"))
        self.assertFalse(research.matches("communication; anyone can persuade", "Persuasion"))

    def test_facts_switch_the_writer(self):
        brief = {"topic": "Mansa Musa", "tone": "stoic", "format": "video", "platforms": ["tiktok"], "quantity": 10,
                 "facts": {"title": "Mansa Musa", "description": "Ruler of Mali", "text": "Mansa Musa ruled Mali."}}
        msgs = prompts.plan(brief, [])
        self.assertIs(msgs[0]["content"], prompts.DOC_SYSTEM)
        self.assertIn("Mansa Musa ruled Mali.", msgs[1]["content"])
        self.assertIn('"facts"', msgs[1]["content"])  # each chapter names the facts only it tells
        self.assertIs(prompts.plan({**brief, "facts": None}, [])[0]["content"], prompts.VIDEO_SYSTEM)

    def test_a_big_pool_is_never_cycled(self):
        pool = [{"id": i} for i in range(12)]
        shots = edit.plan(pool, 45.0, [], "history")
        self.assertEqual(len({id(s["asset"]) for s in shots}), len(shots))

    def test_narrator_is_directed(self):
        voice, note = tts.direction("elder", "grave on the cost")
        self.assertEqual(voice, "Algenib")
        self.assertIn("grandfather", note)
        self.assertIn("grave on the cost", note)
        self.assertEqual(tts.direction("Charon")[0], "Charon")
        self.assertEqual(tts.GENRE_VOICES["stoic"], "raspy")  # ElevenLabs since 2026-11-12
        self.assertEqual(tts.NARRATORS["raspy"]["model"], tts.ELEVEN)
        self.assertEqual(tts.direction("raspy")[0], tts.DEFAULT_VOICE)  # never sent to Gemini; no crash if it is

    def test_music_varies_piece_to_piece(self):
        if len(music.tracks("history")) < 2:
            self.skipTest("music library not built (scripts/make_music.py)")
        self.assertNotEqual(music.pick("history", 1), music.pick("history", 2))
