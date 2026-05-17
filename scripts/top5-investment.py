#!/usr/bin/env python3
"""Top 5 zone di investimento per città — ranking multi-criteria quant-driven.

Combina:
  - Score composito 0-100 del compass (growth+yield+stability+momentum+level)
  - Volume momentum tag (rocket/growing/stable/cooling/frozen)
  - Price-volume quadrant (Q1_HOT/Q2_OVERPRICED/Q3_OPPORTUNITY/Q4_DEAD)
  - Liquidity score (z-normalized IMI + NTN_cagr + NTN_recent_slope)
  - Anomaly z-score (z<-1.5 = sottoprezzo vs fascia, opportunità)

Applica un filtro Pareto-ottimale e produce 5 raccomandazioni RANKED con motivazione esplicita.

Usage:
  python3 scripts/top5-investment.py --city bologna
  python3 scripts/top5-investment.py --city modena
  python3 scripts/top5-investment.py --city catanzaro

Output:
  docs/audit/<city>/top5-investment.md (tabella + motivazioni)
  docs/audit/<city>/fig-top5-ranking.png (radar chart 5 dimensions per zona)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 140,
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
    "axes.spines.top": False, "axes.spines.right": False,
})


def safe_get(d, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d:
            d = d[k]
        else:
            return default
    return d


def normalize(values, reverse=False):
    """Min-max normalize to 0-1. If reverse, lower is better."""
    vs = [v for v in values if v is not None]
    if not vs:
        return [None] * len(values)
    lo, hi = min(vs), max(vs)
    if hi == lo:
        return [0.5 if v is not None else None for v in values]
    out = []
    for v in values:
        if v is None:
            out.append(None)
        else:
            n = (v - lo) / (hi - lo)
            out.append(1 - n if reverse else n)
    return out


def rank_zones(city):
    sig = json.loads((ROOT / "data" / "computed" / f"{city}-signals.json").read_text())
    com = json.loads((ROOT / "data" / "computed" / f"{city}-compass.json").read_text())
    try:
        vol = json.loads((ROOT / "data" / "computed" / f"{city}-volume-signals.json").read_text())
    except FileNotFoundError:
        vol = None

    # Build vol index by NEW zone
    vol_by_zone = {}
    if vol:
        for v in vol.get("zone_volume_metrics", []):
            for nz in (v.get("zona_new") or []):
                vol_by_zone[nz] = v

    abci = com["by_tipologia"]["abitazioni_civili"]
    zones = abci["zone_metrics"]

    # Filtro: solo zone correnti (con dizione) e con cagr/yield/vol/score completi
    candidates = []
    for z in zones:
        if not z.get("dizione"):
            continue
        if z.get("score") is None or z.get("cagr") is None or z.get("yield_lordo_pct") is None:
            continue
        vinfo = vol_by_zone.get(z["zona"], {})
        z["_vol"] = vinfo
        candidates.append(z)

    if not candidates:
        return None, None

    # Estrai vettori per normalization
    cagrs = [z["cagr"] * 100 for z in candidates]
    yields = [z["yield_lordo_pct"] for z in candidates]
    vols_pct = [z.get("volatility_pct") for z in candidates]
    scores = [z["score"] for z in candidates]
    prezzi = [z.get("prezzo_acquisto") for z in candidates]
    liqs = [z.get("_vol", {}).get("liquidity_score") for z in candidates]
    ntn_cagrs = [z.get("_vol", {}).get("ntn_cagr_pct") for z in candidates]

    # Normalizzazioni (higher = better in tutti i casi)
    n_cagr = normalize(cagrs)
    n_yield = normalize(yields)
    n_vol = normalize(vols_pct, reverse=True)  # lower volatility = better
    n_score = normalize(scores)
    n_level = normalize(prezzi, reverse=True)  # lower price = better entry
    n_liq = normalize(liqs)

    # Composite QUANT-RANK con weights propri
    # 30% Score compass (già pesato di growth/yield/stab/mom/level)
    # 20% Yield (cash flow attuale)
    # 15% Liquidity (NTN volume momentum)
    # 15% NTN CAGR (volume crescita)
    # 10% CAGR price (capital gain)
    # 10% Stabilità (1 - vol)
    w = {"score": 0.30, "yield": 0.20, "liq": 0.15, "ntn_cagr": 0.15, "cagr": 0.10, "vol": 0.10}
    n_ntn_cagr = normalize(ntn_cagrs)

    quant_scores = []
    for i, z in enumerate(candidates):
        parts = []
        if n_score[i] is not None: parts.append(("score", w["score"], n_score[i]))
        if n_yield[i] is not None: parts.append(("yield", w["yield"], n_yield[i]))
        if n_liq[i] is not None:   parts.append(("liq", w["liq"], n_liq[i]))
        if n_ntn_cagr[i] is not None: parts.append(("ntn_cagr", w["ntn_cagr"], n_ntn_cagr[i]))
        if n_cagr[i] is not None:  parts.append(("cagr", w["cagr"], n_cagr[i]))
        if n_vol[i] is not None:   parts.append(("vol", w["vol"], n_vol[i]))
        if not parts:
            quant_scores.append(None)
            continue
        s = sum(wgt * val for _, wgt, val in parts)
        w_total = sum(wgt for _, wgt, _ in parts)
        quant_scores.append(s / w_total * 100)

    # Penalità soft: -15 se momentum=frozen
    for i, z in enumerate(candidates):
        if quant_scores[i] is None: continue
        if z.get("_vol", {}).get("momentum_tag") == "frozen":
            quant_scores[i] = max(0, quant_scores[i] - 15)
        elif z.get("_vol", {}).get("momentum_tag") == "cooling":
            quant_scores[i] = max(0, quant_scores[i] - 5)

    # Bonus +5 se quadrant = Q3_OPPORTUNITY (cheap & active)
    for i, z in enumerate(candidates):
        if quant_scores[i] is None: continue
        q = z.get("_vol", {}).get("price_volume_quadrant")
        if q == "Q3_OPPORTUNITY":
            quant_scores[i] = min(100, quant_scores[i] + 5)

    # Sort
    enriched = []
    for i, z in enumerate(candidates):
        enriched.append({
            "zona": z["zona"],
            "dizione": z.get("dizione", "?"),
            "fascia": z.get("fascia", "?"),
            "score_compass": z["score"],
            "verdict": z["verdict"],
            "cagr_pct": z["cagr"] * 100,
            "yield_pct": z["yield_lordo_pct"],
            "vol_pct": z.get("volatility_pct"),
            "prezzo": z["prezzo_acquisto"],
            "liquidity": z.get("_vol", {}).get("liquidity_score"),
            "ntn_last": z.get("_vol", {}).get("ntn_last"),
            "ntn_cagr_pct": z.get("_vol", {}).get("ntn_cagr_pct"),
            "imi_last_pct": z.get("_vol", {}).get("imi_last_pct"),
            "momentum_tag": z.get("_vol", {}).get("momentum_tag", "?"),
            "quadrant": z.get("_vol", {}).get("price_volume_quadrant", "?"),
            "anomaly_flag": z.get("anomaly", {}).get("flag"),
            "anomaly_cagr_z": z.get("anomaly", {}).get("cagr_z"),
            "comparables": [c["zona"] for c in (z.get("comparables") or [])[:3]],
            "quant_score": round(quant_scores[i], 1) if quant_scores[i] is not None else None,
            "_n_score": n_score[i],
            "_n_yield": n_yield[i],
            "_n_cagr": n_cagr[i],
            "_n_vol": n_vol[i],
            "_n_liq": n_liq[i],
            "_n_ntn_cagr": n_ntn_cagr[i],
        })

    enriched.sort(key=lambda z: -(z["quant_score"] or 0))
    return enriched, abci


def build_motivation(z):
    """Genera una motivazione esplicita per la zona."""
    bits = []
    # Score compass
    if z["score_compass"] >= 70:
        bits.append(f"score compass {z['score_compass']:.1f} (BUY)")
    elif z["score_compass"] >= 50:
        bits.append(f"score compass {z['score_compass']:.1f} (WATCH↑)")
    else:
        bits.append(f"score compass {z['score_compass']:.1f}")
    # CAGR
    if z["cagr_pct"] > 1:
        bits.append(f"CAGR prezzi +{z['cagr_pct']:.2f}%/yr")
    elif z["cagr_pct"] >= 0:
        bits.append(f"CAGR prezzi {z['cagr_pct']:+.2f}%/yr (flat)")
    else:
        bits.append(f"CAGR prezzi {z['cagr_pct']:+.2f}%/yr (decline)")
    # Yield
    if z["yield_pct"] >= 5.5:
        bits.append(f"yield {z['yield_pct']:.2f}% (alto)")
    elif z["yield_pct"] >= 4:
        bits.append(f"yield {z['yield_pct']:.2f}%")
    else:
        bits.append(f"yield {z['yield_pct']:.2f}% (basso)")
    # Volume momentum
    if z["momentum_tag"] == "rocket":
        bits.append("volume 🚀 rocket")
    elif z["momentum_tag"] == "growing":
        bits.append(f"volume ↗ growing (NTN CAGR {z.get('ntn_cagr_pct','?')}%)")
    elif z["momentum_tag"] == "stable":
        bits.append(f"volume → stable (NTN CAGR {z.get('ntn_cagr_pct','?')}%)")
    elif z["momentum_tag"] == "cooling":
        bits.append(f"volume ↘ cooling (-{abs(z.get('ntn_cagr_pct',0)):.1f}%/yr) — cautela")
    elif z["momentum_tag"] == "frozen":
        bits.append("volume 💀 frozen — RISCHIO")
    # Quadrant
    qtxt = {"Q1_HOT": "Q1 HOT (premium+liquido)",
            "Q2_OVERPRICED": "Q2 OVERPRICED (premium illiquido)",
            "Q3_OPPORTUNITY": "Q3 OPPORTUNITY (cheap+attivo)",
            "Q4_DEAD": "Q4 DEAD (cheap+illiquido)"}
    if z["quadrant"] in qtxt:
        bits.append(qtxt[z["quadrant"]])
    # Liquidity
    if z.get("liquidity") is not None:
        if z["liquidity"] >= 70:
            bits.append(f"liquidity {z['liquidity']:.0f}/100 (alta)")
        elif z["liquidity"] >= 40:
            bits.append(f"liquidity {z['liquidity']:.0f}/100")
        else:
            bits.append(f"liquidity {z['liquidity']:.0f}/100 (bassa)")
    # Anomalia (z-score CAGR vs fascia)
    if z.get("anomaly_cagr_z") is not None:
        if z["anomaly_cagr_z"] < -1.5:
            bits.append(f"anomalia σ={z['anomaly_cagr_z']:.2f} (sottoprezzo vs fascia)")
        elif z["anomaly_cagr_z"] > 1.5:
            bits.append(f"anomalia σ={z['anomaly_cagr_z']:.2f} (sovraperformante)")
    return " · ".join(bits)


def render_radar(top5, out_path, city):
    """Radar chart 6-dim per top 5 zone."""
    dims = ["score", "yield", "ntn_cagr", "liq", "cagr", "vol"]
    dim_labels = ["Score\ncompass", "Yield", "NTN\nCAGR", "Liquidity", "CAGR\nprice", "Stability\n(1-vol)"]
    angles = np.linspace(0, 2 * np.pi, len(dims), endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(10, 7), subplot_kw=dict(polar=True))
    colors = ["#bc4749", "#1f4068", "#3a5a40", "#f4a261", "#8e6c88"]
    for i, z in enumerate(top5):
        vals = [z.get(f"_n_{d}") or 0 for d in dims]
        vals += vals[:1]
        label = f"#{i+1} {z['zona']} ({z['dizione'][:30]})"
        ax.plot(angles, vals, "o-", lw=1.6, color=colors[i % len(colors)], label=label, alpha=0.85)
        ax.fill(angles, vals, color=colors[i % len(colors)], alpha=0.08)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(dim_labels, fontsize=9)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0.25", "0.50", "0.75", "1.00"], fontsize=7, color="#888")
    ax.set_title(f"{city.title()} · Top 5 zone investimento · radar 6-dim normalizzato", pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.45, 1.05), fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", required=True, choices=["bologna", "modena", "catanzaro"])
    args = ap.parse_args()
    city = args.city

    enriched, abci = rank_zones(city)
    if not enriched:
        sys.exit(f"ERROR: no candidates for {city}")
    top5 = enriched[:5]

    out_dir = ROOT / "docs" / "audit" / city
    out_dir.mkdir(parents=True, exist_ok=True)

    # MD report
    lines = [
        f"# Top 5 zone investimento — {city.title()}",
        "",
        f"**Metodologia:** ranking multi-criteria weighted-normalized su 6 dimensioni:",
        "- Score compass 30% (already weighted growth+yield+stability+momentum+level)",
        "- Yield lordo 20%",
        "- Liquidity score 15%",
        "- NTN CAGR (volume scambi) 15%",
        "- CAGR prezzi 10%",
        "- Stability (1−volatility) 10%",
        "",
        f"**Bonus/penalty:** +5 se quadrant=Q3_OPPORTUNITY; −5 se momentum=cooling; −15 se momentum=frozen.",
        "",
        f"**Universo:** {len(enriched)} zone correnti capoluogo con CAGR+yield+score non-null.",
        "",
        "## Ranking",
        "",
        "| Rank | Zona | Fascia | Dizione | Quant | Compass | CAGR | Yield | Vol | Liq | Momentum | Quadrant |",
        "|---:|:---:|:---:|:---|---:|---:|---:|---:|---:|---:|:---:|:---:|",
    ]
    for i, z in enumerate(top5, 1):
        lines.append(
            f"| **{i}** | **{z['zona']}** | {z['fascia']} | {z['dizione'][:42]} | "
            f"**{z['quant_score']}** | {z['score_compass']:.1f} | {z['cagr_pct']:+.2f}% | "
            f"{z['yield_pct']:.2f}% | {z['vol_pct'] or '?'}% | "
            f"{z['liquidity'] or '?'} | {z['momentum_tag']} | {z['quadrant']} |"
        )

    lines += ["", "## Motivazione per zona", ""]
    for i, z in enumerate(top5, 1):
        lines.append(f"### #{i} · {z['zona']} — {z['dizione']}")
        lines.append("")
        lines.append(f"- **Quant score:** {z['quant_score']}/100 · **Verdict compass:** {z['verdict']}")
        lines.append(f"- **Profilo:** {build_motivation(z)}")
        if z.get("prezzo"):
            lines.append(f"- **Prezzo entry:** €{z['prezzo']:,}/m² · **NTN ultimo anno:** {z.get('ntn_last','?')} scambi · **IMI:** {z.get('imi_last_pct','?')}%")
        if z["comparables"]:
            lines.append(f"- **Comparables (k-NN):** {' · '.join(z['comparables'])}")
        lines.append("")

    # Top 5 vs bottom 5 (per contesto)
    lines += ["## Per contrasto — Bottom 5 (da EVITARE)", ""]
    lines.append("| Rank | Zona | Quant | CAGR | Yield | Momentum | Note |")
    lines.append("|---:|:---:|---:|---:|---:|:---:|:---|")
    for i, z in enumerate(reversed(enriched[-5:]), 1):
        notes = []
        if z["momentum_tag"] == "frozen": notes.append("volume frozen")
        if z["cagr_pct"] < 0: notes.append(f"prezzi {z['cagr_pct']:+.2f}%/yr")
        if z["yield_pct"] < 4: notes.append(f"yield basso {z['yield_pct']:.2f}%")
        if z["quadrant"] == "Q4_DEAD": notes.append("Q4 DEAD")
        lines.append(
            f"| {i} | {z['zona']} | {z['quant_score']} | "
            f"{z['cagr_pct']:+.2f}% | {z['yield_pct']:.2f}% | "
            f"{z['momentum_tag']} | {', '.join(notes) or 'n/a'} |"
        )

    md_path = out_dir / "top5-investment.md"
    md_path.write_text("\n".join(lines))

    render_radar(top5, out_dir / "fig-top5-radar.png", city)

    print(f"\n══ TOP 5 INVESTIMENTO · {city.upper()} ══\n")
    for i, z in enumerate(top5, 1):
        print(f"  #{i} {z['zona']:4s} fascia {z['fascia']} · {z['dizione'][:40]:40s}")
        print(f"      quant={z['quant_score']} compass={z['score_compass']:.1f} verdict={z['verdict']}")
        print(f"      {build_motivation(z)}")
        print()

    print(f"  Report: {md_path.relative_to(ROOT)}")
    print(f"  Radar : {(out_dir / 'fig-top5-radar.png').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
