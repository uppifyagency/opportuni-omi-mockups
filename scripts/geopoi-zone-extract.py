#!/usr/bin/env python3
"""GeoPOI zone extractor — get OMI zone polygons for an Italian comune.

Pipeline (no GDAL, no installs):
  1. GET   geopoi_omi/zoneomi.php?richiesta=3&codcom=<X>          → zone metadata JSON
  2. GET   geopoi_omi/perimetri.php?id=1&prov=<P>&codcom=<X>&semestre=<YYYYS>&formato=kml
                                                                    → KMZ (ZIP of KML)
  3. Parse KML XML, extract Placemark name+coords
  4. Join (name == ZONA) with zone metadata
  5. Optional: join with sagona prezzi CSV for color-by-price
  6. Emit GeoJSON with rich properties

Usage:
  python geopoi-zone-extract.py --codcom F257 --prov MO --semestre 20241
  python geopoi-zone-extract.py --codcom F257 --prov MO --semestre 20241 \
      --prezzi-csv ../data/sagona-backfill/prezzi.csv \
      --out ../data/geojson/modena-zone-omi.geojson
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import ssl
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

GEOPOI_BASE = "https://www1.agenziaentrate.gov.it/servizi/geopoi_omi"
KML_NS = {"k": "http://www.opengis.net/kml/2.2"}

SSL_CTX = ssl.create_default_context()
try:
    SSL_CTX.load_default_certs()
    if not SSL_CTX.get_ca_certs():
        raise ssl.SSLError("no system CAs")
except Exception:
    SSL_CTX = ssl._create_unverified_context()


def http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; opportuni-poc/0.1)",
        "Referer": f"{GEOPOI_BASE}/index.htm",
        "Accept": "*/*",
    })
    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
        return resp.read()


def fetch_zone_list(codcom: str) -> list[dict]:
    """zoneomi.php?richiesta=3&codcom=F257 → [{LINK_ZONA, FASCIA, ZONA, DIZIONE}, ...]"""
    raw = http_get(f"{GEOPOI_BASE}/zoneomi.php?richiesta=3&codcom={codcom}")
    return json.loads(raw)


def fetch_kmz(codcom: str, prov: str, semestre: str) -> bytes:
    return http_get(
        f"{GEOPOI_BASE}/perimetri.php?id=1&prov={prov}&codcom={codcom}"
        f"&semestre={semestre}&formato=kml"
    )


def parse_kml(kml_bytes: bytes) -> list[dict]:
    """Extract every Placemark as {name, coordinates: [[lon,lat], ...] per ring}."""
    root = ET.fromstring(kml_bytes)
    features = []
    for pm in root.iter("{http://www.opengis.net/kml/2.2}Placemark"):
        name_el = pm.find("k:name", KML_NS)
        name = name_el.text.strip() if name_el is not None and name_el.text else ""

        # description sometimes has the zone info too
        desc_el = pm.find("k:description", KML_NS)
        desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ""

        # Polygon / MultiGeometry / Polygon with multiple rings
        polygons = []
        for poly in pm.iter("{http://www.opengis.net/kml/2.2}Polygon"):
            rings = []
            outer = poly.find(".//k:outerBoundaryIs/k:LinearRing/k:coordinates", KML_NS)
            if outer is not None and outer.text:
                rings.append(parse_coords(outer.text))
            for inner in poly.findall(".//k:innerBoundaryIs/k:LinearRing/k:coordinates", KML_NS):
                if inner.text:
                    rings.append(parse_coords(inner.text))
            if rings:
                polygons.append(rings)

        if polygons:
            features.append({
                "name": name,
                "description": desc,
                "polygons": polygons,
            })
    return features


def parse_coords(text: str) -> list[list[float]]:
    """KML coords: 'lon,lat,alt lon,lat,alt ...' → [[lon, lat], ...]"""
    pts = []
    for chunk in text.split():
        parts = chunk.split(",")
        if len(parts) >= 2:
            try:
                pts.append([float(parts[0]), float(parts[1])])
            except ValueError:
                continue
    return pts


def extract_zone_name(placemark_name: str) -> str:
    """KML Placemark names variants:
      'B3', 'C10', 'B3 - CENTRO STORICO', 'MODENA - Zona OMI D33'
    Return the LAST [A-Z]\\d+ token — robust across all forms."""
    matches = re.findall(r"\b([A-Z]\d+)\b", placemark_name)
    return matches[-1] if matches else placemark_name.strip()


def load_prezzi(csv_path: Path, codcom: str) -> dict[str, dict]:
    """Aggregate current-year price per zona for a comune.
    Returns: { 'B3': { 'abitazioni_civili_acquisto_medio': 2500.0, ... }, ... }"""
    if not csv_path.exists():
        return {}
    by_zone: dict[str, dict] = {}
    by_anno: dict[str, int] = {}
    rows = list(csv.DictReader(csv_path.open()))
    annos = sorted({int(r["anno"]) for r in rows if r["comune_catasto"] == codcom})
    if not annos:
        return {}
    current_anno = max(annos)
    for r in rows:
        if r["comune_catasto"] != codcom or int(r["anno"]) != current_anno:
            continue
        zona = r["zona"]
        tipo = r["tipo_immobile"]
        op = r["operazione"]
        try:
            pmed = float(r["prezzo_medio"]) if r["prezzo_medio"] else None
        except ValueError:
            continue
        if pmed is None:
            continue
        by_zone.setdefault(zona, {})[f"{tipo}_{op}_medio"] = pmed
    return by_zone


def build_geojson(
    features: list[dict],
    zone_meta: list[dict],
    prezzi: dict[str, dict],
    codcom: str,
    semestre: str,
) -> dict:
    meta_by_zona = {z["ZONA"]: z for z in zone_meta}
    out_features = []

    for f in features:
        zona_code = extract_zone_name(f["name"])
        meta = meta_by_zona.get(zona_code, {})

        # Build geometry (MultiPolygon if multiple, else Polygon)
        if len(f["polygons"]) == 1:
            geometry = {"type": "Polygon", "coordinates": f["polygons"][0]}
        else:
            geometry = {"type": "MultiPolygon", "coordinates": f["polygons"]}

        props = {
            "comune_catasto": codcom,
            "semestre": semestre,
            "zona": zona_code,
            "kml_name": f["name"],
            "fascia": meta.get("FASCIA"),
            "dizione": meta.get("DIZIONE"),
            "link_zona": meta.get("LINK_ZONA"),
        }
        # Merge price info
        props.update(prezzi.get(zona_code, {}))

        out_features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": props,
        })

    return {
        "type": "FeatureCollection",
        "metadata": {
            "comune_catasto": codcom,
            "semestre": semestre,
            "zone_count": len(out_features),
            "source": "Agenzia delle Entrate / GeoPOI",
            "license": "uso libero con attribuzione",
        },
        "features": out_features,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codcom", required=True, help="Codice catastale (es. F257 = Modena)")
    ap.add_argument("--prov", required=True, help="Sigla provincia (es. MO)")
    ap.add_argument("--semestre", default="20241", help="Anno+semestre compatto (es. 20241)")
    ap.add_argument("--prezzi-csv", default="", help="CSV sagona-backfill per joinare prezzi")
    ap.add_argument("--out", required=True, help="Path output GeoJSON")
    args = ap.parse_args()

    print(f"==> zoneomi.php (lista zone {args.codcom})", flush=True)
    zone_meta = fetch_zone_list(args.codcom)
    print(f"    zone trovate: {len(zone_meta)}")

    print(f"==> perimetri.php (KMZ {args.codcom} sem {args.semestre})", flush=True)
    kmz_bytes = fetch_kmz(args.codcom, args.prov, args.semestre)
    print(f"    KMZ size: {len(kmz_bytes):,} bytes")

    zf = zipfile.ZipFile(io.BytesIO(kmz_bytes))
    kml_name = next((n for n in zf.namelist() if n.lower().endswith(".kml")), None)
    if not kml_name:
        print("ERROR: KMZ vuoto, nessun KML interno", file=sys.stderr)
        return 1
    kml_bytes = zf.read(kml_name)
    print(f"    KML interno: {kml_name} ({len(kml_bytes):,} bytes)")

    print(f"==> Parse KML")
    features = parse_kml(kml_bytes)
    print(f"    placemark estratti: {len(features)}")

    prezzi = {}
    if args.prezzi_csv:
        print(f"==> Join prezzi da {args.prezzi_csv}")
        prezzi = load_prezzi(Path(args.prezzi_csv), args.codcom)
        print(f"    zone con prezzi: {len(prezzi)}")

    geojson = build_geojson(features, zone_meta, prezzi, args.codcom, args.semestre)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(geojson, ensure_ascii=False))
    print(f"\n==> Scritto {out_path} ({out_path.stat().st_size:,} bytes)")
    print(f"    features: {len(geojson['features'])}")
    print(f"    properties di esempio: {json.dumps(geojson['features'][0]['properties'], indent=2, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
