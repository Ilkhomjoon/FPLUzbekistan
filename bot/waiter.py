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
    """"06:00" -> bugungi shu vaqt (LOCAL_TZ bo'yicha), UTC ko'rinishida.

    Agar bu vaqt allaqachon 12 soatdan ko'proq oldin o'tgan bo'lsa, ertangi kun
    tushuniladi. Shu tufayli yarim tunda ishga tushgan jarayon ham to'g'ri
    kunni tanlaydi.
    """
    tz = ZoneInfo(config.LOCAL_TZ)
    ref = (base or now_utc()).astimezone(tz)
    hour, _, minute = hhmm.partition(":")
    target = ref.replace(hour=int(hour), minute=int(minute or 0), second=0, microsecond=0)
    if target < ref - timedelta(hours=12):
        target += timedelta(days=1)
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


def hold_until(hhmm: str | None, label: str = "Post vaqtini kutyapmiz") -> None:
    """LOCAL_TZ bo'yicha "HH:MM" kelguncha ushlab turadi. Vaqt o'tgan bo'lsa — darhol davom etadi.

    Cron erta qo'yiladi, post esa aynan kerakli daqiqada chiqadi.
    """
    if not hhmm:
        return
    target = local_time_today(hhmm)
    if target > now_utc():
        sleep_until(target, label=label)


def _hhmmss(dt: datetime) -> str:
    return dt.astimezone(ZoneInfo(config.LOCAL_TZ)).strftime("%H:%M:%S")
