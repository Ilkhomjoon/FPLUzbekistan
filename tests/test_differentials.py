"""Differentiallar posti: tanlash mantiqi va matn ko'rinishi."""
from __future__ import annotations

import unittest
from collections import Counter

from bot import config, differentials
from bot.formatting import differentials_poll, differentials_post

TEAMS = {
    1: {"short_name": "ARS"},
    2: {"short_name": "MCI"},
    3: {"short_name": "AVL"},
    4: {"short_name": "LEE"},
}


def _element(pid, name, team, cost, owned, points, total=0, tin=0, status="a", form=None):
    return {"id": pid, "web_name": name, "team": team, "now_cost": cost,
            "selected_by_percent": str(owned), "event_points": points,
            "total_points": total, "transfers_in_event": tin, "status": status,
            "form": str(points if form is None else form)}


# element_id -> (oxirgi 5 turdagi jami ochko, nechta turda 5+)
RECENT = {
    1: (38, 4),    # Ødegaard — barqaror
    2: (30, 3),    # White
    3: (40, 5),    # Haaland (egaligi baland — differential emas)
    4: (28, 3),    # Rogers
    5: (5, 0),     # Nobody
    7: (10, 1),    # Passenger — kuchlilarda bor, lekin ochko yo'q
    8: (26, 1),    # Onehit — bitta katta tur, qolgani jim
}

BOOTSTRAP = {"elements": [
    _element(1, "Ødegaard", 1, 65, 9.8, 11, 11, 110701),
    _element(2, "White", 1, 55, 5.2, 11, 11, 45936),
    _element(3, "Haaland", 2, 150, 61.2, 2, 2, 900),
    _element(4, "Rogers", 3, 55, 3.1, 7, 7, 64220),
    _element(5, "Nobody", 4, 45, 0.4, 1, 1, 12),
    _element(6, "Injured", 4, 60, 2.0, 12, 12, 5, status="u"),
    # kuchlilarda bor, lekin ochko keltirmayapti — 👑 bo'limiga tushmasligi kerak
    _element(7, "Passenger", 4, 70, 4.0, 1, 20, 300, form=1.2),
    # ochkosi yaxshi, lekin forma past — bitta omadli tur
    _element(8, "Onehit", 2, 50, 2.5, 8, 9, 800, form=2.0),
]}


class SelectionTest(unittest.TestCase):
    def setUp(self):
        self.players = differentials.pool(BOOTSTRAP)

    def test_unavailable_players_are_dropped(self):
        names = [d.name for d in self.players]
        self.assertNotIn("Injured", names)

    def test_low_owned_picks_high_scorers_under_the_threshold(self):
        rows = differentials.low_owned(self.players)
        names = [d.name for d in rows]
        # ikkalasi ham 11 ochko — egaligi kamrog'i (haqiqiy differential) oldinda
        self.assertEqual(names[:2], ["White", "Ødegaard"])
        self.assertIn("Rogers", names)                        # 7 ochko — chegarada
        self.assertNotIn("Haaland", names)                    # egaligi 61% — differential emas
        self.assertNotIn("Nobody", names)                     # 1 ochko

    def test_rising_is_sorted_by_transfers(self):
        rows = differentials.rising(self.players)
        self.assertEqual(rows[0].name, "Ødegaard")
        self.assertEqual(rows[1].name, "Rogers")
        self.assertTrue(all(d.owned < config.DIFF_MAX_OWN for d in rows))

    def test_percent_is_parsed_from_string(self):
        odegaard = next(d for d in self.players if d.name == "Ødegaard")
        self.assertAlmostEqual(odegaard.owned, 9.8)


class EliteTest(unittest.TestCase):
    def setUp(self):
        self.players = differentials.pool(BOOTSTRAP)
        differentials.apply_recent_form(self.players, RECENT)
        self._orig = (differentials.top_entries, differentials.scan_picks,
                      config.DIFF_ELITE_TIERS, config.DIFF_ELITE_MIN_ROWS)
        differentials.top_entries = lambda size: list(range(1, size + 1))
        config.DIFF_ELITE_TIERS = "10"
        config.DIFF_ELITE_MIN_ROWS = 1

    def tearDown(self):
        (differentials.top_entries, differentials.scan_picks,
         config.DIFF_ELITE_TIERS, config.DIFF_ELITE_MIN_ROWS) = self._orig

    def _scan(self, mapping: dict, scanned: int):
        differentials.scan_picks = lambda entries, gw, workers=None: (
            Counter({k: v for k, v in mapping.items()}), scanned)

    def test_gap_between_elite_and_global_ownership(self):
        # 10 menejerdan 4 tasida Ødegaard, 1 tasida Haaland
        self._scan({1: 4, 3: 1}, 10)
        rows, size = differentials.elite_differentials(self.players, gw=1)
        self.assertEqual([d.name for d in rows], ["Ødegaard"])
        self.assertAlmostEqual(rows[0].elite, 40.0)
        self.assertEqual(size, 10)

    def test_below_threshold_is_ignored(self):
        self._scan({1: 1}, 10)
        rows, _ = differentials.elite_differentials(self.players, gw=1)
        self.assertEqual(rows, [])

    def test_no_managers_scanned_returns_empty(self):
        self._scan({}, 0)
        self.assertEqual(differentials.elite_differentials(self.players, gw=1), ([], 0))

    def test_a_player_without_points_is_dropped(self):
        """Foydalanuvchining shikoyati: kuchlilarda bor, lekin ochko keltirmagan."""
        self._scan({7: 5}, 10)                    # Passenger — 5 turda 10 ochko
        rows, _ = differentials.elite_differentials(self.players, gw=1)
        self.assertEqual(rows, [])

    def test_a_one_off_haul_is_dropped(self):
        """26 ochko, lekin hammasi bitta turdan — barqaror emas."""
        self._scan({8: 5}, 10)                    # Onehit — 1 ta yaxshi tur
        rows, _ = differentials.elite_differentials(self.players, gw=1)
        self.assertEqual(rows, [])

    def test_the_list_widens_when_the_first_tier_is_thin(self):
        """Top-100 dan 2 tadan kam chiqsa — top-1000 ga o'tiladi."""
        config.DIFF_ELITE_TIERS = "10,20"
        config.DIFF_ELITE_MIN_ROWS = 2
        calls = []

        def fake_scan(entries, gw, workers=None):
            calls.append(list(entries))
            # birinchi bosqichda faqat Ødegaard, keyingisida White ham qo'shiladi
            return (Counter({1: 4}) if len(calls) == 1 else Counter({1: 4, 2: 4})), 10
        differentials.scan_picks = fake_scan

        rows, size = differentials.elite_differentials(self.players, gw=1)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], list(range(1, 11)))     # 1-10
        self.assertEqual(calls[1], list(range(11, 21)))    # faqat qolgani qayta o'qildi
        self.assertEqual(sorted(d.name for d in rows), ["White", "Ødegaard"])
        self.assertEqual(size, 20)

    def test_the_first_tier_is_enough_when_it_is_full(self):
        config.DIFF_ELITE_TIERS = "10,20"
        config.DIFF_ELITE_MIN_ROWS = 2
        self._scan({1: 4, 2: 4}, 10)
        rows, size = differentials.elite_differentials(self.players, gw=1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(size, 10)                 # kengaytirishga hojat qolmadi

    def test_rows_are_sorted_by_points(self):
        config.DIFF_ELITE_MIN_ROWS = 1
        self._scan({1: 4, 4: 4}, 10)               # Ødegaard 38, Rogers 28
        rows, _ = differentials.elite_differentials(self.players, gw=1)
        self.assertEqual([d.name for d in rows], ["Ødegaard", "Rogers"])


class FixturesTest(unittest.TestCase):
    FIXTURES = [
        {"event": 1, "team_h": 1, "team_a": 4, "team_h_difficulty": 2, "team_a_difficulty": 4},
        {"event": 2, "team_h": 1, "team_a": 2, "team_h_difficulty": 5, "team_a_difficulty": 2},
        {"event": 3, "team_h": 3, "team_a": 1, "team_h_difficulty": 3, "team_a_difficulty": 3},
        {"event": 4, "team_h": 1, "team_a": 4, "team_h_difficulty": 2, "team_a_difficulty": 4},
    ]

    def test_only_future_fixtures_in_order(self):
        text = differentials.fixtures_for(1, after_event=1, fixtures=self.FIXTURES,
                                          teams=TEAMS, count=3)
        self.assertEqual(text, "MCI (u) · AVL (m) · LEE (u) — 🔴🟡🟢")

    def test_no_fixtures_left(self):
        text = differentials.fixtures_for(1, after_event=9, fixtures=self.FIXTURES,
                                          teams=TEAMS, count=3)
        self.assertEqual(text, "—")

    def test_difficulty_colours(self):
        self.assertEqual(differentials.difficulty_emoji(1), "🟢")
        self.assertEqual(differentials.difficulty_emoji(3), "🟡")
        self.assertEqual(differentials.difficulty_emoji(5), "🔴")


class PostTest(unittest.TestCase):
    def _picks(self):
        players = differentials.pool(BOOTSTRAP)
        differentials.apply_recent_form(players, RECENT)
        by_name = {d.name: d for d in players}
        picks = differentials.Picks()
        picks.window = [1, 2, 3, 4, 5]
        picks.low_owned = differentials.low_owned(players)
        elite = by_name["Ødegaard"]
        elite.elite = 34.0
        picks.top100 = [elite]
        picks.rising = differentials.rising(players)
        cal = by_name["White"]
        cal.fixtures_text = "LEE (u) · MCI (m) — 🟢🔴"
        picks.calendar = [cal]
        local = by_name["Ødegaard"]
        local.local_count, local.local = 41, 7.7
        picks.local = [local]
        picks.local_label = "🏆 FPLUzbekistan"
        picks.local_scanned = 529
        return picks

    def test_every_section_appears(self):
        text = differentials_post(gw=1, next_gw=2, picks=self._picks(), teams=TEAMS)
        # sarlavha matnlari o'zgarishi mumkin — emoji bo'yicha tekshiramiz
        for marker in ("GW2 — differentiallar", "🔥 Egalik foizi kam", "👑 Top-100",
                       "📈 Kech qolmang", "📅 Keyingi", "🇺🇿 🏆 FPLUzbekistan"):
            self.assertIn(marker, text)
        self.assertIn("<b>Ødegaard</b> (ARS) £6.5M — 9.8%", text)
        self.assertIn("top-100: <b>34%</b>", text)
        self.assertIn("<b>38</b> ochko · 4 turda", text)   # 5 turlik natija
        self.assertIn("GW1-GW5", text)
        self.assertIn("41 ta jamoada", text)
        self.assertTrue(text.rstrip().endswith(config.CHANNEL_TAG))
        self.assertLess(len(text), 4096)

    def test_empty_sections_are_skipped(self):
        picks = differentials.Picks()
        picks.low_owned = differentials.low_owned(differentials.pool(BOOTSTRAP))
        text = differentials_post(gw=1, next_gw=2, picks=picks, teams=TEAMS)
        self.assertNotIn("👑", text)
        self.assertNotIn("📈", text)
        self.assertIn("🔥", text)

    def test_poll_has_players_plus_an_opt_out(self):
        question, options = differentials_poll(2, self._picks(), TEAMS)
        self.assertIn("GW2 ga kim", question)
        self.assertEqual(len(options), config.DIFF_POLL_OPTIONS + 1)
        self.assertIn("Hech kimni", options[-1])
        self.assertTrue(all(len(o) <= 100 for o in options))

    def test_poll_starts_with_the_elite_differentials(self):
        """So'rovnoma 👑 bo'limidan boshlanadi — o'tgan tur ochkolaridan emas."""
        _, options = differentials_poll(2, self._picks(), TEAMS)
        self.assertEqual(options[0], "Ødegaard (ARS) £6.5M")

    def test_poll_falls_back_when_there_are_no_elite_rows(self):
        picks = self._picks()
        picks.top100 = []
        _, options = differentials_poll(2, picks, TEAMS)
        self.assertEqual(options[0], "White (ARS) £5.5M")
        self.assertEqual(len(options), config.DIFF_POLL_OPTIONS + 1)

    def test_poll_does_not_repeat_a_player(self):
        _, options = differentials_poll(2, self._picks(), TEAMS)
        self.assertEqual(len(options), len(set(options)))

    def test_poll_options_are_plain_text(self):
        """So'rovnomada HTML ishlamaydi — <b> teglari tushib qolmasligi kerak."""
        _, options = differentials_poll(2, self._picks(), TEAMS)
        self.assertFalse(any("<" in o for o in options))

    def test_every_player_name_is_bold(self):
        text = differentials_post(gw=1, next_gw=2, picks=self._picks(), teams=TEAMS)
        for name in ("Ødegaard", "White", "Rogers"):
            self.assertIn(f"<b>{name}</b>", text)


if __name__ == "__main__":
    unittest.main()


class MultiPollTest(unittest.TestCase):
    """Bir turda bir nechta transfer qilinadi — so'rovnoma ham ko'p javobli."""

    def setUp(self):
        from bot import telegram
        self.telegram = telegram
        self.calls = []
        self._orig = (telegram._call, config.DIFF_POLL_MULTI, config.DRY_RUN)
        telegram._call = lambda method, **payload: (
            self.calls.append((method, payload)) or {"message_id": 9})
        config.DRY_RUN = False

    def tearDown(self):
        self.telegram._call, config.DIFF_POLL_MULTI, config.DRY_RUN = self._orig

    def test_multiple_answers_are_allowed(self):
        self.telegram.send_poll("Kim?", ["A", "B"], multiple=True)
        self.assertTrue(self.calls[0][1]["allows_multiple_answers"])

    def test_single_answer_is_still_possible(self):
        self.telegram.send_poll("Kim?", ["A", "B"])
        self.assertFalse(self.calls[0][1]["allows_multiple_answers"])

    def test_the_question_says_several_can_be_picked(self):
        config.DIFF_POLL_MULTI = True
        question, _ = differentials_poll(5, differentials.Picks(), TEAMS)
        self.assertEqual(question, "GW5 ga kim(lar)ni olasiz?")

    def test_the_hint_disappears_when_the_setting_is_off(self):
        config.DIFF_POLL_MULTI = False
        question, _ = differentials_poll(5, differentials.Picks(), TEAMS)
        self.assertEqual(question, "GW5 ga kimni olasiz?")


class RecentFormTest(unittest.TestCase):
    """👑 bo'limi bitta turga emas, oxirgi bir necha turga qaraydi."""

    def setUp(self):
        self._orig = (differentials.fpl_api.get_live, config.DIFF_RECENT_GWS,
                      config.DIFF_RECENT_HAUL)
        config.DIFF_RECENT_GWS = 5
        config.DIFF_RECENT_HAUL = 5

    def tearDown(self):
        (differentials.fpl_api.get_live, config.DIFF_RECENT_GWS,
         config.DIFF_RECENT_HAUL) = self._orig

    def test_the_window_is_the_last_five_gameweeks(self):
        self.assertEqual(differentials.recent_window(7), [3, 4, 5, 6, 7])

    def test_early_season_uses_what_exists(self):
        self.assertEqual(differentials.recent_window(3), [1, 2, 3])

    def _live(self, points_by_gw):
        def fake(event):
            return {"elements": [{"id": pid, "stats": {"total_points": pts}}
                                 for pid, pts in points_by_gw[event].items()]}
        differentials.fpl_api.get_live = fake

    def test_points_are_summed_and_good_weeks_counted(self):
        self._live({1: {10: 9, 11: 2}, 2: {10: 1, 11: 2}, 3: {10: 7, 11: 2}})
        form = differentials.recent_form([1, 2, 3])
        self.assertEqual(form[10], (17, 2))     # 9 + 1 + 7, ikkita turda 5+
        self.assertEqual(form[11], (6, 0))      # jami 6, bitta ham yaxshi tur yo'q

    def test_a_missing_gameweek_does_not_break_the_rest(self):
        def fake(event):
            if event == 2:
                raise RuntimeError("API yiqildi")
            return {"elements": [{"id": 10, "stats": {"total_points": 6}}]}
        differentials.fpl_api.get_live = fake
        form = differentials.recent_form([1, 2, 3])
        self.assertEqual(form[10], (12, 2))

    def test_players_without_data_get_zeroes(self):
        players = differentials.pool(BOOTSTRAP)
        differentials.apply_recent_form(players, {1: (30, 3)})
        by_id = {d.element_id: d for d in players}
        self.assertEqual((by_id[1].recent_points, by_id[1].good_weeks), (30, 3))
        self.assertEqual((by_id[2].recent_points, by_id[2].good_weeks), (0, 0))
