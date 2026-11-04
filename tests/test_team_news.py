"""Jamoa yangiliklari: nimani xabar qilamiz, nimani jim o'tkazamiz."""
from __future__ import annotations

import unittest
from datetime import timedelta

from bot import config, team_news, waiter
from bot.formatting import team_news_post

TEAMS = {1: {"short_name": "MCI"}, 2: {"short_name": "ARS"}, 3: {"short_name": "NEW"}}


def _player(pid, name, team, owned, status="a", chance=None, news=""):
    return {"id": pid, "web_name": name, "team": team,
            "selected_by_percent": str(owned), "status": status,
            "chance_of_playing_next_round": chance, "news": news}


def _bootstrap(players, deadline=None):
    events = []
    if deadline is not None:
        events = [{"id": 9, "is_next": True,
                   "deadline_time": deadline.isoformat().replace("+00:00", "Z")}]
    return {"elements": players, "events": events,
            "teams": [{"id": i, "short_name": t["short_name"]} for i, t in TEAMS.items()]}


HEALTHY = [_player(1, "Haaland", 1, 54.2), _player(2, "Saka", 2, 31.0),
           _player(3, "Isak", 3, 18.4), _player(4, "Nobody", 1, 0.4)]


class SnapshotTest(unittest.TestCase):
    def test_only_widely_owned_players_are_watched(self):
        snap = team_news.snapshot(_bootstrap(HEALTHY))
        self.assertEqual(sorted(snap), ["1", "2", "3"])    # Nobody — 0.4%, kuzatilmaydi

    def test_the_three_fields_are_remembered(self):
        snap = team_news.snapshot(_bootstrap([_player(1, "Haaland", 1, 54.2,
                                                      "i", 25, "  Knock  - out  ")]))
        self.assertEqual(snap["1"], {"status": "i", "chance": 25, "news": "Knock - out"})


class ChangeTest(unittest.TestCase):
    def setUp(self):
        self.before = team_news.snapshot(_bootstrap(HEALTHY))

    def _after(self, players):
        return team_news.changes(self.before, _bootstrap(players))

    def test_an_injury_is_reported(self):
        rows = self._after([_player(1, "Haaland", 1, 54.2, "i", 25, "Knock")] + HEALTHY[1:])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].name, "Haaland")
        self.assertEqual((rows[0].status, rows[0].chance), ("i", 25))
        self.assertFalse(rows[0].recovered)

    def test_a_recovery_is_reported(self):
        self.before["1"] = {"status": "i", "chance": 25, "news": "Knock"}
        rows = self._after(HEALTHY)
        self.assertTrue(rows[0].recovered)
        self.assertEqual(rows[0].was_status, "i")

    def test_nothing_changed_means_no_post(self):
        self.assertEqual(self._after(HEALTHY), [])

    def test_a_reworded_note_for_a_fit_player_is_ignored(self):
        """Tayyor futbolchining izohi o'zgargani — shovqin, chiqarmaymiz."""
        rows = self._after([_player(1, "Haaland", 1, 54.2, "a", None, "Joined training")]
                           + HEALTHY[1:])
        self.assertEqual(rows, [])

    def test_an_updated_return_date_is_reported(self):
        """Jarohat izohi yangilangani — "qachon qaytadi" ma'lumoti, kerak."""
        self.before["1"] = {"status": "i", "chance": 0, "news": "Hamstring"}
        rows = self._after([_player(1, "Haaland", 1, 54.2, "i", 0,
                                    "Hamstring - expected back 14 Nov")] + HEALTHY[1:])
        self.assertEqual(len(rows), 1)
        self.assertIn("14 Nov", rows[0].news)

    def test_a_new_player_is_only_recorded(self):
        """Ro'yxatga endi tushgan futbolchi uchun post chiqmaydi."""
        rows = team_news.changes({}, _bootstrap(HEALTHY))
        self.assertEqual(rows, [])

    def test_the_most_owned_come_first(self):
        rows = self._after([
            _player(1, "Haaland", 1, 54.2, "i", 25, "Knock"),
            _player(2, "Saka", 2, 31.0, "d", 75, "Minor knock"),
            _player(3, "Isak", 3, 18.4, "s", 0, "Suspended"),
            HEALTHY[3],
        ])
        self.assertEqual([r.name for r in rows], ["Haaland", "Saka", "Isak"])

    def test_the_list_is_capped(self):
        orig = config.NEWS_MAX_ROWS
        config.NEWS_MAX_ROWS = 2
        try:
            rows = self._after([
                _player(1, "Haaland", 1, 54.2, "i", 25, "Knock"),
                _player(2, "Saka", 2, 31.0, "d", 75, "Knock"),
                _player(3, "Isak", 3, 18.4, "s", 0, "Suspended"),
                HEALTHY[3],
            ])
            self.assertEqual(len(rows), 2)
        finally:
            config.NEWS_MAX_ROWS = orig


class RushTest(unittest.TestCase):
    def test_a_near_deadline_turns_on_rush_mode(self):
        soon = waiter.now_utc() + timedelta(minutes=120)
        self.assertTrue(team_news.rush_mode(_bootstrap(HEALTHY, deadline=soon)))

    def test_a_far_deadline_does_not(self):
        later = waiter.now_utc() + timedelta(days=3)
        self.assertFalse(team_news.rush_mode(_bootstrap(HEALTHY, deadline=later)))

    def test_a_passed_deadline_does_not(self):
        past = waiter.now_utc() - timedelta(minutes=30)
        self.assertFalse(team_news.rush_mode(_bootstrap(HEALTHY, deadline=past)))

    def test_no_next_gameweek_does_not(self):
        self.assertFalse(team_news.rush_mode(_bootstrap(HEALTHY)))


class PostTest(unittest.TestCase):
    def _rows(self):
        before = team_news.snapshot(_bootstrap(HEALTHY))
        before["3"] = {"status": "i", "chance": 0, "news": "Hamstring"}
        return team_news.changes(before, _bootstrap([
            _player(1, "Haaland", 1, 54.2, "i", 25, "Knock - to be assessed"),
            _player(2, "Saka", 2, 31.0, "d", 75, "Minor knock"),
            HEALTHY[2], HEALTHY[3],
        ]))

    def test_the_post_shows_status_chance_and_ownership(self):
        text = team_news_post(self._rows(), TEAMS)
        self.assertIn("🔴 <b>Haaland</b> (MCI) · 54.2% — jarohat, o'ynash ehtimoli 25%", text)
        self.assertIn("🟡 <b>Saka</b> (ARS) · 31.0% — shubhali, o'ynash ehtimoli 75%", text)
        self.assertIn("<i>Zarba olgan, holati baholanmoqda</i>", text)
        self.assertTrue(text.rstrip().endswith(config.CHANNEL_TAG))

    def test_a_recovery_names_the_previous_state(self):
        text = team_news_post(self._rows(), TEAMS)
        self.assertIn("🟢 <b>Isak</b> (NEW) · 18.4% — tayyor (ilgari: jarohat)", text)

    def test_the_deadline_line_appears_only_when_close(self):
        rows = self._rows()
        self.assertIn("⏳ Deadline'gacha 2 soat 10 daqiqa",
                      team_news_post(rows, TEAMS, deadline_in=130))
        self.assertIn("⏳ Deadline'gacha 45 daqiqa",
                      team_news_post(rows, TEAMS, deadline_in=45))
        self.assertNotIn("Deadline", team_news_post(rows, TEAMS))

    def test_the_post_fits_telegram(self):
        self.assertLess(len(team_news_post(self._rows(), TEAMS)), 4096)


if __name__ == "__main__":
    unittest.main()
