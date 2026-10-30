"""Deadline yopilgach — sardorlar va chiplar statistikasi.

Tur boshlanishidan oldin FPL bir soatga yangilanish rejimiga o'tadi va
tarkiblarni ko'rib bo'lmaydi. Shu oynada kanalga statistik post chiqaramiz:

  - qaysi futbolchi eng ko'p sardor qilingan (ligalarimizda va overall)
  - nechta jamoa qaysi chipni yoqqan

Ligalar bo'yicha ma'lumot har bir jamoaning tarkibini alohida so'rash bilan
yig'iladi (`/entry/{id}/event/{gw}/picks/`), shuning uchun liga qancha katta
bo'lsa shuncha uzoq davom etadi.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import config, fpl_api, storage, telegram, waiter
from .formatting import deadline_stats_post

log = logging.getLogger("deadline_stats")


@dataclass
class LeagueScan:
    league_id: int
    name: str
    scanned: int = 0
    failed: int = 0
    captains: Counter = field(default_factory=Counter)
    vice: Counter = field(default_factory=Counter)
    chips: Counter = field(default_factory=Counter)


# ---------------- liga ma'lumotlari ----------------

def league_entries(league_id: int, limit: int | None = None) -> tuple[str, list[int]]:
    """Ligadagi jamoalarning id'lari (reyting tartibida) va liga nomi."""
    name = f"#{league_id}"
    entries: list[int] = []
    page = 1
    while True:
        data = fpl_api._get(f"/leagues-classic/{league_id}/standings/", page_standings=page)
        name = data.get("league", {}).get("name", name)
        rows = data.get("standings", {}).get("results", [])
        entries.extend(r["entry"] for r in rows)
        if limit and len(entries) >= limit:
            return name, entries[:limit]
        if not rows or not data.get("standings", {}).get("has_next"):
            return name, entries
        page += 1


def scan_league(league_id: int, event: int, limit: int | None = None,
                workers: int | None = None) -> LeagueScan:
    """Ligadagi har bir jamoaning sardori, vitse-sardori va chipini yig'adi."""
    workers = workers or config.STATS_WORKERS
    name, entries = league_entries(league_id, limit)
    scan = LeagueScan(league_id=league_id, name=name)
    log.info("%s: %d ta jamoa skanerlanmoqda (%d ta parallel)", name, len(entries), workers)
    started = time.monotonic()

    def one(entry_id: int) -> dict | None:
        try:
            return fpl_api._get(f"/entry/{entry_id}/event/{event}/picks/")
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for data in pool.map(one, entries):
            if not data:
                scan.failed += 1
                continue
            scan.scanned += 1
            for p in data.get("picks") or []:
                if p.get("is_captain"):
                    scan.captains[p["element"]] += 1
                elif p.get("is_vice_captain"):
                    scan.vice[p["element"]] += 1
            chip = data.get("active_chip")
            if chip:
                scan.chips[chip] += 1

    log.info("%s: %d ta olindi, %d ta o'tkazib yuborildi, %.0f soniya",
             name, scan.scanned, scan.failed, time.monotonic() - started)
    return scan


def overall_chips(event_data: dict) -> Counter:
    """bootstrap-static ichidagi tayyor chip statistikasi (so'rovsiz)."""
    out: Counter = Counter()
    for c in event_data.get("chip_plays") or []:
        name = c.get("chip_name")
        if name:
            out[name] = int(c.get("num_played") or 0)
    return out


# ---------------- vaqt oynasi ----------------

def first_kickoff(fixtures: list[dict]) -> datetime | None:
    times = [f["kickoff_time"] for f in fixtures if f.get("kickoff_time")]
    if not times:
        return None
    return min(datetime.fromisoformat(t.replace("Z", "+00:00")) for t in times)


def target_event(bootstrap: dict, state: dict, force: bool, wait: bool) -> dict | None:
    """Qaysi tur uchun statistika chiqaramiz.

    FPL `is_current` bayrog'ini faqat deadline o'tgach keyingi turga o'tkazadi.
    Undan oldin bot joriy tur sifatida o'tgan turni ko'radi — uniki esa
    allaqachon chiqarilgan, shuning uchun jim chiqib ketardi va kutish
    mexanizmi umuman ishga tushmasdi.

    23-oktyabrda (GW8, juma kuni) aynan shu bo'ldi: deadline 17:30 da, o'yin
    19:00 da — oradagi 90 daqiqaga bitta ham cron tushmadi va post chiqmadi.

    Shuning uchun joriy tur uchun post allaqachon chiqarilgan bo'lsa, keyingi
    turga qaraymiz: deadline'i yaqin bo'lsa, o'sha vaqtgacha kutib turamiz.
    """
    events = bootstrap.get("events", [])
    current = next((e for e in events if e.get("is_current")), None)
    nxt = next((e for e in events if e.get("is_next")), None)
    # Taqqoslash "teng emas" emas, "kichik" bo'yicha: keyingi tur uchun post
    # chiqib bo'lgach, `is_current` hali eski turda turadi — tenglikka
    # qarasak, o'tgan turning statistikasi ikkinchi marta chiqib ketardi.
    posted = state.get("event") or 0
    if current and (force or posted < current.get("id", 0)):
        return current
    if not wait or force:
        return None
    if nxt and posted < nxt.get("id", 0):
        return nxt
    return None


def run(force: bool = False, wait: bool = False) -> int:
    config.require_telegram()

    bootstrap = fpl_api.get_bootstrap()
    state = storage.load(config.STATS_STATE_FILE, {}) or {}
    event = target_event(bootstrap, state, force, wait)
    if not event:
        current = next((e for e in bootstrap.get("events", []) if e.get("is_current")), None)
        if current:
            log.info("GW%d uchun statistika allaqachon chiqarilgan.", current.get("id"))
        else:
            log.info("Joriy tur yo'q — chiqamiz.")
        return 0

    gw = event["id"]
    now = datetime.now(timezone.utc)
    deadline = datetime.fromisoformat(event["deadline_time"].replace("Z", "+00:00"))
    fixtures = fpl_api.get_fixtures(event=gw)
    kickoff = first_kickoff(fixtures)
    if not kickoff:
        log.info("GW%d uchun o'yin vaqti topilmadi.", gw)
        return 0

    minutes_left = (kickoff - now).total_seconds() / 60

    # --wait: cron kechikkan yoki erta kelgan bo'lsa ham post o'z vaqtida
    # chiqsin uchun jarayon chiqib ketmaydi, kerakli daqiqagacha kutib turadi.
    # Maqsad vaqti — deadline bilan "o'yingacha STATS_LEAD daqiqa" dan
    # KECHROG'I: tarkiblar deadline'da qotadi, shuning uchun undan oldin
    # chiqarib bo'lmaydi.
    target = max(deadline, kickoff - timedelta(minutes=config.STATS_LEAD))
    if wait and not force and now < target:
        ahead = (target - now).total_seconds() / 60
        if ahead > config.STATS_WAKE_LEAD:
            log.info("GW%d uchun post vaqtigacha %.0f daqiqa — hali erta (uyg'onish "
                     "chegarasi %d).", gw, ahead, config.STATS_WAKE_LEAD)
            return 0
        log.info("GW%d: post vaqtigacha %.0f daqiqa — %s gacha kutamiz.",
                 gw, ahead, target.isoformat())
        waiter.sleep_until(target, label="Deadline statistikasi",
                           budget_end=waiter.budget(config.STATS_MAX_MINUTES))
        now = datetime.now(timezone.utc)
        minutes_left = (kickoff - now).total_seconds() / 60
        bootstrap = fpl_api.get_bootstrap()
        event = next((e for e in bootstrap["events"] if e.get("id") == gw), event)

    if now < deadline:
        log.info("Deadline hali o'tmagan (%s) — chiqamiz.", deadline.isoformat())
        return 0

    if not force:
        if minutes_left > config.STATS_LEAD:
            log.info("Birinchi o'yingacha %.0f daqiqa — hali erta (chegara %d).",
                     minutes_left, config.STATS_LEAD)
            return 0
        if minutes_left < config.STATS_MIN_LEAD:
            log.info("Birinchi o'yingacha %.0f daqiqa — kech qoldik, o'tkazib yuboramiz.",
                     minutes_left)
            return 0

    log.info("GW%d statistikasi yig'ilmoqda (o'yingacha %.0f daqiqa)", gw, minutes_left)
    players = fpl_api.players_by_id(bootstrap)
    teams = fpl_api.teams_by_id(bootstrap)

    scans = []
    for league_id, label in config.STATS_LEAGUES:
        try:
            scan = scan_league(league_id, gw, config.STATS_MAX_ENTRIES)
            scans.append((label, scan))
        except Exception as exc:
            log.error("Liga %s skanerlanmadi: %s", league_id, exc)
            telegram.notify_admin(
                f"⚠️ <b>Deadline statistikasi</b>\nLiga {league_id}: <code>{telegram.esc(repr(exc))}</code>"
            )

    if not scans:
        log.error("Hech qanday liga skanerlanmadi — post yuborilmaydi.")
        return 1

    text = deadline_stats_post(
        gw=gw,
        scans=scans,
        players=players,
        teams=teams,
        overall_captain=event.get("most_captained"),
        overall_chip_counts=overall_chips(event),
    )

    res = telegram.send_message(text)
    storage.save(config.STATS_STATE_FILE, {
        "event": gw,
        "message_id": res.get("message_id"),
        "posted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    log.info("Statistika posti yuborildi (GW%d)", gw)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Deadline statistikasi posti")
    ap.add_argument("--dry-run", action="store_true", help="Telegramga yubormasdan terminalga chiqaradi")
    ap.add_argument("--force", action="store_true",
                    help="Vaqt oynasini va 'allaqachon chiqarilgan' tekshiruvini e'tiborsiz qoldiradi")
    ap.add_argument("--wait", action="store_true",
                    help="Erta uyg'onib, kerakli daqiqagacha kutib turadi (cron kechikishiga qarshi)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    if args.dry_run:
        config.DRY_RUN = True

    try:
        return run(force=args.force, wait=args.wait)
    except Exception as exc:
        log.exception("Statistika skriptida xatolik")
        telegram.notify_admin(f"⚠️ <b>FPL bot (deadline statistikasi)</b>\n<code>{telegram.esc(repr(exc))}</code>")
        return 1


if __name__ == "__main__":
    sys.exit(main())
