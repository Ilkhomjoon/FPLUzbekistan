"""FPL ochiq API bilan ishlash."""
from __future__ import annotations

import logging
from datetime import datetime, date, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://fantasy.premierleague.com/api"
log = logging.getLogger(__name__)

_session: requests.Session | None = None


def session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update(
            {
                "User-Agent": "FPLUzbekistanBot/1.0 (+https://t.me/FPLUzbekistan)",
                "Accept": "application/json",
            }
        )
        retry = Retry(
            total=4,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
        )
        s.mount("https://", HTTPAdapter(max_retries=retry))
        _session = s
    return _session


def _get(path: str, **params: Any) -> Any:
    url = f"{BASE}{path}"
    r = session().get(url, params=params or None, timeout=30)
    r.raise_for_status()
    return r.json()


def get_bootstrap() -> dict:
    """Futbolchilar, jamoalar va gameweek'lar haqidagi asosiy ma'lumot."""
    return _get("/bootstrap-static/")


def get_fixtures(event: int | None = None) -> list[dict]:
    """O'yinlar ro'yxati. event berilsa faqat o'sha turdagi o'yinlar."""
    return _get("/fixtures/", **({"event": event} if event else {}))


def get_live(event: int) -> dict:
    """Tur davomidagi jonli statistika — har bir futbolchining ochkolari va harakatlari.

    DefCon uchun kerak: `explain` bloki o'yin bo'yicha `defensive_contribution`
    identifikatorini beradi.
    """
    return _get(f"/event/{event}/live/")


def get_event_status() -> dict:
    """Turning yakunlanish holati — kun-kun.

    `bootstrap-static` dagi `finished` bayrog'i ancha kech qo'yiladi, shuning
    uchun turning yakunlanganini shu endpoint bo'yicha aniqlaymiz.
    """
    return _get("/event-status/")


# ---------- turning yakunlanishi ----------

POINTS_FINAL = "r"  # "p" = provisional (vaqtinchalik), "r" = results (yakuniy)


def points_final_at(status: dict) -> datetime | None:
    """Ochkolar qachon yakuniy bo'lgani — turning oxirgi o'yin kunidan keyingi
    kun, Britaniya vaqti bilan 09:00. `leagues` bayrog'iga qancha kutganimizni
    shu nuqtadan hisoblaymiz."""
    from . import config

    days = [r.get("date") for r in (status.get("status") or []) if r.get("date")]
    if not days:
        return None
    try:
        last = max(date.fromisoformat(d) for d in days)
    except ValueError:
        return None
    tz = ZoneInfo(config.MATCHDAY_TZ)
    return datetime.combine(last + timedelta(days=1), time(9, 0), tz).astimezone(timezone.utc)


def status_verdict(status: dict, now: datetime | None = None) -> tuple[int | None, bool, str]:
    """/event-status/ -> (tur raqami, tayyormi, sabab).

    2026/27 dan FPL ochkolarni turning oxirgi o'yinidan keyingi kuni Britaniya
    vaqti bilan 09:00 da yakuniy qiladi. Shu paytda:

        points:      "p" -> "r"      (ochkolar yakuniy)
        bonus_added: false -> true   (bonus rasman qo'shildi)
        leagues:     "Updating"      (liga jadvallari qayta hisoblanmoqda)

    Birinchi ikkitasi — qat'iy shart. `leagues` esa YUMSHOQ shart: biz liga
    jadvallarini o'qiganimiz uchun uni kutamiz, lekin cheksiz emas.

    19-oktyabrda GW7 ochkolari yakuniy bo'ldi, `leagues` esa ikki kun
    "Updating" bo'lib osilib qoldi — natijada na tur sharhi, na differentiallar
    chiqdi. Shuning uchun endi LEAGUE_UPDATE_GRACE daqiqadan keyin bu bayroqqa
    qaramaymiz; jadval haqiqatan hisoblanganini liganing o'z ma'lumotidan
    (`event_total`) tekshiramiz.
    """
    from . import config

    rows = status.get("status") or []
    if not rows:
        return None, False, "event-status bo'sh"

    event = rows[0].get("event")
    if not all(r.get("points") == POINTS_FINAL for r in rows):
        return event, False, "ochkolar hali vaqtinchalik (points='p')"
    if not all(r.get("bonus_added") for r in rows):
        return event, False, "bonus hali rasman qo'shilmagan"

    if (status.get("leagues") or "").strip().lower() == "updating":
        final_at = points_final_at(status)
        now = now or datetime.now(timezone.utc)
        if final_at is None:
            return event, True, "tayyor (liga bayrog'i 'Updating', sana yo'q)"
        waited = (now - final_at).total_seconds() / 60
        if waited < config.LEAGUE_UPDATE_GRACE:
            return event, False, (f"ochkolar yakunlandi, liga jadvallari yangilanmoqda "
                                  f"({waited:.0f}/{config.LEAGUE_UPDATE_GRACE} daqiqa)")
        return event, True, (f"tayyor (liga bayrog'i {waited/60:.1f} soatdan beri "
                             "'Updating' — osilib qolgan deb hisoblaymiz)")

    return event, True, "tayyor"


def finalised_event(bootstrap: dict, status: dict | None = None) -> dict | None:
    """Yakunlangan turni qaytaradi (yo'q bo'lsa None).

    Avval /event-status/ ga qaraymiz — u `finished` bayrog'idan ancha oldin
    yangilanadi. Undan aniqlanmasa, bootstrap dagi `finished` ga tayanamiz.
    """
    events = bootstrap.get("events", [])
    if status is None:
        try:
            status = get_event_status()
        except Exception:
            status = {}

    event_id, ready, _ = status_verdict(status or {})
    if ready and event_id:
        found = next((e for e in events if e.get("id") == event_id), None)
        if found:
            return found

    finished = [e for e in events if e.get("finished")]
    return finished[-1] if finished else None


# ---------- yordamchi funksiyalar ----------

def players_by_id(bootstrap: dict) -> dict[int, dict]:
    return {p["id"]: p for p in bootstrap["elements"]}


def teams_by_id(bootstrap: dict) -> dict[int, dict]:
    return {t["id"]: t for t in bootstrap["teams"]}


def current_event_id(bootstrap: dict) -> int | None:
    for e in bootstrap.get("events", []):
        if e.get("is_current"):
            return e["id"]
    for e in bootstrap.get("events", []):
        if e.get("is_next"):
            return e["id"]
    return None


def fixture_stat(fixture: dict, identifier: str) -> list[dict]:
    """Fixture ichidagi statistikani (bps, bonus, goals_scored...) tekis ro'yxat qilib qaytaradi."""
    out: list[dict] = []
    for block in fixture.get("stats") or []:
        if block.get("identifier") != identifier:
            continue
        for side in ("h", "a"):
            for item in block.get(side) or []:
                out.append({"element": item["element"], "value": item["value"], "side": side})
    return out
