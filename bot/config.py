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


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))

# --- Telegram ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()  # @FPLUzbekistan yoki -100...
ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").strip()  # xatolik xabarlari uchun

# --- Umumiy ---
ERROR_ALERT_AFTER = _int("ERROR_ALERT_AFTER", 3)  # necha marta ketma-ket xatodan keyin xabar berilsin
DRY_RUN = _bool("DRY_RUN", False)          # True bo'lsa Telegramga yubormaydi, terminalga chiqaradi
CHANNEL_TAG = os.getenv("CHANNEL_TAG", "@FPLUzbekistan")
LOCAL_TZ = os.getenv("LOCAL_TZ", "Asia/Tashkent")        # vaqtlarni ko'rsatish uchun
MATCHDAY_TZ = os.getenv("MATCHDAY_TZ", "Europe/London")  # "o'yin kuni" shu zona bo'yicha aniqlanadi

# --- Narx o'zgarishlari ---
PRICE_STATE_FILE = DATA_DIR / "prices.json"
PRICE_HASHTAG = os.getenv("PRICE_HASHTAG", "#PriceChanges")
PRICE_SHOW_TEAM = _bool("PRICE_SHOW_TEAM", False)  # "Cherki (MCI) (£6.5M)" ko'rinishi
# --watch rejimi: cron erta uyg'onadi, o'zgarishni kutadi va aynan PRICE_POST_AT
# da yuboradi. Shu tufayli GitHub cron'i 1 soat kechiksa ham post o'z vaqtida chiqadi.
PRICE_POST_AT = os.getenv("PRICE_POST_AT", "06:00")        # LOCAL_TZ bo'yicha
PRICE_WATCH_UNTIL = os.getenv("PRICE_WATCH_UNTIL", "07:30")  # shu vaqtgacha kutamiz
PRICE_POLL = _int("PRICE_POLL", 120)                       # necha soniyada bir tekshirilsin

# --- Live bonus ---
LIVE_STATE_FILE = DATA_DIR / "live_message.json"
LIVE_HASHTAG = os.getenv("LIVE_HASHTAG", "#BonusPoints")
LIVE_LABEL = os.getenv("LIVE_LABEL", "🔴 LIVE")      # o'yin ketayotgandagi sarlavha belgisi
DONE_LABEL = os.getenv("DONE_LABEL", "✅ YAKUNLANDI")  # hammasi tugagandagi belgi
WAIT_LABEL = os.getenv("WAIT_LABEL", "⚪️ KUTILMOQDA")  # hali boshlanmagan
SHOW_BPS = _bool("SHOW_BPS", True)                   # bonus yonida BPS ham ko'rsatilsinmi
SHOW_DEFCON = _bool("SHOW_DEFCON", True)             # DefCon oluvchilar qatori chiqsinmi
SHOW_GOALS = _bool("SHOW_GOALS", True)               # gol va assistlar qatori chiqsinmi
SHOW_CARDS = _bool("SHOW_CARDS", True)               # sariq/qizil kartochkalar chiqsinmi
GOALS_SHOW_TEAM = _bool("GOALS_SHOW_TEAM", False)    # "Saka (ARS, 1)" ko'rinishi
BONUS_MIN_BPS = _int("BONUS_MIN_BPS", 5)             # shundan past BPS hisobga olinmaydi
                                                     # (o'yinga chiqqani uchun 3, 60-daqiqadan keyin 6 beriladi)
BONUS_MAX_PLAYERS = _int("BONUS_MAX_PLAYERS", 6)     # bitta o'yinda ko'pi bilan nechta qator
DEFCON_TTL = _int("DEFCON_TTL", 120)                 # DefCon ma'lumoti necha soniyada bir yangilanadi
LIVE_INTERVAL = _int("LIVE_INTERVAL", 60)            # necha soniyada bir yangilanadi
LIVE_MAX_MINUTES = _int("LIVE_MAX_MINUTES", 300)     # bitta jarayon maksimal necha daqiqa ishlaydi
LIVE_START_LEAD = _int("LIVE_START_LEAD", 5)         # o'yin boshlanishiga necha daqiqa qolganda uyg'onsin
LIVE_PREKICK_POLL = _int("LIVE_PREKICK_POLL", 60)    # o'yingacha shuncha soniya qolganda
                                                     # tez-tez so'ray boshlaymiz (undan oldin uxlaymiz)
LIVE_FINISH_GRACE = _int("LIVE_FINISH_GRACE", 10)    # oxirgi o'yin tugagach yana necha daqiqa kuzatsin
COLLAPSE_FINISHED = _bool("COLLAPSE_FINISHED", True)  # tugagan o'yinlar yig'ilgan holda tursinmi
PIN_LIVE_MESSAGE = _bool("PIN_LIVE_MESSAGE", True)   # jonli xabar kanal tepasiga qadalsinmi
UNPIN_AFTER_FINAL = _bool("UNPIN_AFTER_FINAL", True) # yakuniy yangilanishdan keyin olinsinmi
FINAL_SWEEP_MINUTES = _int("FINAL_SWEEP_MINUTES", 150)  # kun yakunlangach necha daqiqadan so'ng
                                                     # oxirgi marta yangilansin (rasmiy DefCon uchun)


# --- Narx bashorati (kechqurungi post) ---
PRICE_WATCH_STATE_FILE = DATA_DIR / "price_watch.json"
PRICE_WATCH_HASHTAG = os.getenv("PRICE_WATCH_HASHTAG", "#PriceWatch")
PRICE_WATCH_MIN = _int("PRICE_WATCH_MIN", 85)          # shu foizdan pastlari ro'yxatga tushmaydi
PRICE_WATCH_MAX = _int("PRICE_WATCH_MAX", 8)           # har tomonda ko'pi bilan nechta futbolchi
PRICE_WATCH_SURE = _int("PRICE_WATCH_SURE", 100)       # shundan oshgani "kutilmoqda" deb qalin yoziladi

# --- Deadline statistikasi (sardorlar va chiplar) ---
STATS_STATE_FILE = DATA_DIR / "deadline_stats.json"
STATS_HASHTAG = os.getenv("STATS_HASHTAG", "#GWStats")
STATS_LEAD = _int("STATS_LEAD", 40)          # birinchi o'yingacha shuncha daqiqa qolganda boshlanadi
STATS_MIN_LEAD = _int("STATS_MIN_LEAD", 3)   # bundan kam qolgan bo'lsa umuman chiqarmaymiz
STATS_WAKE_LEAD = _int("STATS_WAKE_LEAD", 300)  # --wait rejimida: o'yingacha shuncha daqiqadan
                                             # kam qolgan bo'lsa jarayon chiqmaydi, kutib turadi
STATS_WORKERS = _int("STATS_WORKERS", 6)     # parallel so'rovlar soni (FPL API'ni bo'g'ib qo'ymaslik uchun)
STATS_MAX_ENTRIES = _int("STATS_MAX_ENTRIES", 20000)  # xavfsizlik chegarasi
STATS_TOP_N = _int("STATS_TOP_N", 5)         # nechta sardor ko'rsatilsin


# --- Tur yakunlari sharhi ---
GW_REVIEW_STATE_FILE = DATA_DIR / "gw_review.json"
GW_REVIEW_HASHTAG = os.getenv("GW_REVIEW_HASHTAG", "#GWReview")
GW_REVIEW_TOP_N = _int("GW_REVIEW_TOP_N", 5)   # har ligada nechta menejer ko'rsatilsin
# 2026/27 dan FPL ochkolarni turning oxirgi o'yinidan keyingi kuni Britaniya
# vaqti bilan 09:00 da yakuniy qiladi. Toshkentda bu yozda 13:00, qishda 14:00 —
# shuning uchun aniq soat emas, kuzatuv ishlatiladi.
GW_REVIEW_UNTIL = os.getenv("GW_REVIEW_UNTIL", "16:00")  # shu vaqtgacha kutamiz
GW_REVIEW_POLL = _int("GW_REVIEW_POLL", 180)             # necha soniyada bir tekshiriladi


# --- Differentiallar (tur oralig'idagi post) ---
DIFF_STATE_FILE = DATA_DIR / "differentials.json"
DIFF_HASHTAG = os.getenv("DIFF_HASHTAG", "#Differentials")
DIFF_POST_AT = os.getenv("DIFF_POST_AT", "20:00")     # LOCAL_TZ bo'yicha
DIFF_LATEST = os.getenv("DIFF_LATEST", "23:00")       # bundan kech bo'lsa ertaga chiqadi
DIFF_MAX_OWN = _float("DIFF_MAX_OWN", 10.0)           # "differential" chegarasi, %
DIFF_MIN_POINTS = _int("DIFF_MIN_POINTS", 7)          # o'tgan turda shundan kam olgani chiqmaydi
DIFF_TOP_N = _int("DIFF_TOP_N", 5)                    # har bo'limda nechta qator
DIFF_TOP100_SIZE = _int("DIFF_TOP100_SIZE", 100)      # dunyo bo'yicha nechta menejer skanerlansin
DIFF_TOP100_MIN = _float("DIFF_TOP100_MIN", 12.0)     # top-100 da shundan ko'p bo'lsa qiziq
DIFF_RISING_N = _int("DIFF_RISING_N", 3)              # "kech qolmang" bo'limidagi qatorlar
DIFF_FIXTURES = _int("DIFF_FIXTURES", 3)              # kalendar necha turni ko'rsatsin
DIFF_CALENDAR_N = _int("DIFF_CALENDAR_N", 3)          # nechta futbolchi uchun kalendar
DIFF_LOCAL_LEAGUE = _bool("DIFF_LOCAL_LEAGUE", True)  # "bizning ligada" bo'limi chiqsinmi
DIFF_POLL = _bool("DIFF_POLL", True)                  # so'rovnoma yuborilsinmi
DIFF_POLL_OPTIONS = _int("DIFF_POLL_OPTIONS", 3)      # so'rovnomadagi futbolchilar soni
DIFF_WORKERS = _int("DIFF_WORKERS", 6)                # parallel so'rovlar


def _leagues() -> list[tuple[int, str]]:
    """STATS_LEAGUES="137243:🏆 FPLUzbekistan,251:🇺🇿 Uzbekistan" ko'rinishida."""
    raw = os.getenv("STATS_LEAGUES", "137243:🏆 FPLUzbekistan,251:🇺🇿 Uzbekistan")
    out: list[tuple[int, str]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        league_id, _, label = part.partition(":")
        try:
            out.append((int(league_id), label.strip() or f"#{league_id}"))
        except ValueError:
            continue
    return out


STATS_LEAGUES = _leagues()

def require_telegram() -> None:
    """Telegram sozlamalari borligini tekshiradi (DRY_RUN da shart emas)."""
    if DRY_RUN:
        return
    missing = [n for n, v in (("TELEGRAM_BOT_TOKEN", BOT_TOKEN), ("TELEGRAM_CHANNEL_ID", CHANNEL_ID)) if not v]
    if missing:
        raise SystemExit(f"Sozlama yetishmayapti: {', '.join(missing)}. .env faylni yoki GitHub Secrets'ni tekshiring.")
