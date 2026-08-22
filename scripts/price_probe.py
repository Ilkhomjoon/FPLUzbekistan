"""Narx o'zgarishi bashorati API'da qayerda turganini topish (bir martalik razvedka).

FPL 2026/27 da rasmiy "Price Change Predictor" qo'shdi — foiz ko'rinishida.
Bu skript o'sha ma'lumot API javobining qaysi maydonida ekanini qidiradi.

Ishlatish:
    python -m scripts.price_probe
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import fpl_api  # noqa: E402

KEYWORDS = ("price", "change", "progress", "threshold", "predict", "target", "transfer")

CANDIDATE_PATHS = [
    "/price-changes/",
    "/element-price-changes/",
    "/price-change-predictions/",
    "/elements/price-changes/",
    "/event-status/",
]


def main() -> int:
    print("\n=== 1. bootstrap-static: futbolchi maydonlari ===")
    bs = fpl_api.get_bootstrap()
    sample = bs["elements"][0]
    keys = sorted(sample.keys())
    print(f"  jami {len(keys)} ta maydon\n")

    hits = [k for k in keys if any(w in k.lower() for w in KEYWORDS)]
    print("  Qidiruv so'zlariga mos maydonlar:")
    for k in hits:
        print(f"    {k} = {sample[k]!r}")

    print("\n  Barcha maydonlar:")
    for i in range(0, len(keys), 4):
        print("    " + "  ".join(f"{k:<28}" for k in keys[i:i + 4]))

    print("\n=== 2. Eng ko'p transfer qilinganlar (namuna qiymatlar) ===")
    teams = fpl_api.teams_by_id(bs)
    top = sorted(bs["elements"], key=lambda p: -(p.get("transfers_in_event") or 0))[:5]
    bottom = sorted(bs["elements"], key=lambda p: -(p.get("transfers_out_event") or 0))[:5]
    for label, group in (("ko'p kirgan", top), ("ko'p chiqqan", bottom)):
        print(f"\n  {label}:")
        for p in group:
            extra = {k: p[k] for k in hits}
            print(f"    {p['web_name']:<16} ({teams.get(p['team'], {}).get('short_name','')}) "
                  f"in={p.get('transfers_in_event'):>7,} out={p.get('transfers_out_event'):>7,} "
                  f"cost={p['now_cost']/10:.1f}  {extra}")

    print("\n=== 3. Boshqa bo'limlarda bormi ===")
    for key in bs:
        if key in ("elements", "teams", "events", "element_types"):
            continue
        print(f"  {key}: {json.dumps(bs[key])[:160]}")

    print("\n=== 4. Ehtimoliy endpointlar ===")
    for path in CANDIDATE_PATHS:
        try:
            data = fpl_api._get(path)
            preview = json.dumps(data)[:200]
            print(f"  OK   {path} -> {preview}")
        except Exception as exc:
            print(f"  yo'q {path} -> {str(exc)[:90]}")

    print("\n=== 5. Bitta futbolchining to'liq ma'lumoti ===")
    pid = top[0]["id"]
    try:
        summary = fpl_api._get(f"/element-summary/{pid}/")
        print(f"  element-summary/{pid} kalitlari: {list(summary.keys())}")
        if summary.get("history"):
            print(f"  history[0] kalitlari: {sorted(summary['history'][0].keys())}")
    except Exception as exc:
        print(f"  XATO — {exc}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
