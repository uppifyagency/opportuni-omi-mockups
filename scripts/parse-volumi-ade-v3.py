#!/usr/bin/env python3
"""Parser scientifico v3 — header-aware column mapping.

Il problema scoperto in v2: l'ordine delle colonne nelle tabelle AdE
CAMBIA tra anni (Quota NTN in pos 3 nel 2018, pos 5 nel 2023).
Soluzione: leggere i NOMI delle colonne header e mappare per nome.

Rules header → field:
  'NTN ... var %' → ntn_var_pct
  'NTN ...'       → ntn
  'IMI ... diff'  → imi_diff
  'IMI'           → imi_pct
  'Quota NTN'     → quota_pct
  'Quotazione ... var %' → quotazione_var_pct
  'Quotazione media'      → quotazione_eur_mq
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "data" / "volumi"
OUT_JSON = PDF_DIR / "modena-volumi-timeseries.json"
LOG_FILE = PDF_DIR / "parse-log-v3.txt"

MACROAREE_KNOWN = {
    "APPENNINO PANARO", "APPENNINO SECCHIA", "BASSA MODENESE", "FRIGNANO",
    "PEDEMONTANA", "PIANURA PANARO", "PIANURA SECCHIA", "MODENA CAPOLUOGO", "MODENA",
}


def parse_italian_number(s):
    if s is None: return None
    if not isinstance(s, str): s = str(s)
    s = s.strip().rstrip('%').strip()
    if s in ('', '-', 'n.d.', 'nd', '—'): return None
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif '.' in s:
        parts = s.split('.')
        if len(parts) == 2 and len(parts[1]) == 3 and parts[1].isdigit():
            s = s.replace('.', '')
    try:
        return float(s)
    except ValueError:
        return None


def normalize_header(h: str) -> str:
    """Lowercase + strip + flatten newlines."""
    if h is None: return ""
    return re.sub(r'\s+', ' ', h.replace('\n', ' ').lower().strip())


def map_header_to_field(h: str) -> str | None:
    """Mappa header colonna → nome canonico campo output."""
    nh = normalize_header(h)
    if not nh: return None
    # Order matters: more-specific first
    if 'ntn' in nh and 'var' in nh:            return 'ntn_var_pct'
    if 'imi' in nh and ('diff' in nh or 'differenz' in nh):  return 'imi_diff'
    if 'quotazione' in nh and 'var' in nh:     return 'quotazione_var_pct'
    if 'quotazione' in nh and ('media' in nh or '€/m' in nh or 'eur' in nh):
                                                return 'quotazione_eur_mq'
    if 'ntn' in nh:                            return 'ntn'
    if 'imi' in nh:                            return 'imi_pct'
    if 'quota' in nh and 'ntn' in nh:          return 'quota_pct'
    if 'quota' in nh:                          return 'quota_pct'  # fallback
    return None


def parse_table_header(table) -> list[str]:
    """Estrae headers da una tabella. La 1ª riga è header, o 1ª+2ª se multi-line."""
    if not table or not table[0]: return []
    # Try first row, then merge with second if second has more info
    header_row = list(table[0])
    if len(table) > 1 and table[1]:
        # Some PDFs split header in 2 rows: merge
        merged = []
        for i in range(max(len(header_row), len(table[1]))):
            a = header_row[i] if i < len(header_row) else ''
            b = table[1][i] if i < len(table[1]) else ''
            merged.append(f"{a or ''} {b or ''}".strip())
        # Use merged only if it adds info
        if any(b for b in table[1] if b):
            header_row = merged
    return [normalize_header(h) for h in header_row]


def header_map(table) -> dict[int, str]:
    """Returns {column_index: canonical_field_name}."""
    headers = parse_table_header(table)
    out = {}
    for i, h in enumerate(headers):
        f = map_header_to_field(h)
        if f:
            out[i] = f
    return out


def find_modena_pages(pdf):
    p_prov, p_com = None, None
    for i, page in enumerate(pdf.pages):
        try:
            text = (page.extract_text() or "")[:1000]
        except Exception:
            continue
        if p_prov is None and re.search(r'La provincia\s*[-–]\s*Modena', text, re.I):
            p_prov = i
        if p_com is None and re.search(r'Il comune\s*[-–]\s*Modena', text, re.I):
            p_com = i
    return p_prov, p_com


def find_main_table(page, expected_first_col_pattern):
    """Trova la tabella principale nella pagina, identificata dalla prima cella che matcha il pattern."""
    for table in page.extract_tables() or []:
        if not table or len(table) < 2: continue
        # Check first data row's first cell
        for tr in table[1:]:
            if not tr or not tr[0]: continue
            first = str(tr[0]).strip().upper().replace('\n', ' ')
            first = re.sub(r'\s+', ' ', first)
            if re.match(expected_first_col_pattern, first):
                return table
    return None


def parse_provincia(pdf, page_idx, year, log):
    """Header-aware parse della tabella macroaree."""
    rows = []
    for pi in [page_idx, page_idx + 1]:
        if pi >= len(pdf.pages): continue
        # Find main table (first cell matches macroarea name)
        for table in pdf.pages[pi].extract_tables() or []:
            if not table or len(table) < 3: continue
            hmap = header_map(table)
            if not hmap or 'ntn' not in hmap.values(): continue

            # Header rows can occupy 1-3 rows. Skip them: data rows start where first cell is uppercase macroarea
            for tr in table:
                if not tr or not tr[0]: continue
                first = re.sub(r'\s+', ' ', str(tr[0]).strip().upper().replace('\n', ' '))
                if first not in MACROAREE_KNOWN: continue
                row = {"year": year, "level": "macroarea" if first != "MODENA" else "provincia", "name": first}
                for col_idx, field in hmap.items():
                    if col_idx < len(tr):
                        val = parse_italian_number(tr[col_idx])
                        if val is not None:
                            row[field] = val
                # Sanity: must have at least ntn
                if row.get('ntn') is not None:
                    rows.append(row)
    # Dedupe
    seen = set()
    dedup = []
    for r in rows:
        key = (r['year'], r['name'])
        if key not in seen:
            seen.add(key)
            dedup.append(r)
    return dedup


def parse_zone(pdf, page_idx, year, log):
    """Header-aware parse delle 19 zone OMI Modena capoluogo."""
    rows = []
    for pi in [page_idx, page_idx + 1, page_idx + 2]:
        if pi >= len(pdf.pages): continue
        for table in pdf.pages[pi].extract_tables() or []:
            if not table or len(table) < 3: continue
            hmap = header_map(table)
            if not hmap or 'ntn' not in hmap.values(): continue
            # For zona tables, first col is "Zona OMI" (B3, C7, ...), second col is "Denominazione"
            for tr in table:
                if not tr or not tr[0]: continue
                first = str(tr[0]).strip()
                if not re.match(r'^[A-Z]\d{1,2}$', first): continue
                cell1 = (tr[1] or "").strip().replace('\n', ' ')
                cell1 = re.sub(r'\s+', ' ', cell1)
                row = {"year": year, "level": "zona", "zona": first, "denominazione": cell1}
                for col_idx, field in hmap.items():
                    if col_idx < len(tr):
                        val = parse_italian_number(tr[col_idx])
                        if val is not None:
                            row[field] = val
                if row.get('ntn') is not None or row.get('imi_pct') is not None:
                    rows.append(row)
    seen = set()
    dedup = []
    for r in rows:
        key = (r['year'], r['zona'])
        if key not in seen:
            seen.add(key)
            dedup.append(r)
    return dedup


def parse_one(pdf_path: Path, log: list):
    sr_year = int(re.search(r'sr(\d{4})', pdf_path.name).group(1))
    data_year = sr_year - 1
    log.append(f"\n═══ {pdf_path.name} → data_year={data_year} ═══")
    pdf = pdfplumber.open(str(pdf_path))
    p_prov, p_com = find_modena_pages(pdf)
    log.append(f"  pages: provincia={p_prov+1 if p_prov is not None else None}, comune={p_com+1 if p_com is not None else None}")
    if p_prov is None or p_com is None:
        pdf.close()
        return None
    prov = parse_provincia(pdf, p_prov, data_year, log)
    zone = parse_zone(pdf, p_com, data_year, log)
    log.append(f"  parsed: provincia={len(prov)}, zone={len(zone)}")

    # cross-check
    macros = [r for r in prov if r['level'] == 'macroarea']
    tot = next((r for r in prov if r['level'] == 'provincia'), None)
    if tot and macros:
        s = sum(r.get('ntn',0) for r in macros)
        gap = abs(s - tot['ntn']) / tot['ntn'] * 100 if tot.get('ntn') else 0
        log.append(f"  ✓ NTN cross-check: sum_macro={s:.0f} tot={tot['ntn']:.0f} gap={gap:.2f}%")

    # sanity
    issues = 0
    for r in prov + zone:
        if r.get('imi_pct') is not None and not (0 <= r['imi_pct'] <= 10):
            issues += 1
            log.append(f"  ⚠ IMI fuori range {r.get('zona') or r.get('name')}={r['imi_pct']}")
    if issues == 0:
        log.append(f"  ✓ sanity check: tutti IMI ∈ [0, 10]%")

    pdf.close()
    return {"data_year": data_year, "provincia": prov, "zone": zone}


def main():
    log = ["PARSE-VOLUMI v3 (header-aware)"]
    pdfs = sorted(PDF_DIR.glob("sr*.pdf"))
    log.append(f"PDFs: {len(pdfs)}")

    prov_all, zone_all, years = [], [], []
    for pdf in pdfs:
        r = parse_one(pdf, log)
        if r:
            prov_all.extend(r['provincia'])
            zone_all.extend(r['zone'])
            years.append(r['data_year'])

    log.append(f"\n═══ GLOBAL ═══")
    log.append(f"years: {sorted(years)}")
    log.append(f"provincia rows: {len(prov_all)} ({len(prov_all)/max(len(years),1):.1f}/yr, expected 9)")
    log.append(f"zone rows:      {len(zone_all)} ({len(zone_all)/max(len(years),1):.1f}/yr, expected 19)")

    # IMI range check globale
    imi_vals = [r['imi_pct'] for r in prov_all + zone_all if r.get('imi_pct') is not None]
    log.append(f"IMI range globale: min={min(imi_vals):.2f}% max={max(imi_vals):.2f}%  (atteso 0-10%)")

    # Coverage per anno
    for y in sorted(years):
        np = sum(1 for r in prov_all if r['year'] == y)
        nz = sum(1 for r in zone_all if r['year'] == y)
        log.append(f"  {y}: prov={np} zone={nz}")

    payload = {
        "metadata": {
            "source": "Statistiche Regionali OMI Agenzia Entrate (Emilia-Romagna 2019-2024)",
            "url_pattern": "inumeridibolognametropolitana.it/.../sr<YEAR>_emilia_romagna.pdf",
            "publication_lag_note": "SR<YEAR>.pdf contiene dati anno <YEAR-1>",
            "years_covered": sorted(set(years)),
            "parser": "scripts/parse-volumi-ade-v3.py (pdfplumber, header-aware)",
            "metric_keys": {
                "ntn": "Numero Transazioni Normalizzate (volume scambi)",
                "ntn_var_pct": "var % NTN vs anno precedente",
                "imi_pct": "Intensità Mercato Immobiliare (NTN/Stock %)",
                "imi_diff": "delta IMI vs anno precedente (punti %)",
                "quota_pct": "quota macroarea sul totale provincia",
                "quotazione_eur_mq": "€/m² (solo zone OMI)",
                "quotazione_var_pct": "var % quotazione (solo zone OMI)",
            },
        },
        "provincia_series": prov_all,
        "zone_series": zone_all,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    LOG_FILE.write_text('\n'.join(log))
    print('\n'.join(log))
    print(f"\n→ {OUT_JSON} ({OUT_JSON.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
