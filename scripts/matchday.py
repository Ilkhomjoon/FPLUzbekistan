"""Bugun jonli kuzatuv kerakmi? — GitHub Actions uchun darvoza.

GitHub cron'ni shartli qilib bo'lmaydi: u har kuni bir xil ishlaydi. Shuning
uchun ishning boshida shu skript bir marta so'rov yuborib qaraydi:

  - bugun (MATCHDAY_TZ bo'yicha) o'yin bormi?
  - yoki oxirgi o'yin tugaganiga LIVE_ACTIVE_AFTER soatdan kam vaqt o'tdimi?
    (rasmiy bonus va DefCon shu oraliqda yakunlanadi — xabarni yangilash kerak)

Ikkalasi ham yo'q bo'lsa `active=false` qaytaradi va workflow qolgan
qadamlarni umuman bajarmaydi: na kuzatuv, na cron kechikishi haqida xabar.

Ishlatish:
    python -m scripts.matchday          # GITHUB_OUTPUT ga active=true|false yozadi
    python -m scripts.matchday --print  # faqat terminalga chiqaradi
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import config, fpl_api  # noqa: E402

MATCH_LENGTH = timedelta(hours=2)  # o'yin taxminan shuncha davom etadi


def _kickoffs(fixtures: list[dict]) -> list[datetime]:
    out = []
    for f in fixtures:
        ko = f.get("kickoff_time")
        if ko:
            out.append(datetime.fromisoformat(ko.replace("Z", "+00:00")))
    return sorted(out)


def verdict(fixtures: list[dict], now: datetime | None = None) -> tuple[bool, str]:
    """(kerakmi, sabab)"""
    now = now or datetime.now(timezone.utc)
    tz = ZoneInfo(config.MATCHDAY_TZ)
    today = now.astimezone(tz).date()

    kickoffs = _kickoffs(fixtures)
    if not kickoffs:
        return False, "o'yinlar ro'yxati bo'sh"

    todays = [k for k in kickoffs if k.astimezone(tz).date() == today]
    if todays:
        first = min(todays).astimezone(tz).strftime("%H:%M")
        return True, f"bugun {len(todays)} ta o'yin bor (birinchisi {first})"

    past = [k for k in kickoffs if k <= now]
    if past:
        last_end = max(past) + MATCH_LENGTH
        hours = (now - last_end).total_seconds() / 3600
        if 0 <= hours <= config.LIVE_ACTIVE_AFTER:
            return True, (f"oxirgi o'yin {hours:.1f} soat oldin tugadi "
                          f"(chegara {config.LIVE_ACTIVE_AFTER} soat) — "
                          f"rasmiy bonus hali yangilanishi mumkin")
        return False, (f"bugun o'yin yo'q, oxirgisi {hours:.1f} soat oldin tugagan "
                       f"(chegara {config.LIVE_ACTIVE_AFTER} soat)")

    return False, "bugun o'yin yo'q"


def main() -> int:
    ap = argparse.ArgumentParser(description="Bugun jonli kuzatuv kerakmi?")
    ap.add_argument("--print", action="store_true", help="GITHUB_OUTPUT ga yozmaydi")
    args = ap.parse_args()

    try:
        active, reason = verdict(fpl_api.get_fixtures())
    except Exception as exc:
        # API javob bermasa ishni to'xtatmaymiz — skript o'zi tekshirib chiqadi
        active, reason = True, f"o'yinlar ro'yxati olinmadi ({exc}) — ehtiyot uchun davom etamiz"

    print(("✅ Kuzatuv kerak" if active else "⏭️  O'tkazib yuboriladi") + f" — {reason}")

    out = os.getenv("GITHUB_OUTPUT")
    if out and not args.print:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"active={'true' if active else 'false'}\n")
            f.write(f"reason={reason}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
