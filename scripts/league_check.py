"""Ligalarni va deadline'dan keyingi ma'lumotni tekshirish (bir martalik razvedka).

Nima aniqlaydi:
  1. Joriy tur, deadline vaqti, chiplar ma'lumoti allaqachon bormi
  2. Har bir liganing hajmi (nechta jamoa)
  3. Bitta tarkib so'rovi necha soniya oladi
  4. Shundan kelib chiqib: to'liq skanerlash va top-N skanerlash qancha vaqt oladi

Ishlatish:
    python -m scripts.league_check
    python -m scripts.league_check --leagues 137243 251 --workers 6
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import config, fpl_api  # noqa: E402

PAGE_SIZE = 50


# ---------------- liga ----------------

def standings_page(league_id: int, page: int) -> dict:
    return fpl_api._get(f"/leagues-classic/{league_id}/standings/", page_standings=page)


def league_size(league_id: int) -> tuple[str, int, int]:
    """(liga nomi, taxminiy jamoalar soni, sarflangan so'rovlar soni).

    Sahifalarni birma-bir aylanib chiqmaymiz — avval ikki barobar sakraymiz,
    keyin ikkilik qidiruv bilan oxirgi sahifani topamiz. 50 000 jamoali liga
    ham ~20 ta so'rovda aniqlanadi.
    """
    calls = 1
    first = standings_page(league_id, 1)
    name = first.get("league", {}).get("name", f"#{league_id}")
    results = first.get("standings", {}).get("results", [])
    if not first.get("standings", {}).get("has_next"):
        return name, len(results), calls

    lo, hi = 1, 2
    while True:  # oxirgi sahifadan oshib ketguncha ikki barobar sakraymiz
        page = standings_page(league_id, hi)
        calls += 1
        if page.get("standings", {}).get("has_next"):
            lo, hi = hi, hi * 2
        else:
            break

    while lo < hi - 1:  # ikkilik qidiruv
        mid = (lo + hi) // 2
        page = standings_page(league_id, mid)
        calls += 1
        if page.get("standings", {}).get("has_next"):
            lo = mid
        else:
            hi = mid

    last = standings_page(league_id, hi)
    calls += 1
    total = (hi - 1) * PAGE_SIZE + len(last.get("standings", {}).get("results", []))
    return name, total, calls


def sample_entries(league_id: int, limit: int) -> list[int]:
    """Reyting bo'yicha birinchi `limit` ta jamoa id'sini oladi."""
    out: list[int] = []
    page = 1
    while len(out) < limit:
        data = standings_page(league_id, page)
        rows = data.get("standings", {}).get("results", [])
        if not rows:
            break
        out.extend(r["entry"] for r in rows)
        if not data.get("standings", {}).get("has_next"):
            break
        page += 1
    return out[:limit]


def picks(entry_id: int, event: int) -> dict:
    return fpl_api._get(f"/entry/{entry_id}/event/{event}/picks/")


# ---------------- hisobot ----------------

def human(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m} daq {s:02d} son" if m else f"{s} soniya"


def main() -> int:
    ap = argparse.ArgumentParser(description="Liga va API razvedkasi")
    ap.add_argument("--leagues", type=int, nargs="+", default=[137243, 251])
    ap.add_argument("--workers", type=int, default=6, help="parallel so'rovlar soni")
    ap.add_argument("--sample", type=int, default=30, help="tezlikni o'lchash uchun nechta tarkib olinsin")
    args = ap.parse_args()

    print("\n=== 1. Joriy tur ===")
    bs = fpl_api.get_bootstrap()
    ev = next((e for e in bs["events"] if e.get("is_current")), None) \
        or next((e for e in bs["events"] if e.get("is_next")), None)
    if not ev:
        print("Tur topilmadi.")
        return 1

    local = ZoneInfo(config.LOCAL_TZ)
    deadline = datetime.fromisoformat(ev["deadline_time"].replace("Z", "+00:00"))
    print(f"  GW{ev['id']} — {ev.get('name')}")
    print(f"  deadline: {deadline.astimezone(local):%Y-%m-%d %H:%M} (Toshkent)")
    passed = "ha" if datetime.now(timezone.utc) > deadline else "yo'q"
    print(f"  o'tdimi: {passed}")
    print(f"  finished={ev.get('finished')}  data_checked={ev.get('data_checked')}")

    players = fpl_api.players_by_id(bs)
    mc = ev.get("most_captained")
    print(f"\n  most_captained: {players.get(mc, {}).get('web_name', mc)}  (soni berilmaydi)")
    print(f"  most_selected:  {players.get(ev.get('most_selected'), {}).get('web_name', '—')}")
    print(f"  most_vice_captained: {players.get(ev.get('most_vice_captained'), {}).get('web_name', '—')}")

    chips = ev.get("chip_plays") or []
    chip_state = "BOR" if chips else "HALI BO'SH"
    print(f"\n  chip_plays: {chip_state}")
    for c in chips:
        print(f"    {c.get('chip_name')}: {c.get('num_played'):,}")

    print("\n=== 2. Ligalar ===")
    sizes: dict[int, tuple[str, int]] = {}
    for lid in args.leagues:
        try:
            started = time.monotonic()
            name, total, calls = league_size(lid)
            sizes[lid] = (name, total)
            print(f"  {lid}: {name} — ~{total:,} ta jamoa "
                  f"({calls} ta so'rov, {time.monotonic() - started:.1f} s)")
        except Exception as exc:
            print(f"  {lid}: XATO — {exc}")

    print("\n=== 3. Tarkib so'rovi tezligi ===")
    first_league = args.leagues[0]
    try:
        entries = sample_entries(first_league, args.sample)
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            got = list(pool.map(lambda e: picks(e, ev["id"]), entries))
        elapsed = time.monotonic() - started
        per = elapsed / max(1, len(got))
        rate = len(got) / elapsed
        print(f"  {len(got)} ta tarkib / {elapsed:.1f} s "
              f"({args.workers} ta parallel) -> {rate:.1f} ta/soniya")

        ok = got[0]
        cap = next((p for p in ok["picks"] if p.get("is_captain")), None)
        vc = next((p for p in ok["picks"] if p.get("is_vice_captain")), None)
        print(f"  namuna: kapitan={players.get(cap['element'], {}).get('web_name') if cap else '—'}, "
              f"vitse={players.get(vc['element'], {}).get('web_name') if vc else '—'}, "
              f"chip={ok.get('active_chip') or 'yo‘q'}")

        print("\n=== 4. Baholash ===")
        for lid, (name, total) in sizes.items():
            print(f"  {name}:")
            for n in (total, 1000, 500):
                if n > total and n != total:
                    continue
                print(f"    {min(n, total):>6,} ta jamoa -> {human(min(n, total) / rate)}")
    except Exception as exc:
        print(f"  XATO — {exc}")
        print("  (deadline o'tmagan bo'lsa tarkiblar hali yopiq bo'lishi mumkin)")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
