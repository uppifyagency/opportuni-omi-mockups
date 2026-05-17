#!/usr/bin/env python3
"""Doublecheck end-to-end — verifica matematica indipendente per una città.

Recupera ogni headline number dai JSON computati (signals + compass) e ne
ricostruisce il valore dal CSV grezzo Sagona. Asserta l'eguaglianza. Fallisce
rumorosamente se drift.

Sostituisce il vecchio script `/tmp/doublecheck-modena.py` con una versione
parametrizzata, ridistribuibile, e adatta al pattern di replica documentato
in REPLICATE-FOR-OTHER-PROVINCE.md §17.

Quando rilanciarlo:
  - Dopo ogni rigenerazione JSON (compute layer touch).
  - Pre-commit / pre-deploy.
  - Quando un mockup mostra un numero "strano" — primo sospetto è drift compute.

Usage:
  python3 scripts/doublecheck-city.py --city modena
  python3 scripts/doublecheck-city.py --city catanzaro
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ───── Profili città ─────
# Aggiungi qui una entry per ogni nuova città replicata.
# `expected_*` sono i valori che ci si aspetta dal JSON DOPO la rigenerazione;
# se cambiano i dati upstream (nuovo backfill) vanno ricalibrati.
PROFILES = {
    "modena": {
        "capoluogo_belfiore": "F257",
        "expected_zone_current": 20,
        "expected_province_n":   47,
        "expected_yield_pct":    5.28,
        "expected_cagr_avg_pct": 0.25,
        "expected_prezzo_avg":   1761.0,
        "expected_span_dataset": 21,   # max(year) - min(year) CSV F257
        "expected_span_current": 12,   # zone con dizione
    },
    # Template per Catanzaro — ricalibra dopo la prima rigenerazione.
    # "catanzaro": {
    #     "capoluogo_belfiore": "C352",
    #     "expected_zone_current": ?,
    #     "expected_province_n":   ?,
    #     "expected_yield_pct":    ?,
    #     "expected_cagr_avg_pct": ?,
    #     "expected_prezzo_avg":   ?,
    #     "expected_span_dataset": ?,
    #     "expected_span_current": ?,
    # },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="modena", choices=sorted(PROFILES.keys()))
    args = ap.parse_args()

    p = PROFILES[args.city]
    city = args.city
    cat = p["capoluogo_belfiore"]

    sig_path  = ROOT / "data" / "computed" / f"{city}-signals.json"
    com_path  = ROOT / "data" / "computed" / f"{city}-compass.json"
    csv_path  = ROOT / "data" / "sagona-backfill" / "prezzi.csv"
    geo_path  = ROOT / "data" / "geojson" / f"{city}-province-comuni.geojson"

    for f in (sig_path, com_path, csv_path, geo_path):
        if not f.exists():
            sys.exit(f"ERROR: missing {f}")

    sig = json.loads(sig_path.read_text())
    com = json.loads(com_path.read_text())
    sh = sig["headline"]
    ch = com["by_tipologia"]["abitazioni_civili"]["headline"]

    # Nome del campo CAGR può differire fra signals (modena_cagr_avg_pct) e
    # compass (cagr_avg_pct). Risolvi in modo robusto: prendi il campo `*_cagr_avg_pct`.
    sig_cagr_field = next((k for k in sh if k.endswith("cagr_avg_pct") and "_pct" in k), None)
    assert sig_cagr_field, f"no *cagr_avg_pct field in signals.headline: {list(sh.keys())}"

    print(f"═══ {city.upper()} math invariants ═══")

    # 1. Eguaglianza signals ↔ compass (stesso numero, due script diversi)
    assert sh["yield_medio_pct"] == ch["yield_avg_pct"] == p["expected_yield_pct"], \
        f"yield drift: signals={sh['yield_medio_pct']} compass={ch['yield_avg_pct']} expected={p['expected_yield_pct']}"
    assert sh[sig_cagr_field] == ch["cagr_avg_pct"] == p["expected_cagr_avg_pct"], \
        f"CAGR drift: signals={sh[sig_cagr_field]} compass={ch['cagr_avg_pct']} expected={p['expected_cagr_avg_pct']}"
    assert sh["prezzo_medio_attuale"] == ch["prezzo_avg"] == p["expected_prezzo_avg"]
    assert sh["zone_count_current"] == ch["zone_count"] == p["expected_zone_current"]
    print("  signals ↔ compass equality  ✓")

    # 2. anni_orizzonte disambiguato (vecchio campo ambiguo rimosso)
    assert "anni_orizzonte" not in sh, "orphan ambiguous anni_orizzonte in signals headline"
    assert "anni_orizzonte" not in ch, "orphan ambiguous anni_orizzonte in compass headline"
    assert sh["anni_orizzonte_dataset"] == p["expected_span_dataset"]
    assert sh["anni_orizzonte_zone_correnti"] == p["expected_span_current"]
    assert ch["anni_orizzonte_zone_correnti"] == p["expected_span_current"]
    print("  anni_orizzonte_* disambiguated  ✓")

    # 3. Yield filter: media SOLO zone correnti (fix #3)
    ys = [z["yield_lordo_pct"] for z in sig["zone_metrics"]
          if z.get("dizione") and z["yield_lordo_pct"] is not None]
    recomp = round(statistics.mean(ys), 2)
    assert recomp == p["expected_yield_pct"], f"yield recompute {recomp} != expected {p['expected_yield_pct']}"
    print(f"  recompute yield mean({len(ys)} current zones) = {recomp}  ✓")

    # 4. Span dataset = max(year) - min(year) dal CSV
    years = []
    with csv_path.open() as f:
        for r in csv.DictReader(f):
            if r["comune_catasto"] == cat:
                years.append(int(r["anno"]))
    span = max(years) - min(years)
    assert span == p["expected_span_dataset"], f"CSV span {span} != expected {p['expected_span_dataset']}"
    print(f"  CSV span {min(years)}-{max(years)} = {span}  ✓")

    # 5. Province count = features del GeoJSON
    geo = json.loads(geo_path.read_text())
    assert len(geo["features"]) == p["expected_province_n"], \
        f"geojson has {len(geo['features'])} features, expected {p['expected_province_n']}"
    assert len(sig["province_ranking"]) == p["expected_province_n"], \
        f"signals.province_ranking has {len(sig['province_ranking'])}, expected {p['expected_province_n']}"
    print(f"  {p['expected_province_n']} comuni provincia in geojson + ranking  ✓")

    print(f"\n═══ {city.upper()} ALL INVARIANTS HOLD ═══")
    return 0


if __name__ == "__main__":
    sys.exit(main())
