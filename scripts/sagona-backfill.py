#!/usr/bin/env python3
"""Sagona backfill standalone — no DB, no docker, just JSON cache + CSV out.

Fetch quotazioni OMI for one or many comuni × many anni from Sagona API,
respect rate limit, write per-(comune, anno) JSON cache + flat CSV.

Usage:
    python sagona-backfill.py F257                            # Modena, all default years
    python sagona-backfill.py F257 B819 I462                  # Modena, Carpi, Sassuolo
    python sagona-backfill.py --years 2005,2010,2015,2020 F257
    python sagona-backfill.py --out-dir ../data/modena F257
"""
from __future__ import annotations

import argparse
import csv
import json
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# macOS python.org installs frequently miss system root CAs.
# Sagona is a public read-only HTTPS endpoint; unverified context is acceptable here.
SSL_CTX = ssl.create_default_context()
try:
    SSL_CTX.load_default_certs()
    # Probe: if no certs were loaded, fall back to unverified.
    if not SSL_CTX.get_ca_certs():
        raise ssl.SSLError("no system CAs")
except Exception:
    SSL_CTX = ssl._create_unverified_context()

SAGONA_URL = "https://3eurotools.it/api-quotazioni-immobiliari-omi/ricerca"
DEFAULT_YEARS = [2005, 2008, 2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024, None]  # None = current
DELAY_SECONDS = 3.5  # > 3.0 to stay under Sagona's "1 req / 3 s" recharge rate


def fetch(codice_comune: str, anno: int | None, cache_dir: Path) -> dict | None:
    suffix = str(anno) if anno else "current"
    cache_path = cache_dir / f"{codice_comune}_{suffix}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    params = {"codice_comune": codice_comune}
    if anno:
        params["anno"] = str(anno)
    url = f"{SAGONA_URL}?{urllib.parse.urlencode(params)}"

    print(f"  GET {codice_comune} anno={anno or 'current'}", flush=True)
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; opportuni-poc/0.1)",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
            raw = resp.read()
        data = json.loads(raw)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(data, ensure_ascii=False))
        return data
    except Exception as e:
        print(f"    ERROR: {e}", file=sys.stderr)
        return None


def parse_to_rows(codice_comune: str, anno: int | None, data: dict) -> list[dict]:
    """Flatten Sagona response → one row per (zona, tipo, operazione)."""
    rows = []
    rilevazione = anno if anno else 2026  # 'current' = run year
    if not isinstance(data, dict):
        return rows
    for zona, tipologie in data.items():
        if not isinstance(tipologie, dict):
            continue
        fascia = zona[0] if zona else ""
        for tipo, prices in tipologie.items():
            if not isinstance(prices, dict):
                continue
            stato = prices.get("stato_di_conservazione_mediano_della_zona")
            for op, prefix in (("acquisto", "prezzo_acquisto"), ("affitto", "prezzo_affitto")):
                pmin = prices.get(f"{prefix}_min")
                pmax = prices.get(f"{prefix}_max")
                pmed = prices.get(f"{prefix}_medio")
                if pmin is None and pmax is None and pmed is None:
                    continue
                rows.append({
                    "anno": rilevazione,
                    "comune_catasto": codice_comune,
                    "zona": zona,
                    "fascia": fascia,
                    "tipo_immobile": tipo,
                    "operazione": op,
                    "stato_conservazione": stato,
                    "prezzo_min": pmin,
                    "prezzo_max": pmax,
                    "prezzo_medio": pmed,
                })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("comuni", nargs="+", help="codici catastali (es. F257 B819)")
    ap.add_argument("--years", default=",".join(str(y) if y else "current" for y in DEFAULT_YEARS),
                    help="anni separati da virgola (usa 'current' per l'attuale)")
    ap.add_argument("--out-dir", default=str(Path(__file__).parent.parent / "data" / "sagona-backfill"))
    ap.add_argument("--delay", type=float, default=DELAY_SECONDS)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    cache_dir = out_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    years = []
    for y in args.years.split(","):
        y = y.strip()
        years.append(None if y in ("current", "") else int(y))

    all_rows = []
    fetched = 0
    cached_hits = 0

    for codice in args.comuni:
        print(f"--- {codice} ---", flush=True)
        for anno in years:
            suffix = str(anno) if anno else "current"
            cache_path = cache_dir / f"{codice}_{suffix}.json"
            was_cached = cache_path.exists()
            data = fetch(codice, anno, cache_dir)
            if data is None:
                continue
            if was_cached:
                cached_hits += 1
            else:
                fetched += 1
                time.sleep(args.delay)
            rows = parse_to_rows(codice, anno, data)
            all_rows.extend(rows)
            print(f"    {len(rows)} righe ({len(data)} zone)", flush=True)

    if not all_rows:
        print("WARN: zero righe estratte", file=sys.stderr)
        return 1

    csv_path = out_dir / "prezzi.csv"
    fieldnames = list(all_rows[0].keys())
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nDone. fetched={fetched} cached={cached_hits} righe_totali={len(all_rows)}")
    print(f"CSV: {csv_path}")
    print(f"JSON cache: {cache_dir}/ ({len(list(cache_dir.glob('*.json')))} file)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
