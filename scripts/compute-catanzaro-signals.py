#!/usr/bin/env python3
"""Catanzaro investor signal compute layer.

Fork di compute-modena-signals.py (Modena intatto), riconfigurato per provincia
di Catanzaro: capoluogo C352, ~80 comuni, GeoJSON dedicati. Stessa pipeline:

  - per-zone time-series (cleaned, gap-aware)
  - CAGR (compound annual growth rate) 2005 → latest
  - rolling yield: prezzo_affitto_annuo / prezzo_acquisto
  - volatility (std-dev of YoY pct changes)
  - trend score: linear regression slope sign + magnitude
  - fascia-aggregated series (B/C/D/E/R, robust to zone-rename)
  - "signals": top 5 grow / decline / volatile / contrarian
  - province-level: top 5 comuni grow vs decline

Validates everything with asserts before writing JSON.
Writes:
  data/computed/catanzaro-signals.json     (frontend-ready, pre-validated)
  data/computed/catanzaro-zone-series.json (per-zone full timeseries)

Usage:
  python3 scripts/compute-catanzaro-signals.py
"""
from __future__ import annotations

import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "sagona-backfill" / "prezzi.csv"
ZONE_GEOJSON = ROOT / "data" / "geojson" / "catanzaro-zone-omi.geojson"
PROVINCE_GEOJSON = ROOT / "data" / "geojson" / "catanzaro-province-comuni.geojson"
OUT_DIR = ROOT / "data" / "computed"
OUT_SIGNALS = OUT_DIR / "catanzaro-signals.json"
OUT_SERIES = OUT_DIR / "catanzaro-zone-series.json"

CAPOLUOGO_CATASTO = "C352"
CAPOLUOGO_NAME = "Catanzaro"

# Default tipo for headline metrics — most liquid / interpretable for investors
HEADLINE_TIPO = "abitazioni_civili"
HEADLINE_OP = "acquisto"


# ───────────────────────────────────────── load + clean ──
def load_csv() -> list[dict]:
    """Read CSV, coerce types, validate."""
    if not CSV_PATH.exists():
        sys.exit(f"ERROR: {CSV_PATH} not found. Run scripts/sagona-backfill.py first.")
    rows = []
    with CSV_PATH.open() as f:
        for r in csv.DictReader(f):
            r = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in r.items()}
            r["anno"] = int(r["anno"])
            for k in ("prezzo_min", "prezzo_max", "prezzo_medio"):
                v = r.get(k, "")
                r[k] = float(v) if v not in ("", None) else None
            rows.append(r)
    assert len(rows) > 1000, f"too few rows: {len(rows)}"
    print(f"  loaded {len(rows):,} rows from {CSV_PATH.name}")
    return rows


# ───────────────────────────────────────── math primitives ──
def cagr(v0: float, vN: float, years: float) -> float | None:
    if v0 is None or vN is None or v0 <= 0 or vN <= 0 or years <= 0:
        return None
    return (vN / v0) ** (1 / years) - 1


def linreg_slope(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3 or len(ys) != n:
        return None
    xm = sum(xs) / n
    ym = sum(ys) / n
    num = sum((x - xm) * (y - ym) for x, y in zip(xs, ys))
    den = sum((x - xm) ** 2 for x in xs)
    if den == 0:
        return None
    return num / den


def yoy_returns(values: list[float]) -> list[float]:
    out = []
    for a, b in zip(values, values[1:]):
        if a and a > 0 and b is not None:
            out.append((b - a) / a)
    return out


def safe_round(x: float | None, digits: int = 2) -> float | None:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(x, digits)


# ───────────────────────────────────────── core compute ──
def build_zone_series(rows: list[dict], comune: str, tipo: str, op: str) -> dict[str, dict]:
    series: dict[str, dict[int, float]] = defaultdict(dict)
    for r in rows:
        if r["comune_catasto"] != comune or r["tipo_immobile"] != tipo or r["operazione"] != op:
            continue
        if r["prezzo_medio"] is None:
            continue
        series[r["zona"]][r["anno"]] = r["prezzo_medio"]
    return {z: dict(d) for z, d in series.items()}


def build_fascia_series(rows: list[dict], comune: str, tipo: str, op: str) -> dict[str, dict]:
    bucket: dict[tuple[int, str], list[float]] = defaultdict(list)
    for r in rows:
        if r["comune_catasto"] != comune or r["tipo_immobile"] != tipo or r["operazione"] != op:
            continue
        if r["prezzo_medio"] is None or not r["fascia"]:
            continue
        bucket[(r["anno"], r["fascia"])].append(r["prezzo_medio"])

    series: dict[str, dict[int, float]] = defaultdict(dict)
    for (anno, fascia), values in bucket.items():
        series[fascia][anno] = sum(values) / len(values)
    return {f: dict(d) for f, d in series.items()}


def zone_metrics(zona: str, ts_acq: dict, ts_aff: dict) -> dict:
    years_acq = sorted(ts_acq.keys())
    years_aff = sorted(ts_aff.keys())

    metrics: dict = {
        "zona": zona,
        "anni_dati_acquisto": len(years_acq),
        "primo_anno": min(years_acq) if years_acq else None,
        "ultimo_anno": max(years_acq) if years_acq else None,
        "prezzo_acquisto_attuale": ts_acq.get(max(years_acq)) if years_acq else None,
        "prezzo_affitto_attuale": ts_aff.get(max(years_aff)) if years_aff else None,
    }

    if len(years_acq) >= 2:
        v0 = ts_acq[years_acq[0]]
        vN = ts_acq[years_acq[-1]]
        n_years = years_acq[-1] - years_acq[0]
        metrics["cagr_full"] = safe_round(cagr(v0, vN, n_years), 4)
        metrics["delta_total_pct"] = safe_round((vN / v0 - 1) * 100, 1) if v0 else None
    else:
        metrics["cagr_full"] = None
        metrics["delta_total_pct"] = None

    recent_years = [y for y in years_acq if y >= max(years_acq) - 10]
    if len(recent_years) >= 3:
        recent_vals = [ts_acq[y] for y in recent_years]
        slope = linreg_slope([float(y) for y in recent_years], recent_vals)
        metrics["recent_slope_eur_per_year"] = safe_round(slope, 1) if slope else None
        if slope and recent_vals[0]:
            metrics["recent_slope_pct_per_year"] = safe_round(slope / recent_vals[0] * 100, 2)
        else:
            metrics["recent_slope_pct_per_year"] = None
    else:
        metrics["recent_slope_eur_per_year"] = None
        metrics["recent_slope_pct_per_year"] = None

    yoys = yoy_returns([ts_acq[y] for y in years_acq])
    if len(yoys) >= 3:
        metrics["volatility_pct"] = safe_round(statistics.stdev(yoys) * 100, 1)
    else:
        metrics["volatility_pct"] = None

    if metrics["prezzo_acquisto_attuale"] and metrics["prezzo_affitto_attuale"]:
        rent_annual = metrics["prezzo_affitto_attuale"] * 12
        metrics["yield_lordo_pct"] = safe_round(rent_annual / metrics["prezzo_acquisto_attuale"] * 100, 2)
    else:
        metrics["yield_lordo_pct"] = None

    if years_acq and len(years_acq) >= 3:
        vals = [ts_acq[y] for y in years_acq]
        vmin, vmax = min(vals), max(vals)
        denom = vmax - vmin
        metrics["spark_years"] = years_acq
        metrics["spark_values"] = vals
        metrics["spark_normalized"] = [
            safe_round((v - vmin) / denom, 3) if denom else 0.5 for v in vals
        ]
    else:
        metrics["spark_years"] = years_acq
        metrics["spark_values"] = [ts_acq[y] for y in years_acq]
        metrics["spark_normalized"] = []

    return metrics


def load_zone_metadata() -> dict[str, dict]:
    if not ZONE_GEOJSON.exists():
        return {}
    g = json.loads(ZONE_GEOJSON.read_text())
    out = {}
    for f in g["features"]:
        p = f["properties"]
        out[p["zona"]] = {
            "fascia": p.get("fascia"),
            "dizione": p.get("dizione"),
            "link_zona": p.get("link_zona"),
        }
    return out


# ───────────────────────────────────────── province compute ──
def province_metrics(rows: list[dict], geoj: dict) -> list[dict]:
    catasto_to_name = {f["properties"]["com_catasto_code"]: f["properties"]["name"]
                       for f in geoj["features"]}
    out = []
    comuni_with_data = sorted({r["comune_catasto"] for r in rows
                               if r["comune_catasto"] in catasto_to_name})
    for cat in comuni_with_data:
        ts_acq = defaultdict(list)
        for r in rows:
            if r["comune_catasto"] != cat: continue
            if r["tipo_immobile"] != HEADLINE_TIPO: continue
            if r["operazione"] != HEADLINE_OP: continue
            if r["prezzo_medio"] is None: continue
            ts_acq[r["anno"]].append(r["prezzo_medio"])
        if not ts_acq:
            continue
        years = sorted(ts_acq.keys())
        means = {y: sum(ts_acq[y]) / len(ts_acq[y]) for y in years}
        v0, vN = means[years[0]], means[years[-1]]
        c = cagr(v0, vN, years[-1] - years[0])
        ultimo_anno_dati = years[-1]
        # FRESHNESS gate: comuni con ultimo dato < 2020 sono "stale" (es. Martirano: dati solo fino a 2012).
        # Vengono mantenuti nella lista ma marcati e spinti in fondo al ranking.
        is_stale = ultimo_anno_dati < 2020
        out.append({
            "catasto": cat,
            "nome": catasto_to_name.get(cat, cat),
            "prezzo_attuale_medio": safe_round(vN, 0),
            "prezzo_iniziale_medio": safe_round(v0, 0),
            "delta_total_pct": safe_round((vN / v0 - 1) * 100, 1) if v0 else None,
            "cagr": safe_round(c, 4),
            "anni_coperti": years[-1] - years[0] + 1,
            "ultimo_anno_dati": ultimo_anno_dati,
            "stale": is_stale,
        })
    # Stale comuni in fondo (qualunque sia il loro CAGR), fresh comuni ordinati per CAGR desc
    return sorted(out, key=lambda x: (
        x.get("stale", False),  # False prima di True → fresh prima
        -(x["cagr"] if x["cagr"] is not None else -999),
    ))


# ───────────────────────────────────────── validation ──
def validate(signals: dict) -> None:
    zm = signals["zone_metrics"]
    assert len(zm) >= 3, f"too few zones: {len(zm)} (Catanzaro è città piccola, ma min 3 atteso)"
    for z in zm:
        c = z.get("cagr_full")
        if c is not None:
            assert -0.20 <= c <= 0.20, f"crazy CAGR for {z['zona']}: {c}"
        y = z.get("yield_lordo_pct")
        if y is not None:
            assert 0.5 <= y <= 20, f"crazy yield for {z['zona']}: {y}%"
        v = z.get("volatility_pct")
        if v is not None:
            assert 0 <= v <= 50, f"crazy volatility for {z['zona']}: {v}%"

    headline = signals["headline"]
    assert headline["zone_count_total"] == len(zm)
    cagr_avg = headline.get("cagr_avg_pct")
    if cagr_avg is not None:
        assert -10 <= cagr_avg <= 10, f"crazy avg CAGR: {cagr_avg}%"
    yld = headline.get("yield_medio_pct")
    if yld is not None:
        assert 1 <= yld <= 15, f"crazy avg yield: {yld}%"

    pm = signals["province_ranking"]
    assert len(pm) >= 5, f"too few comuni with data: {len(pm)}"
    for p in pm:
        assert p["delta_total_pct"] is None or -90 <= p["delta_total_pct"] <= 500
    print("  ✓ all asserts pass")


# ───────────────────────────────────────── main ──
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = load_csv()
    zone_meta = load_zone_metadata()

    print(f"\n=== {CAPOLUOGO_NAME} {CAPOLUOGO_CATASTO} ({HEADLINE_TIPO} · {HEADLINE_OP}) ===")
    ts_acq = build_zone_series(rows, CAPOLUOGO_CATASTO, HEADLINE_TIPO, "acquisto")
    ts_aff = build_zone_series(rows, CAPOLUOGO_CATASTO, HEADLINE_TIPO, "affitto")
    print(f"  zones with acquisto: {len(ts_acq)}")
    print(f"  zones with affitto:  {len(ts_aff)}")

    zone_metrics_list = []
    for zona in sorted(ts_acq.keys()):
        m = zone_metrics(zona, ts_acq[zona], ts_aff.get(zona, {}))
        m.update(zone_meta.get(zona, {}))
        zone_metrics_list.append(m)

    zone_metrics_list.sort(key=lambda x: (
        x.get("dizione") is None,
        -(x.get("cagr_full") or -999),
    ))

    fascia_acq = build_fascia_series(rows, CAPOLUOGO_CATASTO, HEADLINE_TIPO, "acquisto")
    fascia_metrics = {}
    for fascia, ts in fascia_acq.items():
        years = sorted(ts.keys())
        if len(years) < 2:
            continue
        v0, vN = ts[years[0]], ts[years[-1]]
        fascia_metrics[fascia] = {
            "primo_anno": years[0],
            "ultimo_anno": years[-1],
            "prezzo_iniziale": safe_round(v0, 0),
            "prezzo_attuale": safe_round(vN, 0),
            "delta_total_pct": safe_round((vN / v0 - 1) * 100, 1) if v0 else None,
            "cagr": safe_round(cagr(v0, vN, years[-1] - years[0]), 4),
            "series": {str(y): safe_round(ts[y], 0) for y in years},
        }

    cagrs = [z["cagr_full"] for z in zone_metrics_list if z["cagr_full"] is not None and z.get("dizione")]
    yields = [z["yield_lordo_pct"] for z in zone_metrics_list if z["yield_lordo_pct"] is not None]
    current_prezzi = [z["prezzo_acquisto_attuale"] for z in zone_metrics_list
                      if z["prezzo_acquisto_attuale"] is not None and z.get("dizione")]

    print(f"\n=== Provincia {CAPOLUOGO_NAME} ({HEADLINE_TIPO} · {HEADLINE_OP}) ===")
    province_geoj = json.loads(PROVINCE_GEOJSON.read_text())
    province_rank = province_metrics(rows, province_geoj)
    print(f"  comuni with data: {len(province_rank)}")

    signals = {
        "metadata": {
            "generated_at": "2026-05-14",
            "capoluogo": CAPOLUOGO_NAME,
            "capoluogo_catasto": CAPOLUOGO_CATASTO,
            "headline_tipo": HEADLINE_TIPO,
            "headline_op": HEADLINE_OP,
            "source": "Sagona API + GeoPOI Agenzia Entrate (reverse-engineered)",
        },
        "headline": {
            "zone_count_total": len(zone_metrics_list),
            "zone_count_current": sum(1 for z in zone_metrics_list if z.get("dizione")),
            "cagr_avg_pct": safe_round(sum(cagrs) / len(cagrs) * 100, 2) if cagrs else None,
            "yield_medio_pct": safe_round(sum(yields) / len(yields), 2) if yields else None,
            "prezzo_medio_attuale": safe_round(sum(current_prezzi) / len(current_prezzi), 0) if current_prezzi else None,
            "anni_orizzonte": max(z["ultimo_anno"] for z in zone_metrics_list) - min(z["primo_anno"] for z in zone_metrics_list if z["primo_anno"]) if zone_metrics_list else 0,
        },
        "top_growth": [z for z in zone_metrics_list if z.get("dizione") and z["cagr_full"] is not None][:5],
        "top_decline": sorted([z for z in zone_metrics_list if z.get("dizione") and z["cagr_full"] is not None],
                              key=lambda x: x["cagr_full"])[:5],
        "top_yield": sorted([z for z in zone_metrics_list if z.get("dizione") and z["yield_lordo_pct"] is not None],
                            key=lambda x: -x["yield_lordo_pct"])[:5],
        "top_volatile": sorted([z for z in zone_metrics_list if z.get("dizione") and z["volatility_pct"] is not None],
                               key=lambda x: -x["volatility_pct"])[:5],
        "zone_metrics": zone_metrics_list,
        "fascia_metrics": fascia_metrics,
        "province_ranking": province_rank,
    }

    validate(signals)

    OUT_SIGNALS.write_text(json.dumps(signals, indent=2, ensure_ascii=False))
    print(f"\n  wrote {OUT_SIGNALS} ({OUT_SIGNALS.stat().st_size:,} bytes)")

    series_out = {
        "fascia_series": fascia_acq,
        "zone_series_acquisto": ts_acq,
        "zone_series_affitto": ts_aff,
    }
    OUT_SERIES.write_text(json.dumps(series_out, ensure_ascii=False))
    print(f"  wrote {OUT_SERIES} ({OUT_SERIES.stat().st_size:,} bytes)")

    h = signals["headline"]
    print(f"\n  HEADLINE:")
    print(f"    {CAPOLUOGO_NAME}, {h['zone_count_current']} zone correnti, orizzonte {h['anni_orizzonte']} anni")
    if h['cagr_avg_pct'] is not None:
        print(f"    CAGR medio: {h['cagr_avg_pct']:+.2f}% / anno")
    if h['yield_medio_pct'] is not None:
        print(f"    Yield lordo medio: {h['yield_medio_pct']:.2f}%")
    if h['prezzo_medio_attuale'] is not None:
        print(f"    Prezzo medio attuale: €{h['prezzo_medio_attuale']:,}/m²")
    print(f"\n  TOP 3 GROWTH:")
    for z in signals["top_growth"][:3]:
        print(f"    {z['zona']:4s} {(z.get('dizione') or '')[:50]:50s} CAGR {z['cagr_full']*100:+.2f}%")
    print(f"\n  TOP 3 DECLINE:")
    for z in signals["top_decline"][:3]:
        print(f"    {z['zona']:4s} {(z.get('dizione') or '')[:50]:50s} CAGR {z['cagr_full']*100:+.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
