"""BPS asosida bonus ochkolarni hisoblash.

FPL qoidalari:
  - eng yuqori BPS -> 3 ochko, ikkinchi -> 2, uchinchi -> 1
  - 1-o'rinda 2 kishi teng bo'lsa: ikkalasi ham 3, keyingisi 1 (2 berilmaydi)
  - 1-o'rinda 3+ kishi teng bo'lsa: hammasi 3, boshqa hech kim olmaydi
  - 2-o'rinda 2+ kishi teng bo'lsa: hammasi 2, 1 berilmaydi
  - 3-o'rinda teng bo'lsa: hammasi 1
"""
from __future__ import annotations

from collections import OrderedDict


def bonus_from_bps(bps_rows: list[dict]) -> dict[int, int]:
    """[{'element': id, 'value': bps}, ...] -> {element_id: bonus}"""
    if not bps_rows:
        return {}

    # bir xil BPS qiymatiga ega o'yinchilarni guruhlaymiz (kamayish tartibida)
    groups: "OrderedDict[int, list[int]]" = OrderedDict()
    for row in sorted(bps_rows, key=lambda r: -int(r["value"])):
        groups.setdefault(int(row["value"]), []).append(int(row["element"]))

    tiers = list(groups.items())  # [(bps, [element_ids]), ...]
    result: dict[int, int] = {}

    if not tiers:
        return result

    first_bps, first = tiers[0]
    if first_bps <= 0:  # hali hech kim ochko to'plamagan
        return result
    for e in first:
        result[e] = 3

    if len(first) >= 3:
        return result

    if len(first) == 2:
        # 2 berilmaydi, keyingi guruh 1 oladi
        if len(tiers) > 1:
            for e in tiers[1][1]:
                result[e] = 1
        return result

    # len(first) == 1
    if len(tiers) < 2:
        return result
    second_bps, second = tiers[1]
    for e in second:
        result[e] = 2
    if len(second) >= 2:
        return result  # 1 berilmaydi
    if len(tiers) > 2:
        for e in tiers[2][1]:
            result[e] = 1
    return result


def fixture_bonus(fixture: dict) -> tuple[dict[int, int], bool]:
    """O'yin uchun bonuslarni qaytaradi.

    Qaytaradi: ({element_id: bonus}, official) —
    official=True bo'lsa FPL rasmiy bonusni allaqachon berib bo'lgan.
    """
    from .fpl_api import fixture_stat

    official = [r for r in fixture_stat(fixture, "bonus") if int(r["value"]) > 0]
    if official:
        return {int(r["element"]): int(r["value"]) for r in official}, True
    return bonus_from_bps(fixture_stat(fixture, "bps")), False
