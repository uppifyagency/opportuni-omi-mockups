#!/usr/bin/env python3
"""Firenze investor signal compute layer.

Fork di compute-modena-signals.py riconfigurato per provincia di Firenze:
capoluogo D612, ~55 comuni, GeoJSON dedicati. Stessa pipeline matematica.

Reads sagona-backfill/prezzi.csv and the GeoPOI zone polygons, computes:
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
  data/computed/firenze-signals.json     (frontend-ready, pre-validated)
  data/computed/firenze-zone-series.json (per-zone full timeseries)

Usage:
  python3 scripts/compute-modena-signals.py
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
ZONE_GEOJSON = ROOT / "data" / "geojson" / "firenze-zone-omi.geojson"
PROVINCE_GEOJSON = ROOT / "data" / "geojson" / "firenze-province-comuni.geojson"
OUT_DIR = ROOT / "data" / "computed"
OUT_SIGNALS = OUT_DIR / "firenze-signals.json"
OUT_SERIES = OUT_DIR / "firenze-zone-series.json"

# Default tipo for headline metrics — most liquid / interpretable for investors
HEADLINE_TIPO = "abitazioni_civili"
HEADLINE_OP = "acquisto"

# Minimum semestral datapoints required to treat a zone CAGR as a structural signal.
# Firenze's dataset is biennial 2014–2026 (7 expected datapoints). Zones with only
# 2 datapoints span 2024–2026 and produce noisy 2-year CAGRs that distort averages
# and top-N rankings — they're excluded from top_growth/top_decline and from
# headline.cagr_avg_pct.
MIN_CAGR_YEARS = 5


# ───────────────────────────────────────── load + clean ──
def load_csv() -> list[dict]:
    """Read CSV, coerce types, validate."""
    if not CSV_PATH.exists():
        sys.exit(f"ERROR: {CSV_PATH} not found. Run scripts/sagona-backfill.py first.")
    rows = []
    with CSV_PATH.open() as f:
        for r in csv.DictReader(f):
            # CRLF safety — strip every field
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
    """Compound annual growth rate. Returns None if invalid input."""
    if v0 is None or vN is None or v0 <= 0 or vN <= 0 or years <= 0:
        return None
    return (vN / v0) ** (1 / years) - 1


def linreg_slope(xs: list[float], ys: list[float]) -> float | None:
    """Ordinary least-squares slope. Returns None if degenerate."""
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
    """Year-over-year percentage changes — for volatility computation."""
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
    """Return {zona: {year: prezzo_medio}} for the given filter."""
    series: dict[str, dict[int, float]] = defaultdict(dict)
    for r in rows:
        if r["comune_catasto"] != comune or r["tipo_immobile"] != tipo or r["operazione"] != op:
            continue
        if r["prezzo_medio"] is None:
            continue
        series[r["zona"]][r["anno"]] = r["prezzo_medio"]
    return {z: dict(d) for z, d in series.items()}


def build_fascia_series(rows: list[dict], comune: str, tipo: str, op: str) -> dict[str, dict]:
    """Aggregate per fascia (B/C/D/E/R) — robust to zone renaming.
    For each (anno, fascia) take MEAN of all zone prezzo_medio in that fascia."""
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
    """Compute investor-relevant metrics for one zone."""
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

    # CAGR full-span (first → last)
    if len(years_acq) >= 2:
        v0 = ts_acq[years_acq[0]]
        vN = ts_acq[years_acq[-1]]
        n_years = years_acq[-1] - years_acq[0]
        metrics["cagr_full"] = safe_round(cagr(v0, vN, n_years), 4)
        metrics["delta_total_pct"] = safe_round((vN / v0 - 1) * 100, 1) if v0 else None
    else:
        metrics["cagr_full"] = None
        metrics["delta_total_pct"] = None

    # Recent trend (last 5 years) — investor short-term signal
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

    # Volatility = stddev of YoY % changes
    yoys = yoy_returns([ts_acq[y] for y in years_acq])
    if len(yoys) >= 3:
        metrics["volatility_pct"] = safe_round(statistics.stdev(yoys) * 100, 1)
    else:
        metrics["volatility_pct"] = None

    # Gross yield (annual rent / purchase price) — affitto is €/m²/mese
    if metrics["prezzo_acquisto_attuale"] and metrics["prezzo_affitto_attuale"]:
        rent_annual = metrics["prezzo_affitto_attuale"] * 12
        metrics["yield_lordo_pct"] = safe_round(rent_annual / metrics["prezzo_acquisto_attuale"] * 100, 2)
    else:
        metrics["yield_lordo_pct"] = None

    # Sparkline data (normalized 0-1 for compact rendering)
    # Both spark_values and spark_normalized MUST have the same length, or both empty.
    # Frontend renderers assume aligned arrays.
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
        # Insufficient history (< 3 data points): emit empty arrays for ALL spark fields
        # so frontend can safely skip rendering. NEVER let spark_values and spark_normalized
        # diverge in length — frontend's sparkSvg crashes on .toFixed of undefined.
        metrics["spark_years"] = []
        metrics["spark_values"] = []
        metrics["spark_normalized"] = []

    return metrics


def load_zone_metadata() -> dict[str, dict]:
    """Read zone OMI GeoJSON to enrich with dizione (quartiere name)."""
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
    """Per-comune province ranking — restricted to comuni inside Firenze's province
    boundary (joined via catasto code in the GeoJSON). The CSV occasionally
    includes catasto codes from neighbouring provinces; those would pollute the
    ranking with comuni that aren't actually in Firenze."""
    catasto_to_name = {f["properties"]["com_catasto_code"]: f["properties"]["name"]
                       for f in geoj["features"]}
    province_codes = set(catasto_to_name.keys())
    out = []
    # Fix Inv5: itera su TUTTE le province features per garantire 1:1 con geojson,
    # emette stub con null fields per comuni senza dati abitazioni_civili (es. comuni
    # alpini canavesi che hanno solo "ville" come tipologia OMI).
    for cat in sorted(province_codes):
        ts_acq = defaultdict(list)
        for r in rows:
            if r["comune_catasto"] != cat: continue
            if r["tipo_immobile"] != HEADLINE_TIPO: continue
            if r["operazione"] != HEADLINE_OP: continue
            if r["prezzo_medio"] is None: continue
            ts_acq[r["anno"]].append(r["prezzo_medio"])
        if not ts_acq:
            # Stub: comune in geojson ma senza dati per la tipologia headline
            out.append({
                "catasto": cat,
                "nome": catasto_to_name.get(cat, cat),
                "prezzo_attuale_medio": None,
                "prezzo_iniziale_medio": None,
                "delta_total_pct": None,
                "cagr": None,
                "anni_coperti": 0,
                "no_data": True,
            })
            continue
        years = sorted(ts_acq.keys())
        means = {y: sum(ts_acq[y]) / len(ts_acq[y]) for y in years}
        v0, vN = means[years[0]], means[years[-1]]
        c = cagr(v0, vN, years[-1] - years[0])
        out.append({
            "catasto": cat,
            "nome": catasto_to_name.get(cat, cat),
            "prezzo_attuale_medio": safe_round(vN, 0),
            "prezzo_iniziale_medio": safe_round(v0, 0),
            "delta_total_pct": safe_round((vN / v0 - 1) * 100, 1) if v0 else None,
            "cagr": safe_round(c, 4),
            "anni_coperti": years[-1] - years[0] + 1,
        })
    # Sort: CAGR DESC, null entries last (no_data → bottom della lista, non polluiscono bot3/top)
    return sorted(out, key=lambda x: (x["cagr"] is None, -(x["cagr"] or 0)))


# ───────────────────────────────────────── validation ──
def validate(signals: dict) -> None:
    """Sanity-check the computed JSON before writing."""
    zm = signals["zone_metrics"]
    assert len(zm) >= 15, f"too few zones: {len(zm)}"
    for z in zm:
        # CAGR sanity: -20% to +20% per year is the plausible range
        c = z.get("cagr_full")
        if c is not None:
            assert -0.20 <= c <= 0.20, f"crazy CAGR for {z['zona']}: {c}"
        # Yield sanity: 1% to 15%
        y = z.get("yield_lordo_pct")
        if y is not None:
            assert 0.5 <= y <= 20, f"crazy yield for {z['zona']}: {y}%"
        # Volatility: 0 to 50%
        v = z.get("volatility_pct")
        if v is not None:
            assert 0 <= v <= 50, f"crazy volatility for {z['zona']}: {v}%"

    headline = signals["headline"]
    assert headline["zone_count_total"] == len(zm)
    assert -10 <= headline["cagr_avg_pct"] <= 10
    assert 1 <= headline["yield_medio_pct"] <= 15

    pm = signals["province_ranking"]
    assert len(pm) >= 5
    for p in pm:
        assert p["delta_total_pct"] is None or -90 <= p["delta_total_pct"] <= 200
    print("  ✓ all asserts pass")


# ───────────────────────────────────────── main ──
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = load_csv()
    zone_meta = load_zone_metadata()

    print(f"\n=== Firenze ({HEADLINE_TIPO} · {HEADLINE_OP}) ===")
    ts_acq = build_zone_series(rows, "D612", HEADLINE_TIPO, "acquisto")
    ts_aff = build_zone_series(rows, "D612", HEADLINE_TIPO, "affitto")
    print(f"  zones with acquisto: {len(ts_acq)}")
    print(f"  zones with affitto:  {len(ts_aff)}")

    # Per-zone metrics
    zone_metrics_list = []
    for zona in sorted(ts_acq.keys()):
        m = zone_metrics(zona, ts_acq[zona], ts_aff.get(zona, {}))
        m.update(zone_meta.get(zona, {}))
        zone_metrics_list.append(m)

    # Sort: prefer current-nomenclature zones (those in zone_meta) at top, then by CAGR
    zone_metrics_list.sort(key=lambda x: (
        x.get("dizione") is None,                                  # current zones first
        -(x.get("cagr_full") or -999),                             # then by CAGR desc
    ))

    # Fascia series (stable axis across 20 years)
    fascia_acq = build_fascia_series(rows, "D612", HEADLINE_TIPO, "acquisto")
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

    # Headline cagr_avg_pct: MEDIA SULLE ZONE CORRENTI (con dizione), SENZA filtro
    # MIN_CAGR_YEARS. Allineato a compute-compass.py per coerenza signals↔compass
    # (richiesta da audit §17/§20 Inv1b). Il filtro MIN_CAGR_YEARS viene mantenuto SOLO
    # per top_growth/top_decline più sotto, perché le classifiche top-N devono evitare
    # zone con noise da 2-datapoint CAGR.
    cagrs = [z["cagr_full"] for z in zone_metrics_list
             if z["cagr_full"] is not None and z.get("dizione")]

    # Conteggio zone effettivamente affidabili (>= MIN_CAGR_YEARS) — esposto come metric
    # separato perché informa sul "rischio statistico" del cagr_avg_pct headline.
    cagrs_reliable_only = [z["cagr_full"] for z in zone_metrics_list
                            if z["cagr_full"] is not None and z.get("dizione")
                            and (z.get("anni_dati_acquisto") or 0) >= MIN_CAGR_YEARS]

    # FALLBACK fascia — usato SOLO quando ZERO zone correnti hanno cagr_full valorizzato
    # (caso estremo: provincia appena estratta senza storia). Per Firenze 2026 le
    # 24 zone correnti hanno tutte CAGR su 2024-2026 (debole ma esistente), quindi il
    # fallback non scatta. Mantengo la logica per robustezza future cities.
    cagr_source = "zone_correnti"
    if not cagrs:
        fascia_cagrs = []
        for f, ts in fascia_acq.items():
            if f == "R": continue
            yrs = sorted(ts.keys())
            if len(yrs) >= 5:
                v0, vN = ts[yrs[0]], ts[yrs[-1]]
                if v0 and vN and v0 > 0:
                    c = cagr(v0, vN, yrs[-1] - yrs[0])
                    if c is not None: fascia_cagrs.append(c)
        if fascia_cagrs:
            cagrs = fascia_cagrs
            cagr_source = "fascia_aggregata_BCDE"
            print(f"  ⚠ Fallback: zero zone con CAGR, uso media CAGR fasce B/C/D/E ({len(cagrs)} fasce, range {min(fascia_cagrs)*100:.2f}%..{max(fascia_cagrs)*100:.2f}%)")
    # Yield medio: SOLO zone correnti (con dizione). Le zone storiche hanno
    # prezzo_acquisto/affitto fermi al loro ultimo anno (es. 2012), il loro yield
    # non rappresenta il mercato di oggi. Includerle alterava la media: 4.99% con
    # tutte le 51 zone vs 5.28% sulle 20 zone correnti — quest'ultimo è il dato
    # che un investitore vuole leggere ("yield del mercato attuale").
    yields = [z["yield_lordo_pct"] for z in zone_metrics_list
              if z["yield_lordo_pct"] is not None and z.get("dizione")]
    current_prezzi = [z["prezzo_acquisto_attuale"] for z in zone_metrics_list
                      if z["prezzo_acquisto_attuale"] is not None and z.get("dizione")]

    # Province comparison
    print(f"\n=== Provincia ({HEADLINE_TIPO} · {HEADLINE_OP}) ===")
    province_geoj = json.loads(PROVINCE_GEOJSON.read_text())
    province_rank = province_metrics(rows, province_geoj)
    print(f"  comuni with data: {len(province_rank)}")

    # Build signals payload
    signals = {
        "metadata": {
            "generated_at": "2026-05-14",
            "headline_tipo": HEADLINE_TIPO,
            "headline_op": HEADLINE_OP,
            "source": "Sagona API + GeoPOI Agenzia Entrate (reverse-engineered)",
            "unit_conventions": {
                "note": "Fields with `_pct` suffix are already multiplied by 100 (percent). All other CAGR/slope/yield fields are fractional (multiply by 100 for percent).",
                "percent_fields": [
                    "headline.cagr_avg_pct",
                    "headline.yield_medio_pct",
                    "zone_metrics[].yield_lordo_pct",
                    "zone_metrics[].delta_total_pct",
                    "zone_metrics[].recent_slope_pct_per_year",
                    "zone_metrics[].volatility_pct",
                    "province_ranking[].yield_lordo_pct",
                    "fascia_metrics[].delta_total_pct",
                ],
                "fractional_fields": [
                    "zone_metrics[].cagr_full",
                    "fascia_metrics[].cagr",
                    "province_ranking[].cagr",
                ],
            },
            "filters": {
                "min_cagr_years": MIN_CAGR_YEARS,
                "applies_to": "top_growth, top_decline, headline.cagr_avg_pct",
            },
        },
        "headline": {
            "zone_count_total": len(zone_metrics_list),
            "zone_count_current": sum(1 for z in zone_metrics_list if z.get("dizione")),
            "zone_count_cagr": len(cagrs),
            # Quante zone correnti hanno CAGR statisticamente affidabile (>= MIN_CAGR_YEARS).
            # Per Firenze 2026 = 0 (rinumerazione totale 2024) → cagr_avg_pct viene dai
            # 2-datapoint, da leggersi come "trend recente" non "structural".
            "zone_count_cagr_reliable": len(cagrs_reliable_only),
            "cagr_avg_pct": safe_round(sum(cagrs) / len(cagrs) * 100, 2) if cagrs else None,
            "cagr_avg_pct_min_years": MIN_CAGR_YEARS,
            # Sorgente del cagr_avg_pct: "zone_correnti" (default, no filtro MIN) o
            # "fascia_aggregata_BCDE" (fallback estremo). Per allineamento signals↔compass
            # (audit Inv1b) entrambi usano zone_correnti senza filtro.
            "cagr_avg_pct_source": cagr_source,
            "yield_medio_pct": safe_round(sum(yields) / len(yields), 2) if yields else None,
            "prezzo_medio_attuale": safe_round(sum(current_prezzi) / len(current_prezzi), 0) if current_prezzi else None,
            # Due orizzonti diversi, esposti separati per disambiguare:
            #   - dataset (fascia-aggregato): copertura piena del CSV, parte dal 2005
            #   - zone correnti: finestra max delle zone con dizione (2014–2026)
            # Il vecchio campo `anni_orizzonte` confondeva i due — vedi DECISION_MEMO.
            "anni_orizzonte_dataset": max(z["ultimo_anno"] for z in zone_metrics_list) - min(z["primo_anno"] for z in zone_metrics_list if z["primo_anno"]),
            "anni_orizzonte_zone_correnti": (
                max((z["ultimo_anno"] for z in zone_metrics_list if z.get("dizione") and z.get("ultimo_anno")), default=0)
                - min((z["primo_anno"] for z in zone_metrics_list if z.get("dizione") and z.get("primo_anno")), default=0)
            ),
        },
        # Minimum data coverage for a CAGR to be treated as a structural signal.
        # Zones below this are unreliable (e.g. only 2 datapoints = 0-year window).
        "top_growth": sorted(
            [z for z in zone_metrics_list
             if z.get("dizione") and z["cagr_full"] is not None
             and (z.get("anni_dati_acquisto") or 0) >= MIN_CAGR_YEARS],
            key=lambda x: -x["cagr_full"])[:5],
        "top_decline": sorted(
            [z for z in zone_metrics_list
             if z.get("dizione") and z["cagr_full"] is not None
             and (z.get("anni_dati_acquisto") or 0) >= MIN_CAGR_YEARS],
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

    # Compact series file for charts
    series_out = {
        "fascia_series": fascia_acq,
        "zone_series_acquisto": ts_acq,
        "zone_series_affitto": ts_aff,
    }
    OUT_SERIES.write_text(json.dumps(series_out, ensure_ascii=False))
    print(f"  wrote {OUT_SERIES} ({OUT_SERIES.stat().st_size:,} bytes)")

    # Pretty-print the headline so we can spot-check
    h = signals["headline"]
    print(f"\n  HEADLINE:")
    print(f"    Firenze, {h['zone_count_current']} zone correnti")
    print(f"    Orizzonte dataset: {h['anni_orizzonte_dataset']} anni · Zone correnti: {h['anni_orizzonte_zone_correnti']} anni")
    print(f"    CAGR medio: {h['cagr_avg_pct']:+.2f}% / anno (su {h['zone_count_cagr_reliable']} zone ≥{MIN_CAGR_YEARS} datapoint)")
    print(f"    Yield lordo medio: {h['yield_medio_pct']:.2f}% (su zone correnti, {h['zone_count_current']} entry)")
    print(f"    Prezzo medio attuale: €{h['prezzo_medio_attuale']:,}/m²")
    print(f"\n  TOP 3 GROWTH:")
    for z in signals["top_growth"][:3]:
        print(f"    {z['zona']:4s} {z.get('dizione','')[:50]:50s} CAGR {z['cagr_full']*100:+.2f}%")
    print(f"\n  TOP 3 DECLINE:")
    for z in signals["top_decline"][:3]:
        print(f"    {z['zona']:4s} {z.get('dizione','')[:50]:50s} CAGR {z['cagr_full']*100:+.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
