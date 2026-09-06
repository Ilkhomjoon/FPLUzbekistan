"""FPL CDN eski nusxa qaytarsa, o'yin holati orqaga ketmasligi kerak.

29-avgustda aynan shunday bo'ldi: tugagan o'yin "hali boshlanmagan" bo'lib
qoldi va sarlavha "YAKUNLANDI" dan "KUTILMOQDA" ga qaytdi.
"""
from __future__ import annotations

import unittest

from bot import live_bonus


def _fx(fid, started=False, finished=False, hs=None, aws=None, bps=0):
    stats = []
    if bps:
        stats = [{"identifier": "bps", "h": [{"element": 1, "value": bps}], "a": []}]
    return {"id": fid, "event": 2, "kickoff_time": "2026-08-29T16:30:00Z",
            "started": started, "finished": finished,
            "finished_provisional": finished, "team_h": 1, "team_a": 2,
            "team_h_score": hs, "team_a_score": aws, "stats": stats}


class MergeTest(unittest.TestCase):
    def test_started_never_goes_back(self):
        live = [_fx(1, started=True, hs=1, aws=0, bps=20)]
        stale = [_fx(1)]
        merged = live_bonus.merge_fixtures(live, stale)
        self.assertTrue(merged[0]["started"])
        self.assertEqual(merged[0]["team_h_score"], 1)

    def test_finished_never_goes_back(self):
        done = [_fx(1, started=True, finished=True, hs=2, aws=2, bps=30)]
        stale = [_fx(1, started=True, hs=1, aws=0, bps=10)]
        merged = live_bonus.merge_fixtures(done, stale)
        self.assertTrue(merged[0]["finished"])
        self.assertEqual(merged[0]["team_h_score"], 2)

    def test_real_progress_is_accepted(self):
        before = [_fx(1, started=True, hs=1, aws=0, bps=10)]
        after = [_fx(1, started=True, finished=True, hs=2, aws=1, bps=40)]
        merged = live_bonus.merge_fixtures(before, after)
        self.assertTrue(merged[0]["finished"])
        self.assertEqual(merged[0]["team_a_score"], 1)

    def test_more_stats_wins_at_the_same_stage(self):
        before = [_fx(1, started=True, hs=1, aws=0, bps=10)]
        after = [_fx(1, started=True, hs=1, aws=0, bps=25)]
        merged = live_bonus.merge_fixtures(before, after)
        self.assertEqual(merged[0]["stats"][0]["h"][0]["value"], 25)

    def test_a_goal_that_lowers_the_bps_total_is_still_accepted(self):
        """6-sentyabr holati: Everton gol urdi -> MUN darvozaboni BPS yo'qotdi.

        Jami BPS tushgani uchun yangi nusxa "eski" deb rad etilardi va xabar
        0:1 da muzlab qolgandi. Endi BPS solishtirishga umuman kirmaydi.
        """
        before = [_fx(1, started=True, hs=0, aws=1, bps=33)]
        after = [_fx(1, started=True, hs=1, aws=1, bps=21)]   # gol + BPS tushdi
        merged = live_bonus.merge_fixtures(before, after)
        self.assertEqual(merged[0]["team_h_score"], 1)
        self.assertEqual(merged[0]["stats"][0]["h"][0]["value"], 21)

    def test_the_score_never_goes_back(self):
        """Eski nusxa hisobni 1:2 dan 0:0 ga qaytarib yubormasin."""
        before = [_fx(1, started=True, hs=1, aws=2)]
        merged = live_bonus.merge_fixtures(before, [_fx(1, started=True, hs=0, aws=0)])
        self.assertEqual((merged[0]["team_h_score"], merged[0]["team_a_score"]), (1, 2))

    def test_a_finished_copy_wins_even_with_a_lower_score(self):
        """VAR goli bekor qilinsa — o'yin yakunlangach yangi hisob qabul qilinadi."""
        before = [_fx(1, started=True, hs=1, aws=2)]
        after = [_fx(1, started=True, finished=True, hs=1, aws=1)]
        merged = live_bonus.merge_fixtures(before, after)
        self.assertEqual(merged[0]["team_a_score"], 1)

    def test_fixture_missing_from_the_fresh_copy_is_kept(self):
        before = [_fx(1, started=True, finished=True), _fx(2, started=True)]
        merged = live_bonus.merge_fixtures(before, [_fx(1, started=True, finished=True)])
        self.assertEqual(sorted(f["id"] for f in merged), [1, 2])

    def test_new_fixture_is_added(self):
        merged = live_bonus.merge_fixtures([_fx(1, started=True)], [_fx(1, started=True), _fx(2)])
        self.assertEqual(sorted(f["id"] for f in merged), [1, 2])

    def test_title_stays_finished_after_a_stale_copy(self):
        from bot import config
        from bot.formatting import _live_post

        teams = {1: {"short_name": "A", "name": "A"}, 2: {"short_name": "B", "name": "B"}}
        done = [_fx(1, started=True, finished=True, hs=1, aws=0)]
        merged = live_bonus.merge_fixtures(done, [_fx(1)])
        title = _live_post(merged, {}, teams, 2, {}, 0).split("\n")[0]
        self.assertIn(config.DONE_LABEL, title)


if __name__ == "__main__":
    unittest.main()
