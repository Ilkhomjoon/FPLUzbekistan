"""Telegram post matnlarini tayyorlash."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import config
from .telegram import esc


def price(now_cost: int) -> str:
    """105 -> £10.5M"""
    return f"£{now_cost / 10:.1f}M"


def local_dt(iso: str | None) -> datetime | None:
    if not iso:
        return None
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return dt.astimezone(ZoneInfo(config.LOCAL_TZ))


def now_local() -> datetime:
    return datetime.now(timezone.utc).astimezone(ZoneInfo(config.LOCAL_TZ))


# ---------------- narx o'zgarishlari ----------------

def price_change_post(changes: list[dict], direction: str) -> str:
    """changes: [{'name':..., 'team':..., 'new':int, 'old':int}], direction: 'down' | 'up'"""
    title = "🚨 Narx tushishi! 💷" if direction == "down" else "🚨 Narx ko'tarilishi! 💷"
    rows = sorted(changes, key=lambda c: (-c["new"], c["name"].lower()))

    lines = [title, ""]
    for c in rows:
        who = esc(c["name"])
        if config.PRICE_SHOW_TEAM and c.get("team"):
            who = f"{who} ({esc(c['team'])})"
        lines.append(f"{who} ({price(c['new'])})")
    lines += ["", config.PRICE_HASHTAG, "", config.CHANNEL_TAG]
    return "\n".join(lines)


# ---------------- live bonus ----------------

def _player_label(element_id: int, players: dict, teams: dict) -> str:
    p = players.get(element_id, {})
    name = esc(p.get("web_name", f"#{element_id}"))
    short = teams.get(p.get("team"), {}).get("short_name", "")
    return f"{name} ({esc(short)})" if short else name


def _scorer_line(rows: list[dict], players: dict, teams: dict,
                 always_count: bool = True) -> str:
    """[{'element','value','side'}] -> "Saka (1), Havertz (2)"

    Uy egalari oldin, keyin mehmonlar; ichida ko'p gol urgan tepada.
    always_count=False bo'lsa son faqat 1 dan katta bo'lganda yoziladi —
    kartochkalarda "(1)" ortiqcha ko'rinadi.
    """
    ordered = sorted(
        rows,
        key=lambda r: (r.get("side") != "h", -int(r["value"]),
                       players.get(r["element"], {}).get("web_name", "")),
    )
    parts = []
    for r in ordered:
        p = players.get(r["element"], {})
        name = esc(p.get("web_name", f"#{r['element']}"))
        value = int(r["value"])
        show = always_count or value > 1
        short = teams.get(p.get("team"), {}).get("short_name", "") if config.GOALS_SHOW_TEAM else ""

        if short and show:
            parts.append(f"{name} ({esc(short)}, {value})")
        elif short:
            parts.append(f"{name} ({esc(short)})")
        elif show:
            parts.append(f"{name} ({value})")
        else:
            parts.append(name)
    return ", ".join(parts)


# (identifikator, belgi, sonini doim yozamizmi)
FIXTURE_EVENTS = (
    ("goals_scored", "⚽️", True),
    ("assists", "🅰️", True),
    ("penalties_saved", "🧤", True),
    ("penalties_missed", "❌", True),
    ("own_goals", "🥅", True),
    ("yellow_cards", "🟨", False),
    ("red_cards", "🟥", False),
)
CARD_EVENTS = {"yellow_cards", "red_cards"}


def _fixture_block(fx: dict, players: dict, teams: dict, defcon: dict[int, int] | None = None,
                   level: int = 0) -> list[str]:
    from .bonus import fixture_bonus
    from .fpl_api import fixture_stat

    home = teams.get(fx["team_h"], {}).get("name", "?")
    away = teams.get(fx["team_a"], {}).get("name", "?")

    started = bool(fx.get("started"))
    finished = bool(fx.get("finished") or fx.get("finished_provisional"))

    if not started:
        ko = local_dt(fx.get("kickoff_time"))
        when = ko.strftime("%H:%M") if ko else "TBC"
        return [f"⚪️ {esc(home)} — {esc(away)} ({when})"]

    emoji = "🟢" if finished else "🔴"
    hs = fx.get("team_h_score")
    aws = fx.get("team_a_score")
    score = f"{hs if hs is not None else 0}:{aws if aws is not None else 0}"
    header = f"<b>{emoji} {esc(home)} {score} {esc(away)}</b>"

    bonuses, official = fixture_bonus(fx, config.BONUS_MIN_BPS)
    bps_map = {int(r["element"]): int(r["value"]) for r in fixture_stat(fx, "bps")}

    lines = [header]

    if config.SHOW_GOALS:
        events = []
        for identifier, marker, always_count in FIXTURE_EVENTS:
            if identifier in CARD_EVENTS:
                if not config.SHOW_CARDS:
                    continue
                # matn Telegram limitiga yaqinlashsa, birinchi bo'lib kartochkalar olinadi
                if level >= 1:
                    continue
            rows = [r for r in fixture_stat(fx, identifier) if int(r["value"]) > 0]
            if rows:
                events.append(f"{marker}: {_scorer_line(rows, players, teams, always_count)}")
        if events:
            # sarlavhaga yopishib tursin — orada bo'sh qator kerak emas
            lines.extend(events)

    if bonuses:
        lines.append("")
        # teng bonusda BPS yuqorisi tepada tursin
        ranked = sorted(
            bonuses.items(),
            key=lambda kv: (-kv[1], -bps_map.get(kv[0], 0), players.get(kv[0], {}).get("web_name", "")),
        )
        limit = max(1, config.BONUS_MAX_PLAYERS) if level == 0 else 3
        for element_id, pts in ranked[:limit]:
            bps = bps_map.get(element_id)
            show_bps = config.SHOW_BPS and level < 2 and bps is not None
            bps_txt = f" · {bps} BPS" if show_bps else ""
            lines.append(f"{pts} | {_player_label(element_id, players, teams)}{bps_txt}")
        hidden = len(ranked) - limit
        if hidden > 0:
            lines.append(f"<i>… yana {hidden} ta teng natija</i>")
    elif not finished:
        lines.append("")
        lines.append("<i>hali bonus yo'q</i>")

    if config.SHOW_DEFCON and defcon:
        names = sorted(
            (_player_label(eid, players, teams) for eid in defcon),
            key=str.lower,
        )
        lines.append("")
        lines.append(f"🛡 DefCon: {', '.join(names)}")
    return lines


TELEGRAM_LIMIT = 4096
SAFE_LIMIT = 3900


def live_bonus_post(
    fixtures: list[dict],
    players: dict,
    teams: dict,
    gw: int | None = None,
    defcon: dict[int, dict[int, int]] | None = None,
) -> str:
    """Ko'p o'yinli kunlarda matn Telegram limitidan oshib ketmasligi kerak:
    oshsa, qisqartirilgan ko'rinishda qayta yig'iladi."""
    # 0 = to'liq, 1 = ro'yxat qisqaradi, 2 = BPS raqamlari ham olib tashlanadi
    for level in (0, 1, 2):
        text = _live_post(fixtures, players, teams, gw, defcon, level)
        if len(text) <= SAFE_LIMIT:
            return text
    return text if len(text) <= TELEGRAM_LIMIT else text[: TELEGRAM_LIMIT - 2] + "…"


def _live_post(
    fixtures: list[dict],
    players: dict,
    teams: dict,
    gw: int | None = None,
    defcon: dict[int, dict[int, int]] | None = None,
    level: int = 0,
) -> str:
    stamp = now_local().strftime("%H:%M:%S")

    # Pin panelida xabarning birinchi qatori ko'rinadi — holat shu yerda tursin
    def _done(f: dict) -> bool:
        return bool(f.get("finished") or f.get("finished_provisional"))

    if any(f.get("started") and not _done(f) for f in fixtures):
        status = config.LIVE_LABEL
    elif fixtures and all(_done(f) for f in fixtures):
        status = config.DONE_LABEL
    else:
        status = config.WAIT_LABEL

    title = f"{status} · GW{gw} — Bonus ochkolar" if gw else f"{status} · Bonus ochkolar"
    head = f"<b>{title}</b>\n🔄 So'ngi yangilanish: {stamp}"

    all_done = bool(fixtures) and all(_done(f) for f in fixtures)

    blocks: list[str] = [head]
    ordered = sorted(fixtures, key=lambda f: (f.get("kickoff_time") or "", f.get("id", 0)))
    for fx in ordered:
        fx_defcon = (defcon or {}).get(fx.get("id"), {})
        block = "\n".join(_fixture_block(fx, players, teams, fx_defcon, level))
        # Tugagan o'yinlar doim yig'ib qo'yiladi — ketayotgan va kutilayotganlari
        # ko'zga tashlanib tursin, yakunlangan kunda esa xabar ixcham qolsin.
        if config.COLLAPSE_FINISHED and _done(fx):
            block = f"<blockquote expandable>{block}</blockquote>"
        blocks.append(block)

    if all_done:
        blocks.append("✅ Bugungi o'yinlar yakunlandi.")

    # "BPS nima?" — o'quvchilar tez-tez so'raydi. Joy tor bo'lgan holatda
    # (level 2 — BPS raqamlari ham olib tashlangan) izoh ham tushib qoladi.
    if config.SHOW_BPS and config.BPS_NOTE and level < 2:
        blocks.append(f"<blockquote>{esc(config.BPS_NOTE)}</blockquote>")

    blocks.append(f"{config.LIVE_HASHTAG}\n\n{config.CHANNEL_TAG}")
    return "\n\n".join(blocks)


# ---------------- deadline statistikasi ----------------

CHIP_LABELS = {
    "wildcard": "WC",
    "freehit": "FH",
    "bboost": "BB",
    "3xc": "TC",
    "manager": "AM",
}


def chip_label(name: str) -> str:
    return CHIP_LABELS.get(name, name)


def num(value: int) -> str:
    """1234567 -> '1 234 567'"""
    return f"{value:,}".replace(",", "\u00a0")


def _captain_lines(counts, total: int, players: dict, teams: dict, top_n: int) -> list[str]:
    if not counts or not total:
        return ["<i>ma'lumot yo'q</i>"]
    ranked = sorted(
        counts.items(),
        key=lambda kv: (-kv[1], players.get(kv[0], {}).get("web_name", "")),
    )[:top_n]
    lines = []
    for i, (element_id, count) in enumerate(ranked, 1):
        share = round(count * 100 / total)
        lines.append(f"{i}. {_player_label(element_id, players, teams)} — {num(count)} ({share}%)")
    return lines


def _chip_line(counts) -> str:
    if not counts:
        return "yo'q"
    ordered = sorted(counts.items(), key=lambda kv: -kv[1])
    return " · ".join(f"{chip_label(name)} {num(count)}" for name, count in ordered)


def deadline_stats_post(gw: int, scans, players: dict, teams: dict,
                        overall_captain=None, overall_chip_counts=None) -> str:
    """scans: [(label, LeagueScan), ...] — liga tartibida."""
    top_n = config.STATS_TOP_N
    blocks = [f"📊 <b>GW{gw} Statistikasi</b>"]

    captain_block = ["👑 <b>Eng ko'p sardor qilinganlar</b>"]
    for label, scan in scans:
        captain_block.append("")
        captain_block.append(f"<b>{label}</b> ({num(scan.scanned)} ta jamoa)")
        captain_block.extend(_captain_lines(scan.captains, scan.scanned, players, teams, top_n))
    if overall_captain:
        captain_block.append("")
        captain_block.append(f"<b>🌍 Overall:</b> {_player_label(overall_captain, players, teams)}")
    blocks.append("\n".join(captain_block))

    chip_block = ["🎴 <b>Chiplar</b>", ""]
    for label, scan in scans:
        chip_block.append(f"<b>{label}:</b> {_chip_line(scan.chips)}")
    if overall_chip_counts:
        chip_block.append(f"<b>🌍 Overall:</b> {_chip_line(overall_chip_counts)}")
    blocks.append("\n".join(chip_block))

    blocks.append(f"{config.STATS_HASHTAG}\n\n{config.CHANNEL_TAG}")
    return "\n\n".join(blocks)


# ---------------- narx bashorati ----------------

def _watch_lines(rows: list[dict]) -> list[str]:
    """rows: [{'label': 'Calafiori (ARS)', 'cost': 55, 'percent': 104.2}]"""
    if not rows:
        return ["<i>hozircha yo'q</i>"]
    out = []
    for r in rows:
        pct = abs(r["percent"])
        text = f"{r['label']} {price(r['cost'])} — {pct:.0f}%"
        # chegaradan oshganlar ko'zga tashlanib tursin
        out.append(f"<b>{text}</b>" if pct >= config.PRICE_WATCH_SURE else text)
    return out


def price_watch_post(rises: list[dict], falls: list[dict], stamp: str) -> str:
    blocks = [f"💷 <b>Ertaga narxi o'zgarishi mumkin bo'lgan futbolchilar</b>\n🕘 {stamp} holatiga ko'ra"]

    blocks.append("\n".join(["📈 <b>Narxi ko'tarilishi mumkin</b>"] + _watch_lines(rises)))
    blocks.append("\n".join(["📉 <b>Narxi tushishi mumkin</b>"] + _watch_lines(falls)))

    blocks.append(
        f"ℹ️ {config.PRICE_WATCH_SURE}% dan oshganlar o'zgarishi kutiladi. "
        "Narxlar tunda yangilanadi — oxirgi soatlarda ko'rsatkich o'zgarishi mumkin."
    )
    blocks.append(f"{config.PRICE_WATCH_HASHTAG}\n\n{config.CHANNEL_TAG}")
    return "\n\n".join(blocks)


# ---------------- tur yakunlari sharhi ----------------

ENTRY_URL = "https://fantasy.premierleague.com/entry/{entry}/event/{gw}/"


def manager_link(m, gw: int) -> str:
    """Jamoa nomi — o'sha turdagi tarkibga havola, yonida menejer ismi."""
    url = ENTRY_URL.format(entry=m.entry, gw=gw)
    return f'<a href="{url}">{esc(m.team)}</a> ({esc(m.name)})'


def _behind(value: int | None) -> str:
    if value is None:
        return ""
    if value >= 0:
        return "yetakchi" if value == 0 else f"+{num(value)}"
    return f"−{num(abs(value))}"


def _league_block(review, gw: int) -> str:
    lines = [f"<b>{review.label} · {num(review.total_managers)} ta jamoa</b>",
             f"O'rtacha: {review.average:.0f} ochko"]

    if review.best:
        lines.append("")
        lines.append(f"🔥 Tur menejeri: {manager_link(review.best, gw)} — "
                     f"{num(review.best.event_total)} ochko")

    if review.top:
        lines.append("")
        for i, m in enumerate(review.top, 1):
            extra = []
            if m.overall_rank:
                extra.append(f"🌍 {num(m.overall_rank)}")
            behind = _behind(m.behind_leader)
            if behind:
                extra.append(behind)
            tail = f" ({' · '.join(extra)})" if extra else ""
            lines.append(f"{i}. {manager_link(m, gw)} — {num(m.total)}{tail}")

    if review.riser:
        lines.append("")
        lines.append(f"📈 Eng katta ko'tarilish: {manager_link(review.riser, gw)} — "
                     f"{num(review.riser.last_rank)} → {num(review.riser.rank)} "
                     f"(+{num(review.riser.climb)})")
    return "\n".join(lines)


def differentials_post(gw: int, next_gw: int, picks, teams: dict) -> str:
    """`bot.differentials.Picks` -> tur oralig'idagi differentiallar posti."""
    blocks = [f"💎 <b>GW{next_gw} — differentiallar</b>\n"
              f"<i>GW{gw} natijalari va egalik foizi asosida</i>"]

    if picks.low_owned:
        lines = [f"<b>🔥 Kam olingan, ko'p bergan</b>",
                 f"<i>Egalik {config.DIFF_MAX_OWN:.0f}% dan past, "
                 f"GW{gw} da {config.DIFF_MIN_POINTS}+ ochko</i>", ""]
        for d in picks.low_owned:
            lines.append(f"{d.points} | {d.label(teams)} {price(d.cost)} — {d.owned:.1f}%")
        blocks.append("\n".join(lines))

    if picks.top100:
        lines = ["<b>👑 Top-100 ning yashirin qurollari</b>",
                 "<i>Dunyo bo'yicha eng kuchli menejerlar nimani ushlab turibdi</i>", ""]
        for d in picks.top100:
            lines.append(f"{d.label(teams)} — top-100: <b>{d.elite:.0f}%</b> · "
                         f"umumiy: {d.owned:.1f}% (+{d.elite - d.owned:.0f})")
        blocks.append("\n".join(lines))

    if picks.rising:
        lines = ["<b>📈 Kech qolmang</b>",
                 "<i>Hali differential, lekin tez template'ga aylanyapti</i>", ""]
        for d in picks.rising:
            lines.append(f"{d.label(teams)} — bu hafta <b>+{num(d.transfers_in)}</b> transfer "
                         f"({d.owned:.1f}%)")
        blocks.append("\n".join(lines))

    if picks.calendar:
        lines = [f"<b>📅 Keyingi {config.DIFF_FIXTURES} tur</b>", ""]
        for d in picks.calendar:
            lines.append(f"{d.label(teams)}: {d.fixtures_text}")
        blocks.append("\n".join(lines))

    if picks.local:
        lines = [f"<b>🇺🇿 {picks.local_label}</b>",
                 f"<i>{num(picks.local_scanned)} ta jamoa tekshirildi</i>", ""]
        for d in picks.local:
            lines.append(f"{d.label(teams)} — {num(d.local_count)} ta jamoada "
                         f"({d.local:.1f}%) · dunyoda {d.owned:.1f}%")
        blocks.append("\n".join(lines))

    blocks.append(f"{config.DIFF_HASHTAG}\n\n{config.CHANNEL_TAG}")
    return "\n\n".join(blocks)


def differentials_poll(next_gw: int, picks, teams: dict) -> tuple[str, list[str]]:
    """So'rovnoma: savol va variantlar (oddiy matn, HTML emas)."""
    question = f"GW{next_gw} ga kimni olasiz?"
    options: list[str] = []
    seen: set[int] = set()
    for d in list(picks.low_owned) + list(picks.top100):
        if d.element_id in seen:
            continue
        seen.add(d.element_id)
        short = teams.get(d.team, {}).get("short_name", "")
        name = f"{d.name} ({short})" if short else d.name
        options.append(f"{name} {price(d.cost)}")
        if len(options) >= config.DIFF_POLL_OPTIONS:
            break
    if options:
        options.append("Hech kimni — jamoam tayyor")
    return question, options


def gw_review_post(gw: int, event: dict, players: dict, leader, reviews) -> str:
    blocks = [f"📈 <b>GW{gw} yakunlari</b>"]

    overall = ["<b>🌍 Overall</b>"]
    if event.get("average_entry_score") is not None:
        overall.append(f"O'rtacha: {num(int(event['average_entry_score']))} ochko")
    if event.get("highest_score") is not None:
        overall.append(f"Eng yuqori: {num(int(event['highest_score']))} ochko")
    if leader:
        overall.append(f"Yetakchi: {esc(leader[0])} — {num(leader[1])} ochko")
    top_el = event.get("top_element_info") or {}
    if top_el.get("id"):
        star = players.get(top_el["id"], {}).get("web_name", "—")
        overall.append(f"⭐️ Tur yulduzi: {esc(star)} — {num(int(top_el.get('points') or 0))} ochko")
    blocks.append("\n".join(overall))

    for review in reviews:
        blocks.append(_league_block(review, gw))

    blocks.append(f"{config.GW_REVIEW_HASHTAG}\n\n{config.CHANNEL_TAG}")
    return "\n\n".join(blocks)
