"""Kutish yordamchisi — GitHub cron kechikishini yengish uchun.

GitHub Actions ishni **belgilangan daqiqada boshlashga kafolat bermaydi**.
Bizning o'lchovlarimizda o'rtacha kechikish 17 daqiqa, eng yomoni 102 daqiqa
bo'lgan. Lekin ish bir marta boshlangach, uning ichidagi vaqt aniq — `sleep`
soniyagacha to'g'ri ishlaydi.

Shundan kelib chiqib strategiyamiz shunday:

    ❌ "aniq 06:00 da uyg'on"      -> GitHub 07:06 da uyg'otadi, post kechikadi
    ✅ "04:00 da uyg'on, ichida kut" -> GitHub 05:06 da uyg'otsa ham, jarayon
                                       06:00:00 gacha kutib turadi va o'z
                                       vaqtida yuboradi

Ya'ni cron'ning aniqligiga emas, cron'ning *zaxirasiga* tayanamiz.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config

log = logging.getLogger("waiter")

CHUNK = 300  # bir martada ko'pi bilan 5 daqiqa uxlaymiz — log tirik ko'rinsin


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def local_time_today(hhmm: str, base: datetime | None = None) -> datetime:
    """"06:00" -> shu vaqtning ENG YAQIN nusxasi (LOCAL_TZ bo'yicha), UTC da.

    Natija har doim hozirgi vaqtdan ±12 soat ichida bo'ladi:

      - 12 soatdan ko'proq oldin o'tgan bo'lsa -> ertangi kun
      - 12 soatdan ko'proq keyin bo'lsa       -> kechagi kun (ya'ni o'tib ketgan)

    Ikkinchi qoida yarim tundan keyin ishga tushgan jarayon uchun muhim.
    Masalan cron 23:44 da rejalashtirilgan bo'lib, GitHub uni 00:05 da
    uyg'otsa, "23:00" bugungi kechqurunni emas, kechagi (o'tib ketgan)
    vaqtni bildirishi kerak — aks holda jarayon 23 soat kutib qolardi.
    """
    tz = ZoneInfo(config.LOCAL_TZ)
    ref = (base or now_utc()).astimezone(tz)
    hour, _, minute = hhmm.partition(":")
    target = ref.replace(hour=int(hour), minute=int(minute or 0), second=0, microsecond=0)
    if target < ref - timedelta(hours=12):
        target += timedelta(days=1)
    elif target > ref + timedelta(hours=12):
        target -= timedelta(days=1)
    return target.astimezone(timezone.utc)


def sleep_until(target: datetime, label: str = "Kutish",
                budget_end: float | None = None) -> bool:
    """`target` (UTC) kelguncha uxlaydi.

    budget_end — `time.monotonic()` shkalasidagi chegara (job timeout'idan
    oshib ketmaslik uchun). Vaqt yetsa True, byudjet tugab qolsa False.
    """
    while True:
        left = (target - now_utc()).total_seconds()
        if left <= 0:
            return True

        if budget_end is not None and time.monotonic() + left > budget_end:
            log.warning("%s: %s gacha %.0f daqiqa bor, lekin ish vaqti byudjeti yetmaydi.",
                        label, _hhmmss(target), left / 60)
            return False

        if left > 90:
            log.info("%s: %s gacha %.0f daqiqa qoldi.", label, _hhmmss(target), left / 60)
        time.sleep(min(left, CHUNK))


def budget(minutes: int) -> float:
    """`time.monotonic()` shkalasidagi chegara — job timeout'idan oshib ketmaslik uchun."""
    return time.monotonic() + minutes * 60


def hold_until(hhmm: str | None, label: str = "Post vaqtini kutyapmiz",
               budget_end: float | None = None) -> None:
    """LOCAL_TZ bo'yicha "HH:MM" kelguncha ushlab turadi. Vaqt o'tgan bo'lsa — darhol davom etadi.

    Cron ataylab ancha erta qo'yiladi (GitHub 3 soatgacha kechikishi mumkin),
    post esa aynan kerakli daqiqada chiqadi.
    """
    if not hhmm:
        return
    target = local_time_today(hhmm)
    if target > now_utc():
        sleep_until(target, label=label, budget_end=budget_end)


def _minutes(hhmm: str) -> int:
    hour, _, minute = hhmm.partition(":")
    return int(hour) * 60 + int(minute or 0)


def in_window(window: str | None, now: datetime | None = None) -> bool:
    """LOCAL_TZ bo'yicha "20:00-01:00" oynasi ichidamizmi?

    Bu — oxirgi himoya chizig'i. Cron bir necha soat kechikib, jarayon
    tunda chiqishi kerak bo'lgan postni ertalab yuborib qo'ymasligi uchun.
    Oyna yarim tundan o'tishi mumkin (boshi oxiridan katta bo'lsa).
    """
    if not window:
        return True
    start, _, end = window.partition("-")
    if not end:
        return True
    tz = ZoneInfo(config.LOCAL_TZ)
    ref = (now or now_utc()).astimezone(tz)
    cur = ref.hour * 60 + ref.minute
    a, b = _minutes(start), _minutes(end)
    return a <= cur <= b if a <= b else (cur >= a or cur <= b)


def recent(iso: str | None, hours: float, now: datetime | None = None) -> bool:
    """`iso` vaqtidan beri `hours` soatdan kam o'tdimi?

    Kalendar kuniga emas, o'tgan vaqtga qaraymiz: yarim tundan keyin ishga
    tushgan jarayon "yangi kun" deb postni takrorlab yubormasligi kerak.
    """
    if not iso:
        return False
    try:
        when = datetime.fromisoformat(iso)
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (now or now_utc()) - when < timedelta(hours=hours)


def _hhmmss(dt: datetime) -> str:
    return dt.astimezone(ZoneInfo(config.LOCAL_TZ)).strftime("%H:%M:%S")
