"""Vaqt oynasi va takror himoyasi.

28-avgust 07:19 da narx bashorati posti ikkinchi marta chiqib ketgan edi:
cron kechikkan, jarayon yarim tundan keyin ishga tushgan va kalendar kun
o'zgargani uchun "hali chiqarilmagan" deb hisoblagan.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bot import config, price_watch, waiter

TZ = ZoneInfo("Asia/Tashkent")


def _at(hour, minute=0, day=28):
    return datetime(2026, 8, day, hour, minute, tzinfo=TZ).astimezone(timezone.utc)


class WindowTest(unittest.TestCase):
    def test_window_crossing_midnight(self):
        w = "20:00-01:00"
        for t in [(20, 0), (23, 19), (0, 17), (1, 0)]:
            self.assertTrue(waiter.in_window(w, _at(*t)), f"{t} ruxsat bo'lishi kerak")
        for t in [(19, 30), (1, 30), (7, 19), (15, 0)]:
            self.assertFalse(waiter.in_window(w, _at(*t)), f"{t} bloklanishi kerak")

    def test_normal_window(self):
        w = "05:00-09:00"
        self.assertTrue(waiter.in_window(w, _at(6, 14)))
        self.assertFalse(waiter.in_window(w, _at(12, 0)))
        self.assertFalse(waiter.in_window(w, _at(4, 59)))

    def test_no_window_means_always_allowed(self):
        self.assertTrue(waiter.in_window(None, _at(3, 0)))
        self.assertTrue(waiter.in_window("", _at(3, 0)))


class RecentTest(unittest.TestCase):
    def test_recent_within_the_limit(self):
        posted = (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()
        self.assertTrue(waiter.recent(posted, 20))

    def test_older_than_the_limit(self):
        posted = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        self.assertFalse(waiter.recent(posted, 20))

    def test_missing_or_broken(self):
        self.assertFalse(waiter.recent(None, 20))
        self.assertFalse(waiter.recent("not-a-date", 20))


class PriceWatchGuardTest(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self._orig = {
            "bootstrap": price_watch.fpl_api.get_bootstrap,
            "load": price_watch.storage.load,
            "save": price_watch.storage.save,
            "send": price_watch.telegram.send_message,
            "require": config.require_telegram,
        }
        config.require_telegram = lambda: None
        price_watch.storage.save = lambda *a, **kw: None
        price_watch.telegram.send_message = lambda text, **kw: (
            self.sent.append(text) or {"message_id": 1})
        price_watch.fpl_api.get_bootstrap = lambda: {"elements": [], "teams": []}

    def tearDown(self):
        price_watch.fpl_api.get_bootstrap = self._orig["bootstrap"]
        price_watch.storage.load = self._orig["load"]
        price_watch.storage.save = self._orig["save"]
        price_watch.telegram.send_message = self._orig["send"]
        config.require_telegram = self._orig["require"]

    def test_a_post_from_last_night_blocks_a_repeat(self):
        """Aynan 28-avgust holati: 00:17 da chiqqan post 07:19 da takrorlanmasin.

        Ikkalasi ham bitta kechaga tegishli (kecha 12:00 da tugaydi).
        """
        price_watch.storage.load = lambda *a, **kw: {
            "date": "2026-08-27", "night": price_watch.night_key(),
            "posted_at": (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat(),
        }
        self.assertEqual(price_watch.run(), 0)
        self.assertEqual(self.sent, [])

    def test_an_old_post_does_not_block(self):
        price_watch.storage.load = lambda *a, **kw: {
            "date": "2026-08-20", "night": "2026-08-20",
            "posted_at": (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat(),
        }
        # o'zgarish yo'q -> post yo'q, lekin takror himoyasi to'sqinlik qilmagan
        self.assertEqual(price_watch.run(), 0)

    def test_force_ignores_both_guards(self):
        price_watch.storage.load = lambda *a, **kw: {
            "date": datetime.now(TZ).date().isoformat(),
            "posted_at": datetime.now(timezone.utc).isoformat(),
        }
        self.assertEqual(price_watch.run(force=True, window="20:00-01:00"), 0)


if __name__ == "__main__":
    unittest.main()
