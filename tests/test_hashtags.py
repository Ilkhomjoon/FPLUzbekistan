"""Hashtaglar: har bir postning oxirida umumiy #FPL turishi kerak."""
from __future__ import annotations

import re
import unittest
from pathlib import Path
from unittest.mock import patch

from bot import config

BOT_DIR = Path(config.ROOT) / "bot"


class TagsTest(unittest.TestCase):
    def test_common_tag_is_appended(self):
        self.assertEqual(config.tags("#PriceChanges"), "#PriceChanges #FPL")

    def test_no_duplicate_when_already_present(self):
        self.assertEqual(config.tags("#FPL"), "#FPL")
        self.assertEqual(config.tags("#FPL #Narx"), "#FPL #Narx")

    def test_several_tags_in_one_setting(self):
        self.assertEqual(config.tags("#A #B"), "#A #B #FPL")

    def test_empty_setting_leaves_only_the_common_tag(self):
        self.assertEqual(config.tags(""), "#FPL")
        self.assertEqual(config.tags(None), "#FPL")

    def test_order_is_specific_then_common(self):
        """Maxsus hashtag oldinda: post nima haqidaligi birinchi o'qiladi."""
        self.assertTrue(config.tags("#GWReview").startswith("#GWReview"))

    def test_common_tag_is_configurable(self):
        with patch.object(config, "COMMON_HASHTAG", "#FantasyUz"):
            self.assertEqual(config.tags("#Narx"), "#Narx #FantasyUz")


class EveryPostTest(unittest.TestCase):
    """Yangi post turi qo'shilganda umumiy hashtag unutilmasin.

    Shuning uchun matnni emas, manba kodini tekshiramiz: hashtag sozlamasi
    ishlatilgan har bir qator `config.tags(...)` ichidan o'tishi kerak.
    """

    def test_no_hashtag_is_used_raw(self):
        offenders = []
        for path in sorted(BOT_DIR.glob("*.py")):
            if path.name == "config.py":
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not re.search(r"config\.\w*HASHTAG", line):
                    continue
                if "config.tags(" not in line:
                    offenders.append(f"{path.name}:{number}: {line.strip()}")
        self.assertEqual(offenders, [], "config.tags(...) ishlatilmagan qatorlar")

    def test_each_post_type_has_its_own_tag(self):
        """Har bir sozlama o'ziga xos — hammasi #FPL bo'lib qolmasin."""
        names = [n for n in dir(config) if n.endswith("HASHTAG") and n != "COMMON_HASHTAG"]
        values = [getattr(config, n) for n in names]
        self.assertGreaterEqual(len(names), 7)
        self.assertEqual(len(values), len(set(values)))
        self.assertNotIn(config.COMMON_HASHTAG, values)


if __name__ == "__main__":
    unittest.main()
