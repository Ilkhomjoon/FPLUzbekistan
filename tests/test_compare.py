"""Solishtirish charti: juftlik tanlash, shkala, vaqt va rasm."""
from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from bot import charts, compare, config

TEAMS = {1: {"short_name": "ARS"}, 2: {"short_name": "BOU"}, 3: {"short_name": "NFO"}}


def _element(pid, name, position, transfers, minutes=1800, team=1, **extra):
    base = {
        "id": pid, "web_name": name, "team": team, "element_type": position,
        "now_cost": 70, "selected_by_percent": "12.0", "status": "a",
        "transfers_in_event": transfers, "minutes": minutes,
        "total_points": 100, "bonus": 8,
        "threat": "600.0", "creativity": "500.0", "influence": "400.0",
        "expected_goals_per_90": "0.30", "expected_assists_per_90": "0.20",
        "expected_goal_involvements_per_90": "0.50",
        "saves_per_90": "3.0", "clean_sheets_per_90": "0.30",
        "defensive_contribution_per_90": "2.0",
    }
    base.update(extra)
    return base


class PairTest(unittest.TestCase):
    """C varianti: transfer hajmi eng katta pozitsiyadagi ikkita futbolchi."""

    def setUp(self):
        self.players = compare.pool({"elements": [
            # hujumchilar — bittasi juda mashhur, lekin ikkinchisi yo'q
            _element(1, "Haaland", 4, 900_000),
            _element(2, "Woltemade", 4, 5_000),
            # yarim himoyachilar — ikkalasi ham ko'p olinmoqda
            _element(3, "Semenyo", 3, 400_000),
            _element(4, "Anderson", 3, 300_000),
            # himoyachilar — kam
            _element(5, "Gabriel", 2, 60_000),
            _element(6, "Timber", 2, 50_000),
        ]})

    def test_picks_the_position_with_the_biggest_pair(self):
        a, b = compare.pair(self.players, min_transfers=20_000)
        self.assertEqual({a.name, b.name}, {"Semenyo", "Anderson"})
        self.assertEqual(a.name, "Semenyo")  # kattasi birinchi

    def test_lonely_star_does_not_win(self):
        """900k olingan hujumchi juftliksiz — u pozitsiya tanlanmaydi."""
        a, _ = compare.pair(self.players, min_transfers=20_000)
        self.assertEqual(a.position, 3)

    def test_no_pair_when_nobody_is_popular(self):
        self.assertIsNone(compare.pair(self.players, min_transfers=500_000))

    def test_benchwarmers_are_skipped(self):
        """90 daqiqadan kam o'ynaganning /90 raqami yolg'on — juftlikka kirmaydi."""
        players = compare.pool({"elements": [
            _element(1, "Yangi", 3, 800_000, minutes=20),
            _element(2, "Semenyo", 3, 400_000),
            _element(3, "Anderson", 3, 300_000),
        ]})
        a, b = compare.pair(players, min_transfers=20_000)
        self.assertEqual({a.name, b.name}, {"Semenyo", "Anderson"})


class MetricsTest(unittest.TestCase):
    def test_per90_divides_season_totals(self):
        stats = compare.per90(_element(1, "X", 3, 0, minutes=900,
                                       total_points=50, threat="450.0"))
        self.assertAlmostEqual(stats["points"], 5.0)
        self.assertAlmostEqual(stats["threat"], 45.0)

    def test_per90_survives_zero_minutes(self):
        stats = compare.per90(_element(1, "X", 3, 0, minutes=0))
        self.assertEqual(stats["points"], 0.0)
        self.assertEqual(stats["threat"], 0.0)

    def test_scale_is_the_best_in_that_position(self):
        players = compare.pool({"elements": [
            _element(1, "A", 3, 0, total_points=90),     # 4.5 / 90
            _element(2, "B", 3, 0, total_points=180),    # 9.0 / 90
            _element(3, "C", 4, 0, total_points=360),    # boshqa pozitsiya
        ]})
        self.assertAlmostEqual(compare.scale(players, 3, "points"), 9.0)

    def test_metrics_follow_the_position(self):
        players = compare.pool({"elements": [
            _element(1, "Raya", 1, 0), _element(2, "Sels", 1, 0)]})
        rows = compare.metrics(players, players[0], players[1])
        labels = [m.label for m in rows]
        self.assertIn("Saqlash / 90", labels)     # darvozabon ko'rsatkichi
        self.assertNotIn("xG / 90", labels)       # hujumchiniki emas
        self.assertGreaterEqual(len(rows), charts.MIN_METRICS)

    def test_top_is_never_zero(self):
        """Hamma qiymat nol bo'lsa ham radar bo'linishda yiqilmasin."""
        players = compare.pool({"elements": [
            _element(1, "A", 3, 0, total_points=0, bonus=0, threat="0.0",
                     creativity="0.0", influence="0.0",
                     expected_goals_per_90="0.0", expected_assists_per_90="0.0",
                     expected_goal_involvements_per_90="0.0",
                     defensive_contribution_per_90="0.0"),
            _element(2, "B", 3, 0, total_points=0, bonus=0, threat="0.0",
                     creativity="0.0", influence="0.0",
                     expected_goals_per_90="0.0", expected_assists_per_90="0.0",
                     expected_goal_involvements_per_90="0.0",
                     defensive_contribution_per_90="0.0"),
        ]})
        for metric in compare.metrics(players, players[0], players[1]):
            self.assertGreater(metric.top, 0)
            self.assertEqual(metric.share(metric.a), 0.0)


class TimingTest(unittest.TestCase):
    """Deadline'dan kamida 3 soat oldingi OXIRGI 20:30."""

    def moment(self, deadline_local: str) -> datetime:
        tz = ZoneInfo(config.LOCAL_TZ)
        deadline = datetime.fromisoformat(deadline_local).replace(tzinfo=tz)
        return compare.post_moment(deadline).astimezone(tz)

    def test_evening_before_a_midday_deadline(self):
        # shanba 14:30 -> zaxira 11:30 gacha -> juma 20:30
        got = self.moment("2026-11-07T14:30")
        self.assertEqual(got.strftime("%Y-%m-%d %H:%M"), "2026-11-06 20:30")

    def test_same_evening_when_the_deadline_is_late(self):
        # yakshanba 23:59 -> zaxira 20:59 gacha -> o'sha kuni 20:30
        got = self.moment("2026-11-08T23:59")
        self.assertEqual(got.strftime("%Y-%m-%d %H:%M"), "2026-11-08 20:30")

    def test_three_hour_cushion_is_respected(self):
        # 22:00 deadline -> zaxira 19:00 gacha -> o'sha kunning 20:30 i kech
        got = self.moment("2026-11-08T22:00")
        self.assertEqual(got.strftime("%Y-%m-%d %H:%M"), "2026-11-07 20:30")


class TrendTest(unittest.TestCase):
    def test_window_ends_on_the_last_finished_round(self):
        self.assertEqual(compare.trend_events(11, 6), [6, 7, 8, 9, 10, 11])

    def test_window_shrinks_early_in_the_season(self):
        self.assertEqual(compare.trend_events(3, 6), [1, 2, 3])

    def test_no_window_before_the_first_round(self):
        self.assertEqual(compare.trend_events(0, 6), [])

    def test_missing_round_is_skipped(self):
        def live(event):
            if event == 7:
                raise RuntimeError("CDN jim")
            return {"elements": [{"id": 1, "stats": {"total_points": event}},
                                 {"id": 2, "stats": {"total_points": 2}}]}

        with patch.object(compare.fpl_api, "get_live", side_effect=live):
            gws, a, b = compare.trend([6, 7, 8], 1, 2)
        self.assertEqual(gws, [6, 8])
        self.assertEqual(a, [6, 8])
        self.assertEqual(b, [2, 2])


class CaptionTest(unittest.TestCase):
    def test_caption_mentions_both_and_the_position(self):
        players = compare.pool({"elements": [
            _element(1, "Semenyo", 3, 420_000, team=2),
            _element(2, "Anderson", 3, 310_000, team=3)]})
        text = compare.caption(9, players[0], players[1], TEAMS)
        self.assertIn("Semenyo vs Anderson", text)
        self.assertIn("Yarim himoyachilar", text)
        self.assertIn("420 000", text)      # raqam o'qilishi uchun bo'shliq bilan
        self.assertIn("(BOU)", text)
        self.assertIn(config.COMPARE_HASHTAG, text)
        self.assertLessEqual(len(text), 1024)   # Telegram izoh chegarasi


class RenderTest(unittest.TestCase):
    """Rasm haqiqatan chiziladimi — matplotlib bilan to'liq o'tkazamiz."""

    def test_chart_file_is_written(self):
        bootstrap = {"elements": [
            _element(1, "Semenyo", 3, 420_000, team=2),
            _element(2, "Anderson", 3, 310_000, team=3),
            _element(3, "Fon", 3, 10, total_points=200),
        ]}
        live = {"elements": [{"id": 1, "stats": {"total_points": 8}},
                             {"id": 2, "stats": {"total_points": 3}}]}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "chart.png"
            with patch.object(compare.fpl_api, "get_live", return_value=live):
                built = compare.build(bootstrap, 9, out)
            self.assertIsNotNone(built)
            path, a, b = built
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 10_000)   # bo'sh rasm emas
            self.assertEqual((a.name, b.name), ("Semenyo", "Anderson"))

    def test_logo_is_bundled(self):
        """Suv belgisi bo'lmasa rasm manbasiz tarqalib ketadi."""
        self.assertTrue(Path(config.CHART_LOGO).is_file(), config.CHART_LOGO)

    def test_radar_needs_three_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                charts.comparison_chart(
                    Path(tmp) / "x.png", title="A vs B", subtitle="",
                    name_a="A", name_b="B",
                    metrics=[charts.Metric("Ochko", 1, 2, 3)])


class RunGateTest(unittest.TestCase):
    """Cron har kuni uyg'onadi, post esa haftada bir marta chiqadi."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name, value in (("COMPARE_STATE_FILE", Path(self.tmp.name) / "compare.json"),
                            ("CHART_DIR", Path(self.tmp.name) / "charts"),
                            ("DRY_RUN", True)):
            p = patch.object(config, name, value)
            p.start()
            self.addCleanup(p.stop)

        self.bootstrap = {"elements": [
            _element(1, "Semenyo", 3, 420_000, team=2),
            _element(2, "Anderson", 3, 310_000, team=3),
        ], "teams": [{"id": 2, "short_name": "BOU"}, {"id": 3, "short_name": "NFO"}],
            "events": [{"id": 9, "is_next": True,
                        "deadline_time": "2026-11-07T10:30:00Z"}]}
        # post vaqti: 7-noyabr 13:30 UTC dan 3 soat oldin -> 6-noyabr 20:30 (Toshkent)
        self.moment = compare.post_moment(
            datetime(2026, 11, 7, 10, 30, tzinfo=timezone.utc))

    def _run(self, now: datetime):
        live = {"elements": [{"id": 1, "stats": {"total_points": 8}},
                             {"id": 2, "stats": {"total_points": 3}}]}
        with patch.object(compare.fpl_api, "get_bootstrap", return_value=self.bootstrap), \
             patch.object(compare.fpl_api, "get_live", return_value=live), \
             patch.object(compare.waiter, "now_utc", return_value=now), \
             patch.object(compare.waiter, "sleep_until", return_value=True) as sleep, \
             patch.object(compare.telegram, "send_photo",
                          return_value={"message_id": 77}) as photo, \
             patch.object(compare.telegram, "notify_admin") as alert:
            code = compare.run()
        return code, sleep, photo, alert

    def test_posts_after_waiting_for_the_moment(self):
        _, sleep, photo, alert = self._run(self.moment - timedelta(minutes=120))
        sleep.assert_called_once()
        photo.assert_called_once()
        alert.assert_not_called()

    def test_quiet_on_an_ordinary_day(self):
        """Post sanasi hali uzoq — bu kutilgan holat, admin bezovta qilinmaydi."""
        _, sleep, photo, alert = self._run(self.moment - timedelta(days=3))
        sleep.assert_not_called()
        photo.assert_not_called()
        alert.assert_not_called()

    def test_alerts_when_the_cron_is_hours_early_on_the_day(self):
        _, _, photo, alert = self._run(self.moment - timedelta(hours=9))
        photo.assert_not_called()
        alert.assert_called_once()

    def test_alerts_when_the_cron_is_hours_late(self):
        _, _, photo, alert = self._run(self.moment + timedelta(hours=5))
        photo.assert_not_called()
        alert.assert_called_once()

    def test_nothing_goes_out_right_before_the_deadline(self):
        deadline = datetime(2026, 11, 7, 10, 30, tzinfo=timezone.utc)
        _, _, photo, alert = self._run(deadline - timedelta(minutes=10))
        photo.assert_not_called()
        alert.assert_not_called()

    def test_one_chart_per_round(self):
        self._run(self.moment)
        _, _, photo, _ = self._run(self.moment + timedelta(minutes=5))
        photo.assert_not_called()


class BuildGuardTest(unittest.TestCase):
    def test_no_pair_means_no_chart(self):
        bootstrap = {"elements": [_element(1, "Yolg'iz", 3, 900_000)]}
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(compare.build(bootstrap, 9, Path(tmp) / "x.png"))


if __name__ == "__main__":
    unittest.main()
