"""Jonli bonus: cron kechikib uyg'otsa ham o'yin boshlanishini kutib turishi kerak."""
from __future__ import annotations

import unittest
import unittest.mock
from datetime import datetime, timedelta, timezone

from bot import config, live_bonus


class _Stop(Exception):
    """sleep_until chaqirilganini bilish uchun — undan keyingi sikl kerak emas."""


def _fixtures(kickoff: datetime) -> list[dict]:
    return [{
        "id": 1, "event": 1, "started": False, "finished": False,
        "finished_provisional": False,
        "kickoff_time": kickoff.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "team_h": 1, "team_a": 2, "team_h_score": None, "team_a_score": None,
        "stats": [],
    }]


class PreKickoffWaitTest(unittest.TestCase):
    def setUp(self):
        self.slept: list[datetime] = []
        self._orig = {
            "bootstrap": live_bonus.fpl_api.get_bootstrap,
            "fixtures": live_bonus.fpl_api.get_fixtures,
            "players": live_bonus.fpl_api.players_by_id,
            "teams": live_bonus.fpl_api.teams_by_id,
            "event": live_bonus.fpl_api.current_event_id,
            "sleep_until": live_bonus.waiter.sleep_until,
            "require": config.require_telegram,
            "load": live_bonus.storage.load,
        }
        live_bonus.fpl_api.get_bootstrap = lambda: {"elements": [], "teams": [], "events": []}
        live_bonus.fpl_api.players_by_id = lambda b: {}
        live_bonus.fpl_api.teams_by_id = lambda b: {}
        live_bonus.fpl_api.current_event_id = lambda b: 1
        live_bonus.storage.load = lambda *a, **kw: {}
        config.require_telegram = lambda: None

        def fake_sleep(target, **kw):
            self.slept.append(target)
            raise _Stop
        live_bonus.waiter.sleep_until = fake_sleep

    def tearDown(self):
        live_bonus.fpl_api.get_bootstrap = self._orig["bootstrap"]
        live_bonus.fpl_api.get_fixtures = self._orig["fixtures"]
        live_bonus.fpl_api.players_by_id = self._orig["players"]
        live_bonus.fpl_api.teams_by_id = self._orig["teams"]
        live_bonus.fpl_api.current_event_id = self._orig["event"]
        live_bonus.waiter.sleep_until = self._orig["sleep_until"]
        live_bonus.storage.load = self._orig["load"]
        config.require_telegram = self._orig["require"]

    def test_waits_until_just_before_kickoff(self):
        """Cron 40 daqiqa kechikib uyg'otdi, o'yingacha 50 daqiqa bor -> kutamiz."""
        kickoff = datetime.now(timezone.utc) + timedelta(minutes=50)
        live_bonus.fpl_api.get_fixtures = lambda **kw: _fixtures(kickoff)

        with unittest.mock.patch.object(config, "LIVE_START_LEAD", 115):
            with self.assertRaises(_Stop):
                live_bonus.run()

        self.assertEqual(len(self.slept), 1)
        expected = kickoff - timedelta(seconds=config.LIVE_PREKICK_POLL)
        self.assertAlmostEqual((self.slept[0] - expected).total_seconds(), 0, delta=2)

    def test_exits_when_still_far_from_kickoff(self):
        """O'yingacha LIVE_START_LEAD dan ko'p vaqt bor -> kutmasdan chiqadi."""
        kickoff = datetime.now(timezone.utc) + timedelta(minutes=300)
        live_bonus.fpl_api.get_fixtures = lambda **kw: _fixtures(kickoff)

        with unittest.mock.patch.object(config, "LIVE_START_LEAD", 115):
            self.assertEqual(live_bonus.run(), 0)
        self.assertEqual(self.slept, [])

    def test_once_does_not_wait(self):
        """--once qo'lda sinash uchun — hech qachon kutmasligi kerak."""
        kickoff = datetime.now(timezone.utc) + timedelta(minutes=50)
        live_bonus.fpl_api.get_fixtures = lambda **kw: _fixtures(kickoff)

        with unittest.mock.patch.object(config, "LIVE_START_LEAD", 115):
            live_bonus.run(once=True)
        self.assertEqual(self.slept, [])


if __name__ == "__main__":
    import unittest.mock  # noqa: F401
    unittest.main()
