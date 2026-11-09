"""Poyga charti: o'rinlar, tarix, vaqt va rasm."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from bot import charts, config, race, storage


def _manager(entry_id, name, place, total, last, totals=None):
    return race.Manager(entry_id=entry_id, name=name, team=f"Team {entry_id}",
                        place=place, total=total, last=last, totals=totals or {})


def _six():
    """Oltita menejer, har birining o'n turlik tarixi bilan."""
    plan = [
        ("Sardor Toshmatov", [60, 130, 200, 280, 350, 420, 490, 550, 610, 672]),
        ("Ilkhomjon Yusupov", [70, 140, 210, 275, 345, 415, 480, 545, 607, 665]),
        ("Bekzod Rahimov", [55, 120, 195, 265, 340, 405, 470, 530, 590, 651]),
        ("Jasur Nazarov", [65, 125, 190, 260, 330, 400, 465, 525, 595, 644]),
        ("Aziz Mirzayev", [50, 115, 185, 255, 325, 390, 455, 515, 575, 630]),
        ("Doston Karimov", [45, 110, 180, 250, 315, 380, 445, 505, 565, 618]),
    ]
    out = []
    for index, (name, totals) in enumerate(plan, start=1):
        out.append(_manager(100 + index, name, index, totals[-1], 40 + index,
                            {gw: value for gw, value in enumerate(totals, start=1)}))
    return out


class NameTest(unittest.TestCase):
    def test_surname_is_shortened(self):
        self.assertEqual(race.short_name("Ilkhomjon Yusupov"), "Ilkhomjon Y.")

    def test_single_word_name_survives(self):
        self.assertEqual(race.short_name("Yaypan"), "Yaypan")

    def test_empty_name_does_not_crash(self):
        self.assertEqual(race.short_name(""), "—")

    def test_very_long_name_is_cut(self):
        got = race.short_name("Abdurahmonbekmurod Toshpo'latov")
        self.assertLessEqual(len(got), 17)


class ClubTest(unittest.TestCase):
    """Chart chizig'ida jamoa nomi, jadvalda menejerning ismi."""

    def test_long_team_name_is_cut(self):
        self.assertEqual(race.clip("Olmaliq Wanderers XI"), "Olmaliq Wanderers…")

    def test_short_name_is_left_alone(self):
        self.assertEqual(race.clip("Navoiy City"), "Navoiy City")

    def test_emoji_is_removed_from_the_team_name(self):
        m = _manager(1, "Ilkhomjon Yusupov", 1, 0, 0)
        m.team = "🔥 Qoraqalpoq FC"
        self.assertEqual(m.club, "Qoraqalpoq FC")

    def test_a_nameless_team_falls_back_to_the_person(self):
        m = _manager(1, "Ilkhomjon Yusupov", 1, 0, 0)
        m.team = ""
        self.assertEqual(m.club, "Ilkhomjon Y.")

    def test_the_line_label_is_the_team(self):
        managers = _six()
        for index, m in enumerate(managers):
            m.team = f"Jamoa {index}"
        runner = charts.Runner(name=managers[0].short, label=managers[0].club,
                               ranks=[1], cells=())
        self.assertEqual(runner.name, "Sardor T.")
        self.assertEqual(runner.label, "Jamoa 0")


class HistoryTest(unittest.TestCase):
    def test_history_maps_event_to_total(self):
        payload = {"current": [{"event": 1, "total_points": 60, "overall_rank": 900000},
                               {"event": 2, "total_points": 130, "overall_rank": 12345}]}
        with patch.object(race.fpl_api, "_get", return_value=payload):
            totals, overall = race.history(7)
        self.assertEqual(totals, {1: 60, 2: 130})
        self.assertEqual(overall, 12345)      # oxirgi turdagi dunyo o'rni

    def test_only_shared_rounds_are_charted(self):
        """Keyin qo'shilgan jamoada boshlang'ich turlar yo'q."""
        managers = _six()
        managers[-1].totals = {gw: v for gw, v in managers[-1].totals.items() if gw >= 4}
        self.assertEqual(race.common_events(managers), [4, 5, 6, 7, 8, 9, 10])

    def test_no_history_means_no_events(self):
        self.assertEqual(race.common_events([_manager(1, "A", 1, 0, 0)]), [])

    def test_a_failed_request_leaves_the_others_alone(self):
        managers = _six()[:2]
        for m in managers:
            m.totals = {}

        def one(entry_id):
            if entry_id == managers[0].entry_id:
                raise RuntimeError("CDN jim")
            return {1: 10, 2: 20}, 500

        with patch.object(race, "history", side_effect=one):
            race.load_histories(managers)
        self.assertEqual(managers[0].totals, {})
        self.assertEqual(managers[1].totals, {1: 10, 2: 20})


class BehindTest(unittest.TestCase):
    """Jadvaldagi "O'zbekistondan" va "Overalldan" ustunlari."""

    def test_national_league_falls_back_to_the_second_league(self):
        with patch.object(config, "RACE_NATIONAL_LEAGUE", 0), \
             patch.object(config, "STATS_LEAGUES", [(137243, "Bizniki"), (251, "O'zbekiston")]):
            self.assertEqual(race.national_league(), 251)

    def test_an_explicit_setting_wins(self):
        with patch.object(config, "RACE_NATIONAL_LEAGUE", 999), \
             patch.object(config, "STATS_LEAGUES", [(1, "a"), (2, "b")]):
            self.assertEqual(race.national_league(), 999)

    def test_no_second_league_means_no_column(self):
        with patch.object(config, "RACE_NATIONAL_LEAGUE", 0), \
             patch.object(config, "STATS_LEAGUES", [(137243, "Bizniki")]):
            self.assertEqual(race.national_league(), 0)

    def test_leader_total_is_the_first_row(self):
        payload = {"standings": {"results": [{"entry": 1, "total": 721},
                                             {"entry": 2, "total": 700}]}}
        with patch.object(race.fpl_api, "_get", return_value=payload):
            self.assertEqual(race.leader_total(314), 721)

    def test_an_empty_league_gives_nothing(self):
        with patch.object(race.fpl_api, "_get", return_value={"standings": {"results": []}}):
            self.assertEqual(race.leader_total(314), 0)

    def test_no_league_means_no_request(self):
        with patch.object(race.fpl_api, "_get") as get:
            self.assertEqual(race.leader_total(0), 0)
        get.assert_not_called()

    def test_gap_is_shown_as_a_negative(self):
        self.assertEqual(race.behind(721, 672), "-49")

    def test_the_leader_gets_a_dash(self):
        self.assertEqual(race.behind(672, 672), "—")
        self.assertEqual(race.behind(600, 672), "—")

    def test_a_missing_leader_gets_a_dash(self):
        """Yetakchining ochkosi olinmasa ham post chiqaveradi."""
        self.assertEqual(race.behind(0, 672), "—")

    def test_big_ranks_are_readable(self):
        self.assertEqual(race.thousands(1204877), "1 204 877")
        self.assertEqual(race.thousands(0), "—")

    def test_the_table_has_every_column(self):
        """Jami, oxirgi tur, dunyo o'rni va uchta yetakchidan farq."""
        managers = _six()
        for index, m in enumerate(managers):
            m.overall = 1000 * (index + 1)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(charts, "race_chart") as chart:
                race.build(managers, race.common_events(managers), "L",
                           Path(tmp) / "x.png", national_top=700, overall_top=800)
        runners = chart.call_args.kwargs["runners"]
        self.assertEqual(runners[0].cells,
                         ("672", "41", "1 000", "—", "-28", "-128"))
        self.assertEqual(runners[1].cells[3], "-7")   # o'z ligamiz yetakchisidan

    def test_the_title_and_the_join_code(self):
        managers = _six()
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(config, "LEAGUE_CODE", "hv7h9c"), \
             patch.object(charts, "race_chart") as chart:
            race.build(managers, race.common_events(managers), "L", Path(tmp) / "x.png")
        self.assertEqual(chart.call_args.kwargs["title"], "FPLUzbekistan Poygasi")
        self.assertEqual(chart.call_args.kwargs["code"], "hv7h9c")
        self.assertIn("ushbu menejer", chart.call_args.kwargs["subtitle"])

    def test_no_code_means_no_block(self):
        managers = _six()
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(config, "LEAGUE_CODE", ""), \
             patch.object(charts, "race_chart") as chart:
            race.build(managers, race.common_events(managers), "L", Path(tmp) / "x.png")
        self.assertEqual(chart.call_args.kwargs["code"], "")


class RanksTest(unittest.TestCase):
    def test_rank_is_within_the_shown_group(self):
        managers = _six()
        table = race.ranks(managers, [1, 10])
        # GW1 da Ilkhomjon (70) oldinda, Sardor (60) esa uchinchi;
        # GW10 ga kelib Sardor birinchi o'ringa chiqadi
        self.assertEqual(table[managers[1].entry_id][0], 1)
        self.assertEqual(table[managers[0].entry_id][0], 3)
        self.assertEqual(table[managers[0].entry_id][-1], 1)

    def test_every_place_is_used_once(self):
        managers = _six()
        table = race.ranks(managers, [5])
        places = sorted(v[0] for v in table.values())
        self.assertEqual(places, [1, 2, 3, 4, 5, 6])

    def test_a_tie_keeps_todays_order(self):
        """Teng ochkoda chiziq sakrab ketmasligi kerak."""
        managers = [_manager(1, "A B", 1, 100, 0, {1: 50}),
                    _manager(2, "C D", 2, 100, 0, {1: 50})]
        table = race.ranks(managers, [1])
        self.assertEqual(table[1][0], 1)
        self.assertEqual(table[2][0], 2)

    def test_a_missing_round_counts_as_zero(self):
        managers = [_manager(1, "A B", 1, 100, 0, {1: 50}),
                    _manager(2, "C D", 2, 90, 0, {})]
        table = race.ranks(managers, [1])
        self.assertEqual(table[2][0], 2)


class TimingTest(unittest.TestCase):
    """Ochkolar yakunlangandan 48 soat o'tgach, birinchi 20:00."""

    def moment(self, last_match_day: str):
        status = {"status": [{"date": last_match_day}]}
        got = race.post_moment(status)
        return got.astimezone(ZoneInfo(config.LOCAL_TZ))

    def test_two_days_after_a_sunday_round(self):
        # oxirgi o'yin yakshanba 8-noyabr -> ochkolar dushanba 14:00 (Toshkent)
        # -> +48 soat = chorshanba 14:00 -> o'sha kuni 20:00
        got = self.moment("2026-11-08")
        self.assertEqual(got.strftime("%Y-%m-%d %H:%M"), "2026-11-11 20:00")

    def test_a_monday_round_shifts_by_a_day(self):
        got = self.moment("2026-11-09")
        self.assertEqual(got.strftime("%Y-%m-%d %H:%M"), "2026-11-12 20:00")

    def test_no_date_means_no_moment(self):
        self.assertIsNone(race.post_moment({"status": []}))


class RenderTest(unittest.TestCase):
    def test_chart_file_is_written(self):
        managers = _six()
        events = race.common_events(managers)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "race.png"
            race.build(managers, events, "FPLUzbekistan", out)
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 10_000)

    def test_too_many_runners_is_refused(self):
        runner = charts.Runner(name="A", ranks=[1], cells=("1", "1", "—"))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                charts.race_chart(Path(tmp) / "x.png", title="T", subtitle="",
                                  gws=[1], runners=[runner] * 7)

    def test_empty_input_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                charts.race_chart(Path(tmp) / "x.png", title="T", subtitle="",
                                  gws=[], runners=[])


class PlainTextTest(unittest.TestCase):
    """Emoji matplotlib shriftida yo'q — rasmda bo'sh kvadrat bo'lib chiqadi."""

    def test_emoji_is_stripped(self):
        self.assertEqual(charts.plain("🏆 FPLUzbekistan"), "FPLUzbekistan")
        self.assertEqual(charts.plain("🇺🇿 Uzbekistan"), "Uzbekistan")

    def test_ordinary_punctuation_survives(self):
        self.assertEqual(charts.plain("GW1—GW10 · 6 menejer"), "GW1—GW10 · 6 menejer")

    def test_empty_input(self):
        self.assertEqual(charts.plain(""), "")
        self.assertEqual(charts.plain(None), "")


class CaptionTest(unittest.TestCase):
    def test_caption_lists_everyone_and_the_gap(self):
        managers = _six()
        text = race.caption(managers, [1, 10])
        self.assertIn("Sardor T.", text)
        self.assertIn("(7 orqada)", text)
        self.assertIn("Team 101", text)      # jamoa nomi ham ko'rinadi
        self.assertIn(config.RACE_HASHTAG, text)
        self.assertLessEqual(len(text), 1024)
        self.assertEqual(text.splitlines()[-3:],
                         [config.tags(config.RACE_HASHTAG), "", config.CHANNEL_TAG])

    def test_join_code_appears_only_when_set(self):
        managers = _six()
        with patch.object(config, "LEAGUE_CODE", "hv7h9c"):
            self.assertIn("hv7h9c", race.caption(managers, [1, 10]))
        with patch.object(config, "LEAGUE_CODE", ""):
            self.assertNotIn("qo'shilish kodi", race.caption(managers, [1, 10]))


class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name, value in (("RACE_STATE_FILE", Path(self.tmp.name) / "race.json"),
                            ("CHART_DIR", Path(self.tmp.name) / "charts"),
                            ("DRY_RUN", True)):
            p = patch.object(config, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.status = {"status": [{"date": "2026-11-08"}]}
        self.moment = race.post_moment(self.status)

    def _run(self, now=None, **kwargs):
        managers = _six()
        with patch.object(race.fpl_api, "get_event_status", return_value=self.status), \
             patch.object(race.fpl_api, "status_verdict", return_value=(10, True, "tayyor")), \
             patch.object(race, "league_top", return_value=("FPLUzbekistan", managers)), \
             patch.object(race, "load_histories"), \
             patch.object(race, "leader_total", side_effect=[690, 760]), \
             patch.object(race.waiter, "now_utc", return_value=now or self.moment), \
             patch.object(race.waiter, "sleep_until", return_value=True), \
             patch.object(race.telegram, "send_photo",
                          return_value={"message_id": 9}) as photo, \
             patch.object(race.telegram, "notify_admin") as alert:
            code = race.run(**kwargs)
        return code, photo, alert

    def test_posts_once_per_round(self):
        _, photo, _ = self._run()
        photo.assert_called_once()
        _, photo, _ = self._run()
        photo.assert_not_called()

    def test_quiet_while_the_round_is_still_fresh(self):
        """Tur endigina yopilgan — post ikki kundan keyin, ogohlantirish yo'q."""
        _, photo, alert = self._run(now=self.moment - timedelta(days=2))
        photo.assert_not_called()
        alert.assert_not_called()

    def test_alerts_when_the_cron_is_hours_early_on_the_day(self):
        _, photo, alert = self._run(now=self.moment - timedelta(hours=9))
        photo.assert_not_called()
        alert.assert_called_once()

    def test_an_unfinished_round_posts_nothing(self):
        with patch.object(race.fpl_api, "get_event_status", return_value=self.status), \
             patch.object(race.fpl_api, "status_verdict",
                          return_value=(10, False, "kutilmoqda")), \
             patch.object(race.telegram, "send_photo") as photo:
            race.run()
        photo.assert_not_called()


if __name__ == "__main__":
    unittest.main()
