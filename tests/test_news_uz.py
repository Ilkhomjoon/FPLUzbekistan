"""FPL izohlarini o'zbekchaga o'girish."""
from __future__ import annotations

import unittest

from bot.news_uz import translate


class TranslateTest(unittest.TestCase):
    def test_the_usual_two_part_shape(self):
        self.assertEqual(translate("Hamstring injury - Expected back 14 Nov"),
                         "Son orqa mushagi jarohati, 14-noyabrda qaytishi kutilmoqda")

    def test_a_knock_without_a_date(self):
        self.assertEqual(translate("Knock - Unknown return date"),
                         "Zarba olgan, qaytish sanasi noma'lum")

    def test_a_suspension(self):
        self.assertEqual(translate("Suspended - Expected back 21 Dec"),
                         "Diskvalifikatsiya, 21-dekabrda qaytishi kutilmoqda")

    def test_every_body_part_keeps_the_injury_word(self):
        for english, uzbek in (("Ankle injury", "To'piq jarohati"),
                               ("Knee injury", "Tizza jarohati"),
                               ("Calf injury", "Boldir jarohati"),
                               ("Achilles injury", "Axill payi jarohati")):
            self.assertEqual(translate(english), uzbek)

    def test_the_chance_is_not_repeated(self):
        """O'ynash ehtimoli postda alohida chiqadi — izohda takrorlanmasin."""
        self.assertEqual(translate("Knock - 75% chance of playing"), "Zarba olgan")

    def test_only_a_chance_leaves_nothing(self):
        self.assertEqual(translate("50% chance of playing"), "")

    def test_an_unknown_phrase_stays_in_english(self):
        """Noto'g'ri tarjima qilgandan ko'ra asl matnni ko'rsatamiz."""
        self.assertEqual(translate("Tweaked something odd - Expected back 3 Jan"),
                         "Tweaked something odd, 3-yanvarda qaytishi kutilmoqda")

    def test_an_unknown_body_part_is_not_mangled(self):
        self.assertEqual(translate("Metatarsal injury"), "Metatarsal injury")

    def test_empty_input(self):
        self.assertEqual(translate(""), "")
        self.assertEqual(translate(None), "")

    def test_a_single_part(self):
        self.assertEqual(translate("Illness"), "Kasallik")
        self.assertEqual(translate("Lack of match fitness"), "O'yin holatiga kirmagan")

    def test_a_long_dash_also_separates(self):
        self.assertEqual(translate("Illness – Unknown return date"),
                         "Kasallik, qaytish sanasi noma'lum")

    def test_the_month_is_read_case_insensitively(self):
        self.assertEqual(translate("Expected back 7 NOV"), "7-noyabrda qaytishi kutilmoqda")

    def test_surgery(self):
        self.assertEqual(translate("Knee surgery - Out for season"),
                         "Tizza operatsiyasi, mavsum oxirigacha o'ynamaydi")

    def test_a_trailing_qualifier_is_trimmed(self):
        """FPL "ahead of the weekend" kabi quyruq qo'shadi — ma'no boshida."""
        self.assertEqual(translate("Knock - To be assessed ahead of the weekend"),
                         "Zarba olgan, holati baholanmoqda")

    def test_awaiting_a_scan(self):
        self.assertEqual(translate("Ankle injury - Awaiting scan results"),
                         "To'piq jarohati, tekshiruv natijasi kutilmoqda")

    def test_the_result_starts_with_a_capital(self):
        self.assertTrue(translate("groin injury").startswith("Chov"))


if __name__ == "__main__":
    unittest.main()
