"""Rasmli chartlar — matplotlib bilan PNG tayyorlash.

Bu modul FPL haqida hech narsa bilmaydi: unga faqat tayyor raqamlar beriladi.
Shu sababli uni testda ham, kelajakdagi boshqa chartlarda ham qayta ishlatish
mumkin.

Ikki futbolchini solishtiruvchi rasm uch qismdan iborat:

    · radar — har bir ko'rsatkich o'z pozitsiyasidagi eng yaxshi ko'rsatkichga
      nisbatan chiziladi, ya'ni markazdan uzoqroq nuqta — yaxshiroq natija;
    · oxirgi bir necha turdagi ochkolar chizig'i;
    · aynan o'sha ko'rsatkichlarning raqamli jadvali.

Logotip ikki joyda turadi: radar markazida xira suv belgisi sifatida va
pastda to'liq ko'rinishda. Suv belgisini kesib tashlab bo'lmaydi — rasm
manbasiz tarqalib ketmasligi uchun shunday qilingan.
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # ekran yo'q — fayl sifatida chizamiz

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from . import config

log = logging.getLogger(__name__)

# Qorong'u mavzu. Post kechqurun (21:00 atrofida) chiqadi — o'sha paytda
# telefonlar qorong'u rejimda bo'ladi va oq rasm ko'zni qamashtiradi.
PALETTE = {
    "surface": "#12161c",   # fon
    "ink": "#f0efec",       # asosiy matn
    "ink2": "#c3c2b7",      # yordamchi matn
    "grid": "#333a44",      # to'r chiziqlari
    "s1": "#3987e5",        # birinchi futbolchi
    "s2": "#d95926",        # ikkinchi futbolchi
}

FIG_W, FIG_H = 7.6, 11.4      # dyuym; 150 dpi da 1140x1710 px
RADAR = (0.215, 0.505, 0.57, 0.335)   # (x, y, kenglik, balandlik)
TREND = (0.105, 0.302, 0.845, 0.118)
TREND_TITLE_Y = 0.432
TABLE_TOP = 0.232
TABLE_STEP = 0.027
COL_A, COL_B = 0.42, 0.72     # jadvaldagi raqam ustunlari
MIN_METRICS = 3               # uchburchakdan kam radar bo'lmaydi

# Poyga charti uchun kategoriya ranglari — qat'iy tartibda, aylantirilmaydi.
# Qorong'u fonda tekshirilgan: eng yaqin juftlik CVD bo'yicha dE 8.4, oddiy
# ko'rish bo'yicha 19.3, hammasi fon bilan 3:1 dan yuqori kontrastda.
# Shunga qaramay rang yolg'iz qolmaydi — har chiziqning oxirida ismi yoziladi.
SERIES = ("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300")

# Poyga charti
RACE_FIG = (7.6, 10.0)
RACE_AX = (0.105, 0.480, 0.56, 0.330)
RACE_TABLE_TOP = 0.368
RACE_TABLE_STEP = 0.033
RACE_COLS = ((0.065, "left", ""), (0.330, "center", "Jami"),
             (0.440, "center", "Oxirgi tur"), (0.575, "center", "Overall o'rni"),
             (0.700, "center", "Liga"), (0.815, "center", "O'zbekiston"),
             (0.935, "center", "Overall"))
# Oxirgi uchta ustun — uchta turli yetakchidan orqada qolgan ochko. Sarlavhalarni
# "Ligadan / O'zbekistondan / Overalldan" deb yozsak jadval sig'maydi, shuning
# uchun ularning ustiga bitta umumiy izoh qo'yiladi.
RACE_GROUP = (0.818, "yetakchidan orqada", 0.682, 0.975)
# Ligaga qo'shilish kodi — jadval bilan logotip orasida.
RACE_CODE_LABEL_Y = 0.138
RACE_CODE_Y = 0.107
# Kod uchun bitta aniq shrift: DejaVu Sans Mono matplotlib bilan birga keladi,
# ya'ni GitHub Actions'da ham xuddi shu ko'rinishda chiqadi. O'rnatilmagan
# shriftni so'rasak, server boshqasiga almashtirib yuborardi.
RACE_CODE_FONT = "DejaVu Sans Mono"


# "Kuchlilar nimani olyapti" charti — pastroq, chunki radar yo'q
MOVERS_FIG = (7.6, 8.4)
MOVERS_AX = (0.30, 0.480, 0.60, 0.300)
MOVERS_LEGEND_Y = 0.804
MOVERS_TABLE_TOP = 0.350
MOVERS_TABLE_STEP = 0.039
# jadval ustunlari: (x, tekislash, sarlavha). Birinchisi — ism.
MOVERS_COLS = ((0.08, "left", ""), (0.43, "center", "Narx"),
               (0.58, "center", "Top-1000"), (0.72, "center", "Umumiy"),
               (0.88, "center", "Ochko"))


@dataclass
class Metric:
    """Radar va jadvaldagi bitta qator.

    top — shkala: shu pozitsiyadagi eng yaxshi ko'rsatkich. Shu tufayli
    radarning tashqi halqasi "ligadagi eng yaxshi" degan ma'noni beradi.
    """

    label: str
    a: float
    b: float
    top: float
    fmt: str = "{:.2f}"

    def share(self, value: float) -> float:
        if not self.top:
            return 0.0
        return max(0.0, min(1.0, value / self.top))


@dataclass
class Runner:
    """Poyga chartidagi bitta menejer.

    ranks — har bir turdagi o'rni. Bu o'rin BUTUN liga bo'yicha emas,
    chartdagi menejerlar orasidagi o'rin: aks holda mavsum boshida chiziq
    rasmdan chiqib ketardi (bugungi uchinchi odam GW2 da 180-o'rinda
    bo'lishi mumkin).
    """

    name: str
    ranks: list[int]
    cells: tuple[str, ...] = ()
    label: str = ""      # chiziq oxiridagi yozuv; bo'sh bo'lsa `name` ishlatiladi


@dataclass
class Move:
    """Dumbbell chartdagi bitta qator — bitta futbolchining egalik harakati.

    before/now — top ro'yxatdagi egalik (oyna boshi va oxiri), other — umumiy
    egalik. cells — jadvaldagi tayyor matnlar (MOVERS_COLS dagi sarlavhalar
    tartibida, ismdan keyin).
    """

    name: str
    before: float
    now: float
    other: float
    cells: tuple[str, ...] = ()

    @property
    def rise(self) -> float:
        return self.now - self.before


def logo_path() -> Path | None:
    path = Path(config.CHART_LOGO)
    return path if path.is_file() else None


# Matplotlib shriftida emoji yo'q — ular rasmda bo'sh kvadrat bo'lib chiqadi.
# Matn tashqaridan keladi (liga nomi, menejer ismi), shuning uchun tozalaymiz.
_NON_FONT = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]")


def plain(text: str) -> str:
    """Rasmga tushadigan matndan shriftda yo'q belgilarni olib tashlaydi."""
    return _NON_FONT.sub("", text or "").strip()


def _logo_height(fig, image, width: float) -> float:
    """Figura kvadrat emas — nisbatni saqlash uchun o'lchamlarini hisobga olamiz."""
    fig_w, fig_h = fig.get_size_inches()
    return width * (image.shape[0] / image.shape[1]) * (fig_w / fig_h)


def _logo_axes(fig, left: float, bottom: float, width: float,
               image, alpha: float = 1.0, zorder: float = 5):
    """Nisbatini saqlab logotip qo'yadi."""
    box_h = _logo_height(fig, image, width)
    ax = fig.add_axes([left, bottom, width, box_h], zorder=zorder)
    ax.imshow(image, alpha=alpha)
    ax.axis("off")
    ax.patch.set_alpha(0)
    return box_h


def _radar(fig, metrics: list[Metric], colours: tuple[str, str], c: dict) -> None:
    count = len(metrics)
    angles = [i / count * 2 * math.pi for i in range(count)]
    closed = angles + angles[:1]

    x, y, w, h = RADAR
    ax = fig.add_axes([x, y, w, h], polar=True, facecolor=c["surface"])
    ax.set_theta_offset(math.pi / 2)   # birinchi ko'rsatkich tepada
    ax.set_theta_direction(-1)         # soat yo'nalishi bo'yicha
    ax.set_ylim(0, 1.0)
    ax.set_rgrids([0.25, 0.5, 0.75, 1.0], labels=["", "", "", ""])
    ax.set_xticks(angles)
    ax.set_xticklabels([])
    ax.grid(color=c["grid"], linewidth=0.9)
    ax.spines["polar"].set_color(c["grid"])

    for pick, colour in ((lambda m: m.a, colours[0]), (lambda m: m.b, colours[1])):
        share = [m.share(pick(m)) for m in metrics]
        data = share + share[:1]
        ax.plot(closed, data, color=colour, linewidth=2.5, zorder=3)
        ax.fill(closed, data, color=colour, alpha=0.10, zorder=2)
        ax.plot(closed, data, "o", color=colour, markersize=8.5,
                markeredgecolor=c["surface"], markeredgewidth=2, zorder=4)

    # yozuvlar halqadan tashqarida: tepa/pastda markazda, yonlarda chetga qarab
    for angle, metric in zip(angles, metrics):
        deg = math.degrees(angle)
        ha = "center"
        if 10 < deg < 170:
            ha = "left"
        elif 190 < deg < 350:
            ha = "right"
        ax.text(angle, 1.15, metric.label, ha=ha, va="center",
                color=c["ink"], fontsize=13.5)


def _trend(fig, gws: list[int], series_a: list[int], series_b: list[int],
           colours: tuple[str, str], c: dict, title: str) -> None:
    ax = fig.add_axes(list(TREND), facecolor=c["surface"])
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(c["grid"])
    ax.yaxis.grid(True, color=c["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    ax.set_yticks([])
    ax.set_xticks(range(len(gws)))
    ax.set_xticklabels([f"GW{g}" for g in gws], color=c["ink2"], fontsize=12)
    ax.tick_params(axis="x", length=0, pad=6)

    top = max(series_a + series_b + [1])
    ax.set_ylim(-5.5, top + 4.5)
    ax.set_xlim(-0.35, len(gws) - 0.65)

    for values, other, colour in ((series_a, series_b, colours[0]),
                                  (series_b, series_a, colours[1])):
        xs = list(range(len(values)))
        ax.plot(xs, values, color=colour, linewidth=2.5, zorder=3)
        ax.plot(xs, values, "o", color=colour, markersize=8,
                markeredgecolor=c["surface"], markeredgewidth=2, zorder=4)
        for px, value, rival in zip(xs, values, other):
            # kattasining raqami tepada, kichiginiki pastda — ustma-ust tushmasin
            above = value >= rival
            ax.text(px, value + (1.7 if above else -1.9), str(value),
                    ha="center", va="bottom" if above else "top",
                    color=c["ink"], fontsize=11.5, zorder=5)

    fig.text(TREND[0], TREND_TITLE_Y, title, ha="left", color=c["ink"],
             fontsize=14.5, fontweight="bold")


def _table(fig, name_a: str, name_b: str, metrics: list[Metric],
           colours: tuple[str, str], c: dict) -> None:
    """Sarlavhada rang namunasi turadi — alohida legenda kerak emas."""
    y = TABLE_TOP
    for cx, name, colour in ((COL_A, name_a, colours[0]), (COL_B, name_b, colours[1])):
        fig.add_artist(Line2D([cx - 0.105, cx - 0.062], [y + 0.030, y + 0.030],
                              color=colour, linewidth=4, solid_capstyle="round"))
        fig.text(cx - 0.048, y + 0.025, name, ha="left", color=c["ink"],
                 fontsize=14, fontweight="bold")
    fig.add_artist(Line2D([0.08, 0.92], [y + 0.016, y + 0.016],
                          color=c["grid"], linewidth=1))

    for metric in metrics:
        fig.text(0.08, y - 0.004, metric.label, ha="left", color=c["ink2"], fontsize=12.5)
        leads = metric.a >= metric.b
        fig.text(COL_A, y - 0.004, metric.fmt.format(metric.a), ha="center",
                 color=c["ink"], fontsize=12.5,
                 fontweight="bold" if leads else "normal")
        fig.text(COL_B, y - 0.004, metric.fmt.format(metric.b), ha="center",
                 color=c["ink"], fontsize=12.5,
                 fontweight="bold" if not leads else "normal")
        y -= TABLE_STEP


def _xticks(limit: float) -> list[int]:
    """0 dan `limit` gacha o'qilishi oson qadamlar."""
    step = 5 if limit <= 25 else (10 if limit <= 60 else 20)
    return list(range(0, int(limit) + 1, step))


def _movers_panel(fig, rows: list[Move], c: dict) -> None:
    ax = fig.add_axes(list(MOVERS_AX), facecolor=c["surface"])
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(c["grid"])
    ax.xaxis.grid(True, color=c["grid"], linewidth=0.8)
    ax.set_axisbelow(True)

    count = len(rows)
    limit = max([r.now for r in rows] + [r.other for r in rows]) + 9
    # nolda turgan belgi o'q chizig'iga yopishib, yarmi kesilib qolmasin
    ax.set_xlim(-limit * 0.015, limit)
    ax.set_ylim(-0.7, count - 0.3)
    # eng katta o'sish tepada tursin (matplotlib da y=0 pastda)
    ax.set_yticks(range(count))
    ax.set_yticklabels([r.name for r in reversed(rows)], color=c["ink"], fontsize=13.5)
    ax.tick_params(axis="y", length=0, pad=10)
    # to'r eng uzoq nuqtadan oshib tursin — chiziq havoda qolib ketmasin
    ticks = _xticks(limit)
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{t}%" for t in ticks], color=c["ink2"], fontsize=11.5)
    ax.tick_params(axis="x", length=0, pad=6)

    for i, row in enumerate(reversed(rows)):
        ax.plot([row.before, row.now], [i, i], color=c["grid"], linewidth=4,
                solid_capstyle="round", zorder=2)
        # bo'sh doira — "oldin", to'la doira — "hozir", romb — umumiy egalik.
        # Shakllar rangdan tashqari ikkinchi belgi: rangni ajratolmagan
        # o'quvchi ham qatorni o'qiy oladi.
        ax.plot([row.before], [i], "o", markersize=9, markerfacecolor=c["surface"],
                markeredgecolor=c["grid"], markeredgewidth=2.5, zorder=3)
        ax.plot([row.now], [i], "o", markersize=10, markerfacecolor=c["s1"],
                markeredgecolor=c["surface"], markeredgewidth=2, zorder=4)
        ax.plot([row.other], [i], "D", markersize=8, markerfacecolor=c["s2"],
                markeredgecolor=c["surface"], markeredgewidth=1.6, zorder=5)
        ax.text(row.now + limit * 0.035, i, f"+{row.rise:.1f}", va="center", ha="left",
                color=c["s1"], fontsize=12.5, fontweight="bold", zorder=6)


def _movers_legend(fig, c: dict, labels: tuple[str, str, str]) -> None:
    items = (("o", c["grid"], "none", labels[0], 0.075),
             ("o", c["s1"], c["s1"], labels[1], 0.280),
             ("D", c["s2"], c["s2"], labels[2], 0.600))
    for marker, edge, face, label, x in items:
        fig.add_artist(Line2D([x], [MOVERS_LEGEND_Y], marker=marker, markersize=9,
                              markerfacecolor=face, markeredgecolor=edge,
                              markeredgewidth=2, linestyle="none"))
        fig.text(x + 0.025, MOVERS_LEGEND_Y - 0.0045, label, ha="left",
                 color=c["ink2"], fontsize=12)


def _movers_table(fig, rows: list[Move], c: dict) -> None:
    y = MOVERS_TABLE_TOP
    for x, align, head in MOVERS_COLS:
        if head:
            fig.text(x, y, head, ha=align, color=c["ink2"], fontsize=12,
                     fontweight="bold")
    fig.add_artist(Line2D([0.06, 0.94], [y - 0.014, y - 0.014],
                          color=c["grid"], linewidth=1))

    y -= 0.046
    for row in rows:
        fig.text(MOVERS_COLS[0][0], y, plain(row.name), ha="left", color=c["ink"], fontsize=12.5)
        for (x, align, _), text in zip(MOVERS_COLS[1:], row.cells):
            # "Top-1000" ustuni — postning asosiy raqami, shuning uchun qalin
            main = x == MOVERS_COLS[2][0]
            fig.text(x, y, text, ha=align, color=c["ink"] if main else c["ink2"],
                     fontsize=12.5, fontweight="bold" if main else "normal")
        y -= MOVERS_TABLE_STEP


def movers_chart(out_path: str | Path, title: str, subtitle: str,
                 rows: list[Move],
                 legend: tuple[str, str, str] = ("3 tur oldin", "hozir (top-1000)",
                                                 "umumiy egalik"),
                 palette: dict | None = None) -> Path:
    """Top ro'yxatdagi egalik harakati — dumbbell chart va raqamlar jadvali."""
    if not rows:
        raise ValueError("Chart uchun kamida bitta qator kerak")

    c = {**PALETTE, **(palette or {})}
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=MOVERS_FIG, dpi=150, facecolor=c["surface"])
    try:
        fig.text(0.5, 0.957, plain(title), ha="center", color=c["ink"],
                 fontsize=24, fontweight="bold")
        if subtitle:
            fig.text(0.5, 0.930, plain(subtitle), ha="center", va="top", color=c["ink2"],
                     fontsize=12.5, linespacing=1.45)

        _movers_legend(fig, c, legend)
        _movers_panel(fig, rows, c)
        _movers_table(fig, rows, c)

        mark = logo_path()
        image = mpimg.imread(str(mark)) if mark else None
        if image is not None:
            # suv belgisi chart bilan jadval orasida — rasmni kesib uni
            # olib tashlash mumkin emas
            width = 0.28
            height = _logo_height(fig, image, width)
            _logo_axes(fig, 0.5 - width / 2, 0.408 - height / 2, width,
                       image, alpha=0.12, zorder=2.5)
            _logo_axes(fig, 0.5 - 0.27 / 2, 0.022, 0.27, image)
        else:
            log.warning("Logotip topilmadi (%s) — rasm logosiz chiqadi", config.CHART_LOGO)

        fig.savefig(out_path, facecolor=c["surface"])
    finally:
        plt.close(fig)
    return out_path


def _race_panel(fig, gws: list[int], runners: list[Runner], c: dict) -> None:
    ax = fig.add_axes(list(RACE_AX), facecolor=c["surface"])
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(c["grid"])
    ax.yaxis.grid(True, color=c["grid"], linewidth=0.8)
    ax.set_axisbelow(True)

    count = len(runners)
    ax.set_xlim(gws[0] - 0.4, gws[-1] + 0.4)
    ax.set_ylim(count + 0.6, 0.4)      # birinchi o'rin tepada
    ax.set_yticks(range(1, count + 1))
    ax.set_yticklabels([str(i) for i in range(1, count + 1)],
                       color=c["ink2"], fontsize=12)
    ax.tick_params(axis="y", length=0, pad=8)

    # turlar ko'payganda yorliqlar bir-biriga tiqilib qolmasin
    step = 1 if len(gws) <= 12 else (2 if len(gws) <= 24 else 4)
    ticks = [g for i, g in enumerate(gws) if i % step == 0 or g == gws[-1]]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"GW{g}" for g in ticks], color=c["ink2"], fontsize=11)
    ax.tick_params(axis="x", length=0, pad=6)

    for runner, colour in zip(runners, SERIES):
        ax.plot(gws, runner.ranks, color=colour, linewidth=2.5, zorder=3)
        ax.plot(gws, runner.ranks, "o", color=colour, markersize=7,
                markeredgecolor=c["surface"], markeredgewidth=1.8, zorder=4)
        # ism chiziq oxirida — rangni ajratolmagan o'quvchi ham o'qiy oladi
        ax.annotate(plain(runner.label or runner.name), xy=(gws[-1], runner.ranks[-1]), xytext=(10, 0),
                    textcoords="offset points", va="center", ha="left",
                    color=colour, fontsize=12, fontweight="bold",
                    annotation_clip=False)


def _race_table(fig, runners: list[Runner], c: dict) -> None:
    y = RACE_TABLE_TOP
    group_x, group_text, left, right = RACE_GROUP
    fig.text(group_x, y + 0.023, group_text, ha="center", color=c["ink2"],
             fontsize=10.5)
    fig.add_artist(Line2D([left, right], [y + 0.018, y + 0.018],
                          color=c["grid"], linewidth=1))
    for x, align, head in RACE_COLS:
        if head:
            fig.text(x, y, head, ha=align, color=c["ink2"], fontsize=12,
                     fontweight="bold")
    fig.add_artist(Line2D([0.03, 0.97], [y - 0.013, y - 0.013],
                          color=c["grid"], linewidth=1))

    y -= 0.043
    for index, (runner, colour) in enumerate(zip(runners, SERIES), start=1):
        fig.add_artist(Line2D([0.035, 0.058], [y + 0.005, y + 0.005],
                              color=colour, linewidth=4, solid_capstyle="round"))
        fig.text(RACE_COLS[0][0], y, f"{index}. {plain(runner.name)}", ha="left",
                 color=c["ink"], fontsize=12.5)
        for (x, align, _), text in zip(RACE_COLS[1:], runner.cells):
            main = x == RACE_COLS[1][0]
            fig.text(x, y, text, ha=align, color=c["ink"] if main else c["ink2"],
                     fontsize=12.5, fontweight="bold" if main else "normal")
        y -= RACE_TABLE_STEP


def _race_code(fig, code: str, c: dict) -> None:
    """Ligaga qo'shilish kodi — harflari ajratilgan izoh va ramkadagi kod."""
    spaced = " ".join("LIGA KODI")
    fig.text(0.5, RACE_CODE_LABEL_Y, spaced, ha="center", va="center",
             color=c["ink2"], fontsize=9.5)
    fig.text(0.5, RACE_CODE_Y, code, ha="center", va="center", color=c["ink"],
             fontsize=14, fontweight="bold", family=RACE_CODE_FONT,
             bbox=dict(boxstyle="round,pad=0.42", facecolor=c["surface"],
                       edgecolor=c["s1"], linewidth=1.4))


def race_chart(out_path: str | Path, title: str, subtitle: str,
               gws: list[int], runners: list[Runner], code: str = "",
               palette: dict | None = None) -> Path:
    """Liga yetakchilarining mavsumiy poygasi — o'rin chizig'i va jadval."""
    if not runners or not gws:
        raise ValueError("Poyga charti uchun menejerlar va turlar kerak")
    if len(runners) > len(SERIES):
        raise ValueError(f"Ko'pi bilan {len(SERIES)} ta menejer "
                         f"(berildi: {len(runners)})")

    c = {**PALETTE, **(palette or {})}
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=RACE_FIG, dpi=150, facecolor=c["surface"])
    try:
        fig.text(0.5, 0.960, plain(title), ha="center", color=c["ink"],
                 fontsize=24, fontweight="bold")
        if subtitle:
            fig.text(0.5, 0.928, plain(subtitle), ha="center", va="top",
                     color=c["ink2"], fontsize=12.5, linespacing=1.45)

        _race_panel(fig, gws, runners, c)
        _race_table(fig, runners, c)
        if code:
            _race_code(fig, code, c)

        mark = logo_path()
        image = mpimg.imread(str(mark)) if mark else None
        if image is not None:
            width = 0.26
            height = _logo_height(fig, image, width)
            _logo_axes(fig, 0.5 - width / 2, 0.425 - height / 2, width,
                       image, alpha=0.12, zorder=2.5)
            _logo_axes(fig, 0.5 - 0.24 / 2, 0.014, 0.24, image)
        else:
            log.warning("Logotip topilmadi (%s) — rasm logosiz chiqadi", config.CHART_LOGO)

        fig.savefig(out_path, facecolor=c["surface"])
    finally:
        plt.close(fig)
    return out_path


def comparison_chart(out_path: str | Path, title: str, subtitle: str,
                     name_a: str, name_b: str, metrics: list[Metric],
                     gws: list[int] | None = None,
                     series_a: list[int] | None = None,
                     series_b: list[int] | None = None,
                     trend_title: str = "", palette: dict | None = None) -> Path:
    """Ikki futbolchini solishtiruvchi rasmni chizadi va yo'lini qaytaradi."""
    if len(metrics) < MIN_METRICS:
        raise ValueError(f"Radar uchun kamida {MIN_METRICS} ko'rsatkich kerak "
                         f"(berildi: {len(metrics)})")

    c = {**PALETTE, **(palette or {})}
    colours = (c["s1"], c["s2"])
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=150, facecolor=c["surface"])
    try:
        fig.text(0.5, 0.963, plain(title), ha="center", color=c["ink"],
                 fontsize=24, fontweight="bold")
        if subtitle:
            fig.text(0.5, 0.932, plain(subtitle), ha="center", va="top", color=c["ink2"],
                     fontsize=12.5, linespacing=1.6)

        _radar(fig, metrics, colours, c)

        mark = logo_path()
        image = mpimg.imread(str(mark)) if mark else None
        if image is not None:
            # suv belgisi aynan radar markazida: rasmni kesib, logotipni
            # olib tashlashning imkoni yo'q
            rx, ry, rw, rh = RADAR
            width = 0.30
            height = _logo_height(fig, image, width)
            _logo_axes(fig, rx + rw / 2 - width / 2, ry + rh / 2 - height / 2,
                       width, image, alpha=0.16, zorder=2.6)

        if gws and series_a and series_b:
            _trend(fig, gws, series_a, series_b, colours, c,
                   trend_title or f"Oxirgi {len(gws)} turdagi ochkolar")

        _table(fig, name_a, name_b, metrics, colours, c)

        if image is not None:
            _logo_axes(fig, 0.5 - 0.27 / 2, 0.008, 0.27, image)
        else:
            log.warning("Logotip topilmadi (%s) — rasm logosiz chiqadi", config.CHART_LOGO)

        fig.savefig(out_path, facecolor=c["surface"])
    finally:
        plt.close(fig)
    return out_path
