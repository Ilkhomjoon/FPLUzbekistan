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
  · oyna tashqarisida — hech narsa (Britaniyada tun, yangilik bo'lmaydi);
  · tur ketayotgan paytda — umuman hech narsa (pastga qarang).

Shu tufayli tashqi cron faqat budilnik bo'lib qoladi: har soat uyg'otadi,
nima qilishni kodning o'zi hal qiladi.

Takror postga qarshi ikki qoida
-------------------------------
FPL ma'lumoti CDN orqali tarqatiladi va turli serverlar turli yoshdagi
nusxani qaytaradi. Deadline oldidan bu sezilarli bo'ladi: bir so'rov
"jarohat", keyingisi "tayyor" deydi, keyingisi yana "jarohat". Avval bot
har safar shuni o'zgarish deb hisoblab, yarim soatda bir xil postni
qaytarardi.

  1. O'zgarish ketma-ket NEWS_CONFIRM marta bir xil ko'rinsagina qabul
     qilinadi — bir martalik sakrash o'tib ketadi.
  2. Taqqoslash "oxirgi ko'rgan" holat bilan emas, "kanalga aytilgan"
     holat bilan qilinadi. Shu sababli aynan bir xil xabar ikki marta
     chiqishi mumkin emas: aytilgandan keyin u yangilik bo'lmay qoladi.

Tur ketayotganda jim turamiz
----------------------------
Deadline o'tgach tarkiblar qotadi — o'sha paytdagi jarohat xabari hech
kimga foyda bermaydi, faqat bezovta qiladi. Shuning uchun deadline'dan
turning ochkolari yakunlanishigacha (oxirgi o'yindan keyingi kun) post
chiqmaydi. O'sha davrdagi o'zgarishlar yo'qolmaydi: taqqoslash nuqtasi
joyida turadi va tur yopilgach hammasi birdan chiqadi.
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


def _state_of(player: dict) -> dict:
    """Solishtiriladigan uchlik: holat, ehtimol, izoh."""
    chance = player.get("chance_of_playing_next_round")
    return {
        "status": player.get("status") or "a",
        "chance": None if chance is None else int(chance),
        "news": _clean(player.get("news")),
    }


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
        out[str(p["id"])] = _state_of(p)
    return out


def candidates(baseline: dict[str, dict],
               current: dict[str, dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    """Taqqoslash nuqtasidan farq qiladiganlar -> (e'longa nomzodlar, jimlari).

    Holat yoki o'ynash ehtimoli o'zgarsa — bu yangilik. Faqat izoh matni
    o'zgargan bo'lsa, futbolchi tayyor bo'lmagan holatdagina yangilik
    hisoblanadi: tayyor futbolchining matni o'zgargani shunchaki shovqin,
    uni jimgina yozib qo'yamiz.
    """
    loud: dict[str, dict] = {}
    quiet: dict[str, dict] = {}
    for key, now_state in current.items():
        old = baseline.get(key)
        if old is None or old == now_state:
            continue
        same_state = (old.get("status") == now_state["status"]
                      and old.get("chance") == now_state["chance"])
        if same_state and now_state["status"] == "a":
            quiet[key] = now_state
        else:
            loud[key] = now_state
    return loud, quiet


def confirm(pending: dict[str, dict], found: dict[str, dict],
            need: int | None = None) -> tuple[dict[str, dict], dict[str, dict]]:
    """Ketma-ket bir xil ko'ringan o'zgarishlarnigina qabul qiladi.

    CDN turli yoshdagi nusxalarni qaytargani uchun bitta so'rovga ishonib
    bo'lmaydi. Ikki marta ketma-ket bir xil javob kelsa — bu haqiqiy
    o'zgarish; sakrab turgan qiymat esa sanoqni noldan boshlaydi va
    hech qachon chiqmaydi.

    Qaytaradi: (tasdiqlanganlar, kuzatuvda qolganlar).
    """
    need = config.NEWS_CONFIRM if need is None else need
    ready: dict[str, dict] = {}
    waiting: dict[str, dict] = {}
    for key, state in found.items():
        seen = 1
        prev = pending.get(key)
        if prev and prev.get("state") == state:
            seen = int(prev.get("seen") or 0) + 1
        if seen >= need:
            ready[key] = state
        else:
            waiting[key] = {"state": state, "seen": seen}
    return ready, waiting


def rows_for(ready: dict[str, dict], baseline: dict[str, dict],
             bootstrap: dict) -> list[Change]:
    """Tasdiqlangan o'zgarishlardan post qatorlarini yig'adi."""
    players = {str(p["id"]): p for p in bootstrap.get("elements", [])}
    rows: list[Change] = []
    for key, state in ready.items():
        p = players.get(key)
        if not p:
            continue
        rows.append(Change(
            element_id=int(key),
            name=p.get("web_name") or f"#{key}",
            team=p.get("team"),
            owned=_num(p.get("selected_by_percent"), 0.0),
            status=state["status"],
            chance=state["chance"],
            news=state["news"],
            was_status=(baseline.get(key) or {}).get("status"),
        ))
    rows.sort(key=lambda c: -c.owned)       # eng ko'p olinganlari tepada
    return rows[: config.NEWS_MAX_ROWS]


def changes(baseline: dict[str, dict], bootstrap: dict) -> list[Change]:
    """Taqqoslash nuqtasidan farq qiladigan va e'longa arziydigan qatorlar.

    Tasdiq bu yerda qo'llanmaydi — u `check_once` ichida, chunki ketma-ket
    tekshiruvlar kerak. Bu funksiya "nima yangilik hisoblanadi" degan
    qoidaning o'zini ifodalaydi.
    """
    loud, _ = candidates(baseline, snapshot(bootstrap))
    return rows_for(loud, baseline, bootstrap)


def next_deadline(bootstrap: dict) -> datetime | None:
    nxt = next((e for e in bootstrap.get("events", []) if e.get("is_next")), None)
    if not nxt or not nxt.get("deadline_time"):
        return None
    return datetime.fromisoformat(nxt["deadline_time"].replace("Z", "+00:00"))


def round_in_play(bootstrap: dict, status: dict | None = None,
                  now: datetime | None = None) -> bool:
    """Deadline o'tgan, lekin turning ochkolari hali yakunlanmaganmi?

    O'sha paytda tarkiblar qotgan: jarohat xabari hech narsani o'zgartira
    olmaydi, faqat bezovta qiladi. Tur yakunlanishi — oxirgi o'yindan
    keyingi kun, Britaniya vaqti bilan 09:00.
    """
    current = next((e for e in bootstrap.get("events", []) if e.get("is_current")), None)
    if not current or not current.get("deadline_time"):
        return False
    now = now or waiter.now_utc()
    deadline = datetime.fromisoformat(current["deadline_time"].replace("Z", "+00:00"))
    if now < deadline:
        return False
    if status is None:
        try:
            status = fpl_api.get_event_status()
        except Exception as exc:
            log.warning("Tur holati olinmadi: %s", exc)
            return False
    final_at = fpl_api.points_final_at(status or {})
    return bool(final_at and now < final_at)


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
    """Bitta tekshiruv: tasdiqlangan o'zgarishlarni chiqaradi va holatni qaytaradi.

    `players` — taqqoslash nuqtasi, ya'ni kanalga nima aytilgani. U faqat
    post chiqqanda (yoki jim o'zgarishlarda) yangilanadi, shuning uchun
    aynan bir xil xabar ikki marta chiqa olmaydi.
    """
    baseline = state.get("players") or {}
    pending = state.get("pending") or {}
    current = snapshot(bootstrap)
    now = waiter.now_utc().isoformat(timespec="seconds")

    if not baseline:
        log.info("Birinchi ishga tushirish — hozirgi holat yozib olindi, post yo'q.")
        return {"players": current, "pending": {}, "checked_at": now}

    loud, quiet = candidates(baseline, current)
    ready, waiting = confirm(pending, loud)

    if waiting:
        log.info("%d ta o'zgarish tasdiq kutmoqda.", len(waiting))
    rows = rows_for(ready, baseline, bootstrap) if ready else []
    if rows:
        log.info("%d ta tasdiqlangan o'zgarish — xabar yuborilmoqda.", len(rows))
        _publish(rows, teams, next_deadline(bootstrap))
    elif not waiting:
        log.info("O'zgarish yo'q.")

    # Taqqoslash nuqtasi: e'lon qilinganlar va jim o'zgarishlar yangilanadi,
    # qolgani joyida qoladi.
    updated = {k: v for k, v in baseline.items() if k in current}
    updated.update({k: v for k, v in current.items() if k not in baseline})
    updated.update(quiet)
    updated.update(ready)
    return {"players": updated, "pending": waiting, "checked_at": now}


def run(force: bool = False, once: bool = False, window: str | None = None) -> int:
    config.require_telegram()
    started = waiter.budget(config.NEWS_MAX_MINUTES)

    bootstrap = fpl_api.get_bootstrap()
    teams = fpl_api.teams_by_id(bootstrap)
    state = storage.load(config.NEWS_STATE_FILE, {}) or {}

    if not force and round_in_play(bootstrap):
        log.info("Tur ketyapti — tarkiblar qotgan, yangilik posti chiqmaydi. "
                 "Kuzatuv oxirgi o'yindan keyingi kuni davom etadi.")
        return 0

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
