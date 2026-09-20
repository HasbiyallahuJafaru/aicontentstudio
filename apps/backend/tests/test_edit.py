"""The edit grammar: cuts land on the voice, the timeline still adds up, and genres are cut differently."""
import unittest

from app import edit

# "you stop. <pause> then go." - a clause end at 0.9 and a real gap before 1.6
WORDS = [{"word": "you", "start": 0.0, "end": 0.30},
         {"word": "stop.", "start": 0.35, "end": 0.90},
         {"word": "then", "start": 1.60, "end": 1.90},
         {"word": "go.", "start": 1.95, "end": 2.60}]


def assets(n: int, kind: str = "video") -> list[dict]:
    return [{"id": f"a{i}", "local_path": f"assets/a{i}.mp4", "asset_type": kind, "duration": 12.0}
            for i in range(n)]


class Breaths(unittest.TestCase):
    def test_clause_ends_and_gaps_are_offered_as_cuts(self):
        self.assertEqual(edit.breaths(WORDS), [1.02, 2.6])

    def test_mid_phrase_words_are_not(self):
        self.assertEqual(edit.breaths([{"word": "and", "start": 0.0, "end": 0.2},
                                       {"word": "then", "start": 0.25, "end": 0.5}]), [])


class Cuts(unittest.TestCase):
    def test_cuts_snap_to_a_breath(self):
        self.assertEqual(edit.cuts(9.0, WORDS, 3, (2.6, 3.2)), [0.0, 2.6, 6.0, 9.0])

    def test_without_timings_it_still_cuts_on_cadence(self):
        self.assertEqual(edit.cuts(9.0, [], 3, (2.6, 3.2)), [0.0, 3.0, 6.0, 9.0])

    def test_one_shot_is_the_whole_piece(self):
        self.assertEqual(edit.cuts(9.0, WORDS, 1, (2.6, 3.2)), [0.0, 9.0])

    def test_no_shot_is_shorter_than_the_cadence_floor(self):
        edges = edit.cuts(12.0, WORDS, 4, (2.6, 3.2))
        self.assertTrue(all(b - a >= 2.6 * 0.6 for a, b in zip(edges, edges[1:])), edges)


class Plan(unittest.TestCase):
    def test_timeline_lands_on_the_narration_length(self):
        for tone in edit.CUTS:
            shots = edit.plan(assets(4), 24.0, WORDS, tone)
            total = sum(s["length"] for s in shots) - sum(s.get("tdur", 0) for s in shots)
            self.assertAlmostEqual(total, 24.0, places=2, msg=tone)

    def test_neighbours_are_never_the_same_location(self):
        shots = edit.plan(assets(4), 24.0, WORDS, "hope")
        self.assertTrue(all(a["asset"]["id"] != b["asset"]["id"] for a, b in zip(shots, shots[1:])))

    def test_a_reused_asset_enters_at_a_different_point(self):
        shots = edit.plan(assets(2), 20.0, WORDS, "hope")
        first = [s for s in shots if s["asset"]["id"] == "a0"]
        self.assertGreater(len(first), 1)
        self.assertEqual([s["nth"] for s in first], list(range(len(first))))

    def test_speech_cuts_faster_than_cinema(self):
        self.assertGreater(len(edit.plan(assets(4), 24.0, WORDS, "speech")),
                           len(edit.plan(assets(4), 24.0, WORDS, "cinema")))

    def test_every_join_carries_a_transition_and_the_first_shot_does_not(self):
        shots = edit.plan(assets(4), 24.0, WORDS, "hope")
        self.assertNotIn("transition", shots[0])
        self.assertTrue(all("transition" in s and s["tdur"] > 0 for s in shots[1:]))

    def test_hard_cut_genres_save_the_named_transition_for_the_last_beat(self):
        shots = edit.plan(assets(4), 24.0, WORDS, "speech")
        self.assertEqual(shots[-1]["transition"], "fadeblack")
        self.assertTrue(all(s["transition"] == edit.HARD[0] for s in shots[1:-1]))

    def test_only_ramping_genres_slow_the_turn(self):
        self.assertTrue(any(s["speed"] != 1.0 for s in edit.plan(assets(4), 24.0, WORDS, "cinema")))
        self.assertTrue(all(s["speed"] == 1.0 for s in edit.plan(assets(4), 24.0, WORDS, "hope")))

    def test_a_single_asset_still_yields_a_timeline(self):
        shots = edit.plan(assets(1), 9.0, WORDS, "hope")
        self.assertGreaterEqual(len(shots), 1)
        self.assertAlmostEqual(sum(s["length"] for s in shots) - sum(s.get("tdur", 0) for s in shots), 9.0, places=2)


class Looks(unittest.TestCase):
    def test_auto_resolves_to_the_genre_grade(self):
        self.assertIs(edit.look_for("auto", "cinema"), edit.LOOKS["cinema"])

    def test_a_manual_look_wins(self):
        self.assertIs(edit.look_for("mono", "cinema"), edit.LOOKS["mono"])

    def test_every_genre_and_picker_option_has_a_complete_look(self):
        keys = {"grade", "bloom", "grain", "vignette", "unsharp", "bars"}
        for name, style in edit.LOOKS.items():
            self.assertEqual(set(style), keys, name)
        for tone, cut in edit.CUTS.items():
            self.assertIn(cut["look"], edit.LOOKS, tone)


if __name__ == "__main__":
    unittest.main()
