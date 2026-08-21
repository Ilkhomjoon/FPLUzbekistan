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


def _fixture_block(fx: dict, players: dict, teams: dict, defcon: dict[int, int] | None = None,
                   compact: bool = False) -> list[str]:
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
    header = f"{emoji} {esc(home)} {score} {esc(away)}"

    bonuses, official = fixture_bonus(fx, config.BONUS_MIN_BPS)
    bps_map = {int(r["element"]): int(r["value"]) for r in fixture_stat(fx, "bps")}

    lines = [header]
    if bonuses:
        # teng bonusda BPS yuqorisi tepada tursin
        ranked = sorted(
            bonuses.items(),
            key=lambda kv: (-kv[1], -bps_map.get(kv[0], 0), players.get(kv[0], {}).get("web_name", "")),
        )
        limit = 3 if compact else max(1, config.BONUS_MAX_PLAYERS)
        for element_id, pts in ranked[:limit]:
            bps = bps_map.get(element_id)
            show_bps = config.SHOW_BPS and not compact and bps is not None
            bps_txt = f" · {bps} BPS" if show_bps else ""
            lines.append(f"{pts} | {_player_label(element_id, players, teams)}{bps_txt}")
        hidden = len(ranked) - limit
        if hidden > 0:
            lines.append(f"<i>… yana {hidden} ta teng natija</i>")
    elif not finished:
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
    text = _live_post(fixtures, players, teams, gw, defcon, compact=False)
    if len(text) <= SAFE_LIMIT:
        return text
    text = _live_post(fixtures, players, teams, gw, defcon, compact=True)
    if len(text) <= TELEGRAM_LIMIT:
        return text
    return text[: TELEGRAM_LIMIT - 2] + "…"


def _live_post(
    fixtures: list[dict],
    players: dict,
    teams: dict,
    gw: int | None = None,
    defcon: dict[int, dict[int, int]] | None = None,
    compact: bool = False,
) -> str:
    stamp = now_local().strftime("%H:%M:%S")
    head = f"🔄 So'ngi yangilanish: {stamp}"
    if gw:
        head = f"<b>GW{gw} — Bonus ochkolar</b>\n{head}"

    blocks: list[str] = [head]
    ordered = sorted(fixtures, key=lambda f: (f.get("kickoff_time") or "", f.get("id", 0)))
    for fx in ordered:
        fx_defcon = (defcon or {}).get(fx.get("id"), {})
        blocks.append("\n".join(_fixture_block(fx, players, teams, fx_defcon, compact)))

    all_done = all(f.get("finished") or f.get("finished_provisional") for f in fixtures) and fixtures
    if all_done:
        blocks.append("✅ Bugungi o'yinlar yakunlandi.")

    blocks.append(f"{config.LIVE_HASHTAG}\n\n{config.CHANNEL_TAG}")
    return "\n\n".join(blocks)
