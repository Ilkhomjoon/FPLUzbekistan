"""Differentiallar posti cron vaqti noto'g'ri bo'lsa — jim o'tib ketmasin.

13-oktyabr holati: cron 10:00 da ishladi, FPL turni 13:00 da yopdi. Bot
"GW5 allaqachon chiqarilgan" deb chiqib ketdi va GW6 posti umuman chiqmadi.
"""
from __future__ import annotations

import unittest
from datetime import timedelta

from bot import config, differentials, waiter


def _event(eid, current=False, nxt=False, finished=False):
    # keyingi turning deadline'i doim kelajakda bo'lsin — aks holda test
    # kalendarga bog'lanib qoladi
    soon = (waiter.now_utc() + timedelta(days=3)).isoformat().replace("+00:00", "Z")
    return {"id": eid, "finished": finished, "data_checked": finished,
            "is_current": current, "is_next": nxt, "deadline_time": soon}


BOOTSTRAP = {"events": [_event(5, finished=True), _event(6, current=True), _event(7, nxt=True)],
             "elements": [], "teams": []}


class TooEarlyTest(unittest.TestCase):
    def setUp(self):
        self.alerts = []
        self.sent = []
        self._orig = {
            "bootstrap": differentials.fpl_api.get_bootstrap,
            "fixtures": differentials.fpl_api.get_fixtures,
            "last": differentials.last_finished_event,
            "load": differentials.storage.load,
            "save": differentials.storage.save,
            "notify": differentials.telegram.notify_admin,
            "send": differentials.telegram.send_message,
            "require": config.require_telegram,
        }
        config.require_telegram = lambda: None
        differentials.fpl_api.get_bootstrap = lambda: BOOTSTRAP
        differentials.storage.save = lambda *a, **kw: None
        differentials.telegram.notify_admin = lambda text: self.alerts.append(text)
        differentials.telegram.send_message = lambda text, **kw: (
            self.sent.append(text) or {"message_id": 1})
        # FPL hali GW6 ni yopmagan -> "oxirgi yakunlangan" GW5
        differentials.last_finished_event = lambda b: _event(5, finished=True)
        differentials.storage.load = lambda *a, **kw: {"event": 5}

    def tearDown(self):
        differentials.fpl_api.get_bootstrap = self._orig["bootstrap"]
        differentials.fpl_api.get_fixtures = self._orig["fixtures"]
        differentials.last_finished_event = self._orig["last"]
        differentials.storage.load = self._orig["load"]
        differentials.storage.save = self._orig["save"]
        differentials.telegram.notify_admin = self._orig["notify"]
        differentials.telegram.send_message = self._orig["send"]
        config.require_telegram = self._orig["require"]

    def _fixtures(self, done: bool):
        differentials.fpl_api.get_fixtures = lambda **kw: [
            {"id": 1, "event": 6, "finished": done, "finished_provisional": done}]

    def test_a_played_but_unclosed_gameweek_raises_an_alert(self):
        self._fixtures(True)
        self.assertEqual(differentials.run(), 0)
        self.assertEqual(self.sent, [])              # post yo'q
        self.assertEqual(len(self.alerts), 1)        # lekin admin biladi
        self.assertIn("GW6", self.alerts[0])

    def test_a_gameweek_still_in_play_is_not_an_alert(self):
        """O'yinlar hali tugamagan — bu normal holat, bezovta qilmaymiz."""
        self._fixtures(False)
        self.assertEqual(differentials.run(), 0)
        self.assertEqual(self.alerts, [])


class PostTimeTest(unittest.TestCase):
    """Post vaqtigacha byudjet yetmasa — 5 soat uxlab o'tirmaymiz."""

    def setUp(self):
        self.alerts = []
        self.slept = []
        self._orig = {
            "bootstrap": differentials.fpl_api.get_bootstrap,
            "fixtures": differentials.fpl_api.get_fixtures,
            "last": differentials.last_finished_event,
            "load": differentials.storage.load,
            "save": differentials.storage.save,
            "notify": differentials.telegram.notify_admin,
            "sleep": waiter.sleep_until,
            "collect": differentials.collect,
            "require": config.require_telegram,
            "post_at": config.DIFF_POST_AT,
            "budget": config.DIFF_MAX_MINUTES,
        }
        config.require_telegram = lambda: None
        differentials.fpl_api.get_bootstrap = lambda: BOOTSTRAP
        differentials.fpl_api.get_fixtures = lambda **kw: []
        differentials.last_finished_event = lambda b: _event(6, finished=True)
        differentials.storage.load = lambda *a, **kw: {"event": 5}
        differentials.storage.save = lambda *a, **kw: None
        differentials.telegram.notify_admin = lambda text: self.alerts.append(text)
        differentials.collect = lambda *a, **kw: differentials.Picks()
        waiter.sleep_until = lambda target, **kw: self.slept.append(target) or True

    def tearDown(self):
        differentials.fpl_api.get_bootstrap = self._orig["bootstrap"]
        differentials.fpl_api.get_fixtures = self._orig["fixtures"]
        differentials.last_finished_event = self._orig["last"]
        differentials.storage.load = self._orig["load"]
        differentials.storage.save = self._orig["save"]
        differentials.telegram.notify_admin = self._orig["notify"]
        differentials.collect = self._orig["collect"]
        waiter.sleep_until = self._orig["sleep"]
        config.require_telegram = self._orig["require"]
        config.DIFF_POST_AT = self._orig["post_at"]
        config.DIFF_MAX_MINUTES = self._orig["budget"]

    def _post_at_in(self, hours: float):
        target = waiter.now_utc() + timedelta(hours=hours)
        waiter.local_time_today = lambda hhmm, base=None: target

    def test_an_unreachable_post_time_is_reported(self):
        orig_local = waiter.local_time_today
        try:
            self._post_at_in(10)                 # 10 soat kutish kerak
            config.DIFF_MAX_MINUTES = 300        # byudjet 5 soat
            self.assertEqual(differentials.run(), 0)
            self.assertEqual(self.slept, [])     # uxlamadi
            self.assertEqual(len(self.alerts), 1)
        finally:
            waiter.local_time_today = orig_local

    def test_a_reachable_post_time_still_waits(self):
        orig_local = waiter.local_time_today
        try:
            self._post_at_in(0.2)                # 12 daqiqa
            config.DIFF_MAX_MINUTES = 300
            differentials.run()
            self.assertEqual(len(self.slept), 1)
            self.assertEqual(self.alerts, [])
        finally:
            waiter.local_time_today = orig_local


if __name__ == "__main__":
    unittest.main()
