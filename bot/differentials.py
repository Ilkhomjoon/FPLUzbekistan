"""Tur oralig'idagi differentiallar posti.

Tur yakunlangach, keyingi tur deadline'igacha kanalga chiqadi va olti bo'limdan
iborat bo'ladi:

  🔥 Kam olingan, ko'p bergan — egalik DIFF_MAX_OWN% dan past, o'tgan turda
     DIFF_MIN_POINTS+ ochko olgan futbolchilar
  👑 Top-100 ning yashirin qurollari — dunyo bo'yicha eng kuchli menejerlarda
     ko'p uchraydigan, lekin umumiy egaligi past futbolchilar
  📈 Kech qolmang — hali differential, ammo eng ko'p sotib olinayotganlar
  📅 Keyingi turlar — kalendar va raqiblar qiyinligi
  🇺🇿 Bizning ligada — shu differentiallar bizning ligada qanchada bor

Oxirida so'rovnoma yuboriladi (DIFF_POLL).
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import config, fpl_api, storage, telegram, waiter
from .deadline_stats import league_entries
from .formatting import differentials_poll, differentials_post

log = logging.getLogger("differentials")

OVERALL_LEAGUE_ID = 314  # FPL "Overall" ligasi
PAGE_SIZE = 50           # standings sahifasidagi jamoalar soni


# ---------------- ma'lumot modeli ----------------

@dataclass
class Diff:
    element_id: int
    name: str
    team: int
    cost: int
    owned: float          # selected_by_percent — dunyo bo'yicha egalik
    points: int           # o'tgan turdagi ochko
    total: int            # mavsum boshidan
    transfers_in: int     # shu hafta sotib olinishlar
    elite: float = 0.0    # top-100 dagi egalik, %
    local: float = 0.0    # bizning ligadagi egalik, %
    local_count: int = 0
    fixtures_text: str = ""

    def label(self, teams: dict, bold: bool = True) -> str:
        """"<b>Ødegaard</b> (ARS)" — postda ism qalin yoziladi."""
        from .telegram import esc

        name = f"<b>{esc(self.name)}</b>" if bold else esc(self.name)
        short = teams.get(self.team, {}).get("short_name", "")
        return f"{name} ({esc(short)})" if short else name


@dataclass
class Picks:
    low_owned: list[Diff] = field(default_factory=list)
    top100: list[Diff] = field(default_factory=list)
    rising: list[Diff] = field(default_factory=list)
    calendar: list[Diff] = field(default_factory=list)
    local: list[Diff] = field(default_factory=list)
    local_label: str = ""
    local_scanned: int = 0

    def any(self) -> bool:
        return bool(self.low_owned or self.top100 or self.rising)


# ---------------- bootstrap'dan tanlash ----------------

def _num(value, default=0):
    try:
        return type(default)(value)
    except (TypeError, ValueError):
        return default


def pool(bootstrap: dict) -> list[Diff]:
    """bootstrap-static -> o'ynay oladigan futbolchilar ro'yxati."""
    out: list[Diff] = []
    for p in bootstrap.get("elements", []):
        # jamoadan chiqarilganlar (status 'u') taklif qilinmaydi
        if p.get("status") == "u":
            continue
        out.append(Diff(
            element_id=p["id"],
            name=p.get("web_name") or f"#{p['id']}",
            team=p.get("team"),
            cost=_num(p.get("now_cost"), 0),
            owned=_num(p.get("selected_by_percent"), 0.0),
            points=_num(p.get("event_points"), 0),
            total=_num(p.get("total_points"), 0),
            transfers_in=_num(p.get("transfers_in_event"), 0),
        ))
    return out


def low_owned(players: list[Diff]) -> list[Diff]:
    """Egalik past, o'tgan turda ochko ko'p."""
    rows = [d for d in players
            if d.owned < config.DIFF_MAX_OWN and d.points >= config.DIFF_MIN_POINTS]
    rows.sort(key=lambda d: (-d.points, d.owned))
    return rows[: config.DIFF_TOP_N]


def rising(players: list[Diff]) -> list[Diff]:
    """Hali differential, lekin eng ko'p sotib olinayotganlar."""
    rows = [d for d in players if d.owned < config.DIFF_MAX_OWN and d.transfers_in > 0]
    rows.sort(key=lambda d: -d.transfers_in)
    return rows[: config.DIFF_RISING_N]


# ---------------- boshqa menejerlarning tarkiblari ----------------

def scan_picks(entries: list[int], gw: int, workers: int | None = None) -> tuple[Counter, int]:
    """Berilgan jamoalarning tarkiblarini yig'adi -> (element_id -> soni, tekshirilgani)."""
    workers = workers or config.DIFF_WORKERS
    counts: Counter = Counter()
    scanned = 0

    def one(entry_id: int) -> list[int] | None:
        try:
            data = fpl_api._get(f"/entry/{entry_id}/event/{gw}/picks/")
            return [p["element"] for p in (data.get("picks") or [])]
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=workers) as poolexec:
        for elements in poolexec.map(one, entries):
            if elements is None:
                continue
            scanned += 1
            counts.update(elements)
    return counts, scanned


def top_entries(size: int) -> list[int]:
    """Dunyo bo'yicha eng yuqori `size` ta jamoaning id'lari."""
    entries: list[int] = []
    page = 1
    while len(entries) < size:
        data = fpl_api._get(f"/leagues-classic/{OVERALL_LEAGUE_ID}/standings/",
                            page_standings=page)
        rows = data.get("standings", {}).get("results", [])
        if not rows:
            break
        entries.extend(r["entry"] for r in rows)
        if not data.get("standings", {}).get("has_next"):
            break
        page += 1
    return entries[:size]


def elite_differentials(players: list[Diff], gw: int) -> list[Diff]:
    """Top-100 da ko'p, umumiy egaligi past futbolchilar."""
    entries = top_entries(config.DIFF_TOP100_SIZE)
    if not entries:
        log.warning("Top-100 ro'yxati olinmadi.")
        return []

    counts, scanned = scan_picks(entries, gw)
    if not scanned:
        log.warning("Top-100 tarkiblari o'qilmadi.")
        return []
    log.info("Top-%d: %d ta jamoa tekshirildi", config.DIFF_TOP100_SIZE, scanned)

    by_id = {d.element_id: d for d in players}
    rows: list[Diff] = []
    for element_id, count in counts.items():
        d = by_id.get(element_id)
        if not d or d.owned >= config.DIFF_MAX_OWN:
            continue
        d.elite = count / scanned * 100
        if d.elite >= config.DIFF_TOP100_MIN:
            rows.append(d)
    rows.sort(key=lambda d: -(d.elite - d.owned))
    return rows[: config.DIFF_TOP_N]


def local_ownership(rows: list[Diff], gw: int) -> tuple[str, int]:
    """Bizning ligada shu futbolchilar qanchada borligini to'ldiradi."""
    if not config.STATS_LEAGUES:
        return "", 0
    league_id, label = config.STATS_LEAGUES[0]
    name, entries = league_entries(league_id, config.STATS_MAX_ENTRIES)
    if not entries:
        return "", 0

    counts, scanned = scan_picks(entries, gw)
    if not scanned:
        return "", 0
    for d in rows:
        d.local_count = counts.get(d.element_id, 0)
        d.local = d.local_count / scanned * 100
    log.info("%s: %d ta jamoa tekshirildi", name, scanned)
    return label or name, scanned


# ---------------- kalendar ----------------

def difficulty_emoji(value: int) -> str:
    if value <= 2:
        return "🟢"
    return "🟡" if value == 3 else "🔴"


def fixtures_for(team_id: int, after_event: int, fixtures: list[dict],
                 teams: dict, count: int) -> str:
    """"LEE (u) · BOU (m) · SUN (u) — 🟢🟡🟢" """
    rows = []
    for f in fixtures:
        event = f.get("event")
        if not event or event <= after_event:
            continue
        if f.get("team_h") == team_id:
            rows.append((event, f.get("team_a"), "u", _num(f.get("team_h_difficulty"), 3)))
        elif f.get("team_a") == team_id:
            rows.append((event, f.get("team_h"), "m", _num(f.get("team_a_difficulty"), 3)))
    rows.sort(key=lambda r: r[0])
    rows = rows[:count]
    if not rows:
        return "—"

    names = [f"{teams.get(opp, {}).get('short_name', '?')} ({where})"
             for _, opp, where, _ in rows]
    marks = "".join(difficulty_emoji(diff) for *_, diff in rows)
    return f"{' · '.join(names)} — {marks}"


# ---------------- vaqt ----------------

def last_finished_event(bootstrap: dict) -> dict | None:
    """Yakunlangan tur — /event-status/ bo'yicha (`finished` bayrog'i juda kech qo'yiladi)."""
    return fpl_api.finalised_event(bootstrap)


def next_event(bootstrap: dict) -> dict | None:
    return next((e for e in bootstrap.get("events", []) if e.get("is_next")), None)


def _too_late() -> bool:
    """Kech bo'lib ketdimi — bugun emas, ertaga chiqarish kerakmi?"""
    now = waiter.now_utc()
    return now > waiter.local_time_today(config.DIFF_LATEST)


# ---------------- asosiy ----------------

def collect(bootstrap: dict, gw: int, fixtures: list[dict], teams: dict) -> Picks:
    players = pool(bootstrap)
    picks = Picks()

    picks.low_owned = low_owned(players)
    log.info("Kam olingan, ko'p bergan: %d ta", len(picks.low_owned))

    try:
        picks.top100 = elite_differentials(players, gw)
    except Exception as exc:
        log.error("Top-100 bo'limi tayyorlanmadi: %s", exc)
    log.info("Top-100 qurollari: %d ta", len(picks.top100))

    picks.rising = rising(players)

    # kalendar — yuqoridagi bo'limlarda chiqqan futbolchilar uchun
    seen: set[int] = set()
    shortlist: list[Diff] = []
    for d in picks.low_owned + picks.top100:
        if d.element_id not in seen:
            seen.add(d.element_id)
            shortlist.append(d)
    picks.calendar = shortlist[: config.DIFF_CALENDAR_N]
    for d in picks.calendar:
        d.fixtures_text = fixtures_for(d.team, gw, fixtures, teams, config.DIFF_FIXTURES)

    if config.DIFF_LOCAL_LEAGUE and shortlist:
        try:
            rows = shortlist[: config.DIFF_TOP_N]
            label, scanned = local_ownership(rows, gw)
            if scanned:
                picks.local = rows
                picks.local_label = label
                picks.local_scanned = scanned
        except Exception as exc:
            log.error("Bizning liga bo'limi tayyorlanmadi: %s", exc)

    return picks


def run(force: bool = False) -> int:
    config.require_telegram()

    bootstrap = fpl_api.get_bootstrap()
    event = last_finished_event(bootstrap)
    if not event:
        log.info("Yakunlangan tur yo'q — differentiallar posti kutadi.")
        return 0

    gw = event["id"]
    nxt = next_event(bootstrap)
    next_gw = nxt["id"] if nxt else gw + 1

    state = storage.load(config.DIFF_STATE_FILE, {}) or {}
    if state.get("event") == gw and not force:
        log.info("GW%d differentiallari allaqachon chiqarilgan.", gw)
        return 0

    if nxt and not force:
        deadline = datetime.fromisoformat(nxt["deadline_time"].replace("Z", "+00:00"))
        if datetime.now(timezone.utc) >= deadline:
            log.info("GW%d deadline'i o'tib ketgan — bu turni o'tkazib yuboramiz.", next_gw)
            storage.save(config.DIFF_STATE_FILE, {"event": gw, "skipped": True})
            return 0

    if not force:
        post_at = waiter.local_time_today(config.DIFF_POST_AT)
        if waiter.now_utc() < post_at:
            waiter.sleep_until(post_at, label="Differentiallar posti",
                               budget_end=waiter.budget(config.DIFF_MAX_MINUTES))
        elif _too_late():
            log.info("Kech bo'ldi (%s dan keyin) — post ertaga chiqadi.", config.DIFF_LATEST)
            return 0

    fixtures = fpl_api.get_fixtures()
    teams = fpl_api.teams_by_id(bootstrap)
    picks = collect(bootstrap, gw, fixtures, teams)

    if not picks.any():
        log.info("Ko'rsatishga arziydigan differential topilmadi — post yo'q.")
        storage.save(config.DIFF_STATE_FILE, {"event": gw, "empty": True})
        return 0

    text = differentials_post(gw=gw, next_gw=next_gw, picks=picks, teams=teams)
    res = telegram.send_message(text)

    poll_id = None
    if config.DIFF_POLL:
        question, options = differentials_poll(next_gw, picks, teams)
        if len(options) >= 2:
            try:
                poll_id = telegram.send_poll(question, options).get("message_id")
            except telegram.TelegramError as exc:
                # so'rovnoma chiqmasa ham asosiy post joyida qolsin
                log.warning("So'rovnoma yuborilmadi: %s", exc)

    storage.save(config.DIFF_STATE_FILE, {
        "event": gw,
        "message_id": res.get("message_id"),
        "poll_id": poll_id,
        "posted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    log.info("GW%d differentiallari yuborildi.", gw)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Tur oralig'idagi differentiallar posti")
    ap.add_argument("--dry-run", action="store_true", help="Telegramga yubormasdan terminalga chiqaradi")
    ap.add_argument("--force", action="store_true", help="Vaqt tekshiruvini e'tiborsiz qoldiradi")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    if args.dry_run:
        config.DRY_RUN = True

    try:
        return run(force=args.force)
    except Exception as exc:
        log.exception("Differentiallar skriptida xatolik")
        telegram.notify_admin(f"⚠️ <b>FPL bot (differentiallar)</b>\n<code>{telegram.esc(repr(exc))}</code>")
        return 1


if __name__ == "__main__":
    sys.exit(main())
