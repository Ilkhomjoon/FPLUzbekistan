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


def logo_path() -> Path | None:
    path = Path(config.CHART_LOGO)
    return path if path.is_file() else None


def _logo_axes(fig, left: float, bottom: float, width: float,
               image, alpha: float = 1.0, zorder: float = 5):
    """Nisbatini saqlab logotip qo'yadi (figura cho'zinchoq, shuni hisobga olamiz)."""
    height, pixels = image.shape[0], image.shape[1]
    box_h = width * (height / pixels) * (FIG_W / FIG_H)
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
        fig.text(0.5, 0.963, title, ha="center", color=c["ink"],
                 fontsize=24, fontweight="bold")
        if subtitle:
            fig.text(0.5, 0.932, subtitle, ha="center", va="top", color=c["ink2"],
                     fontsize=12.5, linespacing=1.6)

        _radar(fig, metrics, colours, c)

        mark = logo_path()
        image = mpimg.imread(str(mark)) if mark else None
        if image is not None:
            # suv belgisi aynan radar markazida: rasmni kesib, logotipni
            # olib tashlashning imkoni yo'q
            rx, ry, rw, rh = RADAR
            width = 0.30
            height = width * (image.shape[0] / image.shape[1]) * (FIG_W / FIG_H)
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
