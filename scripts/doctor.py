"""Sozlamalarni tekshiruvchi diagnostika.

Ishlatish:
    python -m scripts.doctor
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import config  # noqa: E402

OK, BAD, WARN = "✓", "✗", "!"

# GitHub Actions ichida .env fayl bo'lmaydi — sozlamalar Secrets orqali keladi
IN_CI = bool(os.getenv("GITHUB_ACTIONS") or os.getenv("CI"))


def mask(value: str, keep: int = 6) -> str:
    if not value:
        return "(bo'sh)"
    return value[:keep] + "…" + value[-3:] if len(value) > keep + 4 else "(qisqa qiymat)"


def line(mark: str, label: str, detail: str = "") -> None:
    print(f" {mark}  {label}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("\n=== FPLUzbekistan bot — diagnostika ===\n")
    problems: list[str] = []

    # 1. Papka va .env
    print("Fayllar:")
    line(OK, "Loyiha papkasi", str(config.ROOT))

    if IN_CI:
        line(OK, "Muhit", "GitHub Actions — sozlamalar Secrets orqali keladi, .env kerak emas")
        return _check_settings(problems)

    exists = config.ENV_FILE.is_file()
    line(OK if exists else BAD, ".env fayl", str(config.ENV_FILE) if exists else f"topilmadi: {config.ENV_FILE}")
    if not exists:
        example = config.ROOT / ".env.example"
        edited_example = False
        if example.is_file():
            try:
                text = example.read_text(encoding="utf-8", errors="replace")
                for raw in text.splitlines():
                    if raw.strip().startswith("TELEGRAM_BOT_TOKEN="):
                        value = raw.split("=", 1)[1].strip()
                        # namunadagi qiymat "123456789:AA..." — haqiqiy token undan uzun
                        edited_example = len(value) > 25 and not value.endswith("...")
            except Exception:
                pass

        if edited_example:
            line(BAD, "Sabab topildi", "token .env.example ichiga yozilgan")
            problems.append(
                "Siz tokenni '.env.example' ga yozgansiz, bot esa '.env' ni o'qiydi.\n"
                "     Nusxa oling:      copy .env.example .env\n"
                "     Keyin MUHIM:      .env.example ichidagi tokenni o'chirib,\n"
                "                       o'rniga namunaviy qiymatni qaytaring —\n"
                "                       bu fayl GitHub'ga yuklanadi!"
            )
        else:
            problems.append(
                ".env fayl yo'q yoki nomi noto'g'ri.\n"
                "     Nusxa olish:  copy .env.example .env\n"
                "     Windows'da Notepad uni '.env.txt' qilib saqlab qo'yishi mumkin.\n"
                "     Tekshirish:   Get-ChildItem -Force\n"
                "     To'g'rilash:  ren .env.txt .env"
            )
        # yonidagi shubhali fayllar
        for cand in config.ROOT.glob(".env*"):
            if cand.name not in (".env", ".env.example"):
                line(WARN, "Shubhali fayl", f"{cand.name} — nomini '.env' ga o'zgartiring")

    status_ok = config.DOTENV_STATUS.startswith("OK")
    line(OK if status_ok else BAD, ".env yuklandimi", config.DOTENV_STATUS)
    if "python-dotenv" in config.DOTENV_STATUS:
        problems.append("python-dotenv o'rnatilmagan:  pip install -r requirements.txt")

    return _check_settings(problems)


def _check_settings(problems: list[str]) -> int:
    # 2. Sozlamalar
    print("\nSozlamalar:")
    line(OK if config.BOT_TOKEN else BAD, "TELEGRAM_BOT_TOKEN", mask(config.BOT_TOKEN))
    line(OK if config.CHANNEL_ID else BAD, "TELEGRAM_CHANNEL_ID", config.CHANNEL_ID or "(bo'sh)")
    line(OK if config.ADMIN_CHAT_ID else WARN, "TELEGRAM_ADMIN_CHAT_ID",
         config.ADMIN_CHAT_ID or "(bo'sh — ixtiyoriy, lekin --send uchun kerak)")

    where = "GitHub Secrets" if IN_CI else ".env fayl"
    if not config.BOT_TOKEN:
        problems.append(f"TELEGRAM_BOT_TOKEN bo'sh — {where}ni tekshiring.")
    if not config.CHANNEL_ID:
        problems.append(
            f"TELEGRAM_CHANNEL_ID bo'sh — {where}ni tekshiring.\n"
            "     Busiz kanalga yuborish ishlamaydi."
        )

    if config.BOT_TOKEN:
        if config.BOT_TOKEN.startswith(("'", '"')) or config.BOT_TOKEN.endswith(("'", '"')):
            problems.append("Token qo'shtirnoq ichida yozilgan — qo'shtirnoqni olib tashlang.")
        elif ":" not in config.BOT_TOKEN:
            problems.append("Token formati noto'g'ri (ichida ':' bo'lishi kerak).")

    # 3. Tarmoq
    print("\nTarmoq:")
    try:
        from bot import fpl_api

        bs = fpl_api.get_bootstrap()
        gw = fpl_api.current_event_id(bs)
        line(OK, "FPL API", f"{len(bs['elements'])} futbolchi, joriy tur: GW{gw}")
    except Exception as exc:
        line(BAD, "FPL API", str(exc)[:120])
        problems.append("FPL API'ga ulanib bo'lmadi — internet yoki VPN'ni tekshiring.")

    if config.BOT_TOKEN:
        try:
            from bot import telegram

            config.DRY_RUN = False
            me = telegram.get_me()
            line(OK, "Telegram bot", f"@{me.get('username')}")
        except Exception as exc:
            line(BAD, "Telegram bot", str(exc)[:120])
            problems.append("Token ishlamayapti — BotFather'dan qayta tekshiring.")

        if config.CHANNEL_ID:
            try:
                chat = telegram.get_chat()
                line(OK, "Kanal", chat.get("title") or config.CHANNEL_ID)
                member = telegram.get_chat_member(me["id"])
                st = member.get("status")
                ok_admin = st == "administrator"
                line(OK if ok_admin else BAD, "Botning maqomi", st or "noma'lum")
                if not ok_admin:
                    problems.append("Bot kanalda administrator emas — post yubora olmaydi.")
                elif not member.get("can_post_messages", True):
                    problems.append("Botda 'Post messages' huquqi yo'q.")
            except Exception as exc:
                line(WARN, "Kanal", str(exc)[:120])

    # Xulosa
    print()
    if problems:
        print(f"{len(problems)} ta muammo topildi:\n")
        for i, p in enumerate(problems, 1):
            print(f"  {i}. {p}")
        print()
        return 1

    if IN_CI:
        print("Hammasi joyida — Secrets to'g'ri o'qildi.\n")
    else:
        print("Hammasi joyida. Endi sinab ko'ring:")
        print("   python -m tests.mock_demo --send\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
