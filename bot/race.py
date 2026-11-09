"""“O'zbekiston poygasi” — ligamiz yetakchilarining mavsumiy kurashi.

Nima chiqadi
------------
Har bir chiziq — bitta menejer. Chiziq yuqorida bo'lsa, o'sha turda u
oldinda edi; chiziqlar kesishgan joy — kimdir kimnidir quvib o'tgan payt.
Pastdagi jadvalda haqiqiy ochkolar va yetakchidan farq turadi.

Y o'qidagi raqam — CHARTDAGI menejerlar orasidagi o'rin, liganing umumiy
o'rni emas. Sababi: bugun uchinchi o'rinda turgan odam GW2 da ligada
180-o'rinda bo'lishi mumkin, va o'sha chiziq rasmdan chiqib ketardi.
Oltilik ichida esa raqam hech qachon oltidan oshmaydi.

Narxi — 7 ta so'rov
-------------------
Chart faqat oltilikning o'zaro o'rnini ko'rsatgani uchun butun liganing
tarixi kerak emas. Bugungi oltilik jadvalning birinchi sahifasidan olinadi
(1 so'rov), keyin o'sha olti kishining tarixi so'raladi (6 so'rov).

Vaqt
----
Ochkolar rasman yakunlangandan RACE_LEAD soat o'tgach, birinchi
RACE_POST_AT da chiqadi. Odatiy haftada bu — tur yopilganidan ikki kun
keyin, ya'ni tur sharhi (shu kuni), differentiallar (shu kuni kechqurun)
va harakat charti (ertasi kuni) bilan to'qnashmaydi.
"""
from __future__ import annotations

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import charts, config, fpl_api, storage, telegram, waiter

log = logging.getLogger("race")

OVERALL_LEAGUE_ID = 314   # FPL "Overall" ligasi — dunyo yetakchisi shu yerda


@dataclass
class Manager:
    entry_id: int
    name: str            # menejerning ismi
    team: str            # jamoasining nomi
    place: int           # ligadagi o'rni
    total: int           # jami ochko
    last: int            # oxirgi turdagi ochko (transfer jarimasi hisobga olingan)
    totals: dict[int, int] = field(default_factory=dict)   # tur -> jami ochko
    overall: int = 0     # dunyo bo'yicha o'rni (oxirgi tur holatiga)

    @property
    def short(self) -> str:
        return short_name(self.name)

    @property
    def club(self) -> str:
        """Jamoa nomi — chart chetiga sig'adigan holda, emojisiz."""
        return clip(charts.plain(self.team)) or self.short


def clip(text: str, limit: int = 18) -> str:
    """Uzun nomni rasm chetiga sig'adigan holga keltiradi."""
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def short_name(name: str, limit: int = 16) -> str:
    """"Ilkhomjon Yusupov" -> "Ilkhomjon Y." — chart chetiga sig'ishi uchun."""
    parts = (name or "").split()
    if not parts:
        return "—"
    if len(parts) == 1:
        return parts[0][:limit]
    short = f"{parts[0]} {parts[1][0]}."
    return short if len(short) <= limit else f"{parts[0][:limit - 3]}… {parts[1][0]}."


# ---------------- ma'lumot ----------------

def _num(value, default=0):
    try:
        return type(default)(value)
    except (TypeError, ValueError):
        return default


def league_top(league_id: int, count: int | None = None) -> tuple[str, list[Manager]]:
    """Liga jadvalining birinchi sahifasidan yetakchilar."""
    count = count or config.RACE_TOP_N
    data = fpl_api._get(f"/leagues-classic/{league_id}/standings/", page_standings=1)
    name = (data.get("league") or {}).get("name") or f"#{league_id}"
    rows = ((data.get("standings") or {}).get("results") or [])[:count]
    return name, [Manager(
        entry_id=r["entry"],
        name=r.get("player_name") or f"#{r['entry']}",
        team=r.get("entry_name") or "",
        place=_num(r.get("rank"), 0),
        total=_num(r.get("total"), 0),
        last=_num(r.get("event_total"), 0),
    ) for r in rows]


def history(entry_id: int) -> tuple[dict[int, int], int]:
    """entry/{id}/history -> ({tur: jami ochko}, dunyo bo'yicha oxirgi o'rin)."""
    data = fpl_api._get(f"/entry/{entry_id}/history/")
    totals: dict[int, int] = {}
    overall = 0
    for row in data.get("current") or []:
        event = row.get("event")
        if event is None:
            continue
        totals[int(event)] = _num(row.get("total_points"), 0)
        overall = _num(row.get("overall_rank"), 0) or overall
    return totals, overall


def national_league() -> int:
    """Milliy liga id'si. Sozlanmagan bo'lsa — STATS_LEAGUES dagi ikkinchisi."""
    if config.RACE_NATIONAL_LEAGUE:
        return config.RACE_NATIONAL_LEAGUE
    leagues = config.STATS_LEAGUES or []
    return leagues[1][0] if len(leagues) > 1 else 0


def leader_total(league_id: int) -> int:
    """Liga yetakchisining jami ochkosi — jadvaldagi "orqada" ustunlari uchun."""
    if not league_id:
        return 0
    data = fpl_api._get(f"/leagues-classic/{league_id}/standings/", page_standings=1)
    rows = (data.get("standings") or {}).get("results") or []
    return _num(rows[0].get("total"), 0) if rows else 0


def thousands(value: int) -> str:
    """1204877 -> "1 204 877" — dunyo o'rni o'qilishi uchun."""
    return f"{int(value):,}".replace(",", " ") if value else "—"


def behind(top: int, total: int) -> str:
    """Yetakchidan necha ochko orqada. Yetakchining o'zi bo'lsa — chiziqcha."""
    if not top or top <= total:
        return "—"
    return f"-{top - total}"


def load_histories(managers: list[Manager], workers: int | None = None) -> None:
    """Har bir menejerning tarixi, dunyo o'rni va milliy liga o'rni."""
    workers = workers or config.RACE_WORKERS

    def one(manager: Manager) -> None:
        try:
            manager.totals, manager.overall = history(manager.entry_id)
        except Exception as exc:
            log.warning("#%d tarixi olinmadi: %s", manager.entry_id, exc)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, managers))


def common_events(managers: list[Manager]) -> list[int]:
    """Hamma menejerda bor turlar. Keyin qo'shilgan jamoada boshlang'ich
    turlar yo'q — ularni tashlab yuboramiz, aks holda chiziq uzilib qoladi."""
    sets = [set(m.totals) for m in managers if m.totals]
    if not sets:
        return []
    shared = set.intersection(*sets)
    return sorted(shared)


def ranks(managers: list[Manager], events: list[int]) -> dict[int, list[int]]:
    """Har bir tur uchun oltilik ichidagi o'rin.

    Teng ochkoda bugungi jadval tartibi hal qiladi — chiziq sakrab
    ketmasligi uchun tartib barqaror bo'lishi kerak.
    """
    order = {m.entry_id: index for index, m in enumerate(managers)}
    out: dict[int, list[int]] = {m.entry_id: [] for m in managers}
    for event in events:
        standing = sorted(managers,
                          key=lambda m: (-m.totals.get(event, 0), order[m.entry_id]))
        for place, manager in enumerate(standing, start=1):
            out[manager.entry_id].append(place)
    return out


# ---------------- matn va rasm ----------------

def build(managers: list[Manager], events: list[int], league: str,
          out_path: Path, national_top: int = 0, overall_top: int = 0) -> Path:
    table = ranks(managers, events)
    leader = managers[0].total
    # Chart chizig'ining oxirida jamoa nomi, jadvalda esa menejerning ismi —
    # ikkalasi bitta rasmda ko'rinadi.
    runners = [charts.Runner(
        name=m.short,
        label=m.club,
        ranks=table[m.entry_id],
        cells=(str(m.total), str(m.last), thousands(m.overall),
               behind(leader, m.total), behind(national_top, m.total),
               behind(overall_top, m.total)),
    ) for m in managers]

    return charts.race_chart(
        out_path,
        title="FPLUzbekistan Poygasi",
        subtitle=(f"Ligamizning eng yaxshi {len(managers)} menejeri · "
                  f"GW{events[0]}—GW{events[-1]}"
                  "\nChiziq yuqorida bo'lsa — o'shanda ushbu menejer "
                  "shu ro'yxat ichida oldinda edi"),
        gws=events,
        runners=runners,
        code=config.LEAGUE_CODE,
    )


def caption(managers: list[Manager], events: list[int]) -> str:
    esc = telegram.esc
    leader = managers[0].total
    lines = [
        "🏁 <b>FPLUzbekistan Poygasi</b>",
        f"GW{events[-1]} holatiga ko'ra",
        "",
    ]
    for index, m in enumerate(managers, start=1):
        gap = "" if m.total == leader else f" ({leader - m.total} orqada)"
        # Izohda jamoa nomi to'liq ko'rinadi — bu yerda kenglik cheklovi yo'q
        club = f" ({esc(m.team.strip())})" if m.team.strip() else ""
        lines.append(f"{index}. <b>{esc(m.short)}</b>{club} — {m.total} ochko{gap}")
    lines.append("")
    if config.LEAGUE_CODE:
        lines.append(f"Ligaga qo'shilish kodi: <code>{esc(config.LEAGUE_CODE)}</code>")
        lines.append("")
    lines += [
        config.tags(config.RACE_HASHTAG),
        "",
        config.CHANNEL_TAG,
    ]
    return "\n".join(lines)


# ---------------- vaqt ----------------

def post_moment(status: dict) -> datetime | None:
    """Ochkolar yakunlangandan RACE_LEAD soat o'tgach — birinchi RACE_POST_AT."""
    final_at = fpl_api.points_final_at(status)
    if final_at is None:
        return None
    ready = final_at + timedelta(hours=config.RACE_LEAD)
    tz = ZoneInfo(config.LOCAL_TZ)
    ref = ready.astimezone(tz)
    hour, _, minute = config.RACE_POST_AT.partition(":")
    target = ref.replace(hour=int(hour), minute=int(minute or 0),
                         second=0, microsecond=0)
    if target < ref:
        target += timedelta(days=1)
    return target.astimezone(timezone.utc)


def local_hhmm(moment: datetime) -> str:
    return moment.astimezone(ZoneInfo(config.LOCAL_TZ)).strftime("%d-%b %H:%M")


# ---------------- asosiy ----------------

def run(force: bool = False, keep: bool = False) -> int:
    config.require_telegram()

    if not config.STATS_LEAGUES:
        log.warning("STATS_LEAGUES bo'sh — qaysi liga ekanini bilmaymiz.")
        return 0
    league_id, label = config.STATS_LEAGUES[0]

    status = fpl_api.get_event_status()
    gw, ready, reason = fpl_api.status_verdict(status)
    if not gw or not ready:
        log.info("Tur hali yakunlanmagan (%s) — poyga charti kutadi.", reason)
        return 0
    if gw < config.RACE_MIN_GW and not force:
        log.info("GW%d — mavsum boshi, poyga hali qiziq emas.", gw)
        return 0

    state = storage.load(config.RACE_STATE_FILE, {}) or {}
    if state.get("event") == gw and not force:
        log.info("GW%d poyga charti allaqachon chiqarilgan.", gw)
        return 0

    if not force:
        moment = post_moment(status)
        if moment is None:
            log.warning("Turning tugash sanasi aniqlanmadi — chart chiqmadi.")
            return 0
        now = waiter.now_utc()
        drift = (moment - now).total_seconds() / 60
        near = abs(drift) <= config.RACE_ALERT_WITHIN

        if drift > config.RACE_MAX_MINUTES:
            log.info("Post vaqtigacha (%s) %.1f soat bor — jarayon kuta olmaydi.",
                     local_hhmm(moment), drift / 60)
            if near:
                telegram.notify_admin(
                    f"⚠️ <b>Poyga charti</b>\nGW{gw} posti {local_hhmm(moment)} da "
                    f"chiqishi kerak, cron esa undan {drift / 60:.1f} soat oldin "
                    "ishga tushdi."
                )
            return 0
        if drift < -config.RACE_GRACE:
            log.info("Post vaqti (%s) o'tib ketgan — chart chiqmadi.", local_hhmm(moment))
            if near:
                telegram.notify_admin(
                    f"⚠️ <b>Poyga charti</b>\nGW{gw} posti {local_hhmm(moment)} da "
                    f"chiqishi kerak edi, cron esa {-drift / 60:.1f} soat kechikdi."
                )
            return 0
        if drift > 0:
            waiter.sleep_until(moment, label="Poyga charti",
                               budget_end=waiter.budget(config.RACE_MAX_MINUTES))

    league, managers = league_top(league_id)
    league = label or league
    if len(managers) < 2:
        log.info("Ligada yetarli jamoa yo'q — post chiqmadi.")
        return 0

    load_histories(managers)
    events = common_events(managers)
    if len(events) < 2:
        log.info("Umumiy tarix yetarli emas (%d tur) — post chiqmadi.", len(events))
        return 0

    # Ikkita yetakchining ochkosi: milliy liga va dunyo. Olinmasa ham post
    # chiqadi — o'sha ustunlarda chiziqcha turadi.
    tops: dict[str, int] = {}
    for key, source in (("national", national_league()), ("overall", OVERALL_LEAGUE_ID)):
        try:
            tops[key] = leader_total(source)
        except Exception as exc:
            log.warning("%s yetakchisining ochkosi olinmadi: %s", key, exc)
            tops[key] = 0
    log.info("Yetakchilar: O'zbekiston %s, Overall %s",
             tops["national"] or "—", tops["overall"] or "—")

    out_path = Path(config.CHART_DIR) / f"race_gw{gw}.png"
    build(managers, events, league, out_path,
          national_top=tops["national"], overall_top=tops["overall"])
    res = telegram.send_photo(out_path, caption=caption(managers, events))

    storage.save(config.RACE_STATE_FILE, {
        "event": gw,
        "league": league_id,
        "message_id": res.get("message_id"),
        "leaders": [m.short for m in managers],
        "posted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    log.info("GW%d poyga charti yuborildi: %s", gw,
             ", ".join(m.short for m in managers))

    if not keep:
        out_path.unlink(missing_ok=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Liga yetakchilarining poyga charti")
    ap.add_argument("--dry-run", action="store_true",
                    help="Telegramga yubormaydi, rasmni faqat faylga chizadi")
    ap.add_argument("--force", action="store_true",
                    help="Vaqt tekshiruvini e'tiborsiz qoldiradi")
    ap.add_argument("--keep", action="store_true", help="Rasm faylini o'chirmaydi")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    if args.dry_run:
        config.DRY_RUN = True

    try:
        return run(force=args.force, keep=args.keep or args.dry_run)
    except Exception as exc:
        log.exception("Poyga charti skriptida xatolik")
        telegram.notify_admin(
            f"⚠️ <b>FPL bot (poyga charti)</b>\n<code>{telegram.esc(repr(exc))}</code>")
        return 1


if __name__ == "__main__":
    sys.exit(main())
