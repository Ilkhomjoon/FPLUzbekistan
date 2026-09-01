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
import time
from datetime import datetime, timedelta, timezone
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


def night_key(moment: datetime | None = None) -> str:
    """Post qaysi "kecha"ga tegishli ekanini aniqlaydi.

    Post 23:00 da chiqadi va tongi 03:30 gacha yangilanib boradi — ya'ni bitta
    post ikki kalendar kunga tegib ketadi. Shuning uchun kunni yarim tunda
    emas, PRICE_WATCH_NIGHT_ENDS (odatda 12:00) da kesamiz:

      31-avgust 23:00  -> "2026-08-31"
      1-sentyabr 03:00 -> "2026-08-31"   (o'sha kechaning yangilanishi)
      1-sentyabr 23:00 -> "2026-09-01"   (YANGI kecha, yangi post)

    Yarim tunni chegara qilib bo'lmaydi: unda 00:17 dagi post 07:19 da
    "yangi kun" bo'lib qaytadan chiqib ketardi (28-avgust holati).
    """
    local = ZoneInfo(config.LOCAL_TZ)
    ref = (moment or datetime.now(timezone.utc)).astimezone(local)
    hour, _, minute = config.PRICE_WATCH_NIGHT_ENDS.partition(":")
    edge = ref.replace(hour=int(hour), minute=int(minute or 0), second=0, microsecond=0)
    day = ref.date() if ref >= edge else ref.date() - timedelta(days=1)
    return day.isoformat()


def state_night(state: dict) -> str | None:
    """Saqlangan holat qaysi kechaga tegishli. Eski fayllarda `night` yo'q —
    u holda oxirgi yozuv vaqtidan kelib chiqamiz."""
    if state.get("night"):
        return state["night"]
    stamp = state.get("posted_at")
    if not stamp:
        return None
    try:
        return night_key(datetime.fromisoformat(stamp))
    except ValueError:
        return None


def _snapshot(bootstrap: dict, seen: set[int] | None = None) -> tuple[list, list, str]:
    """Joriy holat. `seen` berilsa, unda yo'q futbolchilar 🆕 bilan belgilanadi."""
    rises, falls = candidates(bootstrap)
    if seen is not None:
        for row in rises + falls:
            row["new"] = row["id"] not in seen
    stamp = datetime.now(timezone.utc).astimezone(ZoneInfo(config.LOCAL_TZ)).strftime("%H:%M")
    return rises, falls, price_watch_post(rises, falls, stamp)


def run(force: bool = False, window: str | None = None, update: bool = False) -> int:
    """Kechqurungi bashorat posti.

    `update=True` bo'lsa post chiqqandan keyin ham jarayon yashab qoladi va
    PRICE_WATCH_UPDATE_UNTIL gacha xuddi shu xabarni har soatda tahrirlaydi —
    foizlar tun davomida o'zgarib turadi, xabar esa yangi bo'lib qoladi.
    """
    config.require_telegram()
    budget_end = waiter.budget(config.PRICE_WATCH_MAX_MINUTES)

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
    # Har kecha o'ziniki: 23:00 dagi post tongi 03:30 gacha yangilanadi, keyin
    # yopiladi. Ertasi kechqurun — YANGI post, kechagisiga tegilmaydi.
    night = night_key(now)
    same_night = state_night(state) == night
    message_id = state.get("message_id") if same_night else None
    if same_night and not force and not message_id:
        log.info("Bu kecha (%s) allaqachon tekshirilgan, post chiqmagan — takrorlamaymiz.",
                 night)
        return 0
    if message_id:
        log.info("Shu kechagi xabar bor (id=%s) — yangisini yubormay, tahrirlaymiz.",
                 message_id)
    elif state.get("message_id"):
        log.info("Oxirgi post %s kechasiniki edi — bugun (%s) yangisi chiqadi.",
                 state_night(state), night)

    update_until = waiter.local_time_today(config.PRICE_WATCH_UPDATE_UNTIL)
    last_text = state.get("last_text") if message_id else None
    # Birinchi postdagi futbolchilar. Keyin qo'shilganlari 🆕 bilan chiqadi.
    seen: set[int] | None = set(state.get("seen") or []) if message_id else None
    # Postning o'z vaqti. Soatlik yangilanishlar buni oldinga surmaydi —
    # aks holda ertasi kechqurun "hali 20 soat o'tmagan" bo'lib qolardi va
    # yangi post o'rniga kechagisi tahrirlanardi (1-sentyabr holati).
    posted_at = state.get("posted_at") if same_night else None

    while True:
        rises, falls, text = _snapshot(fpl_api.get_bootstrap(), seen)
        log.info("Ko'tarilishi mumkin: %d ta, tushishi mumkin: %d ta", len(rises), len(falls))

        if not rises and not falls and not message_id:
            log.info("Chegaradan (%d%%) oshgan futbolchi yo'q — post yuborilmaydi.",
                     config.PRICE_WATCH_MIN)
            storage.save(config.PRICE_WATCH_STATE_FILE, {
                "date": today, "night": night, "message_id": None,
                "posted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
            return 0

        if message_id is None:
            for r in rises + falls:
                log.info("  %s %.1f%%", r["label"], r["percent"])
            message_id = telegram.send_message(text).get("message_id")
            seen = {r["id"] for r in rises + falls}
            log.info("Narx bashorati posti yuborildi (id=%s)", message_id)
        elif text != last_text:
            added = [r["label"] for r in rises + falls if r.get("new")]
            telegram.edit_message(message_id, text)
            log.info("Xabar yangilandi (id=%s)%s", message_id,
                     f" — yangi: {', '.join(added)}" if added else "")
        else:
            log.info("O'zgarish yo'q — xabar o'sha holicha qoldi.")

        last_text = text
        stamp_now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        posted_at = posted_at or stamp_now
        storage.save(config.PRICE_WATCH_STATE_FILE, {
            "date": today,
            "night": night,
            "message_id": message_id,
            "last_text": text,
            "seen": sorted(seen or ()),
            # `posted_at` — postning o'zi chiqqan vaqt, yangilanishlar uni
            # oldinga surmaydi; `updated_at` — oxirgi tahrir.
            "posted_at": posted_at,
            "updated_at": stamp_now,
        })

        if not update:
            return 0
        if not waiter.sleep_until(
            min(update_until, waiter.now_utc() + timedelta(seconds=config.PRICE_WATCH_INTERVAL)),
            label="Keyingi yangilanish", budget_end=budget_end,
        ):
            log.info("Jarayon vaqti tugadi — yangilanishlar to'xtatildi.")
            return 0
        if waiter.now_utc() >= update_until:
            log.info("Yangilanish oynasi (%s) yakunlandi.", config.PRICE_WATCH_UPDATE_UNTIL)
            return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Ertangi narx o'zgarishi bashorati")
    ap.add_argument("--dry-run", action="store_true", help="Telegramga yubormasdan terminalga chiqaradi")
    ap.add_argument("--force", action="store_true", help="Bugun chiqarilgan bo'lsa ham qayta chiqaradi")
    ap.add_argument("--post-at", default=None, metavar="HH:MM",
                    help="Shu vaqtgacha kutib turadi (cron kechiksa ham post o'z vaqtida chiqadi)")
    ap.add_argument("--window", default=None, metavar="HH:MM-HH:MM",
                    help="Faqat shu oynada chiqaradi (cron juda kechiksa post umuman chiqmaydi)")
    ap.add_argument("--update", action="store_true",
                    help="Postdan keyin xabarni PRICE_WATCH_UPDATE_UNTIL gacha yangilab boradi")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    if args.dry_run:
        config.DRY_RUN = True

    try:
        if not (args.force or args.dry_run):
            waiter.hold_until(args.post_at, label="Narx bashorati",
                              budget_end=waiter.budget(config.PRICE_WATCH_MAX_MINUTES))
        return run(force=args.force, window=args.window, update=args.update)
    except Exception as exc:
        log.exception("Narx bashorati skriptida xatolik")
        telegram.notify_admin(f"⚠️ <b>FPL bot (narx bashorati)</b>\n<code>{telegram.esc(repr(exc))}</code>")
        return 1


if __name__ == "__main__":
    sys.exit(main())
