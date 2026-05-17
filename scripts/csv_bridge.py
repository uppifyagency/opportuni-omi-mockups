"""
CSV → Worker bridge.

Bypassa il bug Chrome MV3 (dynamic import nel SW) leggendo il CSV
esportato da GMP e POSTandolo al worker /api/sync con de-identificazione.

- Estrae place_id dal Google Maps URL (cid=0x...:0x...)
- Geocoda gli address via Nominatim (rate limited 1/s)
- De-identifica: drop email/phone/social PRIMA del POST
- Idempotente: stesso CSV ri-eseguito = 0 nuovi record
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

import requests

WORKER = "http://localhost:8787/api/sync"
TOKEN = "dev-only-change-me-in-prod"

NOMINATIM = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {"User-Agent": "OpportuniPoC/0.1 (PoC research)"}
GEOCACHE = Path(__file__).resolve().parent.parent / "data" / "cache" / "geocache.json"
GEOCACHE.parent.mkdir(parents=True, exist_ok=True)


def load_geocache() -> dict:
    if GEOCACHE.exists():
        return json.loads(GEOCACHE.read_text())
    return {}


def save_geocache(cache: dict) -> None:
    GEOCACHE.write_text(json.dumps(cache, ensure_ascii=False))


def extract_place_id(url: str) -> str | None:
    """Sagona/AdE-style CID is in `cid=0xHEX%3A0xHEX` or `cid=0xHEX:0xHEX`."""
    if not url:
        return None
    decoded = urllib.parse.unquote(url)
    m = re.search(r"cid=(0x[0-9a-fA-F]+:0x[0-9a-fA-Fx]+)", decoded)
    if m:
        return m.group(1)
    # Fallback: !1s pattern (Maps internal)
    m2 = re.search(r"!1s(0x[0-9a-fA-F]+:0x[0-9a-fA-Fx]+)", decoded)
    if m2:
        return m2.group(1)
    return None


def geocode(address: str, comune_hint: str = "Milano", cache: dict | None = None) -> tuple[float, float] | None:
    if not address:
        return None
    key = f"{address}|{comune_hint}"
    if cache is not None and key in cache:
        v = cache[key]
        return (v["lat"], v["lng"]) if v else None
    query = f"{address}, {comune_hint}, Italia"
    try:
        r = requests.get(
            NOMINATIM,
            params={"q": query, "format": "json", "limit": 1, "addressdetails": 0, "countrycodes": "it"},
            headers=NOMINATIM_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        results = r.json()
        if results:
            lat = float(results[0]["lat"])
            lng = float(results[0]["lon"])
            if cache is not None:
                cache[key] = {"lat": lat, "lng": lng}
            return (lat, lng)
        if cache is not None:
            cache[key] = None
    except Exception as e:
        print(f"  WARN: geocode failed for {address[:40]}: {e}", file=sys.stderr)
    return None


def csv_to_business(row: dict, location: tuple[float, float] | None) -> dict | None:
    """Reconstruct business from buggy GMP CSV.

    Known GMP scraping bugs (R10 telemetry should flag these):
    - 'Category' field contains the rating string ("4,7") because span.DkEaL
       in current Maps DOM is the rating element, not category.
    - 'Rating' field contains parseInt() of the misplaced rating, so always 4-5.
    - 'Reviews' field contains random text fragments (year "1999", "24", etc).

    Workaround:
    - Recover REAL rating by parsing 'Category' as "X,Y" Italian decimal.
    - Set raw_category from search context (always pizzeria for this batch).
    - Discard 'Reviews' (unrecoverable) — set to None.
    """
    place_id = extract_place_id(row.get("Google Maps URL", ""))
    name = (row.get("Title") or "").strip()
    if not place_id or not name:
        return None

    # ─── Recover RATING from misnamed 'Category' column ──────────────────
    rating = None
    cat_raw = (row.get("Category") or "").strip()
    rating_match = re.match(r"^(\d+)[,.](\d+)$", cat_raw)
    if rating_match:
        try:
            rating = float(f"{rating_match.group(1)}.{rating_match.group(2)}")
            if rating < 0 or rating > 5:
                rating = None
        except ValueError:
            pass

    # ─── REVIEWS: unrecoverable ──────────────────────────────────────────
    # 'Reviews' col contains noise (1999, 24, 4, etc). Set None.
    reviews = None

    return {
        "place_id": place_id,
        "name": name,
        # We know batch context → set explicitly (the actual category col is broken)
        "raw_category": "Pizzeria",
        "address": (row.get("Address") or "").strip() or None,
        "location": {"lat": location[0], "lng": location[1]} if location else None,
        "rating": rating,
        "reviews": reviews,
        "google_url": row.get("Google Maps URL") or None,
        # NOTE: email/phone/social NOT included → de-identified at source
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: csv_bridge.py <ghost_map_export.csv>")
        return 1
    csv_path = Path(argv[1]).expanduser()
    if not csv_path.exists():
        print(f"CSV not found: {csv_path}", file=sys.stderr)
        return 1

    cache = load_geocache()

    with csv_path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"Loaded {len(rows)} rows from {csv_path.name}")

    businesses: list[dict] = []
    geocoded_new = 0
    geocoded_cached = 0
    skipped_no_addr = 0
    skipped_no_id = 0

    for i, row in enumerate(rows, 1):
        addr = (row.get("Address") or "").strip()
        loc = None
        if addr:
            cache_key = f"{addr}|Milano"
            was_cached = cache_key in cache
            loc = geocode(addr, "Milano", cache=cache)
            if was_cached:
                geocoded_cached += 1
            else:
                geocoded_new += 1
                # Polite Nominatim rate limit: 1 req/s
                time.sleep(1.1)
        else:
            skipped_no_addr += 1

        biz = csv_to_business(row, loc)
        if biz is None:
            skipped_no_id += 1
            continue
        businesses.append(biz)
        loc_str = f"{biz['location']['lat']:.4f},{biz['location']['lng']:.4f}" if biz["location"] else "—"
        print(f"  [{i:>3}/{len(rows)}] {biz['name'][:50]:<50}  loc={loc_str}")

    save_geocache(cache)
    print(f"\nPrepared {len(businesses)} businesses (skipped: no_addr={skipped_no_addr}, no_id={skipped_no_id})")
    print(f"Geocode: new={geocoded_new}, cached={geocoded_cached}")

    payload = {
        "snapshot_id": f"csv-{csv_path.stem}",
        "coverage_complete": False,
        "region_query": "Milano-pizzerie",
        "ateco_filter": ["pizzeria"],
        "businesses": businesses,
    }

    print(f"\nPOST {WORKER} (batch_size={len(businesses)})")
    r = requests.post(
        WORKER,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    print(f"  HTTP {r.status_code}")
    print(f"  Response: {r.text[:300]}")
    return 0 if r.ok else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
