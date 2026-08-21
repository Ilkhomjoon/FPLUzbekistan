"""DefCon (Defensive Contribution) qoidalarini tekshirish."""
import unittest

from bot.defcon import actions, from_live, qualifies

GK, DEF, MID, FWD = 1, 2, 3, 4


def stats(cbi=0, tackles=0, recoveries=0):
    return {
        "clearances_blocks_interceptions": cbi,
        "tackles": tackles,
        "recoveries": recoveries,
    }


class TestQoidalar(unittest.TestCase):
    def test_himoyachi_recovery_hisoblanmaydi(self):
        # 6 CBI + 3 tackle = 9 -> yetmaydi, recovery qo'shilmaydi
        self.assertEqual(actions(stats(6, 3, 20), DEF), 9)
        self.assertFalse(qualifies(stats(6, 3, 20), DEF))

    def test_himoyachi_10_da_oladi(self):
        self.assertTrue(qualifies(stats(7, 3, 0), DEF))
        self.assertTrue(qualifies(stats(20, 5, 0), DEF))  # cheklov yo'q, lekin ochko baribir 2

    def test_yarim_himoyachi_recovery_bilan(self):
        # 4 + 3 + 5 = 12 -> yetadi
        self.assertEqual(actions(stats(4, 3, 5), MID), 12)
        self.assertTrue(qualifies(stats(4, 3, 5), MID))
        self.assertFalse(qualifies(stats(4, 3, 4), MID))  # 11 -> yetmaydi

    def test_hujumchi_chegarasi_12(self):
        self.assertTrue(qualifies(stats(5, 2, 5), FWD))
        self.assertFalse(qualifies(stats(5, 2, 4), FWD))

    def test_darvozabon_ololmaydi(self):
        self.assertIsNone(actions(stats(20, 20, 20), GK))
        self.assertFalse(qualifies(stats(20, 20, 20), GK))

    def test_pozitsiya_nomalum(self):
        self.assertFalse(qualifies(stats(20, 20, 20), None))


class TestLiveDanOqish(unittest.TestCase):
    players = {
        10: {"element_type": DEF},
        11: {"element_type": MID},
        12: {"element_type": DEF},
        13: {"element_type": DEF},
    }

    def test_api_bergan_ochkoni_oladi(self):
        live = {"elements": [
            {"id": 10, "stats": stats(0, 0, 0),
             "explain": [{"fixture": 5, "stats": [
                 {"identifier": "defensive_contribution", "points": 2, "value": 1}]}]},
        ]}
        self.assertEqual(from_live(live, 5, self.players), {10: 2})

    def test_boshqa_oyin_qoshilmaydi(self):
        live = {"elements": [
            {"id": 10, "stats": stats(0, 0, 0),
             "explain": [{"fixture": 9, "stats": [
                 {"identifier": "defensive_contribution", "points": 2, "value": 1}]}]},
        ]}
        self.assertEqual(from_live(live, 5, self.players), {})

    def test_zaxira_hisob_ishlaydi(self):
        # API identifikator bermadi, lekin 11 CBIT bor -> o'zimiz hisoblaymiz
        live = {"elements": [
            {"id": 12, "stats": stats(8, 3, 0), "explain": [{"fixture": 5, "stats": []}]},
        ]}
        self.assertEqual(from_live(live, 5, self.players), {12: 2})

    def test_zaxira_hisob_ikki_oyinda_ishlamaydi(self):
        # Double gameweek: `stats` ikki o'yin yig'indisi, shuning uchun ishonch yo'q
        live = {"elements": [
            {"id": 13, "stats": stats(8, 3, 0),
             "explain": [{"fixture": 5, "stats": []}, {"fixture": 6, "stats": []}]},
        ]}
        self.assertEqual(from_live(live, 5, self.players), {})

    def test_chegaraga_yetmaganlar_chiqmaydi(self):
        live = {"elements": [
            {"id": 12, "stats": stats(5, 2, 9), "explain": [{"fixture": 5, "stats": []}]},
        ]}
        self.assertEqual(from_live(live, 5, self.players), {})


if __name__ == "__main__":
    unittest.main()
