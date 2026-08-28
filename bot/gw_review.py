"""Tur yakunlangach — liga sharhi.

Tur tugagan kunning ertasiga chiqadi va quyidagilarni ko'rsatadi:

  - Overall: o'rtacha va eng yuqori ochko, yetakchi, turning eng zo'r futbolchisi
  - Har bir liga: jamoalar soni, o'rtacha ochko, turning eng zo'r menejeri, top-5
  - Bizning ligada: eng katta ko'tarilish

Top-5 dagi har bir menejer uchun dunyo bo'yicha o'rni va overall yetakchidan
qancha ortda qolgani ham yoziladi (`/entry/{id}/` so'rovi orqali).
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config, fpl_api, storage, telegram, waiter
from .formatting import gw_review_post

log = logging.getLogger("gw_review")

OVERALL_LEAGUE_ID = 314  # FPL "Overall" ligasi


@dataclass
class Manager:
    entry: int
    team: str
    name: str
    rank: int
    last_rank: int
    total: int
    event_total: int
    overall_rank: int | None = None
    behind_leader: int | None = None

    @property
    def climb(self) -> int:
        """Liga ichida nechta o'rin ko'tarilgani (manfiy — tushgani)."""
        if not self.last_rank or not self.rank:
            return 0
        return self.last_rank - self.rank


@dataclass
class LeagueReview:
    label: str
    name: str = ""
    total_managers: int = 0
    average: float = 0.0
    best: Manager | None = None
    top: list[Manager] = field(default_factory=list)
    riser: Manager | None = None


# ---------------- ma'lumot yig'ish ----------------

def standings_rows(league_id: int) -> tuple[str, list[Manager]]:
    """Ligadagi barcha jamoalar (reyting tartibida)."""
    name = f"#{league_id}"
    rows: list[Manager] = []
    page = 1
    while True:
        data = fpl_api._get(f"/leagues-classic/{league_id}/standings/", page_standings=page)
        name = data.get("league", {}).get("name", name)
        results = data.get("standings", {}).get("results", [])
        for r in results:
            rows.append(Manager(
                entry=r["entry"],
                team=r.get("entry_name") or "—",
                name=r.get("player_name") or "—",
                rank=int(r.get("rank") or 0),
                last_rank=int(r.get("last_rank") or 0),
                total=int(r.get("total") or 0),
                event_total=int(r.get("event_total") or 0),
            ))
        if not results or not data.get("standings", {}).get("has_next"):
            return name, rows
        page += 1


def overall_leader() -> tuple[str, int] | None:
    """Dunyo bo'yicha birinchi o'rindagi menejer (ismi, ochkosi)."""
    try:
        data = fpl_api._get(f"/leagues-classic/{OVERALL_LEAGUE_ID}/standings/", page_standings=1)
        top = (data.get("standings", {}).get("results") or [])[:1]
        if top:
            return top[0].get("player_name") or "—", int(top[0].get("total") or 0)
    except Exception as exc:
        log.warning("Overall yetakchini olib bo'lmadi: %s", exc)
    return None


def fill_overall_ranks(managers: list[Manager], leader_total: int | None) -> None:
    """Top-5 uchun dunyo bo'yicha o'rin va yetakchidan farqni to'ldiradi."""
    def one(m: Manager) -> None:
        try:
            data = fpl_api._get(f"/entry/{m.entry}/")
            m.overall_rank = data.get("summary_overall_rank")
            points = data.get("summary_overall_points")
            if leader_total is not None and points is not None:
                m.behind_leader = int(points) - leader_total
        except Exception as exc:
            log.warning("Jamoa %s ma'lumoti olinmadi: %s", m.entry, exc)

    with ThreadPoolExecutor(max_workers=min(5, max(1, len(managers)))) as pool:
        list(pool.map(one, managers))


def review_league(league_id: int, label: str, leader_total: int | None,
                  with_riser: bool) -> LeagueReview:
    name, rows = standings_rows(league_id)
    review = LeagueReview(label=label, name=name, total_managers=len(rows))
    if not rows:
        return review

    review.average = sum(m.event_total for m in rows) / len(rows)
    review.best = max(rows, key=lambda m: m.event_total)
    review.top = sorted(rows, key=lambda m: m.rank or 10**9)[: config.GW_REVIEW_TOP_N]
    fill_overall_ranks(review.top, leader_total)

    if with_riser:
        movers = [m for m in rows if m.last_rank and m.rank]
        if movers:
            best_climb = max(movers, key=lambda m: m.climb)
            if best_climb.climb > 0:
                review.riser = best_climb

    log.info("%s: %d ta jamoa, o'rtacha %.1f, eng zo'ri %s (%d)",
             name, review.total_managers, review.average,
             review.best.name, review.best.event_total)
    return review


# ---------------- vaqt ----------------

def last_finished_event(bootstrap: dict, status: dict | None = None) -> dict | None:
    """Yakunlangan tur — /event-status/ bo'yicha (`finished` bayrog'i juda kech qo'yiladi)."""
    return fpl_api.finalised_event(bootstrap, status)


def _explain_not_finished(bootstrap: dict, status: dict | None = None) -> None:
    """Nega sharh chiqmayotganini logga tushunarli qilib yozadi."""
    if status is None:
        try:
            status = fpl_api.get_event_status()
        except Exception:
            status = {}

    gw, _, reason = fpl_api.status_verdict(status or {})
    if gw:
        log.info("GW%d hali tayyor emas: %s", gw, reason)
        return

    current = next((e for e in bootstrap.get("events", []) if e.get("is_current")), None)
    if not current:
        log.info("Yakunlangan tur yo'q — chiqamiz.")
        return

    gw = current["id"]
    try:
        fixtures = fpl_api.get_fixtures(event=gw)
    except Exception:
        fixtures = []
    played = [f for f in fixtures if f.get("finished") or f.get("finished_provisional")]
    log.info("GW%d hali davom etyapti (%d/%d o'yin o'ynalgan) — chiqamiz.",
             gw, len(played), len(fixtures))


def event_end_date(fixtures: list[dict], tz: str) -> str | None:
    """Turning oxirgi o'yini qaysi kunda bo'lgani."""
    times = [f["kickoff_time"] for f in fixtures if f.get("kickoff_time")]
    if not times:
        return None
    last = max(datetime.fromisoformat(t.replace("Z", "+00:00")) for t in times)
    # o'yin ~2 soat davom etadi
    return (last + timedelta(hours=2)).astimezone(ZoneInfo(tz)).date().isoformat()


# ---------------- asosiy ----------------

def run(force: bool = False, window: str | None = None) -> int:
    config.require_telegram()
    if not force and not waiter.in_window(window):
        log.info("Post oynasi (%s) tashqarisidamiz — sharh chiqarilmaydi.", window)
        return 0

    bootstrap = fpl_api.get_bootstrap()
    try:
        status = fpl_api.get_event_status()
    except Exception as exc:
        log.warning("event-status olinmadi: %s", exc)
        status = {}

    event = last_finished_event(bootstrap, status)
    if not event:
        _explain_not_finished(bootstrap, status)
        return 0

    gw = event["id"]
    state = storage.load(config.GW_REVIEW_STATE_FILE, {}) or {}
    if state.get("event") == gw and not force:
        log.info("GW%d sharhi allaqachon chiqarilgan.", gw)
        return 0

    local = ZoneInfo(config.LOCAL_TZ)
    today = datetime.now(timezone.utc).astimezone(local).date().isoformat()
    end_date = event_end_date(fpl_api.get_fixtures(event=gw), config.LOCAL_TZ)
    if not force and end_date and today <= end_date:
        log.info("GW%d %s da tugadi — sharh ertasiga chiqadi.", gw, end_date)
        return 0

    if not event.get("data_checked"):
        log.warning("GW%d hali FPL tomonidan to'liq tasdiqlanmagan — "
                    "o'rinlar biroz o'zgarishi mumkin.", gw)

    leader = overall_leader()
    leader_total = leader[1] if leader else None

    reviews = []
    for index, (league_id, label) in enumerate(config.STATS_LEAGUES):
        try:
            # eng katta ko'tarilish faqat birinchi ligada (bizniki)
            reviews.append(review_league(league_id, label, leader_total, with_riser=index == 0))
        except Exception as exc:
            log.error("Liga %s sharhi tayyorlanmadi: %s", league_id, exc)
            telegram.notify_admin(
                f"⚠️ <b>Tur sharhi</b>\nLiga {league_id}: <code>{telegram.esc(repr(exc))}</code>"
            )

    if not reviews:
        log.error("Hech qanday liga o'qilmadi — post yuborilmaydi.")
        return 1

    players = fpl_api.players_by_id(bootstrap)
    text = gw_review_post(gw=gw, event=event, players=players, leader=leader, reviews=reviews)

    res = telegram.send_message(text)
    storage.save(config.GW_REVIEW_STATE_FILE, {
        "event": gw,
        "message_id": res.get("message_id"),
        "posted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    log.info("GW%d sharhi yuborildi.", gw)
    return 0


def ready_event(bootstrap: dict, status: dict | None = None) -> dict | None:
    """Chiqarishga tayyor tur bormi? (yakunlangan va hali chiqarilmagan)"""
    event = last_finished_event(bootstrap, status)
    if not event:
        return None
    state = storage.load(config.GW_REVIEW_STATE_FILE, {}) or {}
    return None if state.get("event") == event["id"] else event


def watch(window: str | None = None) -> int:
    """FPL turni rasman yopishini kutadi va shu zahoti sharhni chiqaradi.

    2026/27 dan boshlab FPL ochkolarni turning oxirgi o'yinidan keyingi kuni
    Britaniya vaqti bilan 09:00 da yakuniy qiladi ("lockdown"). Toshkentda bu
    yozda 13:00, qishda 14:00 — ya'ni aniq soatni yozib qo'yib bo'lmaydi.
    Shuning uchun biroz erta uyg'onib, tasdiqlanishini kuzatib turamiz.
    """
    config.require_telegram()

    give_up = waiter.local_time_today(config.GW_REVIEW_UNTIL)
    # Job timeout'ida o'lib qolmaslik uchun o'zimiz chiqamiz — keyingi cron davom ettiradi.
    budget_end = waiter.budget(config.GW_REVIEW_MAX_MINUTES)
    log.info("Kuzatuv boshlandi — FPL tasdig'ini kutamiz (chegara: %s).", give_up.isoformat())

    # FPL API CDN orqali beriladi va turli serverlar turli yoshdagi nusxani
    # qaytaradi — bitta eski javob "tayyor" deb ko'rsatib qo'yishi mumkin.
    # Shuning uchun ketma-ket GW_REVIEW_CONFIRM marta tasdiq talab qilamiz.
    confirmations = 0

    while True:
        bootstrap = fpl_api.get_bootstrap()
        try:
            status = fpl_api.get_event_status()
        except Exception as exc:
            log.warning("event-status olinmadi: %s", exc)
            status = {}

        if ready_event(bootstrap, status):
            confirmations += 1
            if confirmations >= config.GW_REVIEW_CONFIRM:
                log.info("FPL turni yakunladi (%d marta tasdiqlandi) — sharh chiqarilmoqda.",
                         confirmations)
                return run(window=window)
            log.info("Tayyorga o'xshaydi (%d/%d) — %d soniyadan keyin qayta tekshiramiz.",
                     confirmations, config.GW_REVIEW_CONFIRM, config.GW_REVIEW_CONFIRM_WAIT)
            time.sleep(config.GW_REVIEW_CONFIRM_WAIT)
            continue

        if confirmations:
            log.info("Oldingi javob eski nusxa bo'lgan ko'rinadi — hisob nolga qaytarildi.")
            confirmations = 0

        now = waiter.now_utc()
        if now >= give_up:
            log.info("Kutish chegarasi keldi — sharh keyinroq chiqadi.")
            _explain_not_finished(bootstrap, status)
            return 0
        if time.monotonic() >= budget_end:
            log.info("Jarayon vaqti tugadi — keyingi cron kuzatishni davom ettiradi.")
            return 0

        _, _, reason = fpl_api.status_verdict(status or {})
        wait = min(config.GW_REVIEW_POLL, max(1.0, (give_up - now).total_seconds()))
        log.info("Hali tayyor emas (%s) — %.0f soniyadan keyin qayta tekshiramiz.", reason, wait)
        time.sleep(wait)


def main() -> int:
    ap = argparse.ArgumentParser(description="Tur yakunlari sharhi")
    ap.add_argument("--dry-run", action="store_true", help="Telegramga yubormasdan terminalga chiqaradi")
    ap.add_argument("--force", action="store_true", help="Vaqt tekshiruvini e'tiborsiz qoldiradi")
    ap.add_argument("--post-at", default=None, metavar="HH:MM",
                    help="Shu vaqtgacha kutib turadi (cron kechiksa ham post o'z vaqtida chiqadi)")
    ap.add_argument("--watch", action="store_true",
                    help="FPL turni rasman yopishini kutadi va shu zahoti chiqaradi")
    ap.add_argument("--window", default=None, metavar="HH:MM-HH:MM",
                    help="Faqat shu oynada chiqaradi (cron juda kechiksa post umuman chiqmaydi)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    if args.dry_run:
        config.DRY_RUN = True

    try:
        if args.watch and not args.force:
            return watch(window=args.window)
        if not (args.force or args.dry_run):
            waiter.hold_until(args.post_at, label="Tur sharhi",
                              budget_end=waiter.budget(config.GW_REVIEW_MAX_MINUTES))
        return run(force=args.force, window=args.window)
    except Exception as exc:
        log.exception("Tur sharhi skriptida xatolik")
        telegram.notify_admin(f"⚠️ <b>FPL bot (tur sharhi)</b>\n<code>{telegram.esc(repr(exc))}</code>")
        return 1


if __name__ == "__main__":
    sys.exit(main())
