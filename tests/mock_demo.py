"""Soxta (mock) ma'lumot bilan postlarni sinash.

Ekranga chiqarish (internet kerak emas):
    python -m tests.mock_demo

Telegramga haqiqiy yuborish (avval o'zingizga, keyin kanalga):
    python -m tests.mock_demo --send                    # shaxsiy chatga (ADMIN_CHAT_ID)
    python -m tests.mock_demo --send --to @FPLUzbekistan # kanalga
    python -m tests.mock_demo --send --pause 5           # yangilanishlar orasidagi kutish
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timedelta, timezone

from bot import config, formatting, price_changes

TEAMS = [
    {"id": 1, "name": "Man City", "short_name": "MCI"},
    {"id": 2, "name": "Man Utd", "short_name": "MUN"},
    {"id": 3, "name": "Chelsea", "short_name": "CHE"},
    {"id": 4, "name": "Arsenal", "short_name": "ARS"},
]

# element_type: 1=GK, 2=DEF, 3=MID, 4=FWD
PLAYERS = [
    {"id": 1, "web_name": "Cherki", "team": 1, "now_cost": 65, "element_type": 3},
    {"id": 2, "web_name": "Welbeck", "team": 3, "now_cost": 63, "element_type": 4},
    {"id": 3, "web_name": "Wilson", "team": 4, "now_cost": 58, "element_type": 4},
    {"id": 4, "web_name": "Casemiro", "team": 2, "now_cost": 58, "element_type": 3},
    {"id": 5, "web_name": "Haaland", "team": 1, "now_cost": 145, "element_type": 4},
    {"id": 6, "web_name": "Khusanov", "team": 1, "now_cost": 45, "element_type": 2},
    {"id": 7, "web_name": "Saka", "team": 4, "now_cost": 101, "element_type": 3},
    {"id": 8, "web_name": "Gvardiol", "team": 1, "now_cost": 60, "element_type": 2},
]

PLAYER_MAP = {p["id"]: p for p in PLAYERS}
TEAM_MAP = {t["id"]: t for t in TEAMS}


def bootstrap(costs: dict[int, int] | None = None) -> dict:
    elements = []
    for p in PLAYERS:
        q = dict(p)
        if costs and p["id"] in costs:
            q["now_cost"] = costs[p["id"]]
        elements.append(q)
    return {
        "elements": elements,
        "teams": TEAMS,
        "events": [{"id": 3, "is_current": True, "is_next": False}],
    }


def stat(identifier, home, away):
    return {
        "identifier": identifier,
        "h": [{"element": e, "value": v} for e, v in home],
        "a": [{"element": e, "value": v} for e, v in away],
    }


# ---------------- namunaviy matnlar ----------------

def price_texts() -> tuple[str, str]:
    old = price_changes.build_snapshot(bootstrap())
    new = price_changes.build_snapshot(bootstrap({1: 64, 2: 62, 5: 146, 7: 102}))
    down, up = price_changes.diff(old, new)
    return (
        formatting.price_change_post(down, "down"),
        formatting.price_change_post(up, "up"),
    )


def _fixtures(stage: int) -> list[dict]:
    """stage: 1 = o'yin ketyapti, 2 = BPS o'zgardi, 3 = hammasi tugadi."""
    now = datetime.now(timezone.utc)

    def iso(delta_min: int) -> str:
        return (now + timedelta(minutes=delta_min)).isoformat().replace("+00:00", "Z")

    live = {
        "id": 101, "event": 3, "team_h": 1, "team_a": 2,
        "team_h_score": 1, "team_a_score": 1,
        "kickoff_time": iso(-50), "started": True,
        "finished": False, "finished_provisional": False, "minutes": 50,
        "stats": [stat("bps", [(6, 24), (5, 21)], [(4, 22)]), stat("bonus", [], [])],
    }
    done = {
        "id": 102, "event": 3, "team_h": 3, "team_a": 4,
        "team_h_score": 0, "team_a_score": 3,
        "kickoff_time": iso(-170), "started": True,
        "finished": True, "finished_provisional": True, "minutes": 90,
        "stats": [stat("bps", [(2, 12)], [(7, 41), (3, 33)]), stat("bonus", [], [(7, 3), (3, 2)])],
    }
    later = {
        "id": 103, "event": 3, "team_h": 4, "team_a": 1,
        "team_h_score": None, "team_a_score": None,
        "kickoff_time": iso(120), "started": False,
        "finished": False, "finished_provisional": False, "minutes": 0,
        "stats": [],
    }

    if stage == 1:
        return [done, live, later]

    if stage == 2:  # Haaland gol urdi, BPS o'zgardi
        live = dict(live, team_h_score=2, minutes=71,
                    stats=[stat("bps", [(5, 38), (6, 30)], [(4, 22)]), stat("bonus", [], [])])
        return [done, live, later]

    # stage 3 — hammasi tugadi
    live = dict(live, team_h_score=2, minutes=90, finished=True, finished_provisional=True,
                stats=[stat("bps", [(5, 38), (6, 30)], [(4, 22)]),
                       stat("bonus", [(5, 3), (6, 2)], [(4, 1)])])
    later = dict(later, started=True, finished=True, finished_provisional=True,
                 team_h_score=1, team_a_score=1, minutes=90,
                 stats=[stat("bps", [(7, 28)], [(5, 28), (6, 19)]),
                        stat("bonus", [(7, 3)], [(5, 3), (6, 1)])])
    return [done, live, later]


def _live_payload(stage: int) -> dict:
    """`/event/{gw}/live/` javobiga o'xshash soxta ma'lumot (DefCon uchun)."""

    def el(pid, fixture, cbi, tackles, recoveries, awarded=None):
        stats = {
            "clearances_blocks_interceptions": cbi,
            "tackles": tackles,
            "recoveries": recoveries,
        }
        explain_stats = []
        if awarded:
            explain_stats.append({"identifier": "defensive_contribution", "points": 2, "value": 1})
        return {"id": pid, "stats": stats, "explain": [{"fixture": fixture, "stats": explain_stats}]}

    if stage == 1:  # o'yin o'rtasi — hali hech kim chegaraga yetmagan
        return {"elements": [
            el(6, 101, 4, 2, 1), el(8, 101, 5, 1, 0), el(4, 101, 3, 3, 4),
            el(7, 102, 2, 1, 6, awarded=False), el(3, 102, 1, 0, 3),
        ]}

    # 2 va 3-holat — Khusanov va Casemiro chegaradan o'tdi (API o'zi bergan),
    # Gvardiol esa zaxira hisob orqali aniqlanadi (10 CBIT, explain bo'sh)
    return {"elements": [
        el(6, 101, 7, 4, 2, awarded=True),
        el(8, 101, 8, 2, 1),
        el(4, 101, 5, 4, 6, awarded=True),
        el(7, 102, 3, 2, 8),
        el(3, 102, 1, 0, 4),
    ]}


def live_text(stage: int) -> str:
    from bot import defcon as defcon_mod

    fixtures = _fixtures(stage)
    started = [f["id"] for f in fixtures if f.get("started")]
    defcon = defcon_mod.by_fixture(_live_payload(stage), started, PLAYER_MAP)
    return formatting.live_bonus_post(fixtures, PLAYER_MAP, TEAM_MAP, gw=3, defcon=defcon)


# ---------------- rejimlar ----------------

def show() -> None:
    config.DRY_RUN = True
    down, up = price_texts()
    print("\n########## 1) NARX O'ZGARISHLARI ##########\n")
    print(down + "\n")
    print(up)
    print("\n--- o'zgarish bo'lmagan holat ---")
    print("tushgan=0, ko'tarilgan=0 -> kanalga post yuborilmaydi (faqat log)")

    print("\n\n########## 2) JONLI BONUS OCHKOLAR ##########")
    for stage, label in ((1, "o'yin ketyapti"), (2, "BPS o'zgardi"), (3, "hammasi tugadi")):
        print(f"\n--- {label} ---")
        print(live_text(stage))


def send(target: str, pause: int) -> int:
    from bot import telegram

    config.DRY_RUN = False
    if not config.BOT_TOKEN:
        print("XATO: TELEGRAM_BOT_TOKEN topilmadi. .env faylni tekshiring.")
        return 1

    def timed(label: str, fn):
        """Har bir qadamning necha soniya olganini ko'rsatadi."""
        start = time.monotonic()
        result = fn()
        print(f"      ⏱ {label}: {time.monotonic() - start:.1f} s")
        return result

    total_start = time.monotonic()
    me = timed("getMe", telegram.get_me)
    print(f"✓ Bot: @{me.get('username')} (id={me.get('id')})")

    try:
        chat = telegram.get_chat(target)
        print(f"✓ Chat topildi: {chat.get('title') or chat.get('username') or target}")
        if chat.get("type") == "channel":
            member = telegram.get_chat_member(me["id"], target)
            status = member.get("status")
            print(f"✓ Botning maqomi: {status}")
            if status != "administrator":
                print("  ⚠️  Bot administrator emas — post yubora olmaydi!")
            elif not member.get("can_post_messages", True):
                print("  ⚠️  'Post messages' huquqi yo'q!")
    except Exception as exc:
        print(f"  ⚠️  Chatni tekshirib bo'lmadi: {exc}")

    down, up = price_texts()

    print(f"\n[1/4] Narx tushishi posti -> {target}")
    timed("sendMessage", lambda: telegram.send_message(down, chat_id=target))

    print(f"[2/4] Narx ko'tarilishi posti -> {target}")
    timed("sendMessage", lambda: telegram.send_message(up, chat_id=target))

    print("[3/4] Jonli bonus xabari (yangi)")
    res = timed("sendMessage", lambda: telegram.send_message(live_text(1), chat_id=target))
    message_id = res.get("message_id")
    print(f"      message_id={message_id}")

    print(f"[4/4] Xabarni tahrirlash — {pause} soniyada bir, 2 marta")
    for stage in (2, 3):
        time.sleep(pause)
        timed("editMessageText", lambda: telegram.edit_message(message_id, live_text(stage), chat_id=target))
        print(f"      ✓ {stage}-holat yozildi (yuqoridagi xabar o'zgarganini ko'ring)")

    elapsed = time.monotonic() - total_start
    waited = pause * 2
    print(f"\n⏱ Jami: {elapsed:.1f} s (shundan {waited} s — ataylab kutish, "
          f"tarmoqqa ketgani: {elapsed - waited:.1f} s)")
    if elapsed - waited > 20:
        print("   ⚠️  Tarmoq sekin. Telegram API'ga ulanish muammosi bo'lishi mumkin —")
        print("       VPN yoqilgan bo'lsa o'chirib, yoki aksincha, sinab ko'ring.")

    print("\n✅ Test tugadi. Telegramda tekshiring:")
    print("   • 2 ta narx posti alohida xabar bo'lib chiqdimi?")
    print("   • Jonli xabar 3 marta yangilandimi (bitta xabar ichida)?")
    print("   • Emoji, £ belgisi va 'So'ngi yangilanish' vaqti to'g'ri ko'rinyaptimi?")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Mock ma'lumot bilan sinash")
    ap.add_argument("--send", action="store_true", help="Telegramga haqiqiy yuboradi")
    ap.add_argument("--to", default=None, help="Qabul qiluvchi: @kanal yoki chat id (standart: ADMIN_CHAT_ID)")
    ap.add_argument("--pause", type=int, default=8, help="Yangilanishlar orasidagi kutish (soniya)")
    args = ap.parse_args()

    if not args.send:
        show()
        return 0

    target = args.to or config.ADMIN_CHAT_ID
    if not target:
        print("XATO: qabul qiluvchi topilmadi.\n")
        print(f"  .env holati: {config.DOTENV_STATUS}")
        print(f"  .env yo'li:  {config.ENV_FILE}")
        print(f"  TELEGRAM_BOT_TOKEN: {'bor' if config.BOT_TOKEN else 'YO‘Q'}")
        print(f"  TELEGRAM_ADMIN_CHAT_ID: {config.ADMIN_CHAT_ID or 'YO‘Q'}\n")
        print("Batafsil tekshirish uchun:  python -m scripts.doctor")
        print("Yoki to'g'ridan-to'g'ri bering: python -m tests.mock_demo --send --to 94101530")
        return 1
    return send(str(target), args.pause)


if __name__ == "__main__":
    sys.exit(main())