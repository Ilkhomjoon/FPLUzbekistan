"""O'yin daqiqasi va tanaffus jonli xabarda ko'rinib tursin."""
from __future__ import annotations

import unittest

from bot import config
from bot.formatting import _live_post, match_clock

TEAMS = {1: {"name": "Spurs", "short_name": "TOT"},
         2: {"name": "Aston Villa", "short_name": "AVL"}}


def _fx(minutes=None, started=True, finished=False, hs=0, aws=0):
    return {"id": 1, "event": 5, "kickoff_time": "2026-09-19T16:30:00Z",
            "started": started, "finished": finished,
            "finished_provisional": finished, "team_h": 1, "team_a": 2,
            "team_h_score": hs, "team_a_score": aws, "minutes": minutes,
            "stats": []}


class ClockTest(unittest.TestCase):
    def test_minute_is_shown_while_the_match_runs(self):
        self.assertEqual(match_clock(_fx(37)), "37'")

    def test_half_time_is_named(self):
        self.assertEqual(match_clock(_fx(45)), config.HALFTIME_LABEL)

    def test_after_ninety_it_shows_stoppage(self):
        self.assertEqual(match_clock(_fx(90)), "90+")
        self.assertEqual(match_clock(_fx(94)), "90+")

    def test_no_clock_before_kickoff(self):
        self.assertEqual(match_clock(_fx(0)), "")

    def test_a_missing_field_is_not_an_error(self):
        """Eski nusxada `minutes` bo'lmasligi mumkin."""
        fx = _fx(37)
        del fx["minutes"]
        self.assertEqual(match_clock(fx), "")
        self.assertEqual(match_clock({"minutes": "—"}), "")


class LivePostTest(unittest.TestCase):
    def setUp(self):
        self._orig = (config.SHOW_CLOCK, config.SHOW_DEFCON, config.COLLAPSE_FINISHED)
        config.SHOW_DEFCON = False

    def tearDown(self):
        config.SHOW_CLOCK, config.SHOW_DEFCON, config.COLLAPSE_FINISHED = self._orig

    def _title(self, fx):
        text = _live_post([fx], {}, TEAMS, 5, {})
        return next(l for l in text.split("\n") if "Spurs" in l)

    def test_the_minute_sits_next_to_the_score(self):
        self.assertIn("Spurs 0:0 Aston Villa · 37'", self._title(_fx(37)))

    def test_half_time_replaces_the_minute(self):
        self.assertIn(f"Spurs 1:0 Aston Villa · {config.HALFTIME_LABEL}",
                      self._title(_fx(45, hs=1)))

    def test_a_finished_match_has_no_clock(self):
        config.COLLAPSE_FINISHED = False
        line = self._title(_fx(90, finished=True, hs=2, aws=1))
        self.assertIn("Spurs 2:1 Aston Villa", line)
        self.assertNotIn("·", line)

    def test_half_time_turns_the_dot_yellow(self):
        line = self._title(_fx(45, hs=1))
        self.assertIn(config.HALFTIME_EMOJI, line)
        self.assertNotIn("🔴", line)

    def test_the_dot_is_red_while_the_ball_is_rolling(self):
        self.assertIn("🔴", self._title(_fx(37)))

    def test_the_dot_goes_back_to_red_after_the_break(self):
        self.assertIn("🔴", self._title(_fx(46, hs=1)))

    def test_a_finished_match_is_green(self):
        config.COLLAPSE_FINISHED = False
        self.assertIn("🟢", self._title(_fx(90, finished=True, hs=2, aws=1)))

    def test_the_yellow_dot_does_not_depend_on_the_clock_setting(self):
        config.SHOW_CLOCK = False
        line = self._title(_fx(45, hs=1))
        self.assertIn(config.HALFTIME_EMOJI, line)
        self.assertNotIn(config.HALFTIME_LABEL, line)

    def test_the_clock_can_be_switched_off(self):
        config.SHOW_CLOCK = False
        self.assertNotIn("37'", self._title(_fx(37)))


if __name__ == "__main__":
    unittest.main()
