"""Yakuniy yangilanish (`--final`) o'tkazib yuborilmasin.

30-31 avgustda jonli xabar `swept: false` bo'lib pinda qolib ketdi. Endi
GitHub cron'i har kuni 04:00 (Toshkent) da zaxira sifatida ishlaydi, va kun
allaqachon o'tib ketgan bo'lsa `final` bayrog'i bo'lmasa ham yakunlaydi.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from bot import config, live_bonus


def _fx(day: str):
    return {"id": 1, "event": 2, "kickoff_time": f"{day}T16:30:00Z",
            "started": True, "finished": True, "finished_provisional": True,
            "team_h": 1, "team_a": 2, "team_h_score": 1, "team_a_score": 0,
            "stats": []}


BOOTSTRAP = {"teams": [{"id": 1, "short_name": "ARS", "name": "Arsenal"},
                       {"id": 2, "short_name": "CHE", "name": "Chelsea"}],
             "elements": []}


class FinalSweepTest(unittest.TestCase):
    def setUp(self):
        self.edited, self.unpinned, self.saved = [], [], []
        self._orig = {
            "require": config.require_telegram,
            "load": live_bonus.storage.load,
            "save": live_bonus.storage.save,
            "boot": live_bonus.fpl_api.get_bootstrap,
            "fixtures": live_bonus.fpl_api.get_fixtures,
            "edit": live_bonus.telegram.edit_message,
            "unpin": live_bonus.telegram.unpin_message,
            "defcon": config.SHOW_DEFCON,
        }
        config.require_telegram = lambda: None
        config.SHOW_DEFCON = False
        live_bonus.storage.save = lambda path, data: self.saved.append(data)
        live_bonus.fpl_api.get_bootstrap = lambda: BOOTSTRAP
        live_bonus.telegram.edit_message = lambda mid, text, **kw: (
            self.edited.append(mid) or {"message_id": mid})
        live_bonus.telegram.unpin_message = lambda mid, **kw: (
            self.unpinned.append(mid) or True)

    def tearDown(self):
        config.require_telegram = self._orig["require"]
        config.SHOW_DEFCON = self._orig["defcon"]
        live_bonus.storage.load = self._orig["load"]
        live_bonus.storage.save = self._orig["save"]
        live_bonus.fpl_api.get_bootstrap = self._orig["boot"]
        live_bonus.fpl_api.get_fixtures = self._orig["fixtures"]
        live_bonus.telegram.edit_message = self._orig["edit"]
        live_bonus.telegram.unpin_message = self._orig["unpin"]

    def _setup_day(self, day: str, **state):
        base = {"date": day, "message_id": 3678, "last_text": "eski matn"}
        base.update(state)
        live_bonus.storage.load = lambda *a, **kw: dict(base)
        live_bonus.fpl_api.get_fixtures = lambda: [_fx(day)]

    def test_yesterday_is_swept_even_without_the_final_flag(self):
        """Jonli jarayon uzilib qolgan — kun o'tdi, xabar baribir yakunlansin."""
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
        self._setup_day(yesterday, final=False,
                        finished_at=datetime.now(timezone.utc).isoformat())
        self.assertEqual(live_bonus.final_sweep(), 0)
        self.assertEqual(self.edited, [3678])
        self.assertEqual(self.unpinned, [3678])
        self.assertTrue(self.saved[-1]["swept"])

    def test_today_without_the_final_flag_is_left_alone(self):
        """Kun hali tugamagan — erta yakunlab qo'ymaymiz."""
        self._setup_day(live_bonus.matchday_key(), final=False)
        self.assertEqual(live_bonus.final_sweep(), 0)
        self.assertEqual(self.edited, [])
        self.assertEqual(self.unpinned, [])

    def test_today_waits_out_the_sweep_delay(self):
        self._setup_day(live_bonus.matchday_key(), final=True,
                        finished_at=datetime.now(timezone.utc).isoformat())
        self.assertEqual(live_bonus.final_sweep(), 0)
        self.assertEqual(self.edited, [])

    def test_already_swept_is_not_repeated(self):
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
        self._setup_day(yesterday, final=True, swept=True)
        self.assertEqual(live_bonus.final_sweep(), 0)
        self.assertEqual(self.edited, [])
        self.assertEqual(self.unpinned, [])


if __name__ == "__main__":
    unittest.main()
