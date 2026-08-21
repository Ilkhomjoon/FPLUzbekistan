"""Defensive Contribution (DefCon) ochkolarini aniqlash.

FPL qoidasi (2025/26 da joriy etilgan, 2026/27 da ham o'zgarmagan):
  - Himoyachi (DEF): bir o'yinda 10+ CBIT -> 2 ochko
        CBIT = clearances + blocks + interceptions + tackles
  - Yarim himoyachi va hujumchi (MID/FWD): bir o'yinda 12+ CBIRT -> 2 ochko
        CBIRT = CBIT + ball recoveries
  - Darvozabon (GK): bu ochkoni ololmaydi
  - Bir o'yinda maksimum 2 ochko (20 ta harakat qilsa ham 2 ta)

Asosiy manba — FPL'ning o'zi bergan `defensive_contribution` identifikatori
(`/api/event/{gw}/live/` ichidagi `explain` bloki). Agar API uni bermasa,
yuqoridagi qoida bo'yicha o'zimiz hisoblaymiz.
"""
from __future__ import annotations

DEFCON_POINTS = 2
GK, DEF, MID, FWD = 1, 2, 3, 4

THRESHOLDS = {DEF: 10, MID: 12, FWD: 12}


def actions(stats: dict, element_type: int | None) -> int | None:
    """Futbolchining hisobga olinadigan mudofaa harakatlari soni."""
    if element_type not in THRESHOLDS:
        return None  # darvozabon yoki noma'lum pozitsiya
    cbi = int(stats.get("clearances_blocks_interceptions") or 0)
    tackles = int(stats.get("tackles") or 0)
    total = cbi + tackles
    if element_type in (MID, FWD):
        total += int(stats.get("recoveries") or 0)
    return total


def qualifies(stats: dict, element_type: int | None) -> bool:
    total = actions(stats, element_type)
    threshold = THRESHOLDS.get(element_type or 0)
    return bool(threshold and total is not None and total >= threshold)


def from_live(live: dict, fixture_id: int, players: dict) -> dict[int, int]:
    """`/event/{gw}/live/` javobidan bitta o'yin uchun DefCon oluvchilarni ajratadi.

    Qaytaradi: {element_id: ochko}
    """
    out: dict[int, int] = {}
    for el in live.get("elements") or []:
        eid = el.get("id")
        explains = el.get("explain") or []
        mine = [ex for ex in explains if ex.get("fixture") == fixture_id]
        if not mine:
            continue

        awarded = 0
        for ex in mine:
            for s in ex.get("stats") or []:
                if s.get("identifier") == "defensive_contribution":
                    awarded = max(awarded, int(s.get("points") or 0))
        if awarded > 0:
            out[eid] = awarded
            continue

        # Zaxira yo'l: API `defensive_contribution` bermasa o'zimiz hisoblaymiz.
        # Faqat bu turda futbolchining bitta o'yini bo'lsa ishonchli
        # (`stats` tur bo'yicha yig'indi bo'lgani uchun ikki o'yinda aralashib ketadi).
        if len(explains) == 1:
            et = players.get(eid, {}).get("element_type")
            if qualifies(el.get("stats") or {}, et):
                out[eid] = DEFCON_POINTS
    return out


def by_fixture(live: dict, fixture_ids: list[int], players: dict) -> dict[int, dict[int, int]]:
    """Bir nechta o'yin uchun bir yo'la: {fixture_id: {element_id: ochko}}"""
    return {fid: from_live(live, fid, players) for fid in fixture_ids}
