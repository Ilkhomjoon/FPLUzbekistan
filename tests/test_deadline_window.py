"""Deadline statistikasi juma turlarida ham chiqsin.

23-oktyabr (GW8): deadline 17:30, birinchi o'yin 19:00 — oradagi 90 daqiqaga
bitta ham cron tushmadi va post umuman chiqmadi. Sabab: FPL `is_current`
bayrog'ini faqat deadline o'tgach ko'taradi, undan oldin bot o'tgan turni
ko'rib "allaqachon chiqarilgan" deb chiqib ketardi.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from bot import config, deadline_stats, waiter


def _events(current=7, nxt=8, deadline=None):
    rows = [{"id": current, "is_current": True, "is_next": False,
             "deadline_time": "2026-10-17T10:00:00Z"}]
    if nxt:
        rows.append({"id": nxt, "is_current": False, "is_next": True,
                     "deadline_time": deadline or "2026-10-23T17:30:00Z"})
    return {"events": rows}


class TargetEventTest(unittest.TestCase):
    def test_the_current_gameweek_comes_first(self):
        event = deadline_stats.target_event(_events(), {}, force=False, wait=True)
        self.assertEqual(event["id"], 7)

    def test_an_already_posted_gameweek_hands_over_to_the_next(self):
        event = deadline_stats.target_event(_events(), {"event": 7}, force=False, wait=True)
        self.assertEqual(event["id"], 8)

    def test_without_wait_there_is_no_hand_over(self):
        """Oddiy (kutmaydigan) ishga tushirishda keyingi turga o'tmaymiz."""
        self.assertIsNone(
            deadline_stats.target_event(_events(), {"event": 7}, force=False, wait=False))

    def test_the_next_gameweek_is_not_posted_twice(self):
        """GW8 chiqib bo'lgan, `is_current` esa hali GW7 da — orqaga qaytmaymiz."""
        self.assertIsNone(
            deadline_stats.target_event(_events(), {"event": 8}, force=False, wait=True))

    def test_a_brand_new_season_has_no_state(self):
        event = deadline_stats.target_event(_events(current=1, nxt=2), {}, force=False, wait=True)
        self.assertEqual(event["id"], 1)

    def test_force_always_takes_the_current_gameweek(self):
        event = deadline_stats.target_event(_events(), {"event": 7}, force=True, wait=True)
        self.assertEqual(event["id"], 7)


class PostWindowTest(unittest.TestCase):
    """Post vaqti — deadline bilan "o'yingacha 40 daqiqa" dan kechrog'i."""

    def setUp(self):
        self.sent, self.slept = [], []
        self._orig = {
            "bootstrap": deadline_stats.fpl_api.get_bootstrap,
            "fixtures": deadline_stats.fpl_api.get_fixtures,
            "scan": deadline_stats.scan_league,
            "load": deadline_stats.storage.load,
            "save": deadline_stats.storage.save,
            "send": deadline_stats.telegram.send_message,
            "sleep": waiter.sleep_until,
            "require": config.require_telegram,
        }
        config.require_telegram = lambda: None
        deadline_stats.storage.save = lambda *a, **kw: None
        deadline_stats.telegram.send_message = lambda text, **kw: (
            self.sent.append(text) or {"message_id": 1})
        deadline_stats.scan_league = lambda *a, **kw: None
        waiter.sleep_until = lambda target, **kw: self.slept.append(target) or True

    def tearDown(self):
        deadline_stats.fpl_api.get_bootstrap = self._orig["bootstrap"]
        deadline_stats.fpl_api.get_fixtures = self._orig["fixtures"]
        deadline_stats.scan_league = self._orig["scan"]
        deadline_stats.storage.load = self._orig["load"]
        deadline_stats.storage.save = self._orig["save"]
        deadline_stats.telegram.send_message = self._orig["send"]
        waiter.sleep_until = self._orig["sleep"]
        config.require_telegram = self._orig["require"]

    def _setup(self, minutes_to_deadline, gap_minutes=90, state=None):
        """Deadline `minutes_to_deadline` daqiqadan keyin, o'yin undan
        `gap_minutes` keyin (GW8 da bu 90 daqiqa edi)."""
        now = datetime.now(timezone.utc)
        deadline = now + timedelta(minutes=minutes_to_deadline)
        kickoff = deadline + timedelta(minutes=gap_minutes)
        deadline_stats.fpl_api.get_bootstrap = lambda: {"events": [
            {"id": 7, "is_current": True, "is_next": False,
             "deadline_time": (now - timedelta(days=6)).isoformat().replace("+00:00", "Z")},
            {"id": 8, "is_current": False, "is_next": True,
             "deadline_time": deadline.isoformat().replace("+00:00", "Z")},
        ]}
        deadline_stats.fpl_api.get_fixtures = lambda **kw: [
            {"id": 1, "event": 8,
             "kickoff_time": kickoff.isoformat().replace("+00:00", "Z")}]
        deadline_stats.storage.load = lambda *a, **kw: state or {"event": 7}
        return deadline, kickoff

    def test_a_friday_gameweek_is_waited_for(self):
        """GW8 holati: deadline'gacha 70 daqiqa, o'yin undan 90 daqiqa keyin."""
        deadline, kickoff = self._setup(minutes_to_deadline=70)
        deadline_stats.run(wait=True)
        self.assertEqual(len(self.slept), 1)
        # o'yingacha 40 daqiqa — deadline'dan keyin, demak shu vaqt tanlanadi
        self.assertEqual(self.slept[0], kickoff - timedelta(minutes=config.STATS_LEAD))

    def test_a_short_gap_waits_for_the_deadline_itself(self):
        """Deadline bilan o'yin orasi 40 daqiqadan kam bo'lsa — deadline kutiladi."""
        deadline, _ = self._setup(minutes_to_deadline=60, gap_minutes=20)
        deadline_stats.run(wait=True)
        self.assertEqual(self.slept[0], deadline)

    def test_too_far_ahead_is_left_to_a_later_run(self):
        self._setup(minutes_to_deadline=config.STATS_WAKE_LEAD + 120)
        deadline_stats.run(wait=True)
        self.assertEqual(self.slept, [])
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
