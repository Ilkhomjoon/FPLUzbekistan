"""Harakat charti: oyna, tanlash, matn va rasm."""
from __future__ import annotations

import tempfile
import unittest
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from bot import charts, config, differentials, elite_cohort, elite_movers, storage


def _event(players: dict, scanned: int = 1000, source: str = "live",
           cohort: int = 9, survivors: int | None = None) -> dict:
    row = {"scanned": scanned, "source": source, "cohort": cohort,
           "at": "2026-11-01T19:50:00+00:00",
           "players": {str(k): {"name": v[0], "elite": v[1], "owned": v[2]}
                       for k, v in players.items()}}
    if survivors is not None:
        row["survivors"] = survivors
    return row


HISTORY = {"events": {
    "9": _event({1: ("Semenyo", 14.2, 9.0), 2: ("Gordon", 9.1, 5.0),
                 3: ("Rogers", 6.5, 4.0), 6: ("Jarohat", 4.0, 2.0),
                 7: ("Barqaror", 20.0, 18.0)}, source="backfill"),
    "10": _event({1: ("Semenyo", 25.0, 10.0)}),
    "11": _event({1: ("Semenyo", 38.6, 11.4), 2: ("Gordon", 27.3, 6.2),
                  3: ("Rogers", 21.8, 4.9), 6: ("Jarohat", 30.0, 5.0),
                  7: ("Barqaror", 20.4, 18.1), 8: ("Yangi", 12.0, 3.0)},
                 survivors=734),
}}


def _el(pid, name, cost, owned, status="a"):
    return {"id": pid, "web_name": name, "now_cost": cost,
            "selected_by_percent": str(owned), "status": status}


BOOTSTRAP = {"elements": [
    _el(1, "Semenyo", 79, 11.4), _el(2, "Gordon", 75, 6.2),
    _el(3, "Rogers", 58, 4.9), _el(6, "Jarohat", 70, 5.0, "i"),
    _el(7, "Barqaror", 90, 18.1), _el(8, "Yangi", 55, 3.0),
]}


class WindowTest(unittest.TestCase):
    def test_events_are_read_in_order(self):
        self.assertEqual(elite_movers.events_in(HISTORY), [9, 10, 11])

    def test_window_takes_the_last_rounds(self):
        self.assertEqual(elite_movers.window([5, 6, 7, 8, 9], 3), [7, 8, 9])

    def test_window_uses_records_not_numbers(self):
        """Bir hafta skaner ishlamay qolsa, turlar ketma-ket bo'lmaydi."""
        self.assertEqual(elite_movers.window([5, 6, 9], 3), [5, 6, 9])

    def test_window_shrinks_when_history_is_short(self):
        self.assertEqual(elite_movers.window([9, 10], 3), [9, 10])


class MoversTest(unittest.TestCase):
    def rows(self, **kwargs):
        return elite_movers.movers(HISTORY, [9, 10, 11], BOOTSTRAP, **kwargs)

    def test_sorted_by_the_biggest_rise(self):
        self.assertEqual([m.name for m in self.rows()],
                         ["Semenyo", "Gordon", "Rogers", "Yangi"])

    def test_injured_players_are_left_out(self):
        """Eng ko'p ko'tarilgani jarohatlangan bo'lsa — bu tavsiya emas, tuzoq."""
        self.assertNotIn("Jarohat", [m.name for m in self.rows()])

    def test_standing_still_is_not_a_move(self):
        self.assertNotIn("Barqaror", [m.name for m in self.rows()])

    def test_newcomer_counts_from_zero(self):
        """Oyna boshida ro'yxatda yo'q futbolchi nol deb olinadi."""
        row = next(m for m in self.rows(min_rise=1.0) if m.name == "Yangi")
        self.assertEqual(row.before, 0.0)
        self.assertEqual(row.now, 12.0)

    def test_ownership_comes_from_bootstrap_not_history(self):
        row = next(m for m in self.rows() if m.name == "Semenyo")
        self.assertEqual(row.owned, 11.4)
        self.assertEqual(row.price, "£7.9M")

    def test_row_count_is_capped(self):
        self.assertEqual(len(self.rows(count=2, min_rise=1.0)), 2)

    def test_a_single_round_gives_nothing(self):
        self.assertEqual(elite_movers.movers(HISTORY, [11], BOOTSTRAP), [])

    def test_high_threshold_empties_the_list(self):
        self.assertEqual(self.rows(min_rise=50.0), [])


class PointsTest(unittest.TestCase):
    def test_points_are_attached(self):
        rows = elite_movers.movers(HISTORY, [9, 10, 11], BOOTSTRAP)
        with patch.object(differentials, "recent_form",
                          return_value={1: (31, 3), 2: (24, 2), 3: (22, 2)}):
            elite_movers.apply_points(rows, [9, 10, 11])
        self.assertEqual({m.name: m.points for m in rows},
                         {"Semenyo": 31, "Gordon": 24, "Rogers": 22, "Yangi": 0})

    def test_a_failed_request_does_not_break_the_post(self):
        rows = elite_movers.movers(HISTORY, [9, 10, 11], BOOTSTRAP)
        with patch.object(differentials, "recent_form", side_effect=RuntimeError("CDN")):
            elite_movers.apply_points(rows, [9, 10, 11])
        self.assertTrue(all(m.points == 0 for m in rows))


class CaptionTest(unittest.TestCase):
    def test_caption_names_the_window_and_fits(self):
        rows = elite_movers.movers(HISTORY, [9, 10, 11], BOOTSTRAP)
        text = elite_movers.caption(rows, [9, 10, 11])
        self.assertIn("GW9 → GW11", text)
        self.assertIn("Semenyo", text)
        self.assertIn(config.MOVERS_HASHTAG, text)
        self.assertLessEqual(len(text), 1024)


class RenderTest(unittest.TestCase):
    def test_chart_file_is_written(self):
        rows = elite_movers.movers(HISTORY, [9, 10, 11], BOOTSTRAP)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "movers.png"
            elite_movers.build(rows, [9, 10, 11], out)
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 10_000)

    def test_empty_chart_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                charts.movers_chart(Path(tmp) / "x.png", title="T",
                                    subtitle="", rows=[])


class RunTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.history = Path(self.tmp.name) / "elite_history.json"
        storage.save(self.history, HISTORY)
        self.cohort = Path(self.tmp.name) / "cohort.json"
        for name, value in (("ELITE_HISTORY_FILE", self.history),
                            ("ELITE_COHORT_FILE", self.cohort),
                            ("MOVERS_STATE_FILE", Path(self.tmp.name) / "movers.json"),
                            ("CHART_DIR", Path(self.tmp.name) / "charts"),
                            ("DRY_RUN", True)):
            p = patch.object(config, name, value)
            p.start()
            self.addCleanup(p.stop)
        elite_cohort.save([1, 2, 3], from_event=9)

    def _run(self, now=None, **kwargs):
        now = now or elite_movers.waiter.local_time_today(config.MOVERS_POST_AT)
        with patch.object(elite_movers.fpl_api, "get_bootstrap", return_value=BOOTSTRAP), \
             patch.object(differentials, "recent_form", return_value={}), \
             patch.object(differentials, "scan_picks",
                          return_value=(Counter({1: 300}), 1000)) as scan, \
             patch.object(elite_movers.waiter, "now_utc", return_value=now), \
             patch.object(elite_movers.waiter, "sleep_until", return_value=True), \
             patch.object(elite_movers.telegram, "send_photo",
                          return_value={"message_id": 5}) as photo, \
             patch.object(elite_movers.telegram, "notify_admin") as alert:
            code = elite_movers.run(**kwargs)
        return code, photo, alert, scan

    def test_posts_once_per_round(self):
        _, photo, _, scan = self._run()
        photo.assert_called_once()
        scan.assert_not_called()      # uch tur bor, to'ldirish kerak emas
        _, photo, _, _ = self._run()
        photo.assert_not_called()

    def test_the_caption_states_how_the_list_was_frozen(self):
        _, photo, _, _ = self._run()
        text = photo.call_args.kwargs["caption"]
        self.assertIn("GW9 dan muzlatilgan", text)
        self.assertIn("734", text)    # nechtasi hali top-1000 da

    def test_a_brand_new_list_says_only_when_it_was_frozen(self):
        """Yangi olingan ro'yxatda "1000 tadan 1000 tasi" deyishning ma'nosi yo'q."""
        text = elite_movers.caption(
            elite_movers.movers(HISTORY, [9, 10, 11], BOOTSTRAP),
            [9, 10, 11], cohort=9, survivors=None, size=1000)
        self.assertIn("Ro'yxat GW9 dan muzlatilgan.", text)
        self.assertNotIn("hozir ham top-1000 da", text)

    def test_missing_rounds_are_filled_in(self):
        """Ro'yxat yangilangach yangi belgili atigi bitta tur qoladi."""
        storage.save(self.history, {"events": {"11": HISTORY["events"]["11"]}})
        _, _, _, scan = self._run()
        # GW9 va GW10 muzlatilgan ro'yxat bo'yicha qaytadan o'qiladi
        self.assertEqual(scan.call_count, 2)
        filled = storage.load(self.history, {})["events"]
        self.assertEqual(filled["10"]["source"], "backfill")
        self.assertEqual(filled["10"]["cohort"], 9)

    def test_other_cohorts_are_ignored(self):
        """Boshqa ro'yxat bilan o'lchangan turlar solishtirishga yaramaydi."""
        events = {k: dict(v, cohort=4) for k, v in HISTORY["events"].items()}
        storage.save(self.history, {"events": events})
        with patch.object(config, "MOVERS_BACKFILL", False):
            _, photo, alert, _ = self._run()
        photo.assert_not_called()
        alert.assert_not_called()

    def test_waits_for_more_history(self):
        storage.save(self.history, {"events": {"11": HISTORY["events"]["11"]}})
        with patch.object(config, "MOVERS_BACKFILL", False):
            _, photo, alert, _ = self._run()
        photo.assert_not_called()
        alert.assert_not_called()

    def test_quiet_when_nobody_moved(self):
        with patch.object(config, "MOVERS_MIN_RISE", 90.0):
            _, photo, alert, _ = self._run()
        photo.assert_not_called()
        alert.assert_not_called()
        self.assertTrue(storage.load(config.MOVERS_STATE_FILE, {}).get("empty"))

    def test_too_late_means_tomorrow(self):
        late = elite_movers.waiter.local_time_today(config.MOVERS_LATEST) + timedelta(minutes=30)
        _, photo, _, _ = self._run(now=late)
        photo.assert_not_called()
        # holat yozilmaydi — ertaga yana urinadi
        self.assertEqual(storage.load(config.MOVERS_STATE_FILE, {}), {})

    def test_alerts_when_the_cron_is_far_too_early(self):
        early = (elite_movers.waiter.local_time_today(config.MOVERS_POST_AT)
                 - timedelta(hours=9))
        _, photo, alert, _ = self._run(now=early)
        photo.assert_not_called()
        alert.assert_called_once()


class BackfillTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "elite_history.json"
        for name, value in (("ELITE_HISTORY_FILE", self.path),
                            ("ELITE_COHORT_FILE", Path(self.tmp.name) / "cohort.json")):
            p = patch.object(config, name, value)
            p.start()
            self.addCleanup(p.stop)

    def _backfill(self, gw=8):
        return patch.multiple(
            differentials,
            scan_picks=lambda entries, g, workers=None: (Counter({1: 400}), 1000),
        ), patch.object(differentials.fpl_api, "get_bootstrap", return_value={
            "elements": [{"id": 1, "web_name": "Semenyo", "team": 1,
                          "now_cost": 79, "selected_by_percent": "11.4",
                          "event_points": 0, "total_points": 0,
                          "transfers_in_event": 0, "status": "a", "form": "0"}]})

    def test_backfilled_rounds_carry_the_cohort(self):
        elite_cohort.save([1, 2, 3], from_event=9)
        scan, boot = self._backfill()
        with scan, boot:
            saved = differentials.backfill_elite_history(8)

        self.assertEqual(saved, 1)
        row = storage.load(self.path, {})["events"]["8"]
        self.assertEqual(row["source"], "backfill")
        self.assertEqual(row["cohort"], 9)     # o'lchov belgisi
        self.assertEqual(row["players"]["1"]["elite"], 40.0)

    def test_backfill_never_creates_a_cohort(self):
        """O'tmishni to'ldirish o'lchovni o'zgartirib yubormasligi kerak."""
        scan, boot = self._backfill()
        with patch.object(differentials, "top_entries") as entries, scan, boot:
            self.assertEqual(differentials.backfill_elite_history(8), 0)
        entries.assert_not_called()

    def test_an_existing_round_is_not_rescanned(self):
        elite_cohort.save([1, 2, 3], from_event=9)
        storage.save(self.path, {"events": {"8": _event({1: ("Semenyo", 40.0, 11.4)})}})
        with patch.object(differentials, "scan_picks") as scan:
            self.assertEqual(differentials.backfill_elite_history(8), 0)
        scan.assert_not_called()


class CohortTest(unittest.TestCase):
    """Ro'yxat muzlatiladi, qolganlar soni esa uni qachon yangilashni aytadi."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = patch.object(config, "ELITE_COHORT_FILE", Path(self.tmp.name) / "cohort.json")
        p.start()
        self.addCleanup(p.stop)

    def test_first_run_freezes_the_list(self):
        got = elite_cohort.resolve(9, 5, fetch=lambda n: [1, 2, 3, 4, 5])
        self.assertTrue(got.refreshed)
        self.assertEqual(got.from_event, 9)
        self.assertEqual(elite_cohort.load()["entries"], [1, 2, 3, 4, 5])

    def test_the_same_list_comes_back_next_week(self):
        elite_cohort.save([1, 2, 3, 4, 5], from_event=9)
        got = elite_cohort.resolve(10, 5, fetch=lambda n: [3, 4, 5, 6, 7], min_keep=3)
        self.assertFalse(got.refreshed)
        self.assertEqual(got.entries, [1, 2, 3, 4, 5])   # skaner to'liq ro'yxat bo'yicha
        self.assertEqual(got.from_event, 9)
        self.assertEqual(got.survivors, 3)               # kesishma faqat o'lchagich

    def test_too_few_survivors_means_a_new_list(self):
        elite_cohort.save([1, 2, 3, 4, 5], from_event=9)
        got = elite_cohort.resolve(12, 5, fetch=lambda n: [6, 7, 8, 9, 10], min_keep=3)
        self.assertTrue(got.refreshed)
        self.assertEqual(got.entries, [6, 7, 8, 9, 10])
        self.assertEqual(got.from_event, 12)
        self.assertEqual(elite_cohort.load()["from_event"], 12)

    def test_an_unreadable_ranking_keeps_the_old_list(self):
        elite_cohort.save([1, 2, 3], from_event=9)
        got = elite_cohort.resolve(10, 3, fetch=lambda n: [])
        self.assertEqual(got.entries, [1, 2, 3])
        self.assertFalse(got.refreshed)

    def test_read_mode_does_not_fetch(self):
        elite_cohort.save([1, 2, 3], from_event=9)
        calls = []
        got = elite_cohort.resolve(10, 3, fetch=lambda n: calls.append(n) or [9],
                                   refresh=False)
        self.assertEqual(calls, [])
        self.assertEqual(got.entries, [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
