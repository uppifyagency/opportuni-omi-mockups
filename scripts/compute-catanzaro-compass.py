#!/usr/bin/env python3
"""Compass compute layer per provincia di Catanzaro — fork di compute-compass.py.

Stessa pipeline: per ogni tipologia chiave (5 tipi) computa:
  - Metriche per zona Catanzaro città (CAGR, yield, vol, momentum, level)
  - Metriche per ogni comune della provincia (80 comuni)
  - Score composito 0-100 (pesi tunabili nel frontend)
  - Verdict BUY / WATCH / AVOID
  - Anomaly flag (zona divergente >1.5σ dalla fascia)
  - Comparable zones (k-NN su 4 feature)

Output:
  data/computed/catanzaro-compass.json — by_tipologia con 5 tipologie

Validato con asserts allentati (provincia con copertura parziale).

Usage:
  python3 scripts/compute-catanzaro-compass.py
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
OUT_FILE = OUT_DIR / "catanzaro-compass.json"

CAPOLUOGO_CATASTO = "C352"
CAPOLUOGO_NAME = "Catanzaro"

TIPOLOGIE_HEADLINE = [
    "abitazioni_civili",
    "abitazioni_signorili",
    "negozi",
    "uffici",
    "magazzini",
]

# FIX P4 + P9: single source of truth per pesi/soglie/penalty.
# Allineati al caption UI (catanzaro-C-compass.html): 35/30/15/15/5, soglia 70, penalty -10.
# Il JS può ricomputare on-the-fly (slider), ma il default deve coincidere.
WEIGHTS_DEFAULT = {"growth": 0.35, "yield": 0.30, "stability": 0.15,
                   "momentum": 0.15, "level": 0.05}
# FIX threshold-scientific 2026-05-17: Jenks natural breaks (k=3).
# Vedi docs/audit/THRESHOLD-SCIENTIFIC-ANALYSIS.md per il confronto fra 6 metodi.
import sys as _sys
from pathlib import Path as _P
_sys.path.insert(0, str(_P(__file__).parent))
from _threshold_lib import calibrate_thresholds  # noqa: E402
CAGR_NEGATIVE_PENALTY = 10  # FIX P4: ora applicata anche in Python (allineata a JS)


# ───────────────────────────────────────── primitives ──
def cagr(v0, vN, years):
    if v0 is None or vN is None or v0 <= 0 or vN <= 0 or years <= 0:
        return None
    return (vN / v0) ** (1 / years) - 1


def linreg_slope(xs, ys):
    n = len(xs)
    if n < 3 or len(ys) != n:
        return None
    xm = sum(xs) / n; ym = sum(ys) / n
    num = sum((x - xm) * (y - ym) for x, y in zip(xs, ys))
    den = sum((x - xm) ** 2 for x in xs)
    return num / den if den else None


def yoy_returns(values):
    return [(b - a) / a for a, b in zip(values, values[1:]) if a and a > 0 and b is not None]


def safe_round(x, d=2):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(x, d)


def norm(v, vmin, vmax):
    if v is None or vmax == vmin:
        return None
    return max(0.0, min(1.0, (v - vmin) / (vmax - vmin)))


def zscore(v, mean, std):
    if v is None or std is None or std == 0:
        return None
    return (v - mean) / std


# ───────────────────────────────────────── load + clean ──
def load_csv():
    rows = []
    with CSV_PATH.open() as f:
        for r in csv.DictReader(f):
            r = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in r.items()}
            r["anno"] = int(r["anno"])
            for k in ("prezzo_min", "prezzo_max", "prezzo_medio"):
                v = r.get(k, "")
                r[k] = float(v) if v not in ("", None) else None
            rows.append(r)
    return rows


def load_zone_meta():
    if not ZONE_GEOJSON.exists():
        return {}
    g = json.loads(ZONE_GEOJSON.read_text())
    return {f["properties"]["zona"]: f["properties"] for f in g["features"]}


def load_province_meta():
    g = json.loads(PROVINCE_GEOJSON.read_text())
    return {f["properties"]["com_catasto_code"]: f["properties"]["name"]
            for f in g["features"]}


# ───────────────────────────────────────── zone metrics ──
def build_zone_series(rows, comune, tipo, op):
    s = defaultdict(dict)
    for r in rows:
        if (r["comune_catasto"] != comune or r["tipo_immobile"] != tipo
                or r["operazione"] != op or r["prezzo_medio"] is None):
            continue
        s[r["zona"]][r["anno"]] = r["prezzo_medio"]
    return {z: dict(d) for z, d in s.items()}


def zone_metrics(zona, ts_acq, ts_aff):
    years_acq = sorted(ts_acq.keys())
    years_aff = sorted(ts_aff.keys())
    m = {"zona": zona, "anni": len(years_acq)}
    if not years_acq:
        return m

    v0, vN = ts_acq[years_acq[0]], ts_acq[years_acq[-1]]
    n_y = years_acq[-1] - years_acq[0]
    m["prezzo_acquisto"] = vN
    m["prezzo_affitto"] = ts_aff.get(max(years_aff)) if years_aff else None
    m["cagr"] = safe_round(cagr(v0, vN, n_y), 4) if n_y > 0 else None
    m["delta_pct"] = safe_round((vN / v0 - 1) * 100, 1) if v0 else None

    recent_y = years_acq[-5:] if len(years_acq) >= 5 else years_acq
    recent_v = [ts_acq[y] for y in recent_y]
    s = linreg_slope([float(y) for y in recent_y], recent_v)
    m["recent_slope_eur"] = safe_round(s, 1) if s else None
    m["recent_slope_pct"] = safe_round(s / recent_v[0] * 100, 3) if s and recent_v[0] else None

    yoys = yoy_returns([ts_acq[y] for y in years_acq])
    m["volatility_pct"] = safe_round(statistics.stdev(yoys) * 100, 1) if len(yoys) >= 3 else None

    if m["prezzo_acquisto"] and m["prezzo_affitto"]:
        m["yield_lordo_pct"] = safe_round(m["prezzo_affitto"] * 12 / m["prezzo_acquisto"] * 100, 2)
    else:
        m["yield_lordo_pct"] = None

    vals = [ts_acq[y] for y in years_acq]
    if len(vals) >= 3:
        vmin, vmax = min(vals), max(vals)
        d = vmax - vmin
        m["spark_years"] = years_acq
        m["spark_values"] = vals
        m["spark_norm"] = [safe_round((v - vmin) / d, 3) if d else 0.5 for v in vals]
    else:
        m["spark_years"] = years_acq
        m["spark_values"] = vals
        m["spark_norm"] = []

    return m


# ───────────────────────────────────────── score & signals ──
def compute_score(z, pool_stats):
    growth = norm(z.get("cagr"), pool_stats["cagr_min"], pool_stats["cagr_max"])
    yld = norm(z.get("yield_lordo_pct"), pool_stats["yield_min"], pool_stats["yield_max"])
    vol = norm(z.get("volatility_pct"), pool_stats["vol_min"], pool_stats["vol_max"])
    stability = 1 - vol if vol is not None else None
    momentum = None
    if z.get("recent_slope_pct") is not None and z.get("cagr") is not None:
        momentum = 1.0 if z["recent_slope_pct"] / 100 > z["cagr"] * 1.5 else 0.0
    level = norm(z.get("prezzo_acquisto"), pool_stats["prezzo_min"], pool_stats["prezzo_max"])
    level_inv = 1 - level if level is not None else None

    weights = WEIGHTS_DEFAULT  # FIX P9: pesi allineati a caption UI
    parts = []
    if growth is not None: parts.append(weights["growth"] * growth)
    if yld is not None: parts.append(weights["yield"] * yld)
    if stability is not None: parts.append(weights["stability"] * stability)
    if momentum is not None: parts.append(weights["momentum"] * momentum)
    if level_inv is not None: parts.append(weights["level"] * level_inv)
    if not parts:
        return None
    total_w = sum(weights[k] for k, v in zip(
        ["growth", "yield", "stability", "momentum", "level"],
        [growth, yld, stability, momentum, level_inv]) if v is not None)
    score = sum(parts) / total_w * 100 if total_w else None
    # FIX P4: penalty -10 se CAGR<0 (allineata a JS recomputeScore)
    if score is not None and z.get("cagr") is not None and z["cagr"] < 0:
        score = max(0, score - CAGR_NEGATIVE_PENALTY)
    return {
        "score": safe_round(score, 1),
        "components": {
            "growth":    safe_round(growth, 3),
            "yield":     safe_round(yld, 3),
            "stability": safe_round(stability, 3),
            "momentum":  safe_round(momentum, 3),
            "level":     safe_round(level_inv, 3),
        },
    }


def verdict_from_score(score, buy_t, avoid_t):
    """Soglie data-driven Jenks."""
    if score is None:
        return None
    if score >= buy_t: return "BUY"
    if score < avoid_t: return "AVOID"
    return "WATCH"


def detect_anomaly(z, fascia_stats):
    f = z.get("fascia")
    if not f or f not in fascia_stats:
        return None
    fs = fascia_stats[f]
    cagr_z = zscore(z.get("cagr"), fs.get("cagr_mean"), fs.get("cagr_std"))
    yield_z = zscore(z.get("yield_lordo_pct"), fs.get("yield_mean"), fs.get("yield_std"))
    flag = None
    if cagr_z is not None and abs(cagr_z) >= 1.5: flag = "CAGR_OUTLIER"
    if yield_z is not None and abs(yield_z) >= 1.5: flag = "YIELD_OUTLIER" if flag is None else "BOTH"
    return {
        "flag": flag,
        "cagr_z": safe_round(cagr_z, 2),
        "yield_z": safe_round(yield_z, 2),
    }


def find_comparables(target, pool, k=4):
    feats = []
    for z in pool:
        if z["zona"] == target["zona"]:
            continue
        v = [z.get("cagr"), z.get("yield_lordo_pct"),
             z.get("volatility_pct"), z.get("prezzo_acquisto")]
        if any(x is None for x in v):
            continue
        feats.append((z["zona"], v))
    tv = [target.get("cagr"), target.get("yield_lordo_pct"),
          target.get("volatility_pct"), target.get("prezzo_acquisto")]
    if any(x is None for x in tv):
        return []
    all_v = [tv] + [v for _, v in feats]
    mins = [min(col) for col in zip(*all_v)]
    maxs = [max(col) for col in zip(*all_v)]
    def normvec(v): return [(v[i] - mins[i]) / (maxs[i] - mins[i]) if maxs[i] > mins[i] else 0.5 for i in range(len(v))]
    tn = normvec(tv)
    dists = []
    for name, v in feats:
        vn = normvec(v)
        d = math.sqrt(sum((tn[i] - vn[i]) ** 2 for i in range(len(tn))))
        dists.append((name, safe_round(d, 3)))
    dists.sort(key=lambda x: x[1])
    return [{"zona": n, "distance": d} for n, d in dists[:k]]


# ───────────────────────────────────────── per-tipologia pipeline ──
def compute_tipologia(rows, tipo, zone_meta, prov_meta):
    ts_acq = build_zone_series(rows, CAPOLUOGO_CATASTO, tipo, "acquisto")
    ts_aff = build_zone_series(rows, CAPOLUOGO_CATASTO, tipo, "affitto")

    zone_list = []
    for zona in sorted(ts_acq.keys()):
        m = zone_metrics(zona, ts_acq[zona], ts_aff.get(zona, {}))
        meta = zone_meta.get(zona, {})
        m["fascia"] = meta.get("fascia")
        m["dizione"] = meta.get("dizione")
        m["link_zona"] = meta.get("link_zona")
        zone_list.append(m)

    prov_list = []
    for cat, name in prov_meta.items():
        ts_acq_com = defaultdict(list)
        ts_aff_com = defaultdict(list)
        for r in rows:
            if r["comune_catasto"] != cat or r["tipo_immobile"] != tipo:
                continue
            if r["prezzo_medio"] is None:
                continue
            if r["operazione"] == "acquisto":
                ts_acq_com[r["anno"]].append(r["prezzo_medio"])
            else:
                ts_aff_com[r["anno"]].append(r["prezzo_medio"])
        if not ts_acq_com:
            continue
        years = sorted(ts_acq_com.keys())
        means_acq = {y: sum(ts_acq_com[y]) / len(ts_acq_com[y]) for y in years}
        means_aff = {y: sum(ts_aff_com[y]) / len(ts_aff_com[y])
                     for y in ts_aff_com if ts_aff_com[y]}
        v0, vN = means_acq[years[0]], means_acq[years[-1]]
        years_aff = sorted(means_aff.keys()) if means_aff else []
        ultimo_anno_dati = years[-1]
        is_stale = ultimo_anno_dati < 2020
        m = {
            "catasto": cat,
            "zona": cat,
            "nome": name,
            "anni": years[-1] - years[0] + 1,
            "ultimo_anno_dati": ultimo_anno_dati,
            "stale": is_stale,
            "prezzo_acquisto": safe_round(vN, 0),
            "prezzo_affitto": safe_round(means_aff[max(years_aff)], 1) if years_aff else None,
            "cagr": safe_round(cagr(v0, vN, years[-1] - years[0]), 4),
            "delta_pct": safe_round((vN / v0 - 1) * 100, 1) if v0 else None,
        }
        recent_y = years[-5:] if len(years) >= 5 else years
        recent_v = [means_acq[y] for y in recent_y]
        s = linreg_slope([float(y) for y in recent_y], recent_v)
        m["recent_slope_pct"] = safe_round(s / recent_v[0] * 100, 3) if s and recent_v[0] else None
        yoys = yoy_returns([means_acq[y] for y in years])
        m["volatility_pct"] = safe_round(statistics.stdev(yoys) * 100, 1) if len(yoys) >= 3 else None
        if m["prezzo_acquisto"] and m["prezzo_affitto"]:
            m["yield_lordo_pct"] = safe_round(m["prezzo_affitto"] * 12 / m["prezzo_acquisto"] * 100, 2)
        else:
            m["yield_lordo_pct"] = None
        vals = [means_acq[y] for y in years]
        if len(vals) >= 3:
            vmin, vmax = min(vals), max(vals)
            d = vmax - vmin
            m["spark_years"] = years
            m["spark_values"] = vals
            m["spark_norm"] = [safe_round((v - vmin) / d, 3) if d else 0.5 for v in vals]
        prov_list.append(m)

    current_zones = [z for z in zone_list if z.get("dizione")]
    pool = current_zones + prov_list

    def stats(key):
        vs = [z[key] for z in pool if z.get(key) is not None]
        return (min(vs), max(vs), statistics.mean(vs), statistics.stdev(vs) if len(vs) > 1 else 0) if vs else (None, None, None, None)

    cagr_min, cagr_max, cagr_mean, cagr_std = stats("cagr")
    y_min, y_max, y_mean, y_std = stats("yield_lordo_pct")
    v_min, v_max, _, _ = stats("volatility_pct")
    p_min, p_max, _, _ = stats("prezzo_acquisto")
    pool_stats = {
        "cagr_min": cagr_min, "cagr_max": cagr_max,
        "yield_min": y_min, "yield_max": y_max,
        "vol_min": v_min, "vol_max": v_max,
        "prezzo_min": p_min, "prezzo_max": p_max,
    }

    fascia_stats = {}
    fasce = {z["fascia"] for z in current_zones if z.get("fascia")}
    for f in fasce:
        zf = [z for z in current_zones if z.get("fascia") == f]
        cagrs = [z["cagr"] for z in zf if z.get("cagr") is not None]
        yields = [z["yield_lordo_pct"] for z in zf if z.get("yield_lordo_pct") is not None]
        fascia_stats[f] = {
            "cagr_mean": statistics.mean(cagrs) if cagrs else None,
            "cagr_std": statistics.stdev(cagrs) if len(cagrs) > 1 else 0,
            "yield_mean": statistics.mean(yields) if yields else None,
            "yield_std": statistics.stdev(yields) if len(yields) > 1 else 0,
        }

    # Phase 1: compute scores
    for z in zone_list + prov_list:
        sc = compute_score(z, pool_stats)
        if sc:
            z["score"] = sc["score"]
            z["score_components"] = sc["components"]
        else:
            z["score"] = None
            z["score_components"] = None
            z["verdict"] = None

    # Phase 2: calibra soglie Jenks-based — FIX threshold-scientific 2026-05-17
    pool_for_thr = [z["score"] for z in current_zones + prov_list if z.get("score") is not None]
    calib = calibrate_thresholds(pool_for_thr)
    buy_t = calib["buy_threshold"]
    avoid_t = calib["avoid_threshold"]

    # Phase 3: verdict
    for z in zone_list + prov_list:
        if z.get("score") is not None:
            z["verdict"] = verdict_from_score(z["score"], buy_t, avoid_t)

    # Phase 4: tag EMERGING (potenziale crescita) — FIX 2026-05-17
    pool_prices = [z.get("prezzo_acquisto") for z in current_zones + prov_list if z.get("prezzo_acquisto") is not None]
    import numpy as _np2
    p50_score = float(_np2.percentile(pool_for_thr, 50)) if pool_for_thr else 50.0
    median_price = float(_np2.median(pool_prices)) if pool_prices else None
    for z in zone_list + prov_list:
        z["emerging"] = False
        if z.get("score") is None or z.get("cagr") is None:
            continue
        if z["score"] < p50_score or z["score"] >= buy_t:
            continue
        if z["cagr"] <= 0:
            continue
        if median_price is not None and z.get("prezzo_acquisto") is not None and z["prezzo_acquisto"] >= median_price:
            continue
        z["emerging"] = True

    for z in current_zones:
        anom = detect_anomaly(z, fascia_stats)
        if anom and anom["flag"]:
            z["anomaly"] = anom

    for z in current_zones:
        z["comparables"] = find_comparables(z, current_zones, k=4)

    cagrs = [z["cagr"] for z in current_zones if z.get("cagr") is not None]
    yields = [z["yield_lordo_pct"] for z in current_zones if z.get("yield_lordo_pct") is not None]
    prices = [z["prezzo_acquisto"] for z in current_zones if z.get("prezzo_acquisto") is not None]
    years_all = [y for z in current_zones for y in z.get("spark_years", [])]

    fascia_series = {}
    bucket = defaultdict(list)
    for r in rows:
        if r["comune_catasto"] != CAPOLUOGO_CATASTO or r["tipo_immobile"] != tipo or r["operazione"] != "acquisto":
            continue
        if r["prezzo_medio"] is None or not r["fascia"]:
            continue
        bucket[(r["anno"], r["fascia"])].append(r["prezzo_medio"])
    fascia_ts = defaultdict(dict)
    for (anno, fascia), vs in bucket.items():
        fascia_ts[fascia][anno] = sum(vs) / len(vs)
    for fascia, ts in fascia_ts.items():
        years = sorted(ts.keys())
        if len(years) < 2: continue
        v0, vN = ts[years[0]], ts[years[-1]]
        fascia_series[fascia] = {
            "primo_anno": years[0],
            "ultimo_anno": years[-1],
            "prezzo_iniziale": safe_round(v0, 0),
            "prezzo_attuale": safe_round(vN, 0),
            "cagr": safe_round(cagr(v0, vN, years[-1] - years[0]), 4),
            "series": {str(y): safe_round(ts[y], 0) for y in years},
        }

    zone_list.sort(key=lambda x: (x.get("dizione") is None, -(x.get("cagr") or -999)))
    # Province ranking: stale comuni in fondo, fresh ordinati per CAGR desc
    prov_list.sort(key=lambda x: (x.get("stale", False), -(x.get("cagr") or -999)))

    cur = [z for z in zone_list if z.get("dizione") and z.get("cagr") is not None]
    # Top BUY/AVOID/WATCH: escludi comuni stale dal pool (le zone capoluogo non hanno freshness issue: sono GeoPOI 20252)
    fresh_prov = [p for p in prov_list if not p.get("stale", False)]
    pool_for_top = cur + fresh_prov
    top_buy = sorted([z for z in pool_for_top if z.get("score") is not None],
                     key=lambda x: -x["score"])[:6]
    top_avoid = sorted([z for z in pool_for_top if z.get("score") is not None],
                       key=lambda x: x["score"])[:6]
    top_watch = sorted([z for z in pool_for_top
                        if z.get("verdict") == "WATCH"
                        and z.get("recent_slope_pct") is not None
                        and z.get("cagr") is not None
                        and z["recent_slope_pct"] / 100 > z["cagr"] * 1.5],
                       key=lambda x: -(x.get("recent_slope_pct") or -999))[:6]
    top_emerging = sorted([z for z in pool_for_top if z.get("emerging")],
                          key=lambda x: -(x.get("cagr") or 0))[:6]
    anomalies = [z for z in cur if z.get("anomaly")]

    return {
        "tipo": tipo,
        "headline": {
            "zone_count": len(cur),
            "zone_total": len(zone_list),
            "comune_count": len(prov_list),
            "cagr_avg_pct": safe_round(statistics.mean(cagrs) * 100, 2) if cagrs else None,
            "yield_avg_pct": safe_round(statistics.mean(yields), 2) if yields else None,
            "prezzo_avg": safe_round(statistics.mean(prices), 0) if prices else None,
            "anni_orizzonte": (max(years_all) - min(years_all)) if years_all else None,
            "n_buy_zone": sum(1 for z in cur if z.get("verdict") == "BUY"),
            "n_avoid_zone": sum(1 for z in cur if z.get("verdict") == "AVOID"),
            "n_buy_provincia": sum(1 for z in prov_list if z.get("verdict") == "BUY"),
            "n_avoid_provincia": sum(1 for z in prov_list if z.get("verdict") == "AVOID"),
            "n_emerging_zone": sum(1 for z in cur if z.get("emerging")),
            "n_emerging_provincia": sum(1 for z in prov_list if z.get("emerging")),
            "buy_threshold_computed": safe_round(buy_t, 2),
            "avoid_threshold_computed": safe_round(avoid_t, 2),
            "threshold_method": calib["method_used"],
            "threshold_calibration": calib,
        },
        "pool_stats": pool_stats,
        "fascia_stats": fascia_stats,
        "fascia_series": fascia_series,
        "zone_metrics": zone_list,
        "province_ranking": prov_list,
        "top_buy": top_buy,
        "top_avoid": top_avoid,
        "top_watch": top_watch,
        "top_emerging": top_emerging,
        "anomalies": anomalies,
    }


# ───────────────────────────────────────── validate ──
def validate(payload):
    assert "by_tipologia" in payload
    for tipo, data in payload["by_tipologia"].items():
        h = data["headline"]
        # Asserts allentati per Catanzaro — provincia con copertura parziale
        if h["cagr_avg_pct"] is not None:
            assert -15 <= h["cagr_avg_pct"] <= 15, f"{tipo}: CAGR {h['cagr_avg_pct']}"
        if h["yield_avg_pct"] is not None:
            assert 0.5 <= h["yield_avg_pct"] <= 25, f"{tipo}: yield {h['yield_avg_pct']}"
        for z in data["zone_metrics"]:
            if z.get("cagr") is not None:
                assert -0.40 <= z["cagr"] <= 0.40, f"{tipo} {z['zona']}: CAGR {z['cagr']}"
            if z.get("score") is not None:
                assert 0 <= z["score"] <= 100, f"{tipo} {z['zona']}: score {z['score']}"
    print("  ✓ all asserts pass")


# ───────────────────────────────────────── main ──
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  loading {CSV_PATH.name}")
    rows = load_csv()
    print(f"  loaded {len(rows):,} rows")

    zone_meta = load_zone_meta()
    prov_meta = load_province_meta()

    by_tipologia = {}
    for tipo in TIPOLOGIE_HEADLINE:
        print(f"\n=== {tipo} ===")
        try:
            data = compute_tipologia(rows, tipo, zone_meta, prov_meta)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue
        h = data["headline"]
        cagr_str = f"{h['cagr_avg_pct']:+.2f}%" if h['cagr_avg_pct'] is not None else 'n/d'
        yield_str = f"{h['yield_avg_pct']:.2f}%" if h['yield_avg_pct'] is not None else 'n/d'
        print(f"  zones: {h['zone_count']}/{h['zone_total']} current "
              f"| comuni: {h['comune_count']} "
              f"| CAGR avg: {cagr_str} "
              f"| yield avg: {yield_str}")
        print(f"  BUY zone: {h['n_buy_zone']}, AVOID zone: {h['n_avoid_zone']}")
        print(f"  BUY prov: {h['n_buy_provincia']}, AVOID prov: {h['n_avoid_provincia']}")
        by_tipologia[tipo] = data

    payload = {
        "metadata": {
            "generated_at": "2026-05-14",
            "capoluogo": CAPOLUOGO_NAME,
            "capoluogo_catasto": CAPOLUOGO_CATASTO,
            "source": "Sagona API + GeoPOI Agenzia Entrate",
            "tipologie": TIPOLOGIE_HEADLINE,
            "default_tipo": "abitazioni_civili",
            # FIX P4 + P9: single source of truth — JS DEVE leggere da qui
            "scoring": {
                "weights_default": WEIGHTS_DEFAULT,
                "threshold_method_primary": "jenks_natural_breaks_k3",
                "threshold_method_reason": "k-means 1D ottimo, standard GIS per dati immobiliari",
                "threshold_methods_compared": ["jenks_k3", "otsu", "gmm_k3", "p85", "p85_bootstrap"],
                "buy_threshold_fallback": 60.0,
                "avoid_threshold_fallback": 35.0,
                "cagr_negative_penalty": CAGR_NEGATIVE_PENALTY,
                "note": "Score formula: sum(weights[k]*c[k]) / sum(weights[k] dove c[k] is not None) * 100. Se cagr<0, sottrai CAGR_NEGATIVE_PENALTY (clamped 0-100).",
            },
            # FIX P8: documentazione esplicita del pool eterogeneo
            "pool_composition": {
                "current_zones_count": "zone OMI capoluogo con dizione valorizzata",
                "province_ranking_count": "comuni provincia con CAGR>=2 anni dati",
                "warning": "Pool combina zone OMI capoluogo + comuni provincia nella stessa normalizzazione min-max. Score relativi: una zona BUY a Catanzaro NON è automaticamente paragonabile a una BUY a Modena.",
            },
        },
        "by_tipologia": by_tipologia,
    }

    validate(payload)

    OUT_FILE.write_text(json.dumps(payload, ensure_ascii=False))
    print(f"\n  wrote {OUT_FILE} ({OUT_FILE.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
