"""Top-1000 egalik tarixi: yozish, kesish va postga aralashmaslik."""
from __future__ import annotations

import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from bot import config, differentials, storage


def _player(pid, name, owned):
    return differentials.Diff(element_id=pid, name=name, team=1, cost=60,
                              owned=owned, points=0, total=0, transfers_in=0)


class RecordTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "elite_history.json"
        patcher = patch.object(config, "ELITE_HISTORY_FILE", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.players = [_player(1, "Semenyo", 7.5), _player(2, "Anderson", 3.1),
                        _player(3, "Nobody", 0.4)]

    def test_writes_shares_against_the_scanned_count(self):
        counts = Counter({1: 420, 2: 180, 3: 5})
        saved = differentials.record_elite_history(self.players, 9, counts, 1000)
        self.assertEqual(saved, 2)      # 0.5% li futbolchi yozilmaydi

        data = storage.load(self.path, {})
        row = data["events"]["9"]
        self.assertEqual(row["scanned"], 1000)
        self.assertEqual(row["players"]["1"], {"name": "Semenyo", "elite": 42.0, "owned": 7.5})
        self.assertNotIn("3", row["players"])

    def test_keeps_only_the_latest_rounds(self):
        with patch.object(config, "ELITE_HISTORY_KEEP", 3):
            for gw in range(1, 7):
                differentials.record_elite_history(self.players, gw,
                                                   Counter({1: 500}), 1000)
        events = storage.load(self.path, {})["events"]
        self.assertEqual(sorted(events, key=int), ["4", "5", "6"])

    def test_earlier_rounds_survive_a_new_write(self):
        differentials.record_elite_history(self.players, 8, Counter({1: 500}), 1000)
        differentials.record_elite_history(self.players, 9, Counter({1: 300}), 1000)
        events = storage.load(self.path, {})["events"]
        self.assertEqual(events["8"]["players"]["1"]["elite"], 50.0)
        self.assertEqual(events["9"]["players"]["1"]["elite"], 30.0)

    def test_empty_scan_writes_nothing(self):
        self.assertEqual(differentials.record_elite_history(self.players, 9, Counter(), 0), 0)
        self.assertFalse(self.path.exists())


class ExtendScanTest(unittest.TestCase):
    """Tarix uchun qo'shimcha skaner postning raqamlariga tegmasligi kerak."""

    def test_counts_are_merged_without_touching_the_original(self):
        entries = list(range(1, 1001))
        counts = Counter({1: 40})
        with patch.object(config, "DIFF_ELITE_TIERS", "100,1000"), \
             patch.object(differentials, "scan_picks",
                          return_value=(Counter({1: 300, 2: 90}), 900)) as scan:
            merged, scanned = differentials._extend_scan(entries, 9, counts, 100, 100)

        scan.assert_called_once()
        self.assertEqual(len(scan.call_args[0][0]), 900)   # faqat qolganlari
        self.assertEqual(merged[1], 340)
        self.assertEqual(scanned, 1000)
        self.assertEqual(counts[1], 40)    # asl Counter o'zgarmadi
        self.assertNotIn(2, counts)

    def test_nothing_to_do_when_the_full_tier_is_already_scanned(self):
        with patch.object(config, "DIFF_ELITE_TIERS", "100,1000"), \
             patch.object(differentials, "scan_picks") as scan:
            merged, scanned = differentials._extend_scan(
                list(range(1, 1001)), 9, Counter({1: 400}), 1000, 1000)
        scan.assert_not_called()
        self.assertEqual(scanned, 1000)
        self.assertEqual(merged[1], 400)


if __name__ == "__main__":
    unittest.main()
