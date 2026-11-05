"""“Kuchlilar nimani olyapti” — top-1000 egaligidagi harakat charti.

Nima ko'rsatiladi
-----------------
Har bir qator — bitta futbolchi. Kulrang chiziqning chap uchi uning
MOVERS_WINDOW tur oldingi top-1000 dagi egaligi, o'ng uchi — hozirgisi.
Chiziq qancha uzun bo'lsa, kuchli menejerlar uni shuncha tez sotib olishgan.
Uchinchi belgi — umumiy egalik: kuchlilar bilan omma orasidagi masofa aynan
differential tug'iladigan joy.

Ma'lumot qayerdan
-----------------
`data/elite_history.json` — uni differentiallar posti har hafta to'ldiradi
(top-1000 tarkiblari o'sha yerda allaqachon o'qiladi). Bu post faqat shu
faylni o'qiydi, ustiga bootstrap va oynadagi turlarning jonli ma'lumotini
oladi — hammasi bo'lib to'rtta so'rov.

Hamma turlar BITTA muzlatilgan menejerlar ro'yxati bo'yicha hisoblanadi
(bot/elite_cohort.py). Chart faqat bir xil ro'yxat belgisiga ega turlarni
solishtiradi: ro'yxat yangilanganda eski va yangi o'lchov aralashib
ketmasligi kerak. Yangi ro'yxat bo'yicha tur yetishmasa, ular o'sha zahoti
to'ldiriladi (MOVERS_BACKFILL).

Vaqt
----
Cron har kuni MOVERS_POST_AT (19:40) ga qo'yiladi — differentiallardan
(19:50) o'n daqiqa oldin. Tur yopilgan kuni tarixda yangi tur hali yo'q,
demak jim chiqib ketadi; differentiallar uni o'sha kechqurun yozadi; ertasi
kuni esa shu post uni ko'radi va chiqaradi. Ya'ni ikkita post bir kechada
to'planib qolmaydi va buning uchun alohida kelishuv kodi yozilmagan.
"""
from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import charts, config, differentials, elite_cohort, fpl_api, storage, telegram, waiter

log = logging.getLogger("elite_movers")

# Jarohatlangan, diskvalifikatsiya qilingan yoki tarkibdan tashqaridagi
# futbolchi "ko'tarilyapti" deb ko'rsatilsa — bu tuzoq. Faqat o'ynay
# oladiganlar va gumonlilar qoladi.
PLAYABLE = {"a", "d"}


@dataclass
class Mover:
    element_id: int
    name: str
    before: float     # oyna boshidagi top ro'yxatdagi egalik, %
    now: float        # oyna oxiridagi, %
    owned: float      # umumiy egalik, %
    cost: int
    points: int = 0   # oynadagi jami ochko

    @property
    def rise(self) -> float:
        return self.now - self.before

    @property
    def price(self) -> str:
        return f"£{self.cost / 10:.1f}M"


# ---------------- tarixni o'qish ----------------

def events_in(history: dict) -> list[int]:
    """Tarixdagi turlar, o'sish tartibida."""
    rows = (history or {}).get("events") or {}
    return sorted(int(k) for k in rows if str(k).lstrip("-").isdigit())


def cohort_events(history: dict, cohort: int) -> list[int]:
    """Shu menejerlar ro'yxati bo'yicha hisoblangan turlar.

    Boshqa ro'yxat bilan o'lchangan turlar solishtirishga yaramaydi —
    ularning foizlari boshqa odamlar bo'yicha.
    """
    rows = (history or {}).get("events") or {}
    out = []
    for key, row in rows.items():
        if not str(key).isdigit():
            continue
        if int((row or {}).get("cohort") or 0) != cohort:
            continue
        out.append(int(key))
    return sorted(out)


def window(events: list[int], size: int | None = None) -> list[int]:
    """Oxirgi `size` ta yozilgan tur.

    Turlar ketma-ket bo'lmasligi mumkin (biror hafta skaner ishlamay qolsa),
    shuning uchun raqam bo'yicha emas, yozuvlar bo'yicha olamiz.
    """
    size = size or config.MOVERS_WINDOW
    return events[-size:]


def _share(history: dict, event: int, element_id: int) -> float:
    row = ((history.get("events") or {}).get(str(event)) or {})
    player = (row.get("players") or {}).get(str(element_id))
    return float((player or {}).get("elite") or 0.0)


def movers(history: dict, events: list[int], bootstrap: dict,
           count: int | None = None, min_rise: float | None = None) -> list[Mover]:
    """Oyna ichida top ro'yxatdagi egaligi eng ko'p oshgan futbolchilar."""
    if len(events) < 2:
        return []
    count = count or config.MOVERS_TOP_N
    min_rise = config.MOVERS_MIN_RISE if min_rise is None else min_rise
    first, last = events[0], events[-1]

    by_id = {p["id"]: p for p in bootstrap.get("elements", [])}
    latest = ((history.get("events") or {}).get(str(last)) or {}).get("players") or {}

    rows: list[Mover] = []
    for key in latest:
        try:
            element_id = int(key)
        except ValueError:
            continue
        element = by_id.get(element_id)
        if not element or element.get("status") not in PLAYABLE:
            continue
        now = _share(history, last, element_id)
        before = _share(history, first, element_id)
        if now - before < min_rise:
            continue
        rows.append(Mover(
            element_id=element_id,
            name=element.get("web_name") or f"#{element_id}",
            before=before,
            now=now,
            # umumiy egalikni bootstrap'dan olamiz — tarixdagisidan yangiroq
            owned=differentials._num(element.get("selected_by_percent"), 0.0),
            cost=differentials._num(element.get("now_cost"), 0),
        ))

    rows.sort(key=lambda m: -m.rise)
    return rows[:count]


def apply_points(rows: list[Mover], events: list[int]) -> None:
    """Oynadagi jami ochkoni qo'shadi (har tur uchun bitta so'rov)."""
    try:
        form = differentials.recent_form(events)
    except Exception as exc:
        log.warning("Oynadagi ochkolar olinmadi: %s", exc)
        return
    for row in rows:
        row.points = form.get(row.element_id, (0, 0))[0]


# ---------------- matn va rasm ----------------

def build(rows: list[Mover], events: list[int], out_path: Path,
          cohort: int = 0) -> Path:
    moves = [charts.Move(
        name=m.name, before=m.before, now=m.now, other=m.owned,
        cells=(m.price, f"{m.now:.1f}%", f"{m.owned:.1f}%", str(m.points)),
    ) for m in rows]
    # Matn qo'lda ikki qatorga bo'lingan: bitta qatorga sig'maydi (12.5 pt
    # da ~1143 px, sahifa esa 1140 px). Oxirgi qator — o'lchovning izohi;
    # batafsili (nechtasi hali top-1000 da) Telegram izohida beriladi.
    subtitle = ("TOP-1000 likdagi menejerlarning differential dan\n"
                f"tezda templatega aylanayotgan {len(rows)} futbolchisi")
    if cohort:
        subtitle += f"\nO'lchov: GW{cohort} holatidagi TOP-1000lik bilan o'lchanadi"
    return charts.movers_chart(
        out_path,
        title="Kuchlilar kimlarni olyapti?",
        subtitle=subtitle,
        rows=moves,
        # ikkita doira — bitta ko'rsatkich ikki paytda, romb esa boshqasi
        legend=(f"GW{events[0]} da", f"GW{events[-1]} da", "umumiy egalik"),
    )


def caption(rows: list[Mover], events: list[int], cohort: int = 0,
            survivors: int | None = None, size: int = 0) -> str:
    esc = telegram.esc
    lines = [
        "📈 <b>Kuchlilar kimlarni olyapti?</b>",
        f"GW{events[0]} → GW{events[-1]} · top-1000 menejerdagi egalik o'zgarishi",
        "",
    ]
    for m in rows:
        lines.append(f"<b>{esc(m.name)}</b> — {m.before:.1f}% → {m.now:.1f}% "
                     f"(+{m.rise:.1f}), umumiy {m.owned:.1f}%")
    lines += [
        "",
        "Umumiy egalik hali pastda qolgan bo'lsa — differential shu yerda tug'iladi.",
    ]
    if cohort:
        # O'lchov qanday olinganini yashirmaymiz: ro'yxat muzlatilgan, chunki
        # har hafta yangi ro'yxat olinsa, o'sish ro'yxat almashuvi bilan
        # aralashib ketadi.
        note = f"Ro'yxat GW{cohort} dan muzlatilgan"
        if survivors is not None and size:
            note += f" — o'sha {size} menejerdan {survivors} tasi hozir ham top-1000 da"
        lines += ["", note + "."]
    # Hashtaglar va kanal nomi alohida qatorlarda — matnli postlarda ham
    # shunday, rasm izohi ulardan farq qilib turmasin
    lines += ["", config.tags(config.MOVERS_HASHTAG), "", config.CHANNEL_TAG]
    return "\n".join(lines)


def fill_missing(history: dict, cohort: int, latest: int,
                 limit: int | None = None) -> int:
    """Joriy ro'yxat bo'yicha yetishmayotgan oxirgi turlarni to'ldiradi.

    Ikki holatda kerak bo'ladi: birinchi ishga tushirishda (tarix bo'sh) va
    ro'yxat yangilangandan keyin (yangi belgili atigi bitta tur bor). Har
    biri ~1000 so'rov, shuning uchun bitta jarayonda limitlanadi.
    """
    limit = limit or config.MOVERS_BACKFILL_MAX
    have = set(cohort_events(history, cohort))
    missing = [gw for gw in range(max(1, latest - config.MOVERS_WINDOW + 1), latest + 1)
               if gw not in have]
    if not missing:
        return 0

    size = differentials.elite_tiers()[-1]
    picked = differentials.cohort_for(latest, size, refresh=False)
    if not picked.entries:
        log.warning("Menejerlar ro'yxati yo'q — to'ldirib bo'lmadi.")
        return 0

    log.info("Yetishmayotgan turlar: %s — to'ldiramiz.",
             ", ".join(f"GW{g}" for g in missing))
    done = 0
    for gw in sorted(missing, reverse=True)[:limit]:
        try:
            if differentials.backfill_elite_history(gw, overwrite=True, cohort=picked):
                done += 1
        except Exception as exc:
            log.warning("GW%d to'ldirilmadi: %s", gw, exc)
    return done


# ---------------- asosiy ----------------

def run(force: bool = False, keep: bool = False) -> int:
    config.require_telegram()

    history = storage.load(config.ELITE_HISTORY_FILE, {}) or {}
    recorded = events_in(history)
    if not recorded:
        log.info("Egalik tarixi hali bo'sh — post kutadi.")
        return 0

    meta = elite_cohort.load()
    cohort = int(meta.get("from_event") or 0)
    latest = recorded[-1]
    state = storage.load(config.MOVERS_STATE_FILE, {}) or {}
    if state.get("event") == latest and not force:
        log.info("GW%d bo'yicha harakat charti allaqachon chiqarilgan.", latest)
        return 0

    if not force:
        post_at = waiter.local_time_today(config.MOVERS_POST_AT)
        now = waiter.now_utc()
        if now < post_at:
            minutes = (post_at - now).total_seconds() / 60
            if minutes > config.MOVERS_MAX_MINUTES:
                log.warning("Post vaqtigacha (%s) %.1f soat bor — cron juda erta "
                            "ishga tushgan.", config.MOVERS_POST_AT, minutes / 60)
                telegram.notify_admin(
                    f"⚠️ <b>Harakat charti</b>\nPost vaqti {config.MOVERS_POST_AT}, "
                    f"cron esa undan {minutes / 60:.1f} soat oldin ishga tushdi — "
                    "jarayon shuncha kuta olmaydi."
                )
                return 0
            waiter.sleep_until(post_at, label="Harakat charti",
                               budget_end=waiter.budget(config.MOVERS_MAX_MINUTES))
        elif now > waiter.local_time_today(config.MOVERS_LATEST):
            log.info("Kech bo'ldi (%s dan keyin) — post ertaga chiqadi.",
                     config.MOVERS_LATEST)
            return 0

    # Faqat bitta ro'yxat bo'yicha o'lchangan turlar solishtiriladi.
    events = cohort_events(history, cohort)
    if len(events) < config.MOVERS_WINDOW and config.MOVERS_BACKFILL:
        if fill_missing(history, cohort, latest):
            history = storage.load(config.ELITE_HISTORY_FILE, {}) or {}
            events = cohort_events(history, cohort)

    if len(events) < max(config.MOVERS_WINDOW, config.MOVERS_MIN_EVENTS):
        log.info("GW%d ro'yxati bo'yicha %d ta tur bor, kamida %d kerak — post kutadi.",
                 cohort, len(events), max(config.MOVERS_WINDOW, config.MOVERS_MIN_EVENTS))
        return 0

    bootstrap = fpl_api.get_bootstrap()
    picked = window(events)
    rows = movers(history, picked, bootstrap)
    if not rows:
        log.info("Sezilarli harakat yo'q (chegara %.1f%%) — post chiqmadi.",
                 config.MOVERS_MIN_RISE)
        storage.save(config.MOVERS_STATE_FILE, {"event": latest, "empty": True})
        return 0

    apply_points(rows, picked)

    alive = None
    for gw in reversed(picked):
        value = ((history.get("events") or {}).get(str(gw)) or {}).get("survivors")
        if value is not None:
            alive = int(value)
            break

    out_path = Path(config.CHART_DIR) / f"movers_gw{latest}.png"
    build(rows, picked, out_path, cohort=cohort)
    res = telegram.send_photo(out_path, caption=caption(
        rows, picked, cohort=cohort, survivors=alive,
        size=int(meta.get("size") or 0)))

    storage.save(config.MOVERS_STATE_FILE, {
        "event": latest,
        "cohort": cohort,
        "survivors": alive,
        "window": picked,
        "message_id": res.get("message_id"),
        "players": [m.name for m in rows],
        "posted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    log.info("GW%d harakat charti yuborildi: %s", latest,
             ", ".join(m.name for m in rows))

    if not keep:
        out_path.unlink(missing_ok=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Top-1000 egaligidagi harakat charti")
    ap.add_argument("--dry-run", action="store_true",
                    help="Telegramga yubormaydi, rasmni faqat faylga chizadi")
    ap.add_argument("--force", action="store_true",
                    help="Vaqt tekshiruvini e'tiborsiz qoldiradi")
    ap.add_argument("--keep", action="store_true", help="Rasm faylini o'chirmaydi")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    if args.dry_run:
        config.DRY_RUN = True

    try:
        return run(force=args.force, keep=args.keep or args.dry_run)
    except Exception as exc:
        log.exception("Harakat charti skriptida xatolik")
        telegram.notify_admin(
            f"⚠️ <b>FPL bot (harakat charti)</b>\n<code>{telegram.esc(repr(exc))}</code>")
        return 1


if __name__ == "__main__":
    sys.exit(main())
