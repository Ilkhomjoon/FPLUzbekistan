"""Deadline statistikasi postini tekshirish."""
import unittest
from collections import Counter

from bot import config, formatting
from bot.deadline_stats import LeagueScan, overall_chips

PLAYERS = {
    5: {"web_name": "Haaland", "team": 1},
    7: {"web_name": "Saka", "team": 4},
    1: {"web_name": "Cherki", "team": 1},
}
TEAMS = {1: {"short_name": "MCI"}, 4: {"short_name": "ARS"}}


class TestYordamchilar(unittest.TestCase):
    def test_chip_yorliqlari(self):
        self.assertEqual(formatting.chip_label("bboost"), "BB")
        self.assertEqual(formatting.chip_label("3xc"), "TC")
        self.assertEqual(formatting.chip_label("wildcard"), "WC")
        self.assertEqual(formatting.chip_label("freehit"), "FH")
        # noma'lum chip nomi o'zgarishsiz qoladi
        self.assertEqual(formatting.chip_label("yangichip"), "yangichip")

    def test_raqam_formati(self):
        self.assertEqual(formatting.num(814606).replace(" ", " "), "814 606")
        self.assertEqual(formatting.num(12), "12")

    def test_overall_chiplar(self):
        ev = {"chip_plays": [{"chip_name": "bboost", "num_played": 100},
                             {"chip_name": "3xc", "num_played": 50}]}
        self.assertEqual(overall_chips(ev), Counter({"bboost": 100, "3xc": 50}))
        self.assertEqual(overall_chips({}), Counter())


class TestPost(unittest.TestCase):
    def build(self, scan):
        return formatting.deadline_stats_post(
            gw=1, scans=[("🏆 Test", scan)], players=PLAYERS, teams=TEAMS,
            overall_captain=5, overall_chip_counts=Counter({"bboost": 814606}),
        )

    def test_tartib_va_foiz(self):
        scan = LeagueScan(1, "Test", scanned=100, captains=Counter({5: 40, 7: 25, 1: 10}))
        text = self.build(scan)
        self.assertIn("1. Haaland (MCI) — 40 (40%)", text)
        self.assertIn("2. Saka (ARS) — 25 (25%)", text)
        self.assertIn("3. Cherki (MCI) — 10 (10%)", text)

    def test_faqat_top_n(self):
        scan = LeagueScan(1, "Test", scanned=100, captains=Counter({5: 40, 7: 25, 1: 10}))
        self.assertNotIn("4.", self.build(scan))

    def test_chip_yoq(self):
        scan = LeagueScan(1, "Test", scanned=10, captains=Counter({5: 10}))
        self.assertIn("🏆 Test: yo'q", self.build(scan))

    def test_bosh_liga(self):
        scan = LeagueScan(1, "Test", scanned=0)
        self.assertIn("ma'lumot yo'q", self.build(scan))

    def test_taglar_va_kanal(self):
        scan = LeagueScan(1, "Test", scanned=10, captains=Counter({5: 10}))
        text = self.build(scan)
        self.assertIn(config.STATS_HASHTAG, text)
        self.assertTrue(text.rstrip().endswith(config.CHANNEL_TAG))


if __name__ == "__main__":
    unittest.main()
