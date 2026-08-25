"""GitHub Actions cron kechikishini o'lchaydi va yozib boradi.

GitHub cron'ni aniq belgilangan daqiqada ishga tushirishga kafolat bermaydi —
yuklama ko'p bo'lsa bir necha daqiqa kechikadi. Bu skript har ishga tushishda
"rejalashtirilgan vaqt" bilan "haqiqiy vaqt" farqini data/cron_log.csv ga yozadi.

Ishlatish:
    python -m scripts.cron_delay              # kechikishni yozib qo'yadi (workflow ichida)
    python -m scripts.cron_delay --report     # to'plangan statistikani ko'rsatadi
"""
from __future__ import annotations

import argparse
import csv
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import config  # noqa: E402

LOG_FILE = config.DATA_DIR / "cron_log.csv"
HEADER = ["actual_utc", "workflow", "schedule", "expected_utc", "delay_seconds", "queued_seconds"]
ALERT_MINUTES = int(os.getenv("CRON_ALERT_MINUTES", "20"))


# ---------------- cron ifodasini o'qish ----------------

def _expand(field: str, lo: int, hi: int) -> set[int]:
    """"0,30" / "11-22" / "*/15" / "*" -> ruxsat etilgan raqamlar to'plami."""
    if field.strip() == "*":
        return set(range(lo, hi + 1))
    out: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            step = int(step_s)
        if part in ("*", ""):
            start, end = lo, hi
        elif "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(part)
        out.update(range(start, end + 1, step))
    return {v for v in out if lo <= v <= hi}


def expected_time(schedule: str, now: datetime, lookback_hours: int = 6) -> datetime | None:
    """Cron ifodasi bo'yicha `now` dan oldingi eng yaqin rejalashtirilgan vaqtni topadi."""
    parts = schedule.split()
    if len(parts) < 2:
        return None
    minutes = _expand(parts[0], 0, 59)
    hours = _expand(parts[1], 0, 23)

    cursor = now.replace(second=0, microsecond=0)
    limit = now - timedelta(hours=lookback_hours)
    while cursor >= limit:
        if cursor.hour in hours and cursor.minute in minutes:
            return cursor
        cursor -= timedelta(minutes=1)
    return None


# ---------------- yozish ----------------

def _created_at() -> datetime | None:
    """GitHub run yaratilgan vaqt (`github.run_started_at`).

    Bu — cron'ning haqiqiy kechikishi. Undan keyingi vaqt (job navbatda turishi,
    concurrency guruhi band bo'lishi, runner ko'tarilishi) GitHub cron'ining
    aybi emas, shuning uchun alohida `queued_seconds` ustuniga yoziladi.
    """
    raw = os.getenv("CRON_RUN_CREATED_AT", "").strip()
    if not raw:
        return None
    try:
        return (datetime.fromisoformat(raw.replace("Z", "+00:00"))
                .astimezone(timezone.utc).replace(microsecond=0))
    except ValueError:
        return None


def _ensure_header() -> None:
    """Eski (5 ustunli) log faylga yangi `queued_seconds` ustunini qo'shadi.

    Bo'lmasa DictReader sarlavhani 5 ustun deb o'qib, 6-qiymatni yo'qotardi.
    """
    if not LOG_FILE.exists():
        with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(HEADER)
        return

    with open(LOG_FILE, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(HEADER)
        return
    if rows[0] == HEADER:
        return

    width = len(HEADER)
    with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        for row in rows[1:]:
            w.writerow((row + [""] * width)[:width])
    print("cron_log.csv sarlavhasi yangilandi (queued_seconds ustuni qo'shildi).")


def record() -> int:
    schedule = os.getenv("CRON_SCHEDULE", "").strip()
    workflow = os.getenv("CRON_WORKFLOW", os.getenv("GITHUB_WORKFLOW", "noma'lum")).strip()
    now = datetime.now(timezone.utc).replace(microsecond=0)

    if not schedule:
        print("Cron bo'yicha ishga tushmadi (qo'lda ishga tushirilgan) — yozilmadi.")
        return 0

    started = _created_at() or now
    expected = expected_time(schedule, started)
    if expected is None:
        print(f"'{schedule}' bo'yicha kutilgan vaqt topilmadi — yozilmadi.")
        return 0

    delay = int((started - expected).total_seconds())
    queued = max(0, int((now - started).total_seconds()))
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ensure_header()
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(
            [now.isoformat(), workflow, schedule, expected.isoformat(), delay, queued])

    local = ZoneInfo(config.LOCAL_TZ)
    print(
        f"[{workflow}] kutilgan: {expected.astimezone(local):%H:%M:%S} | "
        f"haqiqiy: {started.astimezone(local):%H:%M:%S} | "
        f"kechikish: {delay // 60} daq {delay % 60} son | navbat: {queued // 60} daq"
    )

    if delay > ALERT_MINUTES * 60:
        from bot import telegram

        telegram.notify_admin(
            f"⏰ <b>Cron kechikdi</b>\n{workflow}: <b>{delay // 60} daqiqa</b> "
            f"(kutilgan {expected.astimezone(local):%H:%M}, haqiqiy {now.astimezone(local):%H:%M})"
        )
    return 0


# ---------------- hisobot ----------------

def _fmt(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m} daq {s:02d} son" if m else f"{s} soniya"


def report() -> int:
    if not LOG_FILE.exists():
        print("Hali ma'lumot yo'q. Bir necha marta ishga tushgandan keyin qayta urinib ko'ring.")
        return 0

    with open(LOG_FILE, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("delay_seconds")]

    if not rows:
        print("Log bo'sh.")
        return 0

    by_wf: dict[str, list[int]] = {}
    for r in rows:
        by_wf.setdefault(r["workflow"], []).append(int(r["delay_seconds"]))

    print(f"\nJami yozuv: {len(rows)} ta "
          f"({rows[0]['actual_utc'][:10]} — {rows[-1]['actual_utc'][:10]})\n")
    avg_label = "O'rtacha"
    print(f"{'Workflow':<28}{'Soni':>6}{avg_label:>14}{'Median':>14}{'Eng yomon':>14}")
    print("-" * 76)

    worst_overall = 0
    for wf, delays in sorted(by_wf.items()):
        delays.sort()
        worst_overall = max(worst_overall, delays[-1])
        print(f"{wf[:27]:<28}{len(delays):>6}{_fmt(statistics.mean(delays)):>14}"
              f"{_fmt(statistics.median(delays)):>14}{_fmt(delays[-1]):>14}")

    all_delays = sorted(d for ds in by_wf.values() for d in ds)
    p90 = all_delays[max(0, int(len(all_delays) * 0.9) - 1)]
    over_10 = sum(1 for d in all_delays if d > 600)

    print(f"\n90% hollarda kechikish: {_fmt(p90)} dan kam")
    print(f"10 daqiqadan ortiq kechikkan: {over_10} marta ({over_10 * 100 // len(all_delays)}%)")

    queued = [int(r["queued_seconds"]) for r in rows if r.get("queued_seconds")]
    if queued:
        queued.sort()
        print(f"Job navbatda turgan vaqt (cron aybi emas): median {_fmt(statistics.median(queued))}, "
              f"eng yomoni {_fmt(queued[-1])}")

    print("\nXulosa:", end=" ")
    if worst_overall <= 300:
        print("GitHub Actions yetarli — kechikish sezilarli emas.")
    else:
        print("Kechikish bor, lekin bu postlarning vaqtiga ta'sir qilmaydi:\n"
              "        cron'lar ataylab erta qo'yilgan, kerakli daqiqani jarayonning\n"
              "        o'zi kutadi (README, 3-bo'lim). Faqat kechikish muntazam\n"
              "        2 soatdan oshsa VPS haqida o'ylash kerak.")
    print()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Cron kechikishini o'lchash")
    ap.add_argument("--report", action="store_true", help="To'plangan statistikani ko'rsatadi")
    args = ap.parse_args()
    return report() if args.report else record()


if __name__ == "__main__":
    sys.exit(main())
