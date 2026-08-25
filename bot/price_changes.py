"""Har kungi narx o'zgarishlarini aniqlab, kanalga post qiladi.

Ishlash tartibi:
  1. FPL API'dan barcha futbolchilarning hozirgi narxini oladi
  2. data/prices.json dagi kechagi snapshot bilan solishtiradi
  3. Farq bo'lsa — avval "narx tushishi", keyin "narx ko'tarilishi" postini yuboradi
  4. Farq bo'lmasa — hech narsa yubormaydi, faqat logga yozadi
  5. Yangi snapshot'ni saqlaydi
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone

from . import config, fpl_api, storage, telegram, waiter
from .formatting import price, price_change_post

log = logging.getLogger("price_changes")


def build_snapshot(bootstrap: dict) -> dict:
    teams = fpl_api.teams_by_id(bootstrap)
    return {
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": fpl_api.current_event_id(bootstrap),
        "players": {
            str(p["id"]): {
                "name": p["web_name"],
                "cost": p["now_cost"],
                "team": teams.get(p["team"], {}).get("short_name", ""),
            }
            for p in bootstrap["elements"]
        },
    }


def diff(old: dict, new: dict) -> tuple[list[dict], list[dict]]:
    """Eski va yangi snapshot'ni solishtiradi -> (tushganlar, ko'tarilganlar)"""
    down: list[dict] = []
    up: list[dict] = []
    old_players = (old or {}).get("players", {})
    for pid, cur in new["players"].items():
        prev = old_players.get(pid)
        if not prev:  # yangi qo'shilgan futbolchi — birinchi marta ko'ryapmiz
            continue
        if cur["cost"] == prev["cost"]:
            continue
        row = {
            "id": int(pid),
            "name": cur["name"],
            "team": cur["team"],
            "old": prev["cost"],
            "new": cur["cost"],
        }
        (down if cur["cost"] < prev["cost"] else up).append(row)
    return down, up


def run(force: bool = False) -> int:
    config.require_telegram()
    bootstrap = fpl_api.get_bootstrap()
    new_snap = build_snapshot(bootstrap)
    old_snap = storage.load(config.PRICE_STATE_FILE)

    if not old_snap:
        storage.save(config.PRICE_STATE_FILE, new_snap)
        log.info("Birinchi ishga tushirish: %d futbolchi saqlandi, post yo'q.", len(new_snap["players"]))
        return 0

    down, up = diff(old_snap, new_snap)
    log.info("Narx tushgan: %d ta, ko'tarilgan: %d ta", len(down), len(up))

    if not down and not up and not force:
        log.info("O'zgarish yo'q — kanalga hech narsa yuborilmadi.")
        storage.save(config.PRICE_STATE_FILE, new_snap)
        return 0

    publish(down, up, new_snap)
    return 0


def publish(down: list[dict], up: list[dict], new_snap: dict) -> None:
    """Postlarni yuboradi va yangi snapshot'ni saqlaydi."""
    for row in down + up:
        log.info("  %s: %s -> %s", row["name"], price(row["old"]), price(row["new"]))

    # Avval narx tushishi, keyin narx ko'tarilishi
    if down:
        for chunk in telegram.split_message(price_change_post(down, "down")):
            telegram.send_message(chunk)
    if up:
        for chunk in telegram.split_message(price_change_post(up, "up")):
            telegram.send_message(chunk)

    storage.save(config.PRICE_STATE_FILE, new_snap)


def watch() -> int:
    """Erta uyg'onib, narx o'zgarishini kutadi va PRICE_POST_AT da yuboradi.

    GitHub cron'i bir soat kechikib uyg'otsa ham post o'z vaqtida chiqsin uchun:
    cron ancha erta qo'yiladi, jarayon esa FPL narxlarni o'zgartirgunicha kutadi,
    so'ng belgilangan daqiqagacha ushlab turadi.
    """
    config.require_telegram()

    old_snap = storage.load(config.PRICE_STATE_FILE)
    if not old_snap:
        snap = build_snapshot(fpl_api.get_bootstrap())
        storage.save(config.PRICE_STATE_FILE, snap)
        log.info("Birinchi ishga tushirish: %d futbolchi saqlandi, post yo'q.", len(snap["players"]))
        return 0

    post_at = waiter.local_time_today(config.PRICE_POST_AT)
    give_up = waiter.local_time_today(config.PRICE_WATCH_UNTIL)
    if give_up <= post_at:
        give_up = post_at + timedelta(minutes=90)
    log.info("Kuzatuv boshlandi. Post vaqti: %s, kutish chegarasi: %s",
             post_at.isoformat(), give_up.isoformat())

    while True:
        new_snap = build_snapshot(fpl_api.get_bootstrap())
        down, up = diff(old_snap, new_snap)
        if down or up:
            log.info("O'zgarish topildi: %d tushgan, %d ko'tarilgan.", len(down), len(up))
            break

        now = waiter.now_utc()
        if now >= give_up:
            log.info("Kutish chegarasi keldi — o'zgarish topilmadi, post yo'q.")
            storage.save(config.PRICE_STATE_FILE, new_snap)
            return 0
        wait = min(config.PRICE_POLL, max(1.0, (give_up - now).total_seconds()))
        log.info("Hozircha o'zgarish yo'q — %.0f soniyadan keyin qayta tekshiramiz.", wait)
        time.sleep(wait)

    waiter.sleep_until(post_at, label="Post vaqtini kutyapmiz")
    publish(down, up, new_snap)
    return 0


def preview() -> int:
    """Haqiqiy ma'lumot bilan post qanday ko'rinishini ko'rsatadi (hech narsa yuborilmaydi).

    Snapshot hali yo'q bo'lganda ham ishlaydi: joriy turdagi haqiqiy narx
    o'zgarishlarini (cost_change_event) olib, shablonni chizib beradi.
    """
    config.DRY_RUN = True
    bootstrap = fpl_api.get_bootstrap()
    teams = fpl_api.teams_by_id(bootstrap)

    field = "cost_change_event"
    rows = [p for p in bootstrap["elements"] if p.get(field)]
    if not rows:  # tur endi boshlangan bo'lsa — mavsum boshidan beri o'zgarishlar
        field = "cost_change_start"
        rows = [p for p in bootstrap["elements"] if p.get(field)]
        log.info("Bu turda o'zgarish yo'q — mavsum boshidan beri bo'lgan o'zgarishlar ko'rsatiladi")

    if not rows:
        log.info("Hech qanday narx o'zgarishi topilmadi.")
        return 0

    def row(p: dict) -> dict:
        return {
            "id": p["id"],
            "name": p["web_name"],
            "team": teams.get(p["team"], {}).get("short_name", ""),
            "old": p["now_cost"] - p[field],
            "new": p["now_cost"],
        }

    down = [row(p) for p in rows if p[field] < 0]
    up = [row(p) for p in rows if p[field] > 0]
    log.info("NAMUNA (%s): tushgan %d ta, ko'tarilgan %d ta", field, len(down), len(up))

    if down:
        telegram.send_message(price_change_post(down, "down"))
    if up:
        telegram.send_message(price_change_post(up, "up"))
    if not down and not up:
        log.info("O'zgarish yo'q — kanalga hech narsa yuborilmasdi.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="FPL narx o'zgarishlari posti")
    ap.add_argument("--dry-run", action="store_true", help="Telegramga yubormasdan terminalga chiqaradi")
    ap.add_argument("--preview", action="store_true",
                    help="Haqiqiy ma'lumot bilan post namunasini ko'rsatadi (hech narsa yuborilmaydi)")
    ap.add_argument("--force", action="store_true", help="O'zgarish bo'lmasa ham postni ko'rsatadi (test uchun)")
    ap.add_argument("--reset", action="store_true", help="Snapshot'ni qaytadan oladi va postsiz chiqadi")
    ap.add_argument("--watch", action="store_true",
                    help="Narx o'zgarishini kutadi va PRICE_POST_AT da yuboradi (cron kechikishiga qarshi)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    if args.dry_run:
        config.DRY_RUN = True

    if args.preview:
        try:
            return preview()
        except Exception:
            log.exception("Namuna ko'rsatishda xatolik")
            return 1

    if args.reset:
        storage.save(config.PRICE_STATE_FILE, build_snapshot(fpl_api.get_bootstrap()))
        log.info("Snapshot yangilandi.")
        return 0

    try:
        return watch() if args.watch else run(force=args.force)
    except Exception as exc:
        log.exception("Narx skriptida xatolik")
        telegram.notify_admin(f"⚠️ <b>FPL bot xatoligi (narx)</b>\n<code>{telegram.esc(repr(exc))}</code>")
        return 1


if __name__ == "__main__":
    sys.exit(main())
