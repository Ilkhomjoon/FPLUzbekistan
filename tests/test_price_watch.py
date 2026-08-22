"""Narx bashorati postini tekshirish."""
import unittest

from bot import config, formatting, price_watch

TEAMS = [{"id": 1, "name": "Arsenal", "short_name": "ARS"},
         {"id": 2, "name": "Tottenham", "short_name": "TOT"}]


def player(pid, name, team, cost, proj0, **extra):
    row = {
        "id": pid, "web_name": name, "team": team, "now_cost": cost,
        "removed": False, "price_change_calibrating": False,
        "price_change_locked_until": None,
        "price_change_projections": [
            {"offset": 0, "projected_percent": f"{proj0:.1f}", "likelihood": 3},
            {"offset": 1, "projected_percent": f"{proj0 * 2:.1f}", "likelihood": 4},
        ],
    }
    row.update(extra)
    return row


class TestTanlash(unittest.TestCase):
    def bootstrap(self, elements):
        return {"teams": TEAMS, "elements": elements}

    def test_offset_0_olinadi(self):
        p = player(1, "A", 1, 50, 104.0)
        self.assertAlmostEqual(price_watch.projection(p, 0), 104.0)
        self.assertAlmostEqual(price_watch.projection(p, 1), 208.0)
        self.assertIsNone(price_watch.projection(p, 9))

    def test_chegaradan_pastlari_tushmaydi(self):
        bs = self.bootstrap([player(1, "Yuqori", 1, 50, 120.0), player(2, "Past", 1, 50, 10.0)])
        rises, falls = price_watch.candidates(bs)
        self.assertEqual([r["label"] for r in rises], ["Yuqori (ARS)"])
        self.assertEqual(falls, [])

    def test_qulflangan_va_kalibrlanayotgan_chiqarib_tashlanadi(self):
        bs = self.bootstrap([
            player(1, "Qulf", 1, 50, 150.0, price_change_locked_until="2026-01-01T00:00:00Z"),
            player(2, "Kalib", 1, 50, 150.0, price_change_calibrating=True),
            player(3, "Olib tashlangan", 1, 50, 150.0, removed=True),
            player(4, "Yaxshi", 1, 50, 150.0),
        ])
        rises, _ = price_watch.candidates(bs)
        self.assertEqual([r["label"] for r in rises], ["Yaxshi (ARS)"])

    def test_tartib_va_bolinish(self):
        bs = self.bootstrap([
            player(1, "Kam", 1, 50, 90.0), player(2, "Ko'p", 1, 50, 130.0),
            player(3, "Tushish", 2, 50, -95.0), player(4, "Katta tushish", 2, 50, -140.0),
        ])
        rises, falls = price_watch.candidates(bs)
        self.assertEqual([r["label"] for r in rises], ["Ko'p (ARS)", "Kam (ARS)"])
        self.assertEqual([r["label"] for r in falls], ["Katta tushish (TOT)", "Tushish (TOT)"])

    def test_max_chegarasi(self):
        many = [player(i, f"P{i}", 1, 50, 100.0 + i) for i in range(1, 20)]
        rises, _ = price_watch.candidates(self.bootstrap(many))
        self.assertEqual(len(rises), config.PRICE_WATCH_MAX)


class TestPost(unittest.TestCase):
    def test_chegaradan_oshgani_qalin(self):
        text = formatting.price_watch_post(
            rises=[{"label": "A (ARS)", "cost": 55, "percent": 118.4},
                   {"label": "B (ARS)", "cost": 65, "percent": 92.0}],
            falls=[{"label": "C (TOT)", "cost": 50, "percent": -131.0}],
            stamp="21:00",
        )
        self.assertIn("<b>A (ARS) £5.5M — 118%</b>", text)
        self.assertIn("B (ARS) £6.5M — 92%", text)
        self.assertNotIn("<b>B (ARS)", text)
        # tushish manfiy bo'lsa ham musbat ko'rsatiladi
        self.assertIn("C (TOT) £5.0M — 131%", text)

    def test_bosh_tomon(self):
        text = formatting.price_watch_post(rises=[], falls=[], stamp="21:00")
        self.assertEqual(text.count("hozircha yo'q"), 2)

    def test_taglar(self):
        text = formatting.price_watch_post(rises=[], falls=[], stamp="21:00")
        self.assertIn(config.PRICE_WATCH_HASHTAG, text)
        self.assertTrue(text.rstrip().endswith(config.CHANNEL_TAG))


if __name__ == "__main__":
    unittest.main()
