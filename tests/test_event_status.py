"""Tur qachon "yakunlangan" hisoblanadi.

`bootstrap-static` dagi `finished` bayrog'i lockdown'dan ancha keyin qo'yiladi,
shuning uchun `/event-status/` ga qaraymiz.
"""
from __future__ import annotations

import unittest

from bot import fpl_api


def _status(points="r", bonus=True, leagues="", event=1, days=4):
    return {"status": [{"bonus_added": bonus, "date": f"2026-08-2{i}", "event": event,
                        "points": points} for i in range(1, days + 1)],
            "leagues": leagues}


BOOTSTRAP = {"events": [
    {"id": 1, "finished": False, "data_checked": False, "is_current": True},
    {"id": 2, "finished": False, "data_checked": False, "is_next": True},
]}


class StatusVerdictTest(unittest.TestCase):
    def test_ready_when_points_final_bonus_added_and_leagues_done(self):
        gw, ready, reason = fpl_api.status_verdict(_status())
        self.assertEqual(gw, 1)
        self.assertTrue(ready)
        self.assertEqual(reason, "tayyor")

    def test_provisional_points_are_not_ready(self):
        gw, ready, reason = fpl_api.status_verdict(_status(points="p", bonus=False))
        self.assertEqual(gw, 1)
        self.assertFalse(ready)
        self.assertIn("vaqtinchalik", reason)

    def test_bonus_not_added_yet(self):
        _, ready, reason = fpl_api.status_verdict(_status(bonus=False))
        self.assertFalse(ready)
        self.assertIn("bonus", reason)

    def test_leagues_still_updating(self):
        """Aynan shu holat: ochkolar yakuniy, lekin jadvallar qayta hisoblanmoqda."""
        _, ready, reason = fpl_api.status_verdict(_status(leagues="Updating"))
        self.assertFalse(ready)
        self.assertIn("liga jadvallari", reason)

    def test_one_day_still_provisional_blocks_the_whole_gameweek(self):
        status = _status()
        status["status"][2]["points"] = "p"
        _, ready, _ = fpl_api.status_verdict(status)
        self.assertFalse(ready)

    def test_empty_status(self):
        gw, ready, reason = fpl_api.status_verdict({})
        self.assertIsNone(gw)
        self.assertFalse(ready)


class FinalisedEventTest(unittest.TestCase):
    def test_event_status_wins_before_the_finished_flag(self):
        event = fpl_api.finalised_event(BOOTSTRAP, _status())
        self.assertIsNotNone(event)
        self.assertEqual(event["id"], 1)
        self.assertFalse(event["finished"])   # bayroq hali qo'yilmagan bo'lsa ham

    def test_not_finalised_returns_none(self):
        self.assertIsNone(fpl_api.finalised_event(BOOTSTRAP, _status(leagues="Updating")))

    def test_falls_back_to_the_finished_flag(self):
        bootstrap = {"events": [{"id": 1, "finished": True}, {"id": 2, "finished": False}]}
        event = fpl_api.finalised_event(bootstrap, {"status": [], "leagues": ""})
        self.assertEqual(event["id"], 1)

    def test_unknown_event_id_falls_back(self):
        event = fpl_api.finalised_event({"events": [{"id": 9, "finished": True}]}, _status())
        self.assertEqual(event["id"], 9)


if __name__ == "__main__":
    unittest.main()
