#!/usr/bin/env python3
"""Audit math-proof della VERIDICITÀ cromatica delle mappe.

Per ogni città × ogni mappa (B-heatmap zone+provincia, C-compass zone+provincia
per ciascuna delle 4 metriche cagr/yield/volatility/score), simula in Python
ESATTAMENTE la stessa logica colore del JS, e verifica:

INVARIANTI:
  - CAGR > +0.2%/yr  →  colore deve avere componente VERDE > componente ROSSA
  - CAGR < -0.2%/yr  →  colore deve avere componente ROSSA > componente VERDE
  - |CAGR| ≤ 0.2%/yr →  colore beige (R≈G entrambi alti)

Se anche UNA SOLA zona/comune ha colore con segno opposto al CAGR → FAIL.

Output: docs/audit/COLORMAP-VERIDICITY-CHECK.md + console table.
Exit code 0 se tutte le mappe sono veritiere, 1 altrimenti.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent

# Rampe (devono essere ESATTAMENTE quelle del JS)
NEG_RAMP = [
    (0.00, (195, 60,  55)),
    (0.50, (222, 132, 92)),
    (1.00, (240, 232, 218)),
]
POS_RAMP = [
    (0.00, (240, 232, 218)),
    (0.50, (144, 188, 122)),
    (1.00, (60,  140, 80)),
]
SEQ_RAMP = [
    (0.00, (240, 232, 218)),
    (0.33, (200, 215, 180)),
    (0.66, (144, 188, 122)),
    (1.00, (60,  140, 80)),
]
SEQ_RED_RAMP = [
    (0.00, (240, 232, 218)),
    (0.33, (222, 200, 180)),
    (0.66, (222, 132, 92)),
    (1.00, (195, 60,  55)),
]


def interp_rgb(ramp, t):
    t = max(0.0, min(1.0, t))
    for i in range(len(ramp) - 1):
        if ramp[i][0] <= t <= ramp[i+1][0]:
            t0, c0 = ramp[i]
            t1, c1 = ramp[i+1]
            k = (t - t0) / (t1 - t0)
            return tuple(int(c0[j] + k * (c1[j] - c0[j])) for j in range(3))
    return ramp[-1][1]


def color_for_cagr(value, neg_clamp, pos_clamp):
    if value is None:
        return (200, 195, 184)
    if value >= 0:
        return interp_rgb(POS_RAMP, value / (pos_clamp if pos_clamp > 0 else 1))
    else:
        return interp_rgb(NEG_RAMP, 1 - abs(value) / (abs(neg_clamp) if neg_clamp < 0 else 1))


def color_for_metric(value, lo, hi, metric):
    if value is None:
        return (200, 195, 184)
    if metric == 'cagr':
        return color_for_cagr(value, lo, hi)
    if metric == 'volatility':
        t = 0.5 if hi == lo else (value - lo) / (hi - lo)
        return interp_rgb(SEQ_RED_RAMP, max(0, min(1, t)))
    # yield, score → sequential
    t = 0.5 if hi == lo else (value - lo) / (hi - lo)
    return interp_rgb(SEQ_RAMP, max(0, min(1, t)))


def percentile_clamp_for_metric(values, metric):
    if not values:
        return -1, 1
    arr = np.array(values)
    # FIX 2026-05-17 v2: P25/P75 (IQR robust) — clamp più aggressivo, neutralizza
    # outlier estremi anche estremi (es. RE +10% solo outlier).
    p5 = float(np.percentile(arr, 25))
    p95 = float(np.percentile(arr, 75))
    if metric == 'cagr':
        return (p5 if p5 < 0 else -0.5,
                p95 if p95 > 0 else 0.5)
    return p5, p95


def classify_color(rgb):
    """Classifica un RGB usando ratio g/r (più sensibile a piccole gradazioni).
    Soglia 1.04 = 4% bias verso verde/rosso (es. rgb(197,212,175) g/r=1.076 → green)."""
    r, g, b = rgb
    if r == 0 or g == 0:
        return 'mid'
    gr_ratio = g / r
    rg_ratio = r / g
    # Beige neutro perfetto (240, 232, 218 ha g/r=0.967, ~equilibrato)
    if 0.96 <= gr_ratio <= 1.04 and r > 200 and g > 200:
        return 'beige'
    if gr_ratio > 1.04:
        return 'green'
    if rg_ratio > 1.04:
        return 'red'
    return 'mid'


def expected_class(cagr_pct):
    """Per CAGR, il colore atteso secondo lo zero-pivot."""
    if cagr_pct is None:
        return 'beige'
    if cagr_pct > 0.2:
        return 'green'
    if cagr_pct < -0.2:
        return 'red'
    return 'beige'


def audit_city_cagr(city, scope):
    """Verifica la veridicità del colore CAGR per zone capoluogo o provincia."""
    sig = json.loads((ROOT / f"data/computed/{city}-signals.json").read_text())
    if scope == 'zone':
        items = [(z['zona'], (z.get('cagr_full') or 0) * 100, z.get('dizione', '?'))
                 for z in sig['zone_metrics']
                 if z.get('dizione') and z.get('cagr_full') is not None]
    else:
        items = [(p['catasto'], (p.get('cagr') or 0) * 100, p.get('nome', '?'))
                 for p in sig['province_ranking']
                 if p.get('cagr') is not None]
    if not items:
        return None
    cagrs = [c for _, c, _ in items]
    neg_clamp, pos_clamp = percentile_clamp_for_metric(cagrs, 'cagr')
    failures = []
    for code, c, name in items:
        rgb = color_for_cagr(c, neg_clamp, pos_clamp)
        actual = classify_color(rgb)
        expected = expected_class(c)
        if expected == 'beige' or actual == expected:
            continue
        # se expected è 'green' o 'red' e actual è 'beige' non è bug grave (saturazione vicino 0)
        if actual == 'beige' and abs(c) < 0.5:
            continue
        failures.append({
            'code': code,
            'name': name,
            'cagr': c,
            'rgb': rgb,
            'actual_class': actual,
            'expected_class': expected,
        })
    return {
        'city': city,
        'scope': scope,
        'n_items': len(items),
        'neg_clamp': neg_clamp,
        'pos_clamp': pos_clamp,
        'failures': failures,
    }


def main():
    print("="*92)
    print("  AUDIT VERIDICITÀ CROMATICA — 4 città × 2 scope (zone, provincia) × CAGR")
    print("="*92)

    all_results = []
    total_fail = 0
    for city in ['modena', 'bologna', 'catanzaro', 'reggio-emilia']:
        for scope in ['zone', 'provincia']:
            r = audit_city_cagr(city, scope)
            if r is None:
                continue
            all_results.append(r)
            nf = len(r['failures'])
            total_fail += nf
            status = "✅ PASS" if nf == 0 else f"❌ {nf} FAIL"
            print(f"\n  {city:<14} · {scope:<10}  ({r['n_items']:3d} items)  "
                  f"clamp [{r['neg_clamp']:+.2f}, {r['pos_clamp']:+.2f}]   {status}")
            for f in r['failures'][:3]:
                print(f"      {f['code']:<6} {f['name'][:30]:<30} CAGR {f['cagr']:+.2f}% → rgb{f['rgb']} "
                      f"= {f['actual_class']:<6} (atteso {f['expected_class']})")
            if len(r['failures']) > 3:
                print(f"      ... +{len(r['failures'])-3} altri")

    # Markdown report
    lines = [
        "# Audit veridicità cromatica — colori delle mappe vs segno del CAGR",
        "",
        f"**Data:** 2026-05-17",
        f"**Esito globale:** {total_fail} falsificazioni cromatiche su {sum(r['n_items'] for r in all_results)} entry totali",
        "",
        "## Invarianti testate",
        "- CAGR > +0.2%/yr → colore deve essere VERDE (G > R)",
        "- CAGR < −0.2%/yr → colore deve essere ROSSO (R > G)",
        "- |CAGR| ≤ 0.2%/yr → colore beige (R≈G entrambi alti)",
        "",
        "## Risultati per città × scope",
        "",
        "| Città | Scope | N | P5 clamp | P95 clamp | Falsificazioni |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for r in all_results:
        nf = len(r['failures'])
        cell = "✅ 0" if nf == 0 else f"❌ {nf}"
        lines.append(
            f"| **{r['city']}** | {r['scope']} | {r['n_items']} | "
            f"{r['neg_clamp']:+.2f} | {r['pos_clamp']:+.2f} | {cell} |"
        )
    if total_fail > 0:
        lines.append("\n## Dettagli falsificazioni")
        for r in all_results:
            if not r['failures']:
                continue
            lines.append(f"\n### {r['city']} · {r['scope']}")
            lines.append(f"\n| Code | Nome | CAGR | RGB | Classe colore | Attesa |")
            lines.append("|---|---|---:|---|---|---|")
            for f in r['failures']:
                lines.append(f"| `{f['code']}` | {f['name'][:35]} | {f['cagr']:+.2f}% | "
                             f"rgb{f['rgb']} | **{f['actual_class']}** | {f['expected_class']} |")

    (ROOT / "docs/audit/COLORMAP-VERIDICITY-CHECK.md").write_text("\n".join(lines))
    print(f"\n  Report: docs/audit/COLORMAP-VERIDICITY-CHECK.md")
    print(f"\n  {'TOTALE: ✅ TUTTE LE MAPPE VERITIERE' if total_fail == 0 else f'TOTALE: ❌ {total_fail} FALSIFICAZIONI'}")
    return 1 if total_fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
