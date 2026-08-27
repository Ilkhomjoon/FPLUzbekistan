"""Jonli kuzatuv darvozasi: o'yin yo'q kunlari workflow ishlamasligi kerak."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from bot import config
from scripts import matchday


def _fx(dt: datetime) -> dict:
    return {"kickoff_time": dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)   # 13:00 London


class MatchdayTest(unittest.TestCase):
    def test_fixture_today_is_active(self):
        active, reason = matchday.verdict([_fx(NOW + timedelta(hours=6))], now=NOW)
        self.assertTrue(active)
        self.assertIn("bugun", reason)

    def test_fixture_earlier_today_is_active(self):
        active, _ = matchday.verdict([_fx(NOW - timedelta(hours=2))], now=NOW)
        self.assertTrue(active)

    def test_within_the_window_after_the_last_match(self):
        """Kecha 21:00 da tugagan o'yin -> ertalab 06:00 da hali kuzatiladi.

        Rasmiy bonus va DefCon shu oraliqda yakunlanadi.
        """
        morning = datetime(2026, 8, 27, 5, 0, tzinfo=timezone.utc)      # 06:00 London
        last = datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc)        # 21:00 London
        active, reason = matchday.verdict([_fx(last)], now=morning)
        self.assertTrue(active)
        self.assertIn("rasmiy bonus", reason)

    def test_outside_the_window_is_skipped(self):
        """Xuddi shu o'yin, lekin bir kundan ko'proq o'tgan."""
        later = datetime(2026, 8, 27, 20, 0, tzinfo=timezone.utc)       # 21:00 London
        last = datetime(2026, 8, 26, 20, 0, tzinfo=timezone.utc)
        active, reason = matchday.verdict([_fx(last)], now=later)
        self.assertFalse(active)
        self.assertIn("chegara", reason)

    def test_only_future_fixtures_is_skipped(self):
        active, _ = matchday.verdict([_fx(NOW + timedelta(days=3))], now=NOW)
        self.assertFalse(active)

    def test_no_fixtures_at_all(self):
        active, reason = matchday.verdict([], now=NOW)
        self.assertFalse(active)

    def test_window_boundary(self):
        edge = NOW - timedelta(hours=config.LIVE_ACTIVE_AFTER + 2)  # +2 = o'yin davomiyligi
        self.assertTrue(matchday.verdict([_fx(edge + timedelta(minutes=5))], now=NOW)[0])
        self.assertFalse(matchday.verdict([_fx(edge - timedelta(minutes=5))], now=NOW)[0])


if __name__ == "__main__":
    unittest.main()
