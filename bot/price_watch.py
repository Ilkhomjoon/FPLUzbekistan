"""Kechqurungi post — ertaga narxi o'zgarishi mumkin bo'lgan futbolchilar.

FPL 2026/27 da rasmiy "Price Change Predictor" qo'shdi. `bootstrap-static`
ichida har bir futbolchi uchun quyidagilar bor:

  price_change_percent      — hozirgi holat (masalan "24.4")
  price_change_projections  — [{offset: 0, projected_percent: "38.2", likelihood: 2}, ...]
                              offset 0 = eng yaqin o'zgarish (shu kecha)
  price_change_locked_until — futbolchi vaqtincha qulflangan bo'lsa
  price_change_calibrating  — ma'lumot hali ishonchsiz

Musbat foiz — ko'tarilish tomon, manfiy — tushish tomon. 100% dan oshgani
o'zgarish kutilayotganini bildiradi.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import config, fpl_api, storage, telegram, waiter
from .formatting import price_watch_post

log = logging.getLogger("price_watch")


def projection(player: dict, offset: int = 0) -> float | None:
    """Futbolchining `offset` raqamli o'zgarish uchun bashorat foizi."""
    for row in player.get("price_change_projections") or []:
        if row.get("offset") == offset:
            try:
                return float(row.get("projected_percent"))
            except (TypeError, ValueError):
                return None
    return None


def eligible(player: dict) -> bool:
    """Qulflangan, o'yindan olib tashlangan va kalibrlanayotganlar hisobga olinmaydi."""
    if player.get("removed"):
        return False
    if player.get("price_change_locked_until"):
        return False
    if player.get("price_change_calibrating"):
        return False
    return True


def candidates(bootstrap: dict, offset: int = 0) -> tuple[list[dict], list[dict]]:
    """(ko'tarilishi mumkin, tushishi mumkin) — har biri saralangan ro'yxat."""
    from .formatting import _player_label

    teams = fpl_api.teams_by_id(bootstrap)
    players = fpl_api.players_by_id(bootstrap)

    rises: list[dict] = []
    falls: list[dict] = []
    for p in bootstrap["elements"]:
        if not eligible(p):
            continue
        pct = projection(p, offset)
        if pct is None or abs(pct) < config.PRICE_WATCH_MIN:
            continue
        row = {
            "id": p["id"],
            "label": _player_label(p["id"], players, teams),
            "cost": p["now_cost"],
            "percent": pct,
        }
        (rises if pct > 0 else falls).append(row)

    rises.sort(key=lambda r: -r["percent"])
    falls.sort(key=lambda r: r["percent"])
    return rises[: config.PRICE_WATCH_MAX], falls[: config.PRICE_WATCH_MAX]


def run(force: bool = False, window: str | None = None) -> int:
    config.require_telegram()

    local = ZoneInfo(config.LOCAL_TZ)
    now = datetime.now(timezone.utc).astimezone(local)
    today = now.date().isoformat()

    # Oxirgi himoya: cron bir necha soat kechikkan bo'lsa, "ertaga narxi
    # o'zgaradi" degan postni ertalab yuborib qo'ymaymiz.
    if not force and not waiter.in_window(window, now):
        log.info("Hozir %s — post oynasi (%s) tashqarisida, chiqarilmaydi.",
                 now.strftime("%H:%M"), window)
        return 0

    state = storage.load(config.PRICE_WATCH_STATE_FILE, {}) or {}
    # Kalendar kuniga emas, o'tgan vaqtga qaraymiz: 23:00 dagi post yarim tundan
    # keyin "yangi kun" bo'lgani uchun takrorlanib ketmasin.
    if not force and waiter.recent(state.get("posted_at"), config.PRICE_WATCH_REPEAT_HOURS):
        log.info("Oxirgi post %s da chiqqan — %g soat ichida takrorlamaymiz.",
                 state.get("posted_at"), config.PRICE_WATCH_REPEAT_HOURS)
        return 0
    if state.get("date") == today and not force:
        log.info("%s uchun post allaqachon chiqarilgan.", today)
        return 0

    bootstrap = fpl_api.get_bootstrap()
    rises, falls = candidates(bootstrap)
    log.info("Ko'tarilishi mumkin: %d ta, tushishi mumkin: %d ta", len(rises), len(falls))
    for r in rises + falls:
        log.info("  %s %.1f%%", r["label"], r["percent"])

    if not rises and not falls:
        log.info("Chegaradan (%d%%) oshgan futbolchi yo'q — post yuborilmaydi.",
                 config.PRICE_WATCH_MIN)
        storage.save(config.PRICE_WATCH_STATE_FILE, {
            "date": today, "message_id": None,
            "posted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        return 0

    text = price_watch_post(rises, falls, now.strftime("%H:%M"))
    res = telegram.send_message(text)
    storage.save(config.PRICE_WATCH_STATE_FILE, {
        "date": today,
        "message_id": res.get("message_id"),
        "posted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    log.info("Narx bashorati posti yuborildi.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Ertangi narx o'zgarishi bashorati")
    ap.add_argument("--dry-run", action="store_true", help="Telegramga yubormasdan terminalga chiqaradi")
    ap.add_argument("--force", action="store_true", help="Bugun chiqarilgan bo'lsa ham qayta chiqaradi")
    ap.add_argument("--post-at", default=None, metavar="HH:MM",
                    help="Shu vaqtgacha kutib turadi (cron kechiksa ham post o'z vaqtida chiqadi)")
    ap.add_argument("--window", default=None, metavar="HH:MM-HH:MM",
                    help="Faqat shu oynada chiqaradi (cron juda kechiksa post umuman chiqmaydi)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    if args.dry_run:
        config.DRY_RUN = True

    try:
        if not (args.force or args.dry_run):
            waiter.hold_until(args.post_at, label="Narx bashorati",
                              budget_end=waiter.budget(config.PRICE_WATCH_MAX_MINUTES))
        return run(force=args.force, window=args.window)
    except Exception as exc:
        log.exception("Narx bashorati skriptida xatolik")
        telegram.notify_admin(f"⚠️ <b>FPL bot (narx bashorati)</b>\n<code>{telegram.esc(repr(exc))}</code>")
        return 1


if __name__ == "__main__":
    sys.exit(main())
