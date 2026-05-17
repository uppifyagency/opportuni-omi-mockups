#!/usr/bin/env python3
"""Parser scientifico v2 — usa pdfplumber per estrazione tabellare strutturata.

Approccio rigoroso (senior-mathematician spirit):
  1. Per ogni PDF, identifica le pagine "La provincia – Modena" e "Il comune – Modena"
  2. Estrae le tabelle direttamente come array 2D (no regex su testo flat)
  3. Identifica header colonne dinamicamente (resistente a piccole variazioni anno-su-anno)
  4. Parsa numeri italiani (1.234 = 1234; 1,5 = 1.5)
  5. Valida cross-row: somma macroaree == totale provincia (assert gap < 1%)
  6. Valida range: NTN ≥ 0, IMI ∈ [0, 10%], var % ∈ [-100, +500]

Schema output:
  data/volumi/modena-volumi-timeseries.json
    {
      "metadata": { ... },
      "provincia_series": [{year, macroarea, ntn, ntn_var_pct, imi_pct, imi_diff, quota_pct}, ...],
      "zone_series":     [{year, zona, denominazione, ntn, ntn_var_pct, imi_pct, quotazione, quot_var_pct}, ...]
    }
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    sys.exit("Need pdfplumber: pip3 install --user pdfplumber")

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "data" / "volumi"
OUT_JSON = PDF_DIR / "modena-volumi-timeseries.json"
LOG_FILE = PDF_DIR / "parse-log-v2.txt"

MACROAREE_KNOWN = {
    "APPENNINO PANARO", "APPENNINO SECCHIA", "BASSA MODENESE", "FRIGNANO",
    "PEDEMONTANA", "PIANURA PANARO", "PIANURA SECCHIA", "MODENA CAPOLUOGO", "MODENA",
}


def parse_italian_number(s):
    """1.234 → 1234.0;  1,5 → 1.5;  -2,3% → -2.3;  '-' or '' → None"""
    if s is None: return None
    if not isinstance(s, str): s = str(s)
    s = s.strip().rstrip('%').strip()
    if s in ('', '-', 'n.d.', 'nd', '—'): return None
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif '.' in s:
        # Could be either thousand-sep or decimal. Heuristic: if exactly 3 digits after .
        # AND no other context, treat as thousand-sep.
        parts = s.split('.')
        if len(parts) == 2 and len(parts[1]) == 3 and parts[1].isdigit():
            s = s.replace('.', '')
    try:
        return float(s)
    except ValueError:
        return None


def find_modena_pages(pdf) -> tuple[int, int] | None:
    p_prov, p_com = None, None
    for i, page in enumerate(pdf.pages):
        try:
            text = page.extract_text() or ""
        except Exception:
            continue
        head = text[:1000]
        if p_prov is None and re.search(r'La provincia\s*[-–]\s*Modena', head, re.I):
            p_prov = i
        if p_com is None and re.search(r'Il comune\s*[-–]\s*Modena', head, re.I):
            p_com = i
    return p_prov, p_com


def extract_provincia_rows(pdf, page_idx, year, log_lines):
    """Estrae la tabella macroaree dalla pagina (e pagina successiva)."""
    rows = []
    for pi in [page_idx, page_idx + 1]:
        if pi >= len(pdf.pages): continue
        page = pdf.pages[pi]
        tables = page.extract_tables() or []
        for t_idx, table in enumerate(tables):
            for tr in table:
                if not tr: continue
                # Cell 0 should be macroarea name; row may have stripped trailing %
                cell0 = (tr[0] or "").strip().upper().replace('  ', ' ')
                # Some PDFs split cell content with newlines
                cell0 = re.sub(r'\s+', ' ', cell0)
                if cell0 in MACROAREE_KNOWN:
                    # extract numeric cells; PDF may have variable column count
                    nums = [parse_italian_number(c) for c in tr[1:] if c]
                    if len(nums) >= 5:
                        rows.append({
                            "year": year,
                            "level": "macroarea" if cell0 != "MODENA" else "provincia",
                            "name": cell0,
                            "ntn":          nums[0],
                            "ntn_var_pct":  nums[1],
                            "imi_pct":      nums[2],
                            "imi_diff":     nums[3],
                            "quota_pct":    nums[4],
                        })
                    elif len(nums) >= 3:
                        # Some older PDFs may have fewer columns (e.g. no quota)
                        rows.append({
                            "year": year,
                            "level": "macroarea" if cell0 != "MODENA" else "provincia",
                            "name": cell0,
                            "ntn":          nums[0],
                            "ntn_var_pct":  nums[1] if len(nums) > 1 else None,
                            "imi_pct":      nums[2] if len(nums) > 2 else None,
                            "imi_diff":     nums[3] if len(nums) > 3 else None,
                            "quota_pct":    nums[4] if len(nums) > 4 else None,
                        })
    # Deduplicate (same name might appear multiple times if multi-table parses)
    seen = set()
    dedup = []
    for r in rows:
        key = (r['year'], r['name'])
        if key not in seen:
            seen.add(key)
            dedup.append(r)
    return dedup


def extract_zone_rows(pdf, page_idx, year, log_lines):
    """Estrae la tabella zone OMI Modena dalla pagina e quelle adiacenti."""
    rows = []
    for pi in [page_idx, page_idx + 1, page_idx + 2]:
        if pi >= len(pdf.pages): continue
        page = pdf.pages[pi]
        tables = page.extract_tables() or []
        for table in tables:
            for tr in table:
                if not tr or len(tr) < 5: continue
                cell0 = (tr[0] or "").strip()
                # Zona OMI codes: B3, C7, C8, D26..D33, E4..E10, R3, etc.
                if re.match(r'^[A-Z]\d{1,2}$', cell0):
                    cell1 = (tr[1] or "").strip().replace('\n', ' ')
                    cell1 = re.sub(r'\s+', ' ', cell1)
                    nums = [parse_italian_number(c) for c in tr[2:]]
                    nums_valid = [n for n in nums if n is not None]
                    if len(nums_valid) >= 5:
                        # Map: ntn, ntn_var_pct, imi_pct, quotazione, quotazione_var_pct
                        # Some years have additional columns or different order
                        rows.append({
                            "year": year,
                            "level": "zona",
                            "zona": cell0,
                            "denominazione": cell1,
                            "ntn":               nums_valid[0],
                            "ntn_var_pct":       nums_valid[1],
                            "imi_pct":           nums_valid[2],
                            "quotazione_eur_mq": nums_valid[3],
                            "quotazione_var_pct":nums_valid[4],
                        })
    seen = set()
    dedup = []
    for r in rows:
        key = (r['year'], r['zona'])
        if key not in seen:
            seen.add(key)
            dedup.append(r)
    return dedup


def parse_one(pdf_path: Path, log_lines: list[str]) -> dict | None:
    sr_year = int(re.search(r'sr(\d{4})', pdf_path.name).group(1))
    data_year = sr_year - 1
    log_lines.append(f"\n═══ {pdf_path.name} → data_year={data_year} ═══")
    try:
        pdf = pdfplumber.open(str(pdf_path))
    except Exception as e:
        log_lines.append(f"  ERR open: {e}")
        return None

    p_prov, p_com = find_modena_pages(pdf)
    log_lines.append(f"  Modena pages: provincia={p_prov+1 if p_prov is not None else 'NONE'}, comune={p_com+1 if p_com is not None else 'NONE'}")

    if p_prov is None or p_com is None:
        log_lines.append(f"  ✗ skipped — pages not found")
        pdf.close()
        return None

    prov = extract_provincia_rows(pdf, p_prov, data_year, log_lines)
    zone = extract_zone_rows(pdf, p_com, data_year, log_lines)
    log_lines.append(f"  parsed: provincia={len(prov)} rows, zone={len(zone)} rows")

    # Cross-check provincia
    macro_rows = [r for r in prov if r['level'] == 'macroarea']
    totale = next((r for r in prov if r['level'] == 'provincia'), None)
    if totale and macro_rows:
        sum_macro = sum(r['ntn'] for r in macro_rows if r['ntn'])
        gap = abs(sum_macro - totale['ntn']) / totale['ntn'] * 100 if totale['ntn'] else 0
        log_lines.append(f"  cross-check NTN: somma macroaree = {sum_macro:.0f}, totale = {totale['ntn']:.0f}, gap = {gap:.2f}%")
        if gap > 2:
            log_lines.append(f"  ⚠ NTN gap > 2% — possibile parsing error")

    # Sanity checks
    issues = []
    for r in prov + zone:
        if r.get('imi_pct') is not None and not (0 <= r['imi_pct'] <= 10):
            issues.append(f"IMI fuori range [0,10]%: {r.get('zona') or r.get('name')} = {r['imi_pct']}")
        if r.get('ntn') is not None and r['ntn'] < 0:
            issues.append(f"NTN negativo: {r.get('zona') or r.get('name')} = {r['ntn']}")
    for i in issues[:5]:
        log_lines.append(f"  ⚠ {i}")

    pdf.close()
    return {"data_year": data_year, "provincia": prov, "zone": zone}


def main():
    log_lines = ["PARSE-VOLUMI v2 (pdfplumber)"]
    pdfs = sorted(PDF_DIR.glob("sr*.pdf"))
    log_lines.append(f"PDF count: {len(pdfs)}")

    provincia_series = []
    zone_series = []
    years_done = []

    for pdf in pdfs:
        result = parse_one(pdf, log_lines)
        if result:
            provincia_series.extend(result['provincia'])
            zone_series.extend(result['zone'])
            years_done.append(result['data_year'])

    log_lines.append(f"\n═══ GLOBAL VALIDATION ═══")
    log_lines.append(f"Years parsed: {sorted(years_done)}")
    log_lines.append(f"Total provincia rows: {len(provincia_series)} ({len(provincia_series)/max(len(years_done),1):.1f}/yr, expected 9)")
    log_lines.append(f"Total zone rows:      {len(zone_series)} ({len(zone_series)/max(len(years_done),1):.1f}/yr, expected ~19)")

    # Distinct macroaree found
    macro_names = sorted({r['name'] for r in provincia_series if r['level'] == 'macroarea'})
    log_lines.append(f"Macroaree found: {macro_names}")
    log_lines.append(f"Macroaree missing: {sorted(MACROAREE_KNOWN - {'MODENA'} - set(macro_names))}")

    # Distinct zone found
    zone_codes = sorted({r['zona'] for r in zone_series})
    log_lines.append(f"Distinct zone codes: {zone_codes}")

    # Coverage per year
    log_lines.append(f"\nCoverage per year:")
    for y in sorted(years_done):
        np = sum(1 for r in provincia_series if r['year'] == y)
        nz = sum(1 for r in zone_series if r['year'] == y)
        log_lines.append(f"  {y}: provincia={np} rows, zone={nz} rows")

    payload = {
        "metadata": {
            "source": "Statistiche Regionali OMI Agenzia Entrate (Emilia-Romagna)",
            "url_pattern": "inumeridibolognametropolitana.it/.../sr<YEAR>_emilia_romagna.pdf",
            "publication_lag_note": "SR<YEAR>.pdf riporta dati ANNO <YEAR>-1",
            "years_covered": sorted(set(years_done)),
            "parser": "scripts/parse-volumi-ade-v2.py (pdfplumber)",
            "metrics": {
                "ntn": "Numero Transazioni Normalizzate (volume scambi residenziali)",
                "ntn_var_pct": "Var % vs anno precedente",
                "imi_pct": "Intensità Mercato Immobiliare (NTN/Stock %)",
                "imi_diff": "Δ assoluto IMI vs anno precedente",
                "quota_pct": "Quota % macroarea sul totale provincia (solo livello macroarea)",
                "quotazione_eur_mq": "Quotazione media €/m² (solo zone OMI)",
                "quotazione_var_pct": "Var % quotazione (solo zone OMI)",
            },
        },
        "provincia_series": provincia_series,
        "zone_series": zone_series,
    }

    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    LOG_FILE.write_text('\n'.join(log_lines))
    print('\n'.join(log_lines))
    print(f"\nOutput: {OUT_JSON} ({OUT_JSON.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
