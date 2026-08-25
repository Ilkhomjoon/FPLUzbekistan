"""Telegram Bot API bilan ishlash (sendMessage / editMessageText)."""
from __future__ import annotations

import html
import logging
import time

import requests
from requests.adapters import HTTPAdapter

from . import config

log = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/{method}"

_session: requests.Session | None = None
LAST_CALL_SECONDS = 0.0


def session() -> requests.Session:
    """Bitta umumiy ulanish — har so'rovda yangi TLS handshake qilmaslik uchun.

    Avval har chaqiruv yangi ulanish ochardi; sekin tarmoqda bu har safar
    5-20 soniya qo'shib yuborardi. Endi ulanish qayta ishlatiladi.
    """
    global _session
    if _session is None:
        s = requests.Session()
        s.headers.update({"Connection": "keep-alive"})
        # qayta urinishni o'zimiz boshqaramiz (429 va Telegram xatolari uchun)
        adapter = HTTPAdapter(max_retries=0, pool_connections=4, pool_maxsize=8)
        s.mount("https://", adapter)
        _session = s
    return _session


class TelegramError(RuntimeError):
    pass


class TelegramNetworkError(TelegramError):
    """Tarmoq muammosi — taymaut, uzilish. Odatda o'z-o'zidan tuzaladi."""


def esc(text: str) -> str:
    """HTML parse_mode uchun xavfsiz matn."""
    return html.escape(str(text), quote=False)


def _call(method: str, **payload) -> dict:
    if not config.BOT_TOKEN:
        raise TelegramError("TELEGRAM_BOT_TOKEN o'rnatilmagan")
    global LAST_CALL_SECONDS
    url = API.format(token=config.BOT_TOKEN, method=method)
    last_err: Exception | None = None
    started = time.monotonic()
    for attempt in range(4):
        try:
            # (ulanish, o'qish) taymauti — sekin tarmoqda osilib qolmaslik uchun
            r = session().post(url, json=payload, timeout=(10, 60))
            data = r.json()
            LAST_CALL_SECONDS = time.monotonic() - started
            if LAST_CALL_SECONDS > 5:
                log.warning("%s sekin bajarildi: %.1f s", method, LAST_CALL_SECONDS)
            else:
                log.debug("%s: %.2f s", method, LAST_CALL_SECONDS)
        except Exception as exc:  # tarmoq xatosi
            last_err = exc
            log.warning("%s tarmoq xatosi (%d-urinish): %s", method, attempt + 1, exc)
            time.sleep(2 * (attempt + 1))
            continue
        if data.get("ok"):
            return data["result"]
        desc = data.get("description", "")
        # 429 — juda ko'p so'rov, kutamiz
        if r.status_code == 429:
            wait = int(data.get("parameters", {}).get("retry_after", 5))
            log.warning("Telegram 429, %s soniya kutamiz", wait)
            time.sleep(wait + 1)
            continue
        # matn o'zgarmagan bo'lsa — bu xato emas
        if "message is not modified" in desc:
            log.debug("Xabar o'zgarmadi, tahrirlash o'tkazib yuborildi")
            return {}
        raise TelegramError(f"{method} xatosi: {desc}")
    raise TelegramNetworkError(f"{method} bajarilmadi: {last_err}")


def send_message(text: str, chat_id: str | None = None, silent: bool = False) -> dict:
    chat_id = chat_id or config.CHANNEL_ID
    if config.DRY_RUN:
        print("\n" + "=" * 48)
        print(f"[DRY-RUN] -> {chat_id}")
        print("=" * 48)
        print(text)
        print("=" * 48 + "\n")
        return {"message_id": 0, "dry_run": True}
    return _call(
        "sendMessage",
        chat_id=chat_id,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
        disable_notification=silent,
    )


def edit_message(message_id: int, text: str, chat_id: str | None = None) -> dict:
    chat_id = chat_id or config.CHANNEL_ID
    if config.DRY_RUN:
        print(f"\n[DRY-RUN] xabar #{message_id} yangilandi:\n{text}\n")
        return {"message_id": message_id, "dry_run": True}
    return _call(
        "editMessageText",
        chat_id=chat_id,
        message_id=message_id,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


_last_alert: dict[str, float] = {}
ALERT_COOLDOWN = 900  # bir xil xatolik uchun 15 daqiqada bir marta


def get_me() -> dict:
    """Bot haqidagi ma'lumot — token to'g'riligini tekshirish uchun."""
    return _call("getMe")


def get_chat(chat_id: str | None = None) -> dict:
    """Kanal haqidagi ma'lumot — bot kanalni ko'ra oladimi, shuni tekshiradi."""
    return _call("getChat", chat_id=chat_id or config.CHANNEL_ID)


def get_chat_member(user_id: int, chat_id: str | None = None) -> dict:
    """Botning kanaldagi huquqlari."""
    return _call("getChatMember", chat_id=chat_id or config.CHANNEL_ID, user_id=user_id)


def pin_message(message_id: int, chat_id: str | None = None) -> bool:
    """Xabarni kanal tepasiga qadaydi. Muvaffaqiyatli bo'lsa True."""
    if config.DRY_RUN:
        print(f"[DRY-RUN] xabar #{message_id} pin qilindi")
        return True
    try:
        _call("pinChatMessage", chat_id=chat_id or config.CHANNEL_ID,
              message_id=message_id, disable_notification=True)
        return True
    except TelegramError as exc:
        log.warning("Pin qilib bo'lmadi: %s", exc)
        return False


def unpin_message(message_id: int, chat_id: str | None = None) -> bool:
    """Xabarni tepadan olib tashlaydi."""
    if config.DRY_RUN:
        print(f"[DRY-RUN] xabar #{message_id} pindan olindi")
        return True
    try:
        _call("unpinChatMessage", chat_id=chat_id or config.CHANNEL_ID, message_id=message_id)
        return True
    except TelegramError as exc:
        log.warning("Pindan olib bo'lmadi: %s", exc)
        return False


def notify_admin(text: str) -> None:
    """Xatolik yuz berganda adminga (shaxsiy chatga) xabar. Bir xil xato spam qilmaydi."""
    if not config.ADMIN_CHAT_ID:
        log.warning("ADMIN_CHAT_ID yo'q, ogohlantirish yuborilmadi")
        return
    key = text[:120]
    now = time.time()
    if now - _last_alert.get(key, 0) < ALERT_COOLDOWN:
        log.debug("Bir xil ogohlantirish yaqinda yuborilgan, o'tkazib yuboramiz")
        return
    _last_alert[key] = now
    try:
        send_message(text, chat_id=config.ADMIN_CHAT_ID, silent=False)
    except Exception as exc:  # ogohlantirish yuborilmasa ham dastur to'xtamasin
        log.error("Adminga xabar yuborilmadi: %s", exc)


def split_message(text: str, limit: int = 4000) -> list[str]:
    """Uzun matnni Telegram limitiga sig'adigan bo'laklarga bo'ladi."""
    if len(text) <= limit:
        return [text]
    parts, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > limit:
            parts.append(current.rstrip())
            current = ""
        current += line + "\n"
    if current.strip():
        parts.append(current.rstrip())
    return parts