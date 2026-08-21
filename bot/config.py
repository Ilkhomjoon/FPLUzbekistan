"""Sozlamalar — hammasi environment variable (.env yoki GitHub Secrets) orqali."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = Path(os.getenv("ENV_FILE", ROOT / ".env"))

# .env ni yuklash. Nima bo'lganini DOTENV_STATUS da saqlaymiz — jimgina
# o'tib ketmaslik uchun (avval shu sabab "sozlama yo'q" xatosi tushunarsiz edi).
DOTENV_STATUS = ""
try:
    from dotenv import load_dotenv

    if ENV_FILE.is_file():
        load_dotenv(ENV_FILE, override=False)
        DOTENV_STATUS = f"OK — {ENV_FILE}"
    elif load_dotenv(override=False):
        DOTENV_STATUS = "OK — joriy papkadagi .env"
    else:
        DOTENV_STATUS = f"XATO — .env fayl topilmadi ({ENV_FILE})"
except ImportError:
    DOTENV_STATUS = "XATO — python-dotenv o'rnatilmagan: pip install python-dotenv"
except Exception as _exc:  # pragma: no cover
    DOTENV_STATUS = f"XATO — .env o'qilmadi: {_exc}"


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on", "ha"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))

# --- Telegram ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()  # @FPLUzbekistan yoki -100...
ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").strip()  # xatolik xabarlari uchun

# --- Umumiy ---
DRY_RUN = _bool("DRY_RUN", False)          # True bo'lsa Telegramga yubormaydi, terminalga chiqaradi
CHANNEL_TAG = os.getenv("CHANNEL_TAG", "@FPLUzbekistan")
LOCAL_TZ = os.getenv("LOCAL_TZ", "Asia/Tashkent")        # vaqtlarni ko'rsatish uchun
MATCHDAY_TZ = os.getenv("MATCHDAY_TZ", "Europe/London")  # "o'yin kuni" shu zona bo'yicha aniqlanadi

# --- Narx o'zgarishlari ---
PRICE_STATE_FILE = DATA_DIR / "prices.json"
PRICE_HASHTAG = os.getenv("PRICE_HASHTAG", "#PriceChanges")
PRICE_SHOW_TEAM = _bool("PRICE_SHOW_TEAM", False)  # "Cherki (MCI) (£6.5M)" ko'rinishi

# --- Live bonus ---
LIVE_STATE_FILE = DATA_DIR / "live_message.json"
LIVE_HASHTAG = os.getenv("LIVE_HASHTAG", "#BonusPoints")
SHOW_BPS = _bool("SHOW_BPS", True)                   # bonus yonida BPS ham ko'rsatilsinmi
SHOW_DEFCON = _bool("SHOW_DEFCON", True)             # DefCon oluvchilar qatori chiqsinmi
BONUS_MIN_BPS = _int("BONUS_MIN_BPS", 5)             # shundan past BPS hisobga olinmaydi
                                                     # (o'yinga chiqqani uchun 3, 60-daqiqadan keyin 6 beriladi)
BONUS_MAX_PLAYERS = _int("BONUS_MAX_PLAYERS", 6)     # bitta o'yinda ko'pi bilan nechta qator
DEFCON_TTL = _int("DEFCON_TTL", 120)                 # DefCon ma'lumoti necha soniyada bir yangilanadi
LIVE_INTERVAL = _int("LIVE_INTERVAL", 60)            # necha soniyada bir yangilanadi
LIVE_MAX_MINUTES = _int("LIVE_MAX_MINUTES", 300)     # bitta jarayon maksimal necha daqiqa ishlaydi
LIVE_START_LEAD = _int("LIVE_START_LEAD", 5)         # o'yin boshlanishiga necha daqiqa qolganda uyg'onsin
LIVE_FINISH_GRACE = _int("LIVE_FINISH_GRACE", 10)    # oxirgi o'yin tugagach yana necha daqiqa kuzatsin


def require_telegram() -> None:
    """Telegram sozlamalari borligini tekshiradi (DRY_RUN da shart emas)."""
    if DRY_RUN:
        return
    missing = [n for n, v in (("TELEGRAM_BOT_TOKEN", BOT_TOKEN), ("TELEGRAM_CHANNEL_ID", CHANNEL_ID)) if not v]
    if missing:
        raise SystemExit(f"Sozlama yetishmayapti: {', '.join(missing)}. .env faylni yoki GitHub Secrets'ni tekshiring.")
