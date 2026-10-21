"""Tur qachon "yakunlangan" hisoblanadi.

`bootstrap-static` dagi `finished` bayrog'i lockdown'dan ancha keyin qo'yiladi,
shuning uchun `/event-status/` ga qaraymiz.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from zoneinfo import ZoneInfo

from bot import config, fpl_api


def _recent_status(leagues="Updating", event=1):
    """Ochkolar yakuniy, liga bayrog'i berilgan holatdagi javob."""
    return {"status": [{"bonus_added": True, "date": "2026-10-19",
                        "event": event, "points": "r"}],
            "leagues": leagues}


def _verdict_after(hours_since_final: float, status=None):
    """Yakunlanish nuqtasidan `hours_since_final` soat o'tgandagi hukm.

    Soatni soatga emas, `status_verdict(now=...)` ga beramiz — test qaysi
    kuni ishga tushsa ham natija bir xil bo'lsin.
    """
    status = status or _recent_status()
    final_at = fpl_api.points_final_at(status)
    return fpl_api.status_verdict(status, now=final_at + timedelta(hours=hours_since_final))


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

    def test_leagues_still_updating_blocks_at_first(self):
        """Ochkolar yakuniy, jadvallar qayta hisoblanmoqda — biroz kutamiz."""
        _, ready, reason = _verdict_after(0.2)
        self.assertFalse(ready)
        self.assertIn("liga jadvallari", reason)

    def test_a_stuck_leagues_flag_stops_blocking(self):
        """19-oktyabr holati: bayroq ikki kun 'Updating' bo'lib osilib qoldi."""
        _, ready, reason = _verdict_after(48)
        self.assertTrue(ready)
        self.assertIn("osilib qolgan", reason)

    def test_the_grace_is_measured_from_the_lockdown(self):
        grace = config.LEAGUE_UPDATE_GRACE / 60
        _, before, _ = _verdict_after(grace - 0.2)
        _, after, _ = _verdict_after(grace + 0.2)
        self.assertFalse(before)
        self.assertTrue(after)

    def test_points_not_final_is_never_waived(self):
        """Bayroq osilib qolsa ham, ochkolar vaqtinchalik bo'lsa — kutamiz."""
        status = _recent_status()
        status["status"][0]["points"] = "p"
        _, ready, _ = _verdict_after(48, status)
        self.assertFalse(ready)

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
        # bayroq hozirgina 'Updating' bo'ldi — hali kutamiz
        status = {"status": [{"bonus_added": True, "event": 1, "points": "r",
                              "date": datetime.now(timezone.utc).date().isoformat()}],
                  "leagues": "Updating"}
        self.assertIsNone(fpl_api.finalised_event(BOOTSTRAP, status))

    def test_falls_back_to_the_finished_flag(self):
        bootstrap = {"events": [{"id": 1, "finished": True}, {"id": 2, "finished": False}]}
        event = fpl_api.finalised_event(bootstrap, {"status": [], "leagues": ""})
        self.assertEqual(event["id"], 1)

    def test_unknown_event_id_falls_back(self):
        event = fpl_api.finalised_event({"events": [{"id": 9, "finished": True}]}, _status())
        self.assertEqual(event["id"], 9)


if __name__ == "__main__":
    unittest.main()
