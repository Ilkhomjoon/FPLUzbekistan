"""FPL ning inglizcha izohlarini o'zbekchaga o'girish.

FPL `news` maydoni erkin matn emas — qolipli: deyarli har doim
`<sabab> - <qachon qaytadi>` ko'rinishida bo'ladi va lug'ati o'ttiz-qirq
iboradan oshmaydi:

    "Hamstring injury - Expected back 14 Nov"
    "Knock - Unknown return date"
    "Suspended - Expected back 21 Nov"

Shuning uchun tarjima xizmati kerak emas (GitHub Actions'da u yo'q ham):
lug'at va bir nechta qoida yetarli. Tanimagan ibora INGLIZCHA QOLADI —
noto'g'ri tarjima qilgandan ko'ra, asl matnni ko'rsatgan yaxshi. Bunday
holatlar logga yoziladi, keyin lug'atga qo'shib boramiz.
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger("news_uz")

MONTHS = {
    "jan": "yanvar", "feb": "fevral", "mar": "mart", "apr": "aprel",
    "may": "may", "jun": "iyun", "jul": "iyul", "aug": "avgust",
    "sep": "sentyabr", "oct": "oktyabr", "nov": "noyabr", "dec": "dekabr",
}

# Tana a'zolari — "<a'zo> injury" qolipi uchun
BODY = {
    "hamstring": "son orqa mushagi",
    "calf": "boldir",
    "thigh": "son",
    "groin": "chov",
    "ankle": "to'piq",
    "knee": "tizza",
    "back": "bel",
    "shoulder": "yelka",
    "foot": "oyoq panjasi",
    "toe": "oyoq barmog'i",
    "heel": "tovon",
    "hip": "son-chanoq",
    "head": "bosh",
    "facial": "yuz",
    "face": "yuz",
    "rib": "qovurg'a",
    "chest": "ko'krak",
    "neck": "bo'yin",
    "wrist": "bilak",
    "hand": "qo'l",
    "arm": "qo'l",
    "finger": "barmoq",
    "elbow": "tirsak",
    "achilles": "axill payi",
    "muscle": "mushak",
    "abdominal": "qorin mushagi",
    "quad": "son old mushagi",
    "hernia": "churra",
    "leg": "oyoq",
    "eye": "ko'z",
    "jaw": "jag'",
    "shin": "boldir suyagi",
}

# To'liq iboralar (kichik harflarda solishtiriladi)
PHRASES = {
    "knock": "zarba olgan",
    "minor knock": "kichik zarba olgan",
    "injury": "jarohat",
    "illness": "kasallik",
    "virus": "virus",
    "fitness": "jismoniy holati yetarli emas",
    "lack of match fitness": "o'yin holatiga kirmagan",
    "match fitness": "o'yin holatiga kirmagan",
    "concussion": "miya chayqalishi",
    "suspended": "diskvalifikatsiya",
    "suspension": "diskvalifikatsiya",
    "red card": "qizil kartochka",
    "international duty": "terma jamoada",
    "personal reasons": "shaxsiy sabablar",
    "family reasons": "oilaviy sabablar",
    "compassionate leave": "oilaviy sabablarga ko'ra ta'tilda",
    "loan": "ijaraga berilgan",
    "on loan": "ijaraga berilgan",
    "transferred": "boshqa klubga o'tgan",
    "left the club": "klubni tark etgan",
    "not in squad": "qaydnomada yo'q",
    "not in the squad": "qaydnomada yo'q",
    "lack of fitness": "jismoniy holati yetarli emas",
    "unavailable": "o'ynay olmaydi",
    "doubtful": "shubhali",
    "rested": "dam olmoqda",
    "returned to training": "mashg'ulotlarga qaytdi",
    "in training": "mashg'ulotlarda",
    "unknown return date": "qaytish sanasi noma'lum",
    "no return date": "qaytish sanasi noma'lum",
    "out for season": "mavsum oxirigacha o'ynamaydi",
    "out for the season": "mavsum oxirigacha o'ynamaydi",
    "season ending injury": "mavsumni yakunlagan jarohat",
    "unknown": "noma'lum",
    "knee surgery": "tizza operatsiyasi",
    "surgery": "operatsiya",
    "ill": "kasal",
    "injured": "jarohatlangan",
    "fit": "sog'lom",
}

# Boshlanishiga qarab tanaladigan iboralar: FPL ularning oxiriga "ahead of
# the weekend" kabi qo'shimchalar qo'shadi, lekin ma'no boshida turadi.
PREFIXES = (
    ("to be assessed", "holati baholanmoqda"),
    ("being assessed", "holati baholanmoqda"),
    ("awaiting scan", "tekshiruv natijasi kutilmoqda"),
    ("awaiting results", "tekshiruv natijasi kutilmoqda"),
    ("late fitness test", "o'yin oldidan tekshiriladi"),
    ("has not trained", "mashg'ulot qilmagan"),
    ("not trained", "mashg'ulot qilmagan"),
    ("expected to be fit", "o'yinga tayyor bo'lishi kutilmoqda"),
    ("doubt for", "o'ynashi shubhali"),
    ("out of favour", "murabbiy rejasida yo'q"),
)

# "75% chance of playing" — bu ma'lumot postda alohida qator bilan chiqadi,
# shuning uchun izoh ichida takrorlanmaydi
_CHANCE = re.compile(r"^\d{1,3}%\s+chance of playing", re.I)
_EXPECTED = re.compile(r"^expected back\s+(\d{1,2})\s+([a-z]{3})", re.I)
_EXPECTED_BARE = re.compile(r"^expected back\s*$", re.I)
_INJURY = re.compile(r"^(.+?)\s+injury$", re.I)
_SURGERY = re.compile(r"^(.+?)\s+surgery$", re.I)


def _part(text: str) -> str | None:
    """Bitta bo'lakni o'giradi. None — bu bo'lak umuman kerak emas."""
    raw = text.strip().strip(".")
    if not raw:
        return None
    low = raw.lower()

    if _CHANCE.match(low):
        return None                                  # takror ma'lumot

    if low in PHRASES:
        return PHRASES[low]

    m = _EXPECTED.match(low)
    if m:
        day, mon = m.group(1), MONTHS.get(m.group(2).lower())
        if mon:
            return f"{int(day)}-{mon}da qaytishi kutilmoqda"

    if _EXPECTED_BARE.match(low):
        return "qaytishi kutilmoqda"

    m = _INJURY.match(low)
    if m:
        body = BODY.get(m.group(1).strip())
        if body:
            return f"{body} jarohati"

    m = _SURGERY.match(low)
    if m:
        body = BODY.get(m.group(1).strip())
        if body:
            return f"{body} operatsiyasi"

    for prefix, uzbek in PREFIXES:
        if low.startswith(prefix):
            return uzbek

    log.info("Tarjima lug'atida yo'q: %r", raw)
    return raw                                       # inglizcha qoladi


def translate(news: str | None) -> str:
    """FPL izohini o'zbekchaga o'giradi.

    Bo'laklar " - " bilan ajraladi. Tarjima qilinmagan bo'lak asl holida
    qoladi, butunlay keraksizi (takror foiz) tashlab yuboriladi.
    """
    if not news:
        return ""
    parts = [p for p in re.split(r"\s+-\s+|\s+–\s+", news.strip()) if p.strip()]
    out = [_part(p) for p in parts]
    kept = [p for p in out if p]
    if not kept:
        return ""
    text = ", ".join(kept)
    return text[0].upper() + text[1:]
