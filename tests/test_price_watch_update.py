"""Narx bashorati: post chiqqach xuddi shu xabar yangilanib borishi kerak."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from bot import config, price_watch


def _player(pid, name, cost, percent):
    return {"id": pid, "web_name": name, "team": 1, "now_cost": cost,
            "price_change_percent": str(percent),
            "price_change_projections": [{"offset": 0, "projected_percent": str(percent),
                                          "likelihood": 2}],
            "status": "a"}


def _bootstrap(percent):
    return {"teams": [{"id": 1, "short_name": "ARS", "name": "Arsenal"}],
            "elements": [_player(1, "Saka", 95, percent)]}


class UpdateTest(unittest.TestCase):
    def setUp(self):
        self.sent, self.edited, self.saved = [], [], []
        self._orig = {
            "bootstrap": price_watch.fpl_api.get_bootstrap,
            "load": price_watch.storage.load,
            "save": price_watch.storage.save,
            "send": price_watch.telegram.send_message,
            "edit": price_watch.telegram.edit_message,
            "sleep_until": price_watch.waiter.sleep_until,
            "until": price_watch.waiter.local_time_today,
            "require": config.require_telegram,
        }
        config.require_telegram = lambda: None
        # Yangilanish oynasi soatga bog'liq bo'lmasin: test qaysi vaqtda
        # ishga tushsa ham "oyna hali ochiq" bo'lib tursin.
        price_watch.waiter.local_time_today = lambda *a, **kw: (
            datetime.now(timezone.utc) + timedelta(hours=2))
        price_watch.storage.load = lambda *a, **kw: {}
        price_watch.storage.save = lambda path, data: self.saved.append(data)
        price_watch.telegram.send_message = lambda text, **kw: (
            self.sent.append(text) or {"message_id": 77})
        price_watch.telegram.edit_message = lambda mid, text, **kw: (
            self.edited.append((mid, text)) or {"message_id": mid})

    def tearDown(self):
        price_watch.fpl_api.get_bootstrap = self._orig["bootstrap"]
        price_watch.storage.load = self._orig["load"]
        price_watch.storage.save = self._orig["save"]
        price_watch.telegram.send_message = self._orig["send"]
        price_watch.telegram.edit_message = self._orig["edit"]
        price_watch.waiter.sleep_until = self._orig["sleep_until"]
        price_watch.waiter.local_time_today = self._orig["until"]
        config.require_telegram = self._orig["require"]

    def test_without_update_it_posts_once(self):
        price_watch.fpl_api.get_bootstrap = lambda: _bootstrap(120)
        self.assertEqual(price_watch.run(force=True), 0)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.edited, [])

    def test_update_edits_the_same_message(self):
        """Birinchi aylanishda yuboradi, keyingisida foiz o'zgargani uchun tahrirlaydi."""
        percents = iter([120, 135, 135])
        price_watch.fpl_api.get_bootstrap = lambda: _bootstrap(next(percents, 135))

        rounds = {"n": 0}
        def fake_sleep(target, **kw):
            rounds["n"] += 1
            return rounds["n"] < 2      # ikkinchi chaqiruvda byudjet tugadi deymiz
        price_watch.waiter.sleep_until = fake_sleep

        self.assertEqual(price_watch.run(force=True, update=True), 0)
        self.assertEqual(len(self.sent), 1)          # bitta yangi xabar
        self.assertEqual(len(self.edited), 1)        # va bitta tahrir
        self.assertEqual(self.edited[0][0], 77)      # xuddi shu xabar

    def test_unchanged_text_is_not_edited(self):
        price_watch.fpl_api.get_bootstrap = lambda: _bootstrap(120)
        rounds = {"n": 0}
        def fake_sleep(target, **kw):
            rounds["n"] += 1
            return rounds["n"] < 2
        price_watch.waiter.sleep_until = fake_sleep

        price_watch.run(force=True, update=True)
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(self.edited, [])            # matn o'zgarmagan

    def test_existing_message_is_edited_not_reposted(self):
        """Shu kechada qayta ishga tushirilsa yangi post emas, eskisi yangilanadi."""
        price_watch.storage.load = lambda *a, **kw: {
            "message_id": 77, "last_text": "eski", "night": price_watch.night_key(),
            "posted_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        }
        price_watch.fpl_api.get_bootstrap = lambda: _bootstrap(120)
        self.assertEqual(price_watch.run(), 0)
        self.assertEqual(self.sent, [])
        self.assertEqual(len(self.edited), 1)

    def test_last_nights_message_is_left_alone(self):
        """1-sentyabr holati: kechagi post tahrirlanmasin, yangisi chiqsin."""
        price_watch.storage.load = lambda *a, **kw: {
            "message_id": 3677, "last_text": "kechagi matn", "night": "2026-08-31",
            "seen": [1],
            "posted_at": "2026-08-31T18:00:00+00:00",
            "updated_at": "2026-08-31T22:00:00+00:00",
        }
        price_watch.fpl_api.get_bootstrap = lambda: _bootstrap(120)
        self.assertEqual(price_watch.run(force=True), 0)
        self.assertEqual(len(self.sent), 1)          # yangi post
        self.assertEqual(self.edited, [])            # kechagisiga tegilmadi
        self.assertEqual(self.saved[-1]["message_id"], 77)
        self.assertEqual(self.saved[-1]["night"], price_watch.night_key())
        # yangi kechada hamma futbolchi "yangi" emas — 🆕 faqat post chiqqach
        self.assertNotIn(config.PRICE_WATCH_NEW_MARK, self.sent[0])

    def test_updates_do_not_move_the_post_time(self):
        """`posted_at` post vaqtida qotib qoladi, `updated_at` esa suriladi."""
        price_watch.fpl_api.get_bootstrap = lambda: _bootstrap(120)
        stamp = "2026-09-01T18:00:00+00:00"
        price_watch.storage.load = lambda *a, **kw: {
            "message_id": 77, "last_text": "eski", "night": price_watch.night_key(),
            "posted_at": stamp,
        }
        price_watch.run()
        self.assertEqual(self.saved[-1]["posted_at"], stamp)
        self.assertNotEqual(self.saved[-1]["updated_at"], stamp)


if __name__ == "__main__":
    unittest.main()


class NewMarkTest(unittest.TestCase):
    """Birinchi postdan keyin qo'shilganlar 🆕 bilan ajratilsin."""

    def setUp(self):
        self.sent, self.edited, self.saved = [], [], []
        self._orig = {
            "bootstrap": price_watch.fpl_api.get_bootstrap,
            "load": price_watch.storage.load,
            "save": price_watch.storage.save,
            "send": price_watch.telegram.send_message,
            "edit": price_watch.telegram.edit_message,
            "sleep_until": price_watch.waiter.sleep_until,
            "require": config.require_telegram,
        }
        config.require_telegram = lambda: None
        price_watch.storage.save = lambda path, data: self.saved.append(data)
        price_watch.telegram.send_message = lambda text, **kw: (
            self.sent.append(text) or {"message_id": 77})
        price_watch.telegram.edit_message = lambda mid, text, **kw: (
            self.edited.append(text) or {"message_id": mid})

    def tearDown(self):
        price_watch.fpl_api.get_bootstrap = self._orig["bootstrap"]
        price_watch.storage.load = self._orig["load"]
        price_watch.storage.save = self._orig["save"]
        price_watch.telegram.send_message = self._orig["send"]
        price_watch.telegram.edit_message = self._orig["edit"]
        price_watch.waiter.sleep_until = self._orig["sleep_until"]
        config.require_telegram = self._orig["require"]

    def _two(self, second):
        return {"teams": [{"id": 1, "short_name": "ARS", "name": "Arsenal"}],
                "elements": [_player(1, "Saka", 95, 120)] + (
                    [_player(2, "Rice", 65, 110)] if second else [])}

    def test_first_post_has_no_badge(self):
        price_watch.storage.load = lambda *a, **kw: {}
        price_watch.fpl_api.get_bootstrap = lambda: self._two(False)
        price_watch.run(force=True)
        self.assertNotIn(config.PRICE_WATCH_NEW_MARK, self.sent[0])

    def test_later_arrival_gets_the_badge(self):
        price_watch.storage.load = lambda *a, **kw: {
            "message_id": 77, "last_text": "eski", "seen": [1],
            "night": price_watch.night_key(),
            "posted_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        }
        price_watch.fpl_api.get_bootstrap = lambda: self._two(True)
        price_watch.run()
        text = self.edited[0]
        self.assertIn(f"{config.PRICE_WATCH_NEW_MARK} <b>Rice", text)
        self.assertNotIn(f"{config.PRICE_WATCH_NEW_MARK} <b>Saka", text)

    def test_seen_list_is_saved_with_the_first_post(self):
        price_watch.storage.load = lambda *a, **kw: {}
        price_watch.fpl_api.get_bootstrap = lambda: self._two(True)
        price_watch.run(force=True)
        self.assertEqual(self.saved[-1]["seen"], [1, 2])


class NightKeyTest(unittest.TestCase):
    """Bitta post — bitta kecha. Kecha 12:00 da tugaydi."""

    def _at(self, iso):
        from zoneinfo import ZoneInfo
        local = datetime.fromisoformat(iso).replace(tzinfo=ZoneInfo(config.LOCAL_TZ))
        return price_watch.night_key(local)

    def test_evening_post_belongs_to_that_day(self):
        self.assertEqual(self._at("2026-08-31T23:00"), "2026-08-31")

    def test_after_midnight_update_stays_in_the_same_night(self):
        self.assertEqual(self._at("2026-09-01T03:00"), "2026-08-31")

    def test_morning_still_counts_as_last_night(self):
        # 28-avgust holati: 00:17 dagi post 07:19 da takrorlanmasin
        self.assertEqual(self._at("2026-09-01T07:19"), "2026-08-31")

    def test_the_next_evening_is_a_new_night(self):
        self.assertEqual(self._at("2026-09-01T23:00"), "2026-09-01")

    def test_state_night_falls_back_to_the_post_time(self):
        # eski holat fayllarida `night` yo'q
        self.assertEqual(
            price_watch.state_night({"posted_at": "2026-08-31T18:00:00+00:00"}),
            "2026-08-31")

    def test_state_night_is_none_when_there_is_nothing_to_go_on(self):
        self.assertIsNone(price_watch.state_night({}))
