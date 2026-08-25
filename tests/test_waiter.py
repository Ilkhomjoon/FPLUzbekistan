"""`bot.waiter` — cron kechikishiga qarshi kutish mantiqini tekshiradi."""
from __future__ import annotations

import time
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from bot import config, waiter


class LocalTimeTodayTest(unittest.TestCase):
    def test_returns_todays_local_time_in_utc(self):
        # 2026-08-25 01:00 UTC = 06:00 Toshkent
        base = datetime(2026, 8, 25, 1, 0, tzinfo=timezone.utc)
        target = waiter.local_time_today("06:00", base=base)
        self.assertEqual(target, base)
        self.assertEqual(target.astimezone(ZoneInfo(config.LOCAL_TZ)).hour, 6)

    def test_future_time_same_day(self):
        base = datetime(2026, 8, 24, 23, 10, tzinfo=timezone.utc)  # 04:10 Toshkent (25-avgust)
        target = waiter.local_time_today("06:00", base=base)
        self.assertGreater(target, base)
        self.assertLess((target - base), timedelta(hours=3))

    def test_recently_passed_time_stays_in_the_past(self):
        """Cron kechikib 06:39 da uyg'otsa — 06:00 o'tib ketgan, ertaga surilmasin."""
        base = datetime(2026, 8, 25, 1, 39, tzinfo=timezone.utc)  # 06:39 Toshkent
        target = waiter.local_time_today("06:00", base=base)
        self.assertLess(target, base)
        self.assertEqual((base - target), timedelta(minutes=39))

    def test_minute_is_parsed(self):
        base = datetime(2026, 8, 25, 1, 0, tzinfo=timezone.utc)
        target = waiter.local_time_today("23:30", base=base)
        local = target.astimezone(ZoneInfo(config.LOCAL_TZ))
        self.assertEqual((local.hour, local.minute), (23, 30))


class SleepUntilTest(unittest.TestCase):
    def test_past_target_returns_immediately(self):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        started = time.monotonic()
        self.assertTrue(waiter.sleep_until(past, label="test"))
        self.assertLess(time.monotonic() - started, 1)

    def test_gives_up_when_budget_is_too_small(self):
        far = datetime.now(timezone.utc) + timedelta(hours=5)
        started = time.monotonic()
        # byudjet allaqachon tugagan -> uxlamasdan False qaytarsin
        self.assertFalse(waiter.sleep_until(far, label="test", budget_end=time.monotonic()))
        self.assertLess(time.monotonic() - started, 1)


class HoldUntilTest(unittest.TestCase):
    def test_none_is_a_noop(self):
        started = time.monotonic()
        waiter.hold_until(None)
        self.assertLess(time.monotonic() - started, 1)

    def test_passed_time_does_not_sleep(self):
        """Vaqt o'tib ketgan bo'lsa hech qanday kutish bo'lmasligi kerak."""
        calls = []
        original = waiter.sleep_until
        waiter.sleep_until = lambda *a, **kw: calls.append(a) or True
        try:
            base = datetime.now(timezone.utc)
            # o'tib ketgan vaqtni local_time_today orqali "HH:MM" ga aylantiramiz
            passed = (base - timedelta(minutes=30)).astimezone(
                ZoneInfo(config.LOCAL_TZ)).strftime("%H:%M")
            target = waiter.local_time_today(passed)
            if target > base:  # yarim tundan o'tib ketgan holat — test ma'nosiz
                self.skipTest("yarim tun chegarasi")
            waiter.hold_until(passed)
            self.assertEqual(calls, [])
        finally:
            waiter.sleep_until = original


if __name__ == "__main__":
    unittest.main()
