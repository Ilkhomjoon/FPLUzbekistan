"""Ikki futbolchini solishtiruvchi rasm (radar chart) posti.

Deadline oldidan kanalga bitta rasm chiqadi: shu turda eng ko'p sotib
olinayotgan ikki futbolchi yonma-yon qo'yiladi.

Juftlik qanday tanlanadi
------------------------
Pozitsiyalar aralashib ketmasligi kerak — darvozabon bilan hujumchini
solishtirish ma'nosiz. Shuning uchun:

  1. har pozitsiya (darvozabon, himoyachi, yarim himoyachi, hujumchi) ichida
     shu hafta eng ko'p sotib olinayotgan ikkita futbolchi olinadi;
  2. shu ikkitasining transfer yig'indisi eng katta bo'lgan pozitsiya g'olib —
     ya'ni post FPL jamoasi aynan nima haqida bahslashayotgan joyga tegadi;
  3. ikkinchi futbolchi ham COMPARE_MIN_TRANSFERS dan oshmasa, post chiqmaydi:
     "eng ko'p olinayotgan ikkitasi" degani bittasi mashhur, ikkinchisi
     tasodifiy bo'lishi emas.

Ko'rsatkichlar pozitsiyaga moslashadi (darvozabonda saqlashlar, himoyachida
toza himoya, hujumchida xG). Hammasi "kattasi — yaxshisi" tarzda: xGC kabi
teskari ko'rsatkichlar ishlatilmaydi, aks holda "markazdan uzoqroq — yaxshi"
qoidasi buziladi.

Shkala — shu pozitsiyadagi eng yaxshi ko'rsatkich (kamida COMPARE_MIN_MINUTES
daqiqa o'ynaganlar orasida). Shu tufayli radarning tashqi halqasi "ligadagi
eng yaxshi" degan ma'noni beradi, ikki futbolchining o'zaro nisbati emas.

Vaqt: deadline'dan kamida COMPARE_LEAD daqiqa oldingi OXIRGI COMPARE_POST_AT.
Ya'ni odatda deadline oldidagi kechqurun 20:30 da; deadline erta ertalab
bo'lsa — bir kun oldinroq.
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import charts, config, fpl_api, storage, telegram, waiter

log = logging.getLogger("compare")


# ---------------- pozitsiyalar va ko'rsatkichlar ----------------

@dataclass(frozen=True)
class Position:
    name: str      # "Yarim himoyachi"
    plural: str    # "... yarim himoyachilarni solishtiramiz"
    metrics: tuple[tuple[str, str, str], ...]   # (yorliq, kalit, format)


# Yorliqlar qisqa: radar halqasining yonidagi uzun matn rasmdan chiqib ketadi.
POSITIONS: dict[int, Position] = {
    1: Position("Darvozabon", "darvozabonlarni", (
        ("Ochko / 90", "points", "{:.1f}"),
        ("Saqlash / 90", "saves", "{:.1f}"),
        ("Toza himoya", "clean_sheets", "{:.2f}"),
        ("Bonus / 90", "bonus", "{:.2f}"),
        ("Ta'sir / 90", "influence", "{:.0f}"),
    )),
    2: Position("Himoyachi", "himoyachilarni", (
        ("Ochko / 90", "points", "{:.1f}"),
        ("Toza himoya", "clean_sheets", "{:.2f}"),
        ("Himoya hissasi", "defcon", "{:.1f}"),
        ("xG+xA / 90", "xgi", "{:.2f}"),
        ("Tahdid / 90", "threat", "{:.0f}"),
        ("Bonus / 90", "bonus", "{:.2f}"),
    )),
    3: Position("Yarim himoyachi", "yarim himoyachilarni", (
        ("Ochko / 90", "points", "{:.1f}"),
        ("xG / 90", "xg", "{:.2f}"),
        ("xA / 90", "xa", "{:.2f}"),
        ("Tahdid / 90", "threat", "{:.0f}"),
        ("Ijodkorlik / 90", "creativity", "{:.0f}"),
        ("Himoya hissasi", "defcon", "{:.1f}"),
    )),
    4: Position("Hujumchi", "hujumchilarni", (
        ("Ochko / 90", "points", "{:.1f}"),
        ("xG / 90", "xg", "{:.2f}"),
        ("xA / 90", "xa", "{:.2f}"),
        ("Tahdid / 90", "threat", "{:.0f}"),
        ("Ijodkorlik / 90", "creativity", "{:.0f}"),
        ("Bonus / 90", "bonus", "{:.2f}"),
    )),
}

PAIR_MIN_MINUTES = 90   # bundan kam o'ynagan futbolchining /90 raqami yolg'on


def _num(value, default=0.0):
    try:
        return type(default)(value)
    except (TypeError, ValueError):
        return default


@dataclass
class Player:
    element_id: int
    name: str
    team: int
    position: int
    cost: int
    owned: float
    transfers_in: int
    minutes: int
    stats: dict[str, float] = field(default_factory=dict)

    @property
    def price(self) -> str:
        return f"£{self.cost / 10:.1f}M"


def per90(element: dict) -> dict[str, float]:
    """bootstrap elementidan 90 daqiqaga nisbatan ko'rsatkichlar.

    FPL ba'zilarini tayyor beradi (`expected_goals_per_90`), ba'zilarini esa
    faqat mavsumiy yig'indi sifatida (`threat`, `creativity`, `influence`,
    `bonus`, `total_points`) — ularni o'zimiz bo'lamiz.
    """
    minutes = _num(element.get("minutes"), 0)
    nineties = minutes / 90 if minutes else 0.0

    def ratio(field_name: str) -> float:
        total = _num(element.get(field_name), 0.0)
        return total / nineties if nineties else 0.0

    return {
        "points": ratio("total_points"),
        "bonus": ratio("bonus"),
        "threat": ratio("threat"),
        "creativity": ratio("creativity"),
        "influence": ratio("influence"),
        "xg": _num(element.get("expected_goals_per_90"), 0.0),
        "xa": _num(element.get("expected_assists_per_90"), 0.0),
        "xgi": _num(element.get("expected_goal_involvements_per_90"), 0.0),
        "saves": _num(element.get("saves_per_90"), 0.0),
        "clean_sheets": _num(element.get("clean_sheets_per_90"), 0.0),
        "defcon": _num(element.get("defensive_contribution_per_90"), 0.0),
    }


def pool(bootstrap: dict) -> list[Player]:
    out: list[Player] = []
    for p in bootstrap.get("elements", []):
        if p.get("status") == "u":        # jamoadan chiqarilgan
            continue
        if p.get("element_type") not in POSITIONS:
            continue
        out.append(Player(
            element_id=p["id"],
            name=p.get("web_name") or f"#{p['id']}",
            team=p.get("team"),
            position=p["element_type"],
            cost=_num(p.get("now_cost"), 0),
            owned=_num(p.get("selected_by_percent"), 0.0),
            transfers_in=_num(p.get("transfers_in_event"), 0),
            minutes=_num(p.get("minutes"), 0),
            stats=per90(p),
        ))
    return out


# ---------------- juftlik tanlash (C varianti) ----------------

def pair(players: list[Player],
         min_transfers: int | None = None) -> tuple[Player, Player] | None:
    """Eng "qizigan" pozitsiyadagi ikkita futbolchi."""
    floor = config.COMPARE_MIN_TRANSFERS if min_transfers is None else min_transfers
    best: tuple[int, Player, Player] | None = None

    for position in POSITIONS:
        rows = [p for p in players
                if p.position == position and p.minutes >= PAIR_MIN_MINUTES]
        rows.sort(key=lambda p: -p.transfers_in)
        if len(rows) < 2:
            continue
        first, second = rows[0], rows[1]
        if second.transfers_in < floor:
            # ikkinchisi mashhur emas — bu pozitsiyada "bahs" yo'q
            continue
        volume = first.transfers_in + second.transfers_in
        if best is None or volume > best[0]:
            best = (volume, first, second)

    if best is None:
        return None
    return best[1], best[2]


def scale(players: list[Player], position: int, key: str) -> float:
    """Shu pozitsiyadagi eng yaxshi ko'rsatkich — radar shkalasi."""
    values = [p.stats.get(key, 0.0) for p in players
              if p.position == position and p.minutes >= config.COMPARE_MIN_MINUTES]
    return max(values) if values else 0.0


def metrics(players: list[Player], a: Player, b: Player) -> list[charts.Metric]:
    spec = POSITIONS[a.position]
    out: list[charts.Metric] = []
    for label, key, fmt in spec.metrics:
        va, vb = a.stats.get(key, 0.0), b.stats.get(key, 0.0)
        top = max(scale(players, a.position, key), va, vb)
        out.append(charts.Metric(label=label, a=va, b=vb, top=top or 1.0, fmt=fmt))
    return out


# ---------------- oxirgi turlardagi ochkolar ----------------

def trend_events(last_gw: int, count: int | None = None) -> list[int]:
    count = count or config.COMPARE_TREND_GWS
    if last_gw < 1:
        return []
    return list(range(max(1, last_gw - count + 1), last_gw + 1))


def trend(events: list[int], a: int, b: int) -> tuple[list[int], list[int], list[int]]:
    """Har bir tur uchun bitta `/event/{gw}/live/` so'rovi -> (turlar, A, B).

    Ma'lumot kelmagan tur tashlab yuboriladi — chizik qolganlari bo'yicha
    chiziladi, post esa chiqadi.
    """
    gws: list[int] = []
    series_a: list[int] = []
    series_b: list[int] = []
    for ev in events:
        try:
            live = fpl_api.get_live(ev)
        except Exception as exc:
            log.warning("GW%d jonli ma'lumoti olinmadi: %s", ev, exc)
            continue
        points = {}
        for el in live.get("elements") or []:
            if el.get("id") in (a, b):
                points[el["id"]] = int(_num((el.get("stats") or {}).get("total_points"), 0))
        gws.append(ev)
        series_a.append(points.get(a, 0))
        series_b.append(points.get(b, 0))
    return gws, series_a, series_b


# ---------------- matnlar ----------------

def thousands(value: int) -> str:
    """312450 -> "312 450" — uzun raqam o'qilishi uchun."""
    return f"{int(value):,}".replace(",", " ")


def subtitle(position: Position) -> str:
    return (f"Bu turda eng ko'p sotib olinayotgan {position.plural} solishtiramiz"
            "\nMarkazdan uzoqroq — ko'rsatkich shunchalik yaxshi")


def caption(gw: int, a: Player, b: Player, teams: dict) -> str:
    esc = telegram.esc
    position = POSITIONS[a.position]

    def row(p: Player) -> str:
        short = teams.get(p.team, {}).get("short_name", "")
        head = f"<b>{esc(p.name)}</b>" + (f" ({esc(short)})" if short else "")
        return (f"{head} — {p.price} · egalik {p.owned:.1f}% · "
                f"bu hafta +{thousands(p.transfers_in)}")

    lines = [
        f"🔍 <b>{esc(a.name)} vs {esc(b.name)}</b>",
        f"{esc(position.name)}lar · GW{gw} oldidan eng ko'p sotib olinayotgan ikkitasi",
        "",
        row(a),
        row(b),
        "",
        "Raqamlar — mavsum boshidan, 90 daqiqaga nisbatan hisoblangan.",
        "",
        f"{config.tags(config.COMPARE_HASHTAG)} {config.CHANNEL_TAG}",
    ]
    return "\n".join(lines)


# ---------------- vaqt ----------------

def post_moment(deadline: datetime) -> datetime:
    """Deadline'dan kamida COMPARE_LEAD daqiqa oldingi oxirgi COMPARE_POST_AT.

    Misol: deadline shanba 14:30 (Toshkent) bo'lsa, zaxira 3 soat —
    ya'ni 11:30 gacha. Shanbadagi 20:30 kech, shuning uchun post juma
    kuni 20:30 da chiqadi.
    """
    latest = deadline - timedelta(minutes=config.COMPARE_LEAD)
    tz = ZoneInfo(config.LOCAL_TZ)
    ref = latest.astimezone(tz)
    hour, _, minute = config.COMPARE_POST_AT.partition(":")
    target = ref.replace(hour=int(hour), minute=int(minute or 0),
                         second=0, microsecond=0)
    if target > ref:
        target -= timedelta(days=1)
    return target.astimezone(timezone.utc)


def local_hhmm(moment: datetime) -> str:
    return moment.astimezone(ZoneInfo(config.LOCAL_TZ)).strftime("%d-%b %H:%M")


def next_event(bootstrap: dict) -> dict | None:
    return next((e for e in bootstrap.get("events", []) if e.get("is_next")), None)


def deadline_of(event: dict) -> datetime:
    return datetime.fromisoformat(event["deadline_time"].replace("Z", "+00:00"))


# ---------------- yig'ish va yuborish ----------------

def build(bootstrap: dict, gw: int, out_path: Path) -> tuple[Path, Player, Player] | None:
    """Rasmni tayyorlaydi -> (fayl, A, B). Juftlik topilmasa None."""
    players = pool(bootstrap)
    chosen = pair(players)
    if not chosen:
        return None
    a, b = chosen

    rows = metrics(players, a, b)
    gws, series_a, series_b = trend(trend_events(gw - 1), a.element_id, b.element_id)
    position = POSITIONS[a.position]

    charts.comparison_chart(
        out_path,
        title=f"{a.name} vs {b.name}",
        subtitle=subtitle(position),
        name_a=a.name,
        name_b=b.name,
        metrics=rows,
        gws=gws,
        series_a=series_a,
        series_b=series_b,
        trend_title=f"Oxirgi {len(gws)} turdagi ochkolar" if gws else "",
    )
    log.info("Chart tayyor: %s vs %s (%s), %d ko'rsatkich, %d tur",
             a.name, b.name, position.name, len(rows), len(gws))
    return out_path, a, b


def run(force: bool = False, keep: bool = False) -> int:
    config.require_telegram()

    bootstrap = fpl_api.get_bootstrap()
    event = next_event(bootstrap)
    if not event:
        log.info("Keyingi tur yo'q — chart posti kutadi.")
        return 0
    gw = event["id"]

    if gw < config.COMPARE_MIN_GW and not force:
        log.info("GW%d — mavsum boshi, /90 raqamlari hali ishonchsiz.", gw)
        return 0

    state = storage.load(config.COMPARE_STATE_FILE, {}) or {}
    if state.get("event") == gw and not force:
        log.info("GW%d charti allaqachon chiqarilgan.", gw)
        return 0

    deadline = deadline_of(event)
    now = waiter.now_utc()
    if not force:
        if now >= deadline - timedelta(minutes=config.COMPARE_MIN_LEAD):
            log.info("GW%d deadline'iga %.0f daqiqa qoldi — chart kech, o'tkazamiz.",
                     gw, (deadline - now).total_seconds() / 60)
            storage.save(config.COMPARE_STATE_FILE, {"event": gw, "skipped": True})
            return 0

        # Cron har kuni uyg'onadi, post esa haftada bir marta chiqadi. Shuning
        # uchun "vaqti kelmagan" holat odatiy — unga ogohlantirish yozilmaydi.
        # Ogohlantirish faqat post kuni yaqin bo'lsa (COMPARE_ALERT_WITHIN)
        # yuboriladi: aynan o'shanda cron vaqti noto'g'ri qo'yilgan bo'ladi.
        moment = post_moment(deadline)
        drift = (moment - now).total_seconds() / 60
        near = abs(drift) <= config.COMPARE_ALERT_WITHIN

        if drift > config.COMPARE_MAX_MINUTES:
            log.info("Post vaqtigacha (%s) %.1f soat bor — jarayon bunchalik kuta olmaydi.",
                     local_hhmm(moment), drift / 60)
            if near:
                telegram.notify_admin(
                    f"⚠️ <b>Solishtirish charti</b>\nGW{gw} posti {local_hhmm(moment)} da "
                    f"chiqishi kerak, cron esa undan {drift / 60:.1f} soat oldin ishga "
                    "tushdi — jarayon shuncha kuta olmaydi.\n"
                    "Tashqi cron vaqtini kechroqqa suring."
                )
            return 0

        if drift < -config.COMPARE_GRACE:
            log.info("Post vaqti (%s) o'tib ketgan — chart chiqmadi.", local_hhmm(moment))
            if near:
                telegram.notify_admin(
                    f"⚠️ <b>Solishtirish charti</b>\nGW{gw} posti {local_hhmm(moment)} da "
                    f"chiqishi kerak edi, cron esa undan {-drift / 60:.1f} soat keyin "
                    "ishga tushdi.\nTashqi cron vaqtini ertaroqqa suring."
                )
            return 0

        if drift > 0:
            waiter.sleep_until(moment, label="Solishtirish charti",
                               budget_end=waiter.budget(config.COMPARE_MAX_MINUTES))
            # kutish davomida transfer raqamlari o'zgaradi — yangisini olamiz
            bootstrap = fpl_api.get_bootstrap()

    out_path = Path(config.CHART_DIR) / f"compare_gw{gw}.png"
    built = build(bootstrap, gw, out_path)
    if not built:
        log.info("Solishtirishga arziydigan juftlik topilmadi — post yo'q.")
        storage.save(config.COMPARE_STATE_FILE, {"event": gw, "empty": True})
        return 0

    path, a, b = built
    teams = fpl_api.teams_by_id(bootstrap)
    res = telegram.send_photo(path, caption=caption(gw, a, b, teams))
    message_id = res.get("message_id")

    if config.COMPARE_PIN and message_id:
        telegram.pin_message(message_id)

    storage.save(config.COMPARE_STATE_FILE, {
        "event": gw,
        "message_id": message_id,
        "pair": [a.name, b.name],
        "position": POSITIONS[a.position].name,
        "posted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    log.info("GW%d charti yuborildi: %s vs %s", gw, a.name, b.name)

    if not keep:
        # rasm Telegramda qoldi, repoda saqlashning hojati yo'q
        Path(path).unlink(missing_ok=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Ikki futbolchini solishtiruvchi chart posti")
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
        log.exception("Solishtirish charti skriptida xatolik")
        telegram.notify_admin(
            f"⚠️ <b>FPL bot (solishtirish charti)</b>\n<code>{telegram.esc(repr(exc))}</code>")
        return 1


if __name__ == "__main__":
    sys.exit(main())
