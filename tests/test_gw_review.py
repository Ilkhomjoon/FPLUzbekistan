"""Tur yakunlari sharhini tekshirish."""
import unittest

from bot import config, formatting, gw_review
from bot.gw_review import LeagueReview, Manager


def mgr(entry=1, team="Team", name="Ism", rank=1, last_rank=1, total=100, event_total=50, **kw):
    m = Manager(entry=entry, team=team, name=name, rank=rank, last_rank=last_rank,
                total=total, event_total=event_total)
    for k, v in kw.items():
        setattr(m, k, v)
    return m


class TestKotarilish(unittest.TestCase):
    def test_kotarilish_hisobi(self):
        self.assertEqual(mgr(rank=63, last_rank=214).climb, 151)
        self.assertEqual(mgr(rank=214, last_rank=63).climb, -151)

    def test_yangi_qoshilgan_hisobga_olinmaydi(self):
        # last_rank=0 — bu tur birinchi marta qatnashyapti
        self.assertEqual(mgr(rank=5, last_rank=0).climb, 0)


class TestYetakchidanFarq(unittest.TestCase):
    def test_ortda(self):
        self.assertEqual(formatting._behind(-27), "−27")

    def test_yetakchining_ozi(self):
        self.assertEqual(formatting._behind(0), "yetakchi")

    def test_oldinda(self):
        self.assertEqual(formatting._behind(5), "+5")

    def test_nomalum(self):
        self.assertEqual(formatting._behind(None), "")


class TestHavola(unittest.TestCase):
    def test_jamoa_nomi_havola(self):
        link = formatting.manager_link(mgr(entry=42, team="Aziz FC", name="Aziz K."), gw=3)
        self.assertIn('href="https://fantasy.premierleague.com/entry/42/event/3/"', link)
        self.assertIn(">Aziz FC</a>", link)
        self.assertIn("(Aziz K.)", link)

    def test_maxsus_belgilar_ekranlanadi(self):
        link = formatting.manager_link(mgr(team="A & B <FC>", name="X"), gw=1)
        self.assertIn("A &amp; B &lt;FC&gt;", link)


class TestPost(unittest.TestCase):
    def build(self, review):
        return formatting.gw_review_post(
            gw=3,
            event={"average_entry_score": 52, "highest_score": 128,
                   "top_element_info": {"id": 5, "points": 16}},
            players={5: {"web_name": "Haaland"}},
            leader=("J. Anderson", 214),
            reviews=[review],
        )

    def test_asosiy_qismlar(self):
        review = LeagueReview(label="🏆 Test", total_managers=529, average=54.3,
                              best=mgr(name="Aziz", event_total=97),
                              top=[mgr(rank=1, total=187, overall_rank=142118, behind_leader=-27)])
        text = self.build(review)
        self.assertIn("📈 <b>GW3 yakunlari</b>", text)
        self.assertIn("<b>🌍 Overall</b>", text)
        self.assertIn("<b>🏆 Test · 529 ta jamoa</b>", text)
        self.assertIn("O'rtacha: 54 ochko", text)
        self.assertIn("🔥", text)  # turning eng yaxshi menejeri qatori
        self.assertIn("— 97 ochko", text)
        self.assertIn("⭐️ Tur yulduzi: Haaland — 16 ochko", text)

    def test_koterilish_yozilmaydi_agar_yoq_bolsa(self):
        review = LeagueReview(label="🏆 Test", total_managers=10, average=50.0,
                              best=mgr(), top=[mgr()], riser=None)
        self.assertNotIn("Eng katta ko'tarilish", self.build(review))

    def test_bosh_liga(self):
        review = LeagueReview(label="🏆 Test", total_managers=0)
        text = self.build(review)
        self.assertIn("<b>🏆 Test · 0 ta jamoa</b>", text)
        self.assertIn(config.GW_REVIEW_HASHTAG, text)


class TestVaqt(unittest.TestCase):
    def test_oxirgi_yakunlangan_tur(self):
        bs = {"events": [{"id": 1, "finished": True}, {"id": 2, "finished": True},
                         {"id": 3, "finished": False}]}
        self.assertEqual(gw_review.last_finished_event(bs)["id"], 2)

    def test_yakunlangan_tur_yoq(self):
        self.assertIsNone(gw_review.last_finished_event({"events": [{"id": 1, "finished": False}]}))

    def test_tur_tugagan_kun(self):
        fixtures = [{"kickoff_time": "2026-08-22T14:00:00Z"},
                    {"kickoff_time": "2026-08-23T15:30:00Z"}]
        # 15:30 UTC + 2 soat = 17:30 UTC = 22:30 Toshkent -> o'sha kun
        self.assertEqual(gw_review.event_end_date(fixtures, "Asia/Tashkent"), "2026-08-23")

    def test_kechqurungi_oyin_ertangi_kunga_otadi(self):
        # 20:00 UTC + 2 soat = 22:00 UTC = 03:00 Toshkent (ertasi kun)
        fixtures = [{"kickoff_time": "2026-08-23T20:00:00Z"}]
        self.assertEqual(gw_review.event_end_date(fixtures, "Asia/Tashkent"), "2026-08-24")


if __name__ == "__main__":
    unittest.main()
