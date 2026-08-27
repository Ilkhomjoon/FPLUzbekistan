"""`bot.price_changes --watch` va cron kechikishini o'lchash mantiqini tekshiradi."""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone

from bot import config, price_changes, waiter


def _bootstrap(costs: dict[int, int]) -> dict:
    return {
        "events": [],
        "teams": [{"id": 1, "short_name": "ARS", "name": "Arsenal"}],
        "elements": [
            {"id": pid, "web_name": f"P{pid}", "team": 1, "now_cost": cost}
            for pid, cost in costs.items()
        ],
    }


class WatchTest(unittest.TestCase):
    def setUp(self):
        self.saved = {}
        self.sent = []
        self.slept = []

        self._orig = {
            "get_bootstrap": price_changes.fpl_api.get_bootstrap,
            "current_event_id": price_changes.fpl_api.current_event_id,
            "load": price_changes.storage.load,
            "save": price_changes.storage.save,
            "send": price_changes.telegram.send_message,
            "sleep_until": price_changes.waiter.sleep_until,
            "require": config.require_telegram,
        }
        price_changes.fpl_api.current_event_id = lambda b: 1
        price_changes.storage.save = lambda path, data: self.saved.update({str(path): data})
        price_changes.telegram.send_message = lambda text, **kw: self.sent.append(text) or {"message_id": 1}
        price_changes.waiter.sleep_until = lambda target, **kw: self.slept.append(target) or True
        config.require_telegram = lambda: None

    def tearDown(self):
        price_changes.fpl_api.get_bootstrap = self._orig["get_bootstrap"]
        price_changes.fpl_api.current_event_id = self._orig["current_event_id"]
        price_changes.storage.load = self._orig["load"]
        price_changes.storage.save = self._orig["save"]
        price_changes.telegram.send_message = self._orig["send"]
        price_changes.waiter.sleep_until = self._orig["sleep_until"]
        config.require_telegram = self._orig["require"]

    def test_posts_at_the_target_time_when_a_change_is_found(self):
        old = price_changes.build_snapshot(_bootstrap({1: 50, 2: 75}))
        price_changes.storage.load = lambda *a, **kw: old
        price_changes.fpl_api.get_bootstrap = lambda: _bootstrap({1: 49, 2: 76})

        self.assertEqual(price_changes.watch(), 0)
        # bitta tushish + bitta ko'tarilish posti
        self.assertEqual(len(self.sent), 2)
        # va post vaqtini kutgan bo'lishi kerak
        self.assertEqual(len(self.slept), 1)
        self.assertEqual(self.slept[0], waiter.local_time_today(config.PRICE_POST_AT))

    def test_no_change_means_no_post(self):
        old = price_changes.build_snapshot(_bootstrap({1: 50}))
        price_changes.storage.load = lambda *a, **kw: old
        price_changes.fpl_api.get_bootstrap = lambda: _bootstrap({1: 50})

        # kutish chegarasi allaqachon o'tgan bo'lsin -> bitta tekshiruvdan keyin chiqadi
        original = waiter.local_time_today
        fixed = {
            config.PRICE_POST_AT: datetime.now(timezone.utc) - timedelta(minutes=30),
            config.PRICE_WATCH_UNTIL: datetime.now(timezone.utc) - timedelta(minutes=1),
        }
        price_changes.waiter.local_time_today = lambda hhmm: fixed[hhmm]
        try:
            self.assertEqual(price_changes.watch(), 0)
        finally:
            price_changes.waiter.local_time_today = original

        self.assertEqual(self.sent, [])
        # post vaqti o'tib ketgan -> kutish darhol qaytadi, lekin baribir chaqiriladi
        self.assertEqual(len(self.slept), 1)

    def test_first_run_only_saves_the_snapshot(self):
        price_changes.storage.load = lambda *a, **kw: None
        price_changes.fpl_api.get_bootstrap = lambda: _bootstrap({1: 50})
        self.assertEqual(price_changes.watch(), 0)
        self.assertEqual(self.sent, [])
        self.assertTrue(self.saved)


class CronDelayTest(unittest.TestCase):
    """Navbatda turgan vaqt cron kechikishi deb hisoblanmasligi kerak."""

    def test_run_created_at_is_used_when_present(self):
        from scripts import cron_delay

        os.environ["CRON_RUN_CREATED_AT"] = "2026-08-25T01:07:00Z"
        try:
            created = cron_delay._created_at()
        finally:
            del os.environ["CRON_RUN_CREATED_AT"]
        self.assertEqual(created, datetime(2026, 8, 25, 1, 7, tzinfo=timezone.utc))

    def test_missing_or_broken_value_is_ignored(self):
        from scripts import cron_delay

        os.environ.pop("CRON_RUN_CREATED_AT", None)
        self.assertIsNone(cron_delay._created_at())
        os.environ["CRON_RUN_CREATED_AT"] = "not-a-date"
        try:
            self.assertIsNone(cron_delay._created_at())
        finally:
            del os.environ["CRON_RUN_CREATED_AT"]


class WatchOrderTest(unittest.TestCase):
    """Kuzatuv AVVAL post vaqtigacha kutishi, KEYIN solishtirishi kerak.

    Aks holda 04:07 da ishga tushgan jarayon kechagi qoldiq farqlarni ko'rib,
    tungi haqiqiy o'zgarishdan oldin post qilib yuborardi.
    """

    def setUp(self):
        self.events = []
        self._orig = {
            "bootstrap": price_changes.fpl_api.get_bootstrap,
            "event": price_changes.fpl_api.current_event_id,
            "load": price_changes.storage.load,
            "save": price_changes.storage.save,
            "send": price_changes.telegram.send_message,
            "sleep_until": price_changes.waiter.sleep_until,
            "require": config.require_telegram,
        }
        config.require_telegram = lambda: None
        price_changes.fpl_api.current_event_id = lambda b: 1
        price_changes.storage.save = lambda path, data: self.events.append("save")
        price_changes.telegram.send_message = lambda text, **kw: (
            self.events.append("send") or {"message_id": 1})
        price_changes.waiter.sleep_until = lambda target, **kw: (
            self.events.append("wait") or True)

    def tearDown(self):
        price_changes.fpl_api.get_bootstrap = self._orig["bootstrap"]
        price_changes.fpl_api.current_event_id = self._orig["event"]
        price_changes.storage.load = self._orig["load"]
        price_changes.storage.save = self._orig["save"]
        price_changes.telegram.send_message = self._orig["send"]
        price_changes.waiter.sleep_until = self._orig["sleep_until"]
        config.require_telegram = self._orig["require"]

    def test_waits_before_comparing(self):
        old = price_changes.build_snapshot(_bootstrap({1: 50}))
        price_changes.storage.load = lambda *a, **kw: old
        price_changes.fpl_api.get_bootstrap = lambda: _bootstrap({1: 49})

        self.assertEqual(price_changes.watch(), 0)
        # kutish yuborishdan oldin bo'lishi shart
        self.assertEqual(self.events[0], "wait")
        self.assertIn("send", self.events)
        self.assertLess(self.events.index("wait"), self.events.index("send"))


if __name__ == "__main__":
    unittest.main()
