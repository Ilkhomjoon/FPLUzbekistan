"""Bonus hisoblash qoidalarini tekshirish."""
import unittest

from bot.bonus import bonus_from_bps, fixture_bonus


def rows(pairs):
    return [{"element": e, "value": v} for e, v in pairs]


class TestBonus(unittest.TestCase):
    def test_oddiy(self):
        r = bonus_from_bps(rows([(1, 33), (2, 28), (3, 25), (4, 20)]))
        self.assertEqual(r, {1: 3, 2: 2, 3: 1})

    def test_birinchida_ikki_kishi_teng(self):
        # ikkalasi 3 oladi, 2 berilmaydi, keyingisi 1 oladi
        r = bonus_from_bps(rows([(1, 33), (2, 33), (3, 25), (4, 20)]))
        self.assertEqual(r, {1: 3, 2: 3, 3: 1})

    def test_birinchida_uch_kishi_teng(self):
        r = bonus_from_bps(rows([(1, 33), (2, 33), (3, 33), (4, 20)]))
        self.assertEqual(r, {1: 3, 2: 3, 3: 3})

    def test_ikkinchida_teng(self):
        # 2-o'rinda ikki kishi -> ikkalasi 2, 1 berilmaydi
        r = bonus_from_bps(rows([(1, 40), (2, 30), (3, 30), (4, 20)]))
        self.assertEqual(r, {1: 3, 2: 2, 3: 2})

    def test_uchinchida_teng(self):
        r = bonus_from_bps(rows([(1, 40), (2, 35), (3, 30), (4, 30), (5, 10)]))
        self.assertEqual(r, {1: 3, 2: 2, 3: 1, 4: 1})

    def test_kam_oyinchi(self):
        self.assertEqual(bonus_from_bps(rows([(1, 20)])), {1: 3})
        self.assertEqual(bonus_from_bps(rows([(1, 20), (2, 10)])), {1: 3, 2: 2})
        self.assertEqual(bonus_from_bps([]), {})

    def test_hech_kim_ochko_toplamagan(self):
        self.assertEqual(bonus_from_bps(rows([(1, 0), (2, 0)])), {})


class TestMinBps(unittest.TestCase):
    def test_oyin_boshida_hamma_teng_bolsa_royxat_bosh(self):
        # 1 kishi 5, 1 kishi 4, 20 kishi 3 BPS — chegarasiz 22 kishi chiqib ketadi
        early = rows([(1, 5), (2, 4)] + [(i, 3) for i in range(10, 30)])
        self.assertEqual(len(bonus_from_bps(early)), 22)
        self.assertEqual(bonus_from_bps(early, min_bps=5), {1: 3})  # faqat 5 BPS liq qoladi

    def test_haqiqiy_qiymatlarda_odatdagidek_ishlaydi(self):
        mid = rows([(1, 34), (2, 28), (3, 25), (4, 11), (5, 9)])
        self.assertEqual(bonus_from_bps(mid, min_bps=12), {1: 3, 2: 2, 3: 1})

    def test_chegara_pastdagilarni_kesadi(self):
        # 3-o'rin chegaradan past -> unga ochko berilmaydi
        mid = rows([(1, 30), (2, 20), (3, 5)])
        self.assertEqual(bonus_from_bps(mid, min_bps=12), {1: 3, 2: 2})

    def test_tugagan_oyinda_chegara_qollanmaydi(self):
        fx = {
            "finished": True, "finished_provisional": True,
            "stats": [
                {"identifier": "bps", "h": rows([(1, 30), (2, 8)]), "a": rows([(3, 5)])},
                {"identifier": "bonus", "h": [], "a": []},
            ],
        }
        awarded, official = fixture_bonus(fx, min_bps=12)
        self.assertFalse(official)
        self.assertEqual(awarded, {1: 3, 2: 2, 3: 1})


if __name__ == "__main__":
    unittest.main()
