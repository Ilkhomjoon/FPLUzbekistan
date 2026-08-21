"""Bonus hisoblash qoidalarini tekshirish."""
import unittest

from bot.bonus import bonus_from_bps


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


if __name__ == "__main__":
    unittest.main()
