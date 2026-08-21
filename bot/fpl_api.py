"""FPL ochiq API bilan ishlash."""
from __future__ import annotations

import logging
from typing import Any

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
