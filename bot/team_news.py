"""Jamoa yangiliklari — jarohat, diskvalifikatsiya va tuzalishlar.

FPL `bootstrap-static` da har bir futbolchi uchun uchta maydon bor:

    status                        "a" tayyor, "d" shubhali, "i" jarohat,
                                  "s" diskvalifikatsiya, "u"/"n" o'ynamaydi
    chance_of_playing_next_round  null yoki 0/25/50/75/100
    news                          FPL yozadigan qisqa izoh (inglizcha)

Bot shu uchtasini eslab qoladi va o'zgarganda kanalga xabar beradi.

Chiqish vaqti jadvalga emas, o'zgarishga bog'liq — lekin FPL bizga xabar
bermagani uchun tekshirib turamiz:

  · deadline'gacha NEWS_RUSH_LEAD daqiqa qolganda — jarayon ichida har
    NEWS_INTERVAL soniyada (soatdan qat'i nazar: deadline tongda ham bo'ladi);
  · qolgan paytda — NEWS_WINDOW oynasida bitta tekshiruv;
  · oyna tashqarisida — hech narsa (Britaniyada tun, yangilik bo'lmaydi).

Shu tufayli tashqi cron faqat budilnik bo'lib qoladi: har soat uyg'otadi,
nima qilishni kodning o'zi hal qiladi.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import config, fpl_api, storage, telegram, waiter
from .formatting import team_news_post

log = logging.getLogger("team_news")

# status -> (emoji, nima deb yoziladi)
STATUS_LABELS = {
    "a": ("🟢", "tayyor"),
    "d": ("🟡", "shubhali"),
    "i": ("🔴", "jarohat"),
    "s": ("🟠", "diskvalifikatsiya"),
    "u": ("⚫️", "jamoadan chiqarilgan"),
    "n": ("⚪️", "o'ynay olmaydi"),
}


@dataclass
class Change:
    element_id: int
    name: str
    team: int
    owned: float
    status: str
    chance: int | None
    news: str
    was_status: str | None       # oldingi holat (yangi futbolchi bo'lsa None)

    @property
    def recovered(self) -> bool:
        """Jarohatdan/diskvalifikatsiyadan qaytdimi?"""
        return self.status == "a" and self.was_status not in (None, "a")


def _num(value, default=0.0):
    try:
        return type(default)(value)
    except (TypeError, ValueError):
        return default


def _clean(text: str | None) -> str:
    """Izoh matnini solishtirish uchun bir ko'rinishga keltiramiz."""
    return " ".join((text or "").split())


def snapshot(bootstrap: dict) -> dict[str, dict]:
    """element_id (matn) -> {status, chance, news}.

    Faqat egaligi NEWS_MIN_OWNED% dan yuqori futbolchilar kuzatiladi: aks
    holda har kuni o'nlab begona nom chiqib, post o'qilmas bo'lib qolardi.
    """
    out: dict[str, dict] = {}
    for p in bootstrap.get("elements", []):
        if _num(p.get("selected_by_percent"), 0.0) < config.NEWS_MIN_OWNED:
            continue
        chance = p.get("chance_of_playing_next_round")
        out[str(p["id"])] = {
            "status": p.get("status") or "a",
            "chance": None if chance is None else int(chance),
            "news": _clean(p.get("news")),
        }
    return out


def changes(previous: dict[str, dict], bootstrap: dict) -> list[Change]:
    """Oldingi holat bilan solishtirib, o'zgarganlarini qaytaradi.

    Holat yoki o'ynash ehtimoli o'zgarsa — albatta xabar beramiz. Faqat izoh
    matni o'zgargan bo'lsa, futbolchi tayyor bo'lmagan holatdagina chiqaramiz:
    odatda bu "qachon qaytadi" degan ma'lumotning yangilanishi bo'ladi.
    """
    current = snapshot(bootstrap)
    players = {str(p["id"]): p for p in bootstrap.get("elements", [])}

    rows: list[Change] = []
    for key, now_state in current.items():
        old = previous.get(key)
        if old is None:
            continue                      # birinchi marta ko'rdik — bazaga yozamiz, xolos
        same_state = (old.get("status") == now_state["status"]
                      and old.get("chance") == now_state["chance"])
        if same_state and old.get("news") == now_state["news"]:
            continue
        if same_state and now_state["status"] == "a":
            continue                      # tayyor futbolchining matni o'zgargani — shovqin

        p = players[key]
        rows.append(Change(
            element_id=int(key),
            name=p.get("web_name") or f"#{key}",
            team=p.get("team"),
            owned=_num(p.get("selected_by_percent"), 0.0),
            status=now_state["status"],
            chance=now_state["chance"],
            news=now_state["news"],
            was_status=old.get("status"),
        ))

    # eng ko'p olinganlari tepada tursin
    rows.sort(key=lambda c: -c.owned)
    return rows[: config.NEWS_MAX_ROWS]


def next_deadline(bootstrap: dict) -> datetime | None:
    nxt = next((e for e in bootstrap.get("events", []) if e.get("is_next")), None)
    if not nxt or not nxt.get("deadline_time"):
        return None
    return datetime.fromisoformat(nxt["deadline_time"].replace("Z", "+00:00"))


def rush_mode(bootstrap: dict, now: datetime | None = None) -> bool:
    """Deadline yaqinmi? Unda tez-tez tekshiramiz."""
    deadline = next_deadline(bootstrap)
    if not deadline:
        return False
    now = now or waiter.now_utc()
    minutes = (deadline - now).total_seconds() / 60
    return 0 < minutes <= config.NEWS_RUSH_LEAD


def _publish(rows: list[Change], teams: dict, deadline: datetime | None) -> None:
    left = None
    if deadline:
        minutes = (deadline - waiter.now_utc()).total_seconds() / 60
        if 0 < minutes <= config.NEWS_RUSH_LEAD:
            left = int(minutes)
    telegram.send_message(team_news_post(rows, teams, deadline_in=left))
    for c in rows:
        log.info("  %s %s (%s%%) -> %s/%s", c.name, c.status, f"{c.owned:.1f}",
                 c.status, c.chance)


def check_once(state: dict, bootstrap: dict, teams: dict) -> dict:
    """Bitta tekshiruv: o'zgarishlarni chiqaradi va yangi holatni qaytaradi."""
    previous = state.get("players") or {}
    rows = changes(previous, bootstrap) if previous else []

    if not previous:
        log.info("Birinchi ishga tushirish — hozirgi holat yozib olindi, post yo'q.")
    elif rows:
        log.info("%d ta o'zgarish topildi — xabar yuborilmoqda.", len(rows))
        _publish(rows, teams, next_deadline(bootstrap))
    else:
        log.info("O'zgarish yo'q.")

    return {
        "players": snapshot(bootstrap),
        "checked_at": waiter.now_utc().isoformat(timespec="seconds"),
    }


def run(force: bool = False, once: bool = False, window: str | None = None) -> int:
    config.require_telegram()
    started = waiter.budget(config.NEWS_MAX_MINUTES)

    bootstrap = fpl_api.get_bootstrap()
    teams = fpl_api.teams_by_id(bootstrap)
    state = storage.load(config.NEWS_STATE_FILE, {}) or {}

    rush = rush_mode(bootstrap)
    window = window or config.NEWS_WINDOW
    if not force and not rush and not waiter.in_window(window):
        log.info("Hozir %s — kuzatuv oynasi (%s) tashqarisida va deadline uzoq.",
                 waiter.now_utc().astimezone().strftime("%H:%M"), window)
        return 0

    state = check_once(state, bootstrap, teams)
    storage.save(config.NEWS_STATE_FILE, state)

    if once or force or not rush:
        return 0

    # Deadline yaqin — jarayon yashab qoladi va tez-tez tekshiradi
    deadline = next_deadline(bootstrap)
    log.info("Deadline yaqin (%s) — har %d soniyada tekshiramiz.",
             deadline.isoformat() if deadline else "?", config.NEWS_INTERVAL)
    while True:
        target = waiter.now_utc() + timedelta(seconds=config.NEWS_INTERVAL)
        if deadline and target >= deadline:
            log.info("Deadline keldi — kuzatuv tugadi.")
            return 0
        if not waiter.sleep_until(target, label="Jamoa yangiliklari",
                                  budget_end=started):
            log.info("Jarayon vaqti tugadi — keyingi cron davom ettiradi.")
            return 0
        try:
            bootstrap = fpl_api.get_bootstrap()
            state = check_once(state, bootstrap, teams)
            storage.save(config.NEWS_STATE_FILE, state)
        except Exception as exc:
            log.warning("Tekshiruvda xatolik: %s", exc)


def main() -> int:
    ap = argparse.ArgumentParser(description="Jamoa yangiliklari kuzatuvchisi")
    ap.add_argument("--dry-run", action="store_true", help="Telegramga yubormasdan terminalga chiqaradi")
    ap.add_argument("--force", action="store_true", help="Oyna tekshiruvisiz, hoziroq tekshiradi")
    ap.add_argument("--once", action="store_true", help="Faqat bir marta tekshiradi")
    ap.add_argument("--window", default=None, metavar="HH:MM-HH:MM",
                    help="Kuzatuv oynasi (standart: NEWS_WINDOW)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    if args.dry_run:
        config.DRY_RUN = True

    try:
        return run(force=args.force, once=args.once, window=args.window)
    except Exception as exc:
        log.exception("Jamoa yangiliklari skriptida xatolik")
        telegram.notify_admin(f"⚠️ <b>FPL bot (jamoa yangiliklari)</b>\n<code>{telegram.esc(repr(exc))}</code>")
        return 1


if __name__ == "__main__":
    sys.exit(main())
