#!/usr/bin/env python3
"""compute-volume-signals.py — join volumi storici (PDF AdE) con segnali esistenti.

Output:
  data/computed/modena-volume-signals.json
  {
    "metadata": {...},
    "zone_volume_metrics": [  # 19 zone OLD code (= storico) join con zone NEW via mapping
      {
        "zona_old": "D29",
        "zona_new": ["D29"],
        "denominazione": "...",
        "rel": "direct|renamed|split|merged",
        # serie temporale NTN
        "ntn_series": [{"year": 2018, "ntn": 123, "imi_pct": 2.5, ...}, ...],
        # metrics
        "ntn_first": 100, "ntn_last": 145,
        "ntn_cagr_pct": 5.2,           # CAGR del volume scambi
        "ntn_delta_pct": 45.0,         # variazione totale
        "imi_avg_pct": 2.8,            # IMI medio (liquidità struct.)
        "imi_last_pct": 3.1,
        "imi_trend_slope": +0.05,      # regressione lineare IMI vs anno
        # volume momentum tag (4 livelli)
        "momentum_tag": "rocket|growing|stable|cooling|frozen",
        # quadrant prezzo×volume
        "price_volume_quadrant": "Q1|Q2|Q3|Q4",
        # liquidity score 0-100
        "liquidity_score": 78
      }, ...
    ],
    "macroaree_volume_metrics": [...],  # 8 macroaree provincia
    "totale_provincia_metrics": {...},
    "summary": {...}
  }

LOGICA:
  - momentum_tag basato su ntn_cagr_pct + imi_trend:
      🚀 rocket   : cagr > +8%/yr AND imi crescente
      ↗  growing  : cagr > +2%/yr
      →  stable   : -2% ≤ cagr ≤ +2%
      ↘  cooling  : -8% ≤ cagr < -2%
      💀 frozen   : cagr < -8% OR imi_last < 1.0%

  - price_volume_quadrant (vs mediane provincia):
      Q1 = HOT     : prezzo>med, volume>med  (mercato caldo, premium liquido)
      Q2 = OVERPRICED: prezzo>med, volume<med (premium illiquido, watch out)
      Q3 = OPPORTUNITY: prezzo<med, volume>med (cheap & active, BUY signal)
      Q4 = DEAD     : prezzo<med, volume<med (cheap & illiquid, RISK)

  - liquidity_score = 50 + 25*z(imi_last) + 15*z(ntn_cagr) + 10*z(ntn_recent_slope)
    clamped [0,100]; z = z-score vs distribuzione zone.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
from statistics import mean, median, stdev

ROOT = Path(__file__).resolve().parent.parent
VOL_JSON = ROOT / "data" / "volumi" / "modena-volumi-timeseries.json"
MAP_JSON = ROOT / "data" / "volumi" / "zone-mapping-old-new.json"
SIG_JSON = ROOT / "data" / "computed" / "modena-signals.json"
OUT_JSON = ROOT / "data" / "computed" / "modena-volume-signals.json"


def linreg_slope(xs, ys):
    """Slope di regressione lineare semplice (least-squares)."""
    if len(xs) < 2 or len(set(xs)) < 2: return 0.0
    n = len(xs)
    mx, my = mean(xs), mean(ys)
    num = sum((x-mx)*(y-my) for x,y in zip(xs,ys))
    den = sum((x-mx)**2 for x in xs)
    return num/den if den != 0 else 0.0


def cagr(first, last, years):
    """Compound Annual Growth Rate. years = numero di periodi (last - first)."""
    if first is None or last is None or first <= 0 or years <= 0: return None
    try:
        return ((last/first) ** (1.0/years) - 1.0) * 100.0
    except (ValueError, ZeroDivisionError):
        return None


def momentum_tag(cagr_pct, imi_last_pct, imi_trend_slope):
    if cagr_pct is None: return "unknown"
    if imi_last_pct is not None and imi_last_pct < 1.0: return "frozen"
    if cagr_pct < -8: return "frozen"
    if cagr_pct < -2: return "cooling"
    if cagr_pct <= 2: return "stable"
    if cagr_pct > 8 and imi_trend_slope and imi_trend_slope > 0: return "rocket"
    return "growing"


def z_score(value, mean_v, sd_v):
    if value is None or sd_v == 0 or sd_v is None: return 0.0
    return (value - mean_v) / sd_v


def main():
    vol = json.loads(VOL_JSON.read_text())
    zmap = {m['old']: m for m in json.loads(MAP_JSON.read_text())['mapping']}
    sig = json.loads(SIG_JSON.read_text())
    sig_by_zona = {z['zona']: z for z in sig['zone_metrics']}

    # === ZONE: 19 zone OLD code, ognuna con time series 2018-2023
    zone_series = vol['zone_series']
    # Group by zona
    by_zona = {}
    for r in zone_series:
        by_zona.setdefault(r['zona'], []).append(r)

    zone_metrics = []
    for zona_old, rows in by_zona.items():
        rows = sorted(rows, key=lambda r: r['year'])
        # FIX: rimuovi trailing zero NTN (phantom da zone-rename events come E7→E11).
        # Un NTN=0 nell'ULTIMO anno con prev > 5 è quasi sempre artefatto di codice deprecato.
        while rows and len(rows) >= 2 and rows[-1].get('ntn') in (0, 0.0, None) and (rows[-2].get('ntn') or 0) > 5:
            rows.pop()
        years = [r['year'] for r in rows]
        ntns = [r.get('ntn') for r in rows]
        imis = [r.get('imi_pct') for r in rows]
        quots = [r.get('quotazione_eur_mq') for r in rows]

        ntn_first = next((v for v in ntns if v is not None), None)
        ntn_last = next((v for v in reversed(ntns) if v is not None), None)
        valid_years = [y for y,v in zip(years,ntns) if v is not None]
        ntn_cagr = None
        if len(valid_years) >= 2:
            years_span = valid_years[-1] - valid_years[0]
            ntn_cagr = cagr(ntn_first, ntn_last, years_span)
        ntn_delta = None
        if ntn_first and ntn_last:
            ntn_delta = (ntn_last/ntn_first - 1.0) * 100.0

        imi_valid = [v for v in imis if v is not None]
        imi_avg = mean(imi_valid) if imi_valid else None
        imi_last = next((v for v in reversed(imis) if v is not None), None)
        imi_first = next((v for v in imis if v is not None), None)
        # linreg slope imi vs year
        imi_xs = [y for y,v in zip(years,imis) if v is not None]
        imi_ys = [v for v in imis if v is not None]
        imi_slope = linreg_slope(imi_xs, imi_ys) if len(imi_xs) >= 2 else 0.0

        # recent slope NTN (last 3 years if available)
        ntn_recent = [(y,v) for y,v in zip(years, ntns) if v is not None][-3:]
        ntn_slope = linreg_slope([p[0] for p in ntn_recent], [p[1] for p in ntn_recent]) if len(ntn_recent) >= 2 else 0.0

        # variabilità (CV)
        ntn_cv = (stdev([v for v in ntns if v is not None]) / mean([v for v in ntns if v is not None]) * 100.0) if len([v for v in ntns if v is not None]) >= 2 else None

        zmap_entry = zmap.get(zona_old, {})
        zone_metrics.append({
            "zona_old": zona_old,
            "zona_new": zmap_entry.get('new', [zona_old]),
            "denominazione": rows[-1].get('denominazione', ''),
            "rel": zmap_entry.get('rel', 'unknown'),
            "mapping_notes": zmap_entry.get('notes', ''),
            "years_covered": valid_years,
            "ntn_series": [
                {"year": r['year'], "ntn": r.get('ntn'), "ntn_var_pct": r.get('ntn_var_pct'),
                 "imi_pct": r.get('imi_pct'), "quotazione_eur_mq": r.get('quotazione_eur_mq'),
                 "quotazione_var_pct": r.get('quotazione_var_pct')}
                for r in rows
            ],
            "ntn_first": ntn_first, "ntn_last": ntn_last,
            "ntn_cagr_pct": round(ntn_cagr, 2) if ntn_cagr is not None else None,
            "ntn_delta_pct": round(ntn_delta, 2) if ntn_delta is not None else None,
            "ntn_recent_slope": round(ntn_slope, 2),
            "ntn_volatility_cv_pct": round(ntn_cv, 1) if ntn_cv is not None else None,
            "imi_avg_pct": round(imi_avg, 2) if imi_avg is not None else None,
            "imi_first_pct": round(imi_first, 2) if imi_first is not None else None,
            "imi_last_pct": round(imi_last, 2) if imi_last is not None else None,
            "imi_trend_slope": round(imi_slope, 3),
            "momentum_tag": momentum_tag(ntn_cagr, imi_last, imi_slope),
        })

    # === LIQUIDITY SCORE (z-score normalization vs distribuzione zone)
    imi_vals = [z['imi_last_pct'] for z in zone_metrics if z['imi_last_pct'] is not None]
    cagr_vals = [z['ntn_cagr_pct'] for z in zone_metrics if z['ntn_cagr_pct'] is not None]
    slope_vals = [z['ntn_recent_slope'] for z in zone_metrics if z['ntn_recent_slope'] is not None]
    imi_mean, imi_sd = (mean(imi_vals), stdev(imi_vals)) if len(imi_vals) >= 2 else (0,1)
    cagr_mean, cagr_sd = (mean(cagr_vals), stdev(cagr_vals)) if len(cagr_vals) >= 2 else (0,1)
    slope_mean, slope_sd = (mean(slope_vals), stdev(slope_vals)) if len(slope_vals) >= 2 else (0,1)

    for z in zone_metrics:
        z_imi = z_score(z['imi_last_pct'], imi_mean, imi_sd)
        z_cagr = z_score(z['ntn_cagr_pct'], cagr_mean, cagr_sd)
        z_slope = z_score(z['ntn_recent_slope'], slope_mean, slope_sd)
        # Score base 50, +25*z_imi (livello attuale), +15*z_cagr (long-term), +10*z_slope (recent)
        score = 50 + 25*z_imi + 15*z_cagr + 10*z_slope
        z['liquidity_score'] = round(max(0, min(100, score)), 1)
        z['_z_components'] = {
            "z_imi": round(z_imi, 2),
            "z_cagr": round(z_cagr, 2),
            "z_slope": round(z_slope, 2),
        }

    # === PRICE × VOLUME QUADRANT
    # Per join con quotazione attuale, uso modena-signals.zone_metrics se zona_new matcha
    price_vals = []
    for z in zone_metrics:
        # Map first available zona_new
        zn = z['zona_new'][0] if z['zona_new'] else None
        sig_z = sig_by_zona.get(zn) if zn else None
        if sig_z and sig_z.get('prezzo_acquisto_attuale'):
            price_vals.append(sig_z['prezzo_acquisto_attuale'])
            z['prezzo_attuale_eur_mq'] = sig_z['prezzo_acquisto_attuale']
    vol_vals = [z['ntn_last'] for z in zone_metrics if z['ntn_last'] is not None]
    price_med = median(price_vals) if price_vals else None
    vol_med = median(vol_vals) if vol_vals else None

    for z in zone_metrics:
        p = z.get('prezzo_attuale_eur_mq')
        v = z.get('ntn_last')
        if p is None or v is None or price_med is None or vol_med is None:
            z['price_volume_quadrant'] = 'unknown'
            continue
        high_p = p >= price_med
        high_v = v >= vol_med
        z['price_volume_quadrant'] = (
            'Q1_HOT' if high_p and high_v else
            'Q2_OVERPRICED' if high_p and not high_v else
            'Q3_OPPORTUNITY' if not high_p and high_v else
            'Q4_DEAD'
        )

    # === MACROAREE
    macro_series = [r for r in vol['provincia_series'] if r.get('level') == 'macroarea']
    by_macro = {}
    for r in macro_series:
        by_macro.setdefault(r['name'], []).append(r)
    macro_metrics = []
    for name, rows in by_macro.items():
        rows = sorted(rows, key=lambda r: r['year'])
        years = [r['year'] for r in rows]
        ntns = [r.get('ntn') for r in rows]
        imis = [r.get('imi_pct') for r in rows]
        ntn_first = next((v for v in ntns if v is not None), None)
        ntn_last = next((v for v in reversed(ntns) if v is not None), None)
        valid_years = [y for y,v in zip(years,ntns) if v is not None]
        ntn_cagr = None
        if len(valid_years) >= 2:
            ntn_cagr = cagr(ntn_first, ntn_last, valid_years[-1] - valid_years[0])
        imi_last = next((v for v in reversed(imis) if v is not None), None)
        imi_xs = [y for y,v in zip(years,imis) if v is not None]
        imi_ys = [v for v in imis if v is not None]
        imi_slope = linreg_slope(imi_xs, imi_ys) if len(imi_xs) >= 2 else 0.0
        macro_metrics.append({
            "name": name,
            "ntn_series": [{"year": r['year'], "ntn": r.get('ntn'), "imi_pct": r.get('imi_pct'),
                            "quota_pct": r.get('quota_pct')} for r in rows],
            "ntn_first": ntn_first, "ntn_last": ntn_last,
            "ntn_cagr_pct": round(ntn_cagr,2) if ntn_cagr is not None else None,
            "imi_last_pct": round(imi_last,2) if imi_last is not None else None,
            "imi_trend_slope": round(imi_slope,3),
            "quota_last_pct": rows[-1].get('quota_pct'),
            "momentum_tag": momentum_tag(ntn_cagr, imi_last, imi_slope),
        })

    # === TOTALE PROVINCIA
    # PRIMARIO: somma macroaree per anno (copertura 2018-2023 completa).
    # FALLBACK: row level='provincia' se presente (solo 2022/2023 nel nostro dataset).
    all_years_p = sorted(set(r['year'] for r in vol['provincia_series']))
    prov_synth = []
    for y in all_years_p:
        macros_y = [r for r in vol['provincia_series'] if r['year']==y and r['level']=='macroarea']
        if not macros_y: continue
        sum_ntn = sum(r.get('ntn',0) or 0 for r in macros_y)
        # IMI provincia: media pesata per NTN delle macroaree (proxy)
        wsum = sum(r.get('imi_pct',0)*r.get('ntn',0) for r in macros_y if r.get('imi_pct') is not None and r.get('ntn'))
        imi_w = wsum / sum_ntn if sum_ntn else None
        # Also pull declared totale row if available
        totrow = next((r for r in vol['provincia_series'] if r['year']==y and r['level']=='provincia'), None)
        prov_synth.append({
            "year": y,
            "ntn_sum_macroaree": sum_ntn,
            "ntn_declared_totale": totrow.get('ntn') if totrow else None,
            "imi_weighted_avg_pct": round(imi_w,2) if imi_w else None,
            "imi_declared_totale_pct": totrow.get('imi_pct') if totrow else None,
            "n_macroaree": len(macros_y),
        })

    if prov_synth:
        ntn_first = prov_synth[0]['ntn_sum_macroaree']
        ntn_last = prov_synth[-1]['ntn_sum_macroaree']
        years_span = prov_synth[-1]['year'] - prov_synth[0]['year']
        prov_cagr = cagr(ntn_first, ntn_last, years_span)
        imi_last_p = prov_synth[-1]['imi_weighted_avg_pct']
        imi_vals_p = [p['imi_weighted_avg_pct'] for p in prov_synth if p['imi_weighted_avg_pct'] is not None]
        totale_provincia = {
            "_method": "ntn_sum_macroaree (sum 8 macroaree per anno) + imi_weighted_avg (weighted by NTN)",
            "ntn_series": prov_synth,
            "ntn_first": ntn_first, "ntn_last": ntn_last,
            "ntn_cagr_pct": round(prov_cagr,2) if prov_cagr is not None else None,
            "ntn_delta_pct": round((ntn_last/ntn_first-1)*100,2) if ntn_first else None,
            "ntn_peak": max(p['ntn_sum_macroaree'] for p in prov_synth),
            "ntn_peak_year": max(prov_synth, key=lambda p: p['ntn_sum_macroaree'])['year'],
            "imi_last_pct": imi_last_p,
            "imi_avg_pct": round(mean(imi_vals_p),2) if imi_vals_p else None,
        }
    else:
        totale_provincia = {}

    # === OUTPUT
    payload = {
        "metadata": {
            "generated_at": "2026-05-14",
            "source": "data/volumi/modena-volumi-timeseries.json (PDF AdE Statistiche Regionali) + data/computed/modena-signals.json (Sagona OMI quotazioni)",
            "years_covered": sorted(set(r['year'] for r in vol['provincia_series'])),
            "scoring": {
                "liquidity_score": "50 + 25*z(imi_last) + 15*z(ntn_cagr) + 10*z(ntn_recent_slope), clamped [0,100]",
                "momentum_tag_thresholds": {
                    "rocket": "cagr > +8%/yr AND imi_trend_slope > 0",
                    "growing": "cagr > +2%/yr",
                    "stable": "-2% ≤ cagr ≤ +2%",
                    "cooling": "-8% ≤ cagr < -2%",
                    "frozen": "cagr < -8% OR imi_last < 1.0%"
                },
                "quadrant_legend": {
                    "Q1_HOT": "prezzo>=median AND volume>=median (premium liquido)",
                    "Q2_OVERPRICED": "prezzo>=median AND volume<median (premium illiquido - cautela)",
                    "Q3_OPPORTUNITY": "prezzo<median AND volume>=median (cheap & active - BUY)",
                    "Q4_DEAD": "prezzo<median AND volume<median (cheap & illiquid - RISCHIO)"
                }
            },
            "distribution_stats": {
                "imi_last_pct":  {"mean": round(imi_mean,2),  "sd": round(imi_sd,2),  "n": len(imi_vals)},
                "ntn_cagr_pct":  {"mean": round(cagr_mean,2), "sd": round(cagr_sd,2), "n": len(cagr_vals)},
                "ntn_recent_slope": {"mean": round(slope_mean,2), "sd": round(slope_sd,2), "n": len(slope_vals)},
                "price_median_eur_mq": round(price_med,0) if price_med else None,
                "volume_median_ntn":   round(vol_med,1) if vol_med else None,
            }
        },
        "zone_volume_metrics": sorted(zone_metrics, key=lambda z: -z['liquidity_score']),
        "macroaree_volume_metrics": sorted(macro_metrics, key=lambda m: -(m.get('ntn_last') or 0)),
        "totale_provincia_metrics": totale_provincia,
        "summary": {
            "n_zone": len(zone_metrics),
            "n_macroaree": len(macro_metrics),
            "tag_distribution": {
                tag: sum(1 for z in zone_metrics if z['momentum_tag']==tag)
                for tag in ['rocket','growing','stable','cooling','frozen','unknown']
            },
            "quadrant_distribution": {
                q: sum(1 for z in zone_metrics if z['price_volume_quadrant']==q)
                for q in ['Q1_HOT','Q2_OVERPRICED','Q3_OPPORTUNITY','Q4_DEAD','unknown']
            }
        }
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    print(f"=== OUTPUT: {OUT_JSON.name} ({OUT_JSON.stat().st_size:,} bytes) ===")
    print(f"Zone:        {len(zone_metrics)}")
    print(f"Macroaree:   {len(macro_metrics)}")
    print(f"Anni:        {payload['metadata']['years_covered']}")
    print()
    print("Tag distribution:")
    for t,n in payload['summary']['tag_distribution'].items():
        print(f"  {t:10s}: {n}")
    print()
    print("Quadrant distribution:")
    for q,n in payload['summary']['quadrant_distribution'].items():
        print(f"  {q:18s}: {n}")
    print()
    ordered = sorted(zone_metrics, key=lambda z: -(z['liquidity_score'] or 0))
    print("Top 5 liquidity score:")
    for z in ordered[:5]:
        print(f"  {z['zona_old']:4s} [{z['momentum_tag']:8s}] score={z['liquidity_score']:5.1f}  NTN_cagr={z['ntn_cagr_pct']}  IMI_last={z['imi_last_pct']}%  → {z['denominazione'][:40]}")
    print()
    print("Bottom 5 liquidity score:")
    for z in ordered[-5:]:
        print(f"  {z['zona_old']:4s} [{z['momentum_tag']:8s}] score={z['liquidity_score']:5.1f}  NTN_cagr={z['ntn_cagr_pct']}  IMI_last={z['imi_last_pct']}%  → {z['denominazione'][:40]}")
    print()
    print(f"Provincia totale: NTN {totale_provincia.get('ntn_first')} → {totale_provincia.get('ntn_last')} (CAGR {totale_provincia.get('ntn_cagr_pct')}%, IMI {totale_provincia.get('imi_last_pct')}%)")


if __name__ == "__main__":
    main()
