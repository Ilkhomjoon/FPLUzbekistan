"""Yakuniy yangilanish o'tkazib yuborilsa, eski xabar pinda qolib ketmasin."""
from __future__ import annotations

import unittest

from bot import config, live_bonus

FIXTURES = [
    {"id": 1, "event": 2, "kickoff_time": "2026-08-28T19:00:00Z", "started": True,
     "finished": True, "finished_provisional": True, "team_h": 1, "team_a": 2,
     "team_h_score": 1, "team_a_score": 4, "stats": []},
    {"id": 2, "event": 2, "kickoff_time": "2026-08-29T11:30:00Z", "started": False,
     "finished": False, "finished_provisional": False, "team_h": 1, "team_a": 2,
     "team_h_score": None, "team_a_score": None, "stats": []},
]
PLAYERS: dict = {}
TEAMS = {1: {"short_name": "CRY", "name": "Crystal Palace"},
         2: {"short_name": "MCI", "name": "Man City"}}


class RetireTest(unittest.TestCase):
    def setUp(self):
        self.edited = []
        self.unpinned = []
        self.saved = []
        self._orig = (live_bonus.telegram.edit_message,
                      live_bonus.telegram.unpin_message,
                      live_bonus.storage.save,
                      live_bonus.config.SHOW_DEFCON)
        live_bonus.telegram.edit_message = lambda mid, text, **kw: (
            self.edited.append(mid) or {"message_id": mid})
        live_bonus.telegram.unpin_message = lambda mid, **kw: (
            self.unpinned.append(mid) or True)
        # Haqiqiy holat fayliga tegmasin
        live_bonus.storage.save = lambda path, data: self.saved.append(data)
        live_bonus.config.SHOW_DEFCON = False

    def tearDown(self):
        (live_bonus.telegram.edit_message, live_bonus.telegram.unpin_message,
         live_bonus.storage.save, live_bonus.config.SHOW_DEFCON) = self._orig

    def test_unswept_message_is_updated_and_unpinned(self):
        previous = {"date": "2026-08-28", "message_id": 3654,
                    "final": True, "swept": False, "last_text": "eski matn"}
        live_bonus.retire_previous(previous, FIXTURES, PLAYERS, TEAMS)
        self.assertEqual(self.edited, [3654])
        self.assertEqual(self.unpinned, [3654])

    def test_already_swept_is_left_alone(self):
        previous = {"date": "2026-08-28", "message_id": 3654, "swept": True}
        live_bonus.retire_previous(previous, FIXTURES, PLAYERS, TEAMS)
        self.assertEqual(self.edited, [])
        self.assertEqual(self.unpinned, [])

    def test_no_message_id_is_a_noop(self):
        live_bonus.retire_previous({"date": "2026-08-28"}, FIXTURES, PLAYERS, TEAMS)
        self.assertEqual(self.unpinned, [])

    def test_unchanged_text_still_unpins(self):
        text = live_bonus.live_bonus_post(
            [FIXTURES[0]], PLAYERS, TEAMS, 2, defcon={})
        previous = {"date": "2026-08-28", "message_id": 3654,
                    "swept": False, "last_text": text}
        live_bonus.retire_previous(previous, FIXTURES, PLAYERS, TEAMS)
        self.assertEqual(self.edited, [])          # matn o'zgarmagan
        self.assertEqual(self.unpinned, [3654])    # lekin pindan olindi

    def test_telegram_failure_does_not_raise(self):
        def boom(*a, **kw):
            raise live_bonus.telegram.TelegramError("xato")
        live_bonus.telegram.edit_message = boom
        previous = {"date": "2026-08-28", "message_id": 3654, "swept": False}
        live_bonus.retire_previous(previous, FIXTURES, PLAYERS, TEAMS)  # ko'tarilmasligi kerak

    def test_sweeping_marks_the_state(self):
        """Ikkinchi marta ishga tushsa takrorlanmasin — `swept` yozib qo'yiladi."""
        previous = {"date": "2026-08-28", "message_id": 3654, "swept": False}
        self.assertTrue(live_bonus.retire_previous(previous, FIXTURES, PLAYERS, TEAMS))
        self.assertTrue(previous["swept"])
        self.assertTrue(self.saved[-1]["swept"])
        self.assertFalse(live_bonus.retire_previous(previous, FIXTURES, PLAYERS, TEAMS))
        self.assertEqual(self.unpinned, [3654])    # ikkinchi marta pinga tegmadi


if __name__ == "__main__":
    unittest.main()
