"""Tur hali rasman yopilmaganda gw_review nima qilishi kerak."""
from __future__ import annotations

import logging
import unittest
from datetime import datetime, timedelta, timezone

from bot import config, gw_review


def _status(points="p", bonus=False, leagues="", event=1):
    """/event-status/ javobi. Standart holat — hali yakunlanmagan."""
    return {"status": [{"bonus_added": bonus, "date": "2026-08-24",
                        "event": event, "points": points}],
            "leagues": leagues}


def _fixture(finished: bool, provisional: bool) -> dict:
    return {"id": 1, "event": 1, "finished": finished,
            "finished_provisional": provisional, "kickoff_time": "2026-08-24T19:00:00Z"}


class NotFinishedTest(unittest.TestCase):
    def setUp(self):
        self._orig = {
            "bootstrap": gw_review.fpl_api.get_bootstrap,
            "fixtures": gw_review.fpl_api.get_fixtures,
            "status": gw_review.fpl_api.get_event_status,
            "require": config.require_telegram,
            "send": gw_review.telegram.send_message,
        }
        config.require_telegram = lambda: None
        gw_review.fpl_api.get_event_status = lambda: _status()
        self.sent = []
        gw_review.telegram.send_message = lambda text, **kw: self.sent.append(text) or {"message_id": 1}

    def tearDown(self):
        gw_review.fpl_api.get_bootstrap = self._orig["bootstrap"]
        gw_review.fpl_api.get_fixtures = self._orig["fixtures"]
        gw_review.fpl_api.get_event_status = self._orig["status"]
        config.require_telegram = self._orig["require"]
        gw_review.telegram.send_message = self._orig["send"]

    def test_all_played_but_points_are_still_provisional(self):
        """Ochkolar hali "p" -> post yo'q, log sababini aytishi kerak."""
        gw_review.fpl_api.get_bootstrap = lambda: {
            "events": [{"id": 1, "is_current": True, "finished": False, "data_checked": False}],
            "elements": [], "teams": [],
        }
        gw_review.fpl_api.get_fixtures = lambda **kw: [_fixture(False, True)] * 10

        with self.assertLogs("gw_review", level=logging.INFO) as logs:
            self.assertEqual(gw_review.run(), 0)

        self.assertEqual(self.sent, [])
        self.assertIn("vaqtinchalik", " ".join(logs.output))

    def test_leagues_still_updating_blocks_the_post(self):
        """Aynan bugungi holat: ochkolar yakuniy, jadvallar qayta hisoblanmoqda."""
        gw_review.fpl_api.get_event_status = lambda: _status(
            points="r", bonus=True, leagues="Updating")
        gw_review.fpl_api.get_bootstrap = lambda: {
            "events": [{"id": 1, "is_current": True, "finished": False, "data_checked": False}],
            "elements": [], "teams": [],
        }
        gw_review.fpl_api.get_fixtures = lambda **kw: [_fixture(False, True)] * 10

        with self.assertLogs("gw_review", level=logging.INFO) as logs:
            self.assertEqual(gw_review.run(), 0)
        self.assertEqual(self.sent, [])
        self.assertIn("liga jadvallari", " ".join(logs.output))

    def test_gameweek_still_in_progress(self):
        gw_review.fpl_api.get_bootstrap = lambda: {
            "events": [{"id": 1, "is_current": True, "finished": False, "data_checked": False}],
            "elements": [], "teams": [],
        }
        gw_review.fpl_api.get_event_status = lambda: {"status": [], "leagues": ""}
        gw_review.fpl_api.get_fixtures = lambda **kw: (
            [_fixture(True, True)] * 6 + [_fixture(False, False)] * 4)

        with self.assertLogs("gw_review", level=logging.INFO) as logs:
            self.assertEqual(gw_review.run(), 0)

        self.assertEqual(self.sent, [])
        self.assertIn("davom etyapti", " ".join(logs.output))

    def test_no_current_event(self):
        gw_review.fpl_api.get_event_status = lambda: {"status": [], "leagues": ""}
        gw_review.fpl_api.get_bootstrap = lambda: {"events": [], "elements": [], "teams": []}
        with self.assertLogs("gw_review", level=logging.INFO):
            self.assertEqual(gw_review.run(), 0)
        self.assertEqual(self.sent, [])


class WatchTest(unittest.TestCase):
    """--watch: FPL tasdiqlaguncha kutadi, tasdiqlangach darhol chiqaradi."""

    def setUp(self):
        self._orig = {
            "bootstrap": gw_review.fpl_api.get_bootstrap,
            "status": gw_review.fpl_api.get_event_status,
            "fixtures": gw_review.fpl_api.get_fixtures,
            "run": gw_review.run,
            "load": gw_review.storage.load,
            "sleep": gw_review.time.sleep,
            "require": config.require_telegram,
        }
        config.require_telegram = lambda: None
        gw_review.fpl_api.get_event_status = lambda: _status()
        gw_review.fpl_api.get_fixtures = lambda **kw: []
        gw_review.storage.load = lambda *a, **kw: {}
        self.slept = []
        gw_review.time.sleep = lambda s: self.slept.append(s)
        self.ran = []
        gw_review.run = lambda *a, **kw: self.ran.append(True) or 0

    def tearDown(self):
        gw_review.fpl_api.get_bootstrap = self._orig["bootstrap"]
        gw_review.fpl_api.get_event_status = self._orig["status"]
        gw_review.fpl_api.get_fixtures = self._orig["fixtures"]
        gw_review.run = self._orig["run"]
        gw_review.storage.load = self._orig["load"]
        gw_review.time.sleep = self._orig["sleep"]
        config.require_telegram = self._orig["require"]

    def test_posts_as_soon_as_fpl_confirms(self):
        gw_review.fpl_api.get_event_status = lambda: _status(points="r", bonus=True)
        gw_review.fpl_api.get_bootstrap = lambda: {
            "events": [{"id": 1, "finished": False, "data_checked": False}]}
        self.assertEqual(gw_review.watch(), 0)
        self.assertEqual(len(self.ran), 1)
        # to'liq POLL kutmagan — faqat tasdiqlash tanaffusi
        self.assertEqual(self.slept, [config.GW_REVIEW_CONFIRM_WAIT])

    def test_gives_up_after_the_deadline(self):
        gw_review.fpl_api.get_bootstrap = lambda: {
            "events": [{"id": 1, "is_current": True, "finished": False, "data_checked": False}]}
        gw_review.fpl_api.get_fixtures = lambda **kw: []
        original = gw_review.waiter.local_time_today
        gw_review.waiter.local_time_today = lambda hhmm: (
            datetime.now(timezone.utc) - timedelta(minutes=1))
        try:
            self.assertEqual(gw_review.watch(), 0)
        finally:
            gw_review.waiter.local_time_today = original
        self.assertEqual(self.ran, [])
        self.assertEqual(self.slept, [])

    def test_already_posted_gameweek_is_not_repeated(self):
        gw_review.storage.load = lambda *a, **kw: {"event": 1}
        gw_review.fpl_api.get_event_status = lambda: _status(points="r", bonus=True)
        gw_review.fpl_api.get_bootstrap = lambda: {
            "events": [{"id": 1, "is_current": True, "finished": True, "data_checked": True}]}
        original = gw_review.waiter.local_time_today
        gw_review.waiter.local_time_today = lambda hhmm: (
            datetime.now(timezone.utc) - timedelta(minutes=1))
        try:
            self.assertEqual(gw_review.watch(), 0)
        finally:
            gw_review.waiter.local_time_today = original
        self.assertEqual(self.ran, [])


class ConfirmationTest(unittest.TestCase):
    """FPL CDN eski nusxa qaytarishi mumkin — bitta "tayyor" javob yetarli emas."""

    def setUp(self):
        self._orig = {
            "bootstrap": gw_review.fpl_api.get_bootstrap,
            "status": gw_review.fpl_api.get_event_status,
            "fixtures": gw_review.fpl_api.get_fixtures,
            "run": gw_review.run,
            "load": gw_review.storage.load,
            "sleep": gw_review.time.sleep,
            "require": config.require_telegram,
        }
        config.require_telegram = lambda: None
        gw_review.fpl_api.get_fixtures = lambda **kw: []
        gw_review.fpl_api.get_bootstrap = lambda: {
            "events": [{"id": 1, "is_current": True, "finished": False, "data_checked": False}]}
        gw_review.storage.load = lambda *a, **kw: {}
        # kutish chegarasi haqiqiy soatga bog'liq bo'lmasin
        self._local_time = gw_review.waiter.local_time_today
        gw_review.waiter.local_time_today = lambda hhmm: (
            datetime.now(timezone.utc) + timedelta(hours=6))
        self.slept = []
        gw_review.time.sleep = lambda s: self.slept.append(s)
        self.ran = []
        gw_review.run = lambda *a, **kw: self.ran.append(True) or 0

    def tearDown(self):
        gw_review.waiter.local_time_today = self._local_time
        for key, value in self._orig.items():
            if key == "run":
                gw_review.run = value
            elif key == "load":
                gw_review.storage.load = value
            elif key == "sleep":
                gw_review.time.sleep = value
            elif key == "require":
                config.require_telegram = value
            else:
                setattr(gw_review.fpl_api, {"bootstrap": "get_bootstrap",
                                            "status": "get_event_status",
                                            "fixtures": "get_fixtures"}[key], value)

    def _sequence(self, answers):
        """Har chaqiruvda navbatdagi javobni qaytaradi."""
        box = list(answers)
        def nxt():
            return box.pop(0) if box else box_last[0]
        box_last = [answers[-1]]
        gw_review.fpl_api.get_event_status = nxt

    def test_two_confirmations_are_required(self):
        ready = _status(points="r", bonus=True)
        self._sequence([ready, ready])
        self.assertEqual(gw_review.watch(), 0)
        self.assertEqual(len(self.ran), 1)
        # birinchi tasdiqdan keyin qisqa tanaffus bo'lishi kerak
        self.assertEqual(self.slept, [config.GW_REVIEW_CONFIRM_WAIT])

    def test_a_stale_answer_resets_the_count(self):
        ready = _status(points="r", bonus=True)
        stale = _status(points="p", bonus=False)
        self._sequence([ready, stale, ready, ready])
        self.assertEqual(gw_review.watch(), 0)
        self.assertEqual(len(self.ran), 1)
        # tanaffus, to'liq kutish, tanaffus
        self.assertEqual(self.slept,
                         [config.GW_REVIEW_CONFIRM_WAIT, config.GW_REVIEW_POLL,
                          config.GW_REVIEW_CONFIRM_WAIT])


if __name__ == "__main__":
    unittest.main()
