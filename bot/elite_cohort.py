"""Muzlatilgan top-1000 menejerlar ro'yxati (kogorta).

Nega muzlatamiz
---------------
Reytingning eng tepasi har turda almashib turadi. Agar har hafta "o'sha
paytdagi top-1000" ni skanerlasak, egalikdagi o'sish ikki narsadan iborat
bo'ladi: kuchlilar haqiqatan sotib olgani VA ro'yxat tarkibi almashgani.
Ikkinchisi bir tomonga qiyshaygan — top-1000 ga aynan o'tgan turda ko'p
ochko olgan futbolchiga ega menejerlar kiradi. Natijada "kuchlilar nimaga
ishonmoqda" o'rniga "kim o'tgan turda ko'p ochko oldi" o'lchanadi.

Shuning uchun ro'yxat bir marta olinadi va saqlab qo'yiladi: har hafta
AYNAN o'sha 1000 menejer skanerlanadi. Maxraj o'zgarmaydi, demak haftalik
foizlar bir-biriga to'g'ridan-to'g'ri solishtiriladi.

Qachon yangilanadi
------------------
Ro'yxat abadiy emas: vaqt o'tib uning a'zolari pastga tushadi. Har safar
joriy top-1000 bilan kesishma sanaladi; qolganlar ELITE_COHORT_MIN (500)
dan kam bo'lsa — ro'yxat o'sha turdan qaytadan olinadi.

Muhim: kesishma faqat O'LCHAGICH. Skaner har doim to'liq 1000 ta bo'yicha
ketadi. Tushib ketganlarni chiqarib tashlash — biz qochayotgan qiyshayishning
o'zi bo'lardi: ular tushgan, chunki o'tgan turda ochko olmagan.

Har bir tur yozuvi qaysi ro'yxat bo'yicha hisoblangani bilan belgilanadi
(`cohort: 9`), chart esa faqat bir xil belgili turlarni solishtiradi.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from . import config, storage

log = logging.getLogger(__name__)


@dataclass
class Cohort:
    entries: list[int] = field(default_factory=list)
    from_event: int = 0           # ro'yxat qaysi turdan keyin olingan
    survivors: int | None = None  # shulardan nechtasi hozir ham top-1000 da
    refreshed: bool = False       # shu chaqiruvda yangilandimi

    def __bool__(self) -> bool:
        return bool(self.entries)


def load() -> dict:
    return storage.load(config.ELITE_COHORT_FILE, {}) or {}


def save(entries: list[int], from_event: int) -> dict:
    data = {
        "from_event": from_event,
        "size": len(entries),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entries": list(entries),
    }
    storage.save(config.ELITE_COHORT_FILE, data)
    return data


def survivors(entries: list[int], current: list[int]) -> int:
    return len(set(entries) & set(current))


def resolve(gw: int, size: int, fetch: Callable[[int], list[int]],
            refresh: bool = True, min_keep: int | None = None) -> Cohort:
    """Skanerlanadigan menejerlar ro'yxati.

    `fetch(size)` — joriy reytingdan birinchi `size` ta jamoani oladi.
    `refresh=False` bo'lsa ro'yxat faqat o'qiladi (backfill uchun: o'tmishni
    to'ldirayotganda ro'yxat almashib ketmasligi kerak).
    """
    min_keep = config.ELITE_COHORT_MIN if min_keep is None else min_keep
    stored = load()
    entries = [int(e) for e in (stored.get("entries") or [])]

    if not entries:
        if not refresh:
            # O'qish rejimi: yo'q ro'yxatni shu yerda yaratmaymiz. Ro'yxat
            # haftalik skaner paytida tuziladi — backfill uni o'zgartirmasin.
            log.info("Saqlangan ro'yxat yo'q, o'qish rejimida tuzilmaydi.")
            return Cohort()
        fresh = fetch(size)
        if not fresh:
            log.warning("Dunyo bo'yicha reyting olinmadi — kogorta tuzilmadi.")
            return Cohort()
        save(fresh, gw)
        log.info("Kogorta tuzildi: GW%d holatidagi %d ta menejer.", gw, len(fresh))
        return Cohort(fresh, gw, survivors=len(fresh), refreshed=True)

    from_event = int(stored.get("from_event") or 0)
    if not refresh:
        return Cohort(entries, from_event)

    current = fetch(size)
    if not current:
        # reyting o'qilmadi — eski ro'yxat bilan davom etaveramiz
        log.warning("Joriy reyting o'qilmadi, kogorta tekshirilmadi.")
        return Cohort(entries, from_event)

    alive = survivors(entries, current)
    if alive >= min_keep:
        log.info("Kogorta GW%d dan: %d tadan %d tasi hali ham top-%d da.",
                 from_event, len(entries), alive, size)
        return Cohort(entries, from_event, survivors=alive)

    log.info("Kogortada %d ta qoldi (chegara %d) — GW%d dan yangi ro'yxat olinadi.",
             alive, min_keep, gw)
    save(current, gw)
    return Cohort(current, gw, survivors=len(current), refreshed=True)
