"""Jonli bonus ochkolar — bitta xabar yuborib, uni har daqiqada yangilab boradi.

Ishlash tartibi:
  1. Bugungi (MATCHDAY_TZ bo'yicha) o'yinlarni topadi
  2. Birinchi o'yin boshlanishi bilan kanalga yangi xabar yuboradi
  3. Har LIVE_INTERVAL soniyada BPS'ni qayta olib, xabarni tahrirlaydi
  4. O'yin tugagach 🔴 -> 🟢 ga o'zgaradi va rasmiy bonus qo'yiladi
  5. Kunning barcha o'yinlari tugagach, oxirgi yangilanishdan so'ng chiqadi
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config, fpl_api, storage, telegram
from .formatting import live_bonus_post

log = logging.getLogger("live_bonus")


# ---------------- yordamchilar ----------------

def matchday_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return now.astimezone(ZoneInfo(config.MATCHDAY_TZ)).date().isoformat()


def fixture_day(fx: dict) -> str | None:
    ko = fx.get("kickoff_time")
    if not ko:
        return None
    dt = datetime.fromisoformat(ko.replace("Z", "+00:00"))
    return dt.astimezone(ZoneInfo(config.MATCHDAY_TZ)).date().isoformat()


def todays_fixtures(all_fixtures: list[dict], day: str) -> list[dict]:
    return [f for f in all_fixtures if fixture_day(f) == day]


def commit_state() -> None:
    """GitHub Actions'da holatni darhol repoga saqlash uchun (ixtiyoriy)."""
    import os

    cmd = os.getenv("STATE_COMMIT_CMD")
    if not cmd:
        return
    try:
        subprocess.run(cmd, shell=True, check=False, timeout=120)
    except Exception as exc:
        log.warning("Holatni commit qilib bo'lmadi: %s", exc)


def is_done(fx: dict) -> bool:
    return bool(fx.get("finished") or fx.get("finished_provisional"))


def fetch_defcon(event_ids: list[int], fixtures: list[dict], players: dict) -> dict[int, dict[int, int]]:
    """Har bir o'yin uchun DefCon oluvchilarni yig'adi: {fixture_id: {element_id: ochko}}"""
    from . import defcon as defcon_mod

    out: dict[int, dict[int, int]] = {}
    for ev in event_ids:
        fids = [f["id"] for f in fixtures if f.get("started") and f.get("event") == ev]
        if not fids:
            continue
        live = fpl_api.get_live(ev)
        out.update(defcon_mod.by_fixture(live, fids, players))
    return out


# ---------------- asosiy sikl ----------------

def run(once: bool = False) -> int:
    config.require_telegram()

    bootstrap = fpl_api.get_bootstrap()
    bootstrap_at = time.monotonic()
    players = fpl_api.players_by_id(bootstrap)
    teams = fpl_api.teams_by_id(bootstrap)
    gw = fpl_api.current_event_id(bootstrap)

    day = matchday_key()
    all_fixtures = fpl_api.get_fixtures()
    today = todays_fixtures(all_fixtures, day)

    if not today:
        log.info("%s sanasida o'yin yo'q — chiqamiz.", day)
        return 0

    event_ids = sorted({f["event"] for f in today if f.get("event")})
    kickoffs = [f["kickoff_time"] for f in today if f.get("kickoff_time")]
    first_ko = min(datetime.fromisoformat(k.replace("Z", "+00:00")) for k in kickoffs)
    now = datetime.now(timezone.utc)

    if now < first_ko - timedelta(minutes=config.LIVE_START_LEAD) and not once:
        log.info("Birinchi o'yin %s da boshlanadi — hali erta, chiqamiz.", first_ko.isoformat())
        return 0

    if all(is_done(f) for f in today):
        state = storage.load(config.LIVE_STATE_FILE, {})
        if state.get("date") == day and state.get("final"):
            log.info("Bugungi o'yinlar allaqachon yakunlangan va xabar yangilangan — chiqamiz.")
            return 0

    state = storage.load(config.LIVE_STATE_FILE, {}) or {}
    message_id = state.get("message_id") if state.get("date") == day else None
    last_text = state.get("last_text") if state.get("date") == day else None

    deadline = time.monotonic() + config.LIVE_MAX_MINUTES * 60
    all_done_since: float | None = None
    defcon_cache: dict[int, dict[int, int]] = {}
    defcon_at = 0.0

    while True:
        try:
            # bootstrap'ni har 30 daqiqada yangilaymiz (yangi futbolchi/nom o'zgarishi uchun)
            if time.monotonic() - bootstrap_at > 1800:
                bootstrap = fpl_api.get_bootstrap()
                bootstrap_at = time.monotonic()
                players = fpl_api.players_by_id(bootstrap)
                teams = fpl_api.teams_by_id(bootstrap)
                gw = fpl_api.current_event_id(bootstrap) or gw

            fresh: list[dict] = []
            for ev in event_ids or [gw]:
                fresh.extend(fpl_api.get_fixtures(event=ev))
            today = todays_fixtures(fresh, day) or today

            any_started = any(f.get("started") for f in today)
            all_done = all(is_done(f) for f in today)

            if any_started and config.SHOW_DEFCON and time.monotonic() - defcon_at > config.DEFCON_TTL:
                try:
                    defcon_cache = fetch_defcon(event_ids or [gw], today, players)
                    defcon_at = time.monotonic()
                    log.debug("DefCon yangilandi: %d o'yin", len(defcon_cache))
                except Exception as exc:
                    # DefCon olinmasa ham bonus posti to'xtamasligi kerak
                    log.warning("DefCon ma'lumotini olib bo'lmadi: %s", exc)

            if any_started:
                text = live_bonus_post(today, players, teams, gw, defcon=defcon_cache)

                if message_id is None:
                    res = telegram.send_message(text)
                    message_id = res.get("message_id")
                    last_text = text
                    storage.save(
                        config.LIVE_STATE_FILE,
                        {"date": day, "message_id": message_id, "last_text": text, "final": all_done},
                    )
                    commit_state()  # xabar id'sini darhol saqlaymiz
                    log.info("Yangi jonli xabar yuborildi (id=%s)", message_id)
                elif text != last_text:
                    try:
                        telegram.edit_message(message_id, text)
                    except telegram.TelegramError as exc:
                        # xabar o'chirilgan bo'lsa — yangisini yuboramiz
                        if any(s in str(exc).lower() for s in ("message to edit not found", "message_id_invalid",
                                                              "message can't be edited")):
                            log.warning("Eski xabar topilmadi, yangisini yuboramiz")
                            message_id = None
                            last_text = None
                            continue
                        raise
                    last_text = text
                    storage.save(
                        config.LIVE_STATE_FILE,
                        {"date": day, "message_id": message_id, "last_text": text, "final": all_done},
                    )
                    log.info("Xabar yangilandi (id=%s)", message_id)
                else:
                    log.debug("O'zgarish yo'q, tahrirlash o'tkazib yuborildi")
            else:
                log.info("Bugungi o'yinlar hali boshlanmadi (%d ta o'yin)", len(today))

            if all_done and any_started:
                if all_done_since is None:
                    all_done_since = time.monotonic()
                    log.info("Barcha o'yinlar tugadi — rasmiy bonus uchun %d daqiqa kuzatamiz",
                             config.LIVE_FINISH_GRACE)
                elif time.monotonic() - all_done_since > config.LIVE_FINISH_GRACE * 60:
                    storage.save(
                        config.LIVE_STATE_FILE,
                        {"date": day, "message_id": message_id, "last_text": last_text, "final": True},
                    )
                    commit_state()
                    log.info("Kun yakunlandi.")
                    return 0
        except Exception as exc:
            log.exception("Sikl ichida xatolik (davom etamiz)")
            telegram.notify_admin(f"⚠️ <b>FPL bot (live bonus)</b>\n<code>{telegram.esc(repr(exc))}</code>")

        if once:
            return 0
        if time.monotonic() > deadline:
            log.warning("Vaqt limiti tugadi — chiqamiz (keyingi cron davom ettiradi).")
            storage.save(
                config.LIVE_STATE_FILE,
                {"date": day, "message_id": message_id, "last_text": last_text, "final": False},
            )
            commit_state()
            return 0
        time.sleep(config.LIVE_INTERVAL)


def main() -> int:
    ap = argparse.ArgumentParser(description="FPL jonli bonus ochkolar")
    ap.add_argument("--dry-run", action="store_true", help="Telegramga yubormasdan terminalga chiqaradi")
    ap.add_argument("--once", action="store_true", help="Faqat bir marta yangilab chiqadi")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    if args.dry_run:
        config.DRY_RUN = True

    try:
        return run(once=args.once)
    except Exception as exc:
        log.exception("Live skriptida xatolik")
        telegram.notify_admin(f"⚠️ <b>FPL bot xatoligi (live)</b>\n<code>{telegram.esc(repr(exc))}</code>")
        return 1


if __name__ == "__main__":
    sys.exit(main())
