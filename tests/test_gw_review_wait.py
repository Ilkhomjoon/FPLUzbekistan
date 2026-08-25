"""Tur hali rasman yopilmaganda gw_review nima qilishi kerak."""
from __future__ import annotations

import logging
import unittest

from bot import config, gw_review


def _fixture(finished: bool, provisional: bool) -> dict:
    return {"id": 1, "event": 1, "finished": finished,
            "finished_provisional": provisional, "kickoff_time": "2026-08-24T19:00:00Z"}


class NotFinishedTest(unittest.TestCase):
    def setUp(self):
        self._orig = {
            "bootstrap": gw_review.fpl_api.get_bootstrap,
            "fixtures": gw_review.fpl_api.get_fixtures,
            "require": config.require_telegram,
            "send": gw_review.telegram.send_message,
        }
        config.require_telegram = lambda: None
        self.sent = []
        gw_review.telegram.send_message = lambda text, **kw: self.sent.append(text) or {"message_id": 1}

    def tearDown(self):
        gw_review.fpl_api.get_bootstrap = self._orig["bootstrap"]
        gw_review.fpl_api.get_fixtures = self._orig["fixtures"]
        config.require_telegram = self._orig["require"]
        gw_review.telegram.send_message = self._orig["send"]

    def test_all_played_but_fpl_has_not_confirmed(self):
        """FPL bayrog'i yo'q -> post yo'q, lekin log sababini aytishi kerak."""
        gw_review.fpl_api.get_bootstrap = lambda: {
            "events": [{"id": 1, "is_current": True, "finished": False, "data_checked": False}],
            "elements": [], "teams": [],
        }
        gw_review.fpl_api.get_fixtures = lambda **kw: [_fixture(False, True)] * 10

        with self.assertLogs("gw_review", level=logging.INFO) as logs:
            self.assertEqual(gw_review.run(), 0)

        self.assertEqual(self.sent, [])
        joined = " ".join(logs.output)
        self.assertIn("10/10", joined)
        self.assertIn("rasman", joined)

    def test_gameweek_still_in_progress(self):
        gw_review.fpl_api.get_bootstrap = lambda: {
            "events": [{"id": 1, "is_current": True, "finished": False, "data_checked": False}],
            "elements": [], "teams": [],
        }
        gw_review.fpl_api.get_fixtures = lambda **kw: (
            [_fixture(True, True)] * 6 + [_fixture(False, False)] * 4)

        with self.assertLogs("gw_review", level=logging.INFO) as logs:
            self.assertEqual(gw_review.run(), 0)

        self.assertEqual(self.sent, [])
        self.assertIn("davom etyapti", " ".join(logs.output))

    def test_no_current_event(self):
        gw_review.fpl_api.get_bootstrap = lambda: {"events": [], "elements": [], "teams": []}
        with self.assertLogs("gw_review", level=logging.INFO):
            self.assertEqual(gw_review.run(), 0)
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
