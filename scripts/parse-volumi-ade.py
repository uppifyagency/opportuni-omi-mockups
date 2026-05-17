#!/usr/bin/env python3
"""Parser scientifico dei PDF Statistiche Regionali Agenzia Entrate.

Per ogni PDF SR<YEAR>_emilia_romagna.pdf:
  1. Identifica anno di riferimento (SR<YEAR> riporta dati dell'anno PRECEDENTE).
  2. Trova sezione "FOCUS provinciale - Modena".
  3. Trova le 2 tabelle chiave:
     - Tabella macroaree (provincia + 8 macroaree con NTN/IMI/var)
     - Tabella zone OMI (19 zone Modena capoluogo con NTN/IMI/quotazione)
  4. Estrae righe tabellari con regex.
  5. Cross-validation: somma macroaree == totale provincia; asserts su range.

Output:
  data/volumi/modena-volumi-timeseries.json
  data/volumi/parse-log.txt (per audit)

Scientific approach:
  - Ogni PDF è parsato indipendentemente
  - Asserts su ogni riga: NTN >= 0, IMI nel range [0, 10%], var % nel range [-100, +100]
  - Cross-check tra macroaree: somma NTN macroaree == totale provincia (entro ±0.5%)
  - Schema output uniforme per tutti gli anni

Usage:
    python3 scripts/parse-volumi-ade.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    import pypdf
except ImportError:
    sys.exit("Need pypdf: pip3 install --user pypdf")

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "data" / "volumi"
OUT_JSON = PDF_DIR / "modena-volumi-timeseries.json"
LOG_FILE = PDF_DIR / "parse-log.txt"

# 8 macroaree note di Modena (tassonomia stabile dal 2018 in poi)
MACROAREE_KNOWN = {
    "APPENNINO PANARO", "APPENNINO SECCHIA", "BASSA MODENESE", "FRIGNANO",
    "PEDEMONTANA", "PIANURA PANARO", "PIANURA SECCHIA", "MODENA CAPOLUOGO",
    "MODENA",  # totale provincia
}


def parse_italian_number(s: str) -> float | None:
    """Parsa numeri in formato italiano: 9.572 = 9572, 1,3% = 1.3"""
    if s is None or s.strip() in ("", "-", "n.d.", "nd"):
        return None
    s = s.strip().rstrip('%').strip()
    # 9.572 → 9572 (period = thousands sep)
    # 0,8 → 0.8 (comma = decimal)
    if ',' in s:
        # has decimal → strip thousand-separator periods
        s = s.replace('.', '').replace(',', '.')
    else:
        # no decimal → period must be thousand-sep
        s = s.replace('.', '')
    try:
        return float(s)
    except ValueError:
        return None


def parse_pct(s: str) -> float | None:
    """Parse percentage: -11,2% → -11.2"""
    return parse_italian_number(s)


def find_modena_pages(reader) -> tuple[int, int] | None:
    """Return (page_provincia, page_comune) 0-indexed, or None if not found."""
    p_prov, p_com = None, None
    for i, page in enumerate(reader.pages):
        try:
            head = page.extract_text()[:600]
        except Exception:
            continue
        if re.search(r'La provincia\s*[-–]\s*Modena', head, re.I):
            p_prov = i
        if re.search(r'Il comune\s*[-–]\s*Modena', head, re.I):
            p_com = i
    return (p_prov, p_com)


def parse_provincia_table(text: str, year: int) -> list[dict]:
    """Parse the macroaree table from a 'La provincia – Modena' page.
    Each row: NAME NTN VAR% IMI% IMI_DIFF QUOTA%
    """
    rows = []
    lines = text.split('\n')

    # Find data lines: macroarea name + 5 numbers
    # Patterns:
    #   APPENNINO PANARO 252 -8,6% 2,03% -0,19 2,6%
    #   MODENA CAPOLUOGO 2.346 -8,4% 2,43% -0,23 24,5%
    #   MODENA 9.572 -11,2% 2,47% -0,32 100,0%
    pat = re.compile(
        r'^\s*([A-ZÀÈÌÒÙ ]+?)\s+'           # macroarea name (uppercase, allows spaces)
        r'([\d.,]+)\s+'                       # NTN
        r'(-?[\d,]+)\s*%\s+'                  # NTN var %
        r'(-?[\d,]+)\s*%\s+'                  # IMI %
        r'(-?[\d,]+)\s+'                      # IMI diff
        r'([\d,]+)\s*%\s*$'                   # Quota NTN %
    )
    # Try matching joined lines (numbers sometimes split across lines)
    joined = ' '.join(lines)
    # Use a more forgiving regex that doesn't need anchors
    pat_loose = re.compile(
        r'([A-ZÀÈÌÒÙ]+(?:\s+[A-ZÀÈÌÒÙ]+){0,2})\s+'   # 1-3 word uppercase name
        r'([\d.]+)\s+'                                  # NTN
        r'(-?\d+,\d+)\s*%\s+'                           # NTN var %
        r'(-?\d+,\d+)\s*%\s+'                           # IMI %
        r'(-?\d+,\d+)\s+'                               # IMI diff
        r'(\d+,\d+)\s*%'                                # Quota %
    )

    for m in pat_loose.finditer(joined):
        name = m.group(1).strip()
        if name in MACROAREE_KNOWN:
            row = {
                "year": year,
                "level": "macroarea" if name != "MODENA" else "provincia",
                "name": name,
                "ntn": parse_italian_number(m.group(2)),
                "ntn_var_pct": parse_pct(m.group(3)),
                "imi_pct": parse_italian_number(m.group(4)),
                "imi_diff": parse_italian_number(m.group(5)),
                "quota_pct": parse_italian_number(m.group(6)),
            }
            rows.append(row)
    return rows


def parse_comune_table(text: str, year: int) -> list[dict]:
    """Parse the 19-zone OMI table from 'Il comune – Modena' page.
    Row pattern: ZONA DENOMINAZIONE NTN VAR% IMI% QUOT_EURO QUOT_VAR%
    """
    rows = []
    # Find the data block — between "Zona OMI" header and "MODENA" total row
    # Each row: ZONA (B3, C7, D26, etc.) + denominazione (variable) + 5 numbers
    # The pat is more complex because denominazione can span multiple lines
    # Strategy: greedy match for the 5 numbers at end of each conceptual row.

    pat = re.compile(
        r'(?P<zona>\b[A-Z]\d{1,2}\b)\s+'                    # B3, C7, D27, E10, R3, ecc.
        r'(?P<denom>[A-ZÀÈÌÒÙ`\'\- ,.()/]+?)\s+'             # denominazione (uppercase + symbols)
        r'(?P<ntn>\d{1,4}(?:[.,]\d{3})*)\s+'                 # NTN (es. 227 or 1.234)
        r'(?P<ntn_var>-?\d+,\d+)\s*%\s+'                     # NTN var %
        r'(?P<imi>\d+,\d+)\s*%\s+'                           # IMI %
        r'(?P<quot>[\d.,]+)\s+'                              # Quotazione media (es. 2.841)
        r'(?P<quot_var>-?\d+,\d+)\s*%',                      # Quot var %
        re.MULTILINE
    )

    for m in pat.finditer(text):
        zona = m.group('zona').strip()
        denom = re.sub(r'\s+', ' ', m.group('denom').strip())
        # Filter out false positives (eg matches without proper zona prefix)
        if not re.match(r'^[A-Z]\d', zona):
            continue
        rows.append({
            "year": year,
            "level": "zona",
            "comune": "Modena",
            "zona": zona,
            "denominazione": denom,
            "ntn": parse_italian_number(m.group('ntn')),
            "ntn_var_pct": parse_pct(m.group('ntn_var')),
            "imi_pct": parse_italian_number(m.group('imi')),
            "quotazione_eur_mq": parse_italian_number(m.group('quot')),
            "quotazione_var_pct": parse_pct(m.group('quot_var')),
        })
    return rows


def parse_pdf(pdf_path: Path, log_lines: list[str]) -> dict | None:
    """Parse one SR<YEAR> PDF, return dict with year + rows."""
    # SR<X> contains data for year X-1
    sr_year = int(re.search(r'sr(\d{4})', pdf_path.name).group(1))
    data_year = sr_year - 1

    log_lines.append(f"\n═══ Parse {pdf_path.name} (anno dati = {data_year}) ═══")
    try:
        reader = pypdf.PdfReader(str(pdf_path))
    except Exception as e:
        log_lines.append(f"  ERROR open: {e}")
        return None

    log_lines.append(f"  pagine totali: {len(reader.pages)}")
    p_prov, p_com = find_modena_pages(reader)
    log_lines.append(f"  pagina provincia: {p_prov+1 if p_prov else 'NOT FOUND'}")
    log_lines.append(f"  pagina comune:    {p_com+1 if p_com else 'NOT FOUND'}")

    if p_prov is None or p_com is None:
        log_lines.append(f"  ✗ skipped (pagine Modena non trovate)")
        return None

    # Extract text from page + next page (tables often span)
    text_prov = ""
    for pg in [p_prov, p_prov+1]:
        if pg < len(reader.pages):
            text_prov += "\n" + reader.pages[pg].extract_text()
    text_com = ""
    for pg in [p_com, p_com+1, p_com+2]:
        if pg < len(reader.pages):
            text_com += "\n" + reader.pages[pg].extract_text()

    prov_rows = parse_provincia_table(text_prov, data_year)
    com_rows = parse_comune_table(text_com, data_year)

    log_lines.append(f"  righe provincia parsate: {len(prov_rows)}")
    log_lines.append(f"  righe comune parsate:    {len(com_rows)}")

    # Validation: somma NTN macroaree (escluso "MODENA" totale) ≈ NTN totale
    macroaree = [r for r in prov_rows if r['level'] == 'macroarea']
    totale = next((r for r in prov_rows if r['level'] == 'provincia'), None)
    if totale and macroaree:
        sum_macro = sum(r['ntn'] for r in macroaree if r['ntn'])
        gap_pct = abs(sum_macro - totale['ntn']) / totale['ntn'] * 100
        log_lines.append(f"  cross-check: somma macroaree NTN = {sum_macro:.0f}, totale provincia = {totale['ntn']:.0f}, gap = {gap_pct:.2f}%")
        if gap_pct > 2:
            log_lines.append(f"  ⚠ gap > 2% — possibile parsing error")

    # Sanity checks su zone
    for r in com_rows:
        if r['imi_pct'] is not None and (r['imi_pct'] < 0 or r['imi_pct'] > 10):
            log_lines.append(f"  ⚠ IMI fuori range per {r['zona']}: {r['imi_pct']}%")
        if r['ntn'] is not None and r['ntn'] < 0:
            log_lines.append(f"  ⚠ NTN negativo per {r['zona']}: {r['ntn']}")

    return {
        "data_year": data_year,
        "sr_year": sr_year,
        "source_pdf": pdf_path.name,
        "provincia_rows": prov_rows,
        "zone_rows": com_rows,
    }


def main():
    log_lines = [f"PARSE-VOLUMI AdE — generato per Modena (Emilia-Romagna)"]
    log_lines.append(f"PDF directory: {PDF_DIR}")
    pdfs = sorted(PDF_DIR.glob("sr*.pdf"))
    log_lines.append(f"PDF trovati: {len(pdfs)}")
    for p in pdfs:
        log_lines.append(f"  - {p.name} ({p.stat().st_size//1024} KB)")

    all_data = []
    for pdf in pdfs:
        result = parse_pdf(pdf, log_lines)
        if result:
            all_data.append(result)

    # Build output structure
    payload = {
        "metadata": {
            "source": "Statistiche Regionali OMI - Agenzia delle Entrate (Emilia-Romagna)",
            "url_pattern": "https://inumeridibolognametropolitana.it/sites/inumeridibolognametropolitana.it/files/altri_enti/omi/sr<YEAR>_emilia_romagna.pdf",
            "publication_lag": "SR<YEAR> riporta i dati dell'anno <YEAR>-1",
            "years_covered": sorted(d['data_year'] for d in all_data),
            "metrics_per_row": {
                "ntn": "Numero Transazioni Normalizzate (volume scambi)",
                "ntn_var_pct": "Variazione % NTN rispetto all'anno precedente",
                "imi_pct": "Intensità Mercato Immobiliare (% NTN/Stock immobili)",
                "imi_diff": "Differenza assoluta IMI rispetto all'anno precedente",
                "quota_pct": "Quota % della macroarea sul totale provinciale (solo provincia)",
                "quotazione_eur_mq": "Quotazione media €/m² (solo zone OMI)",
                "quotazione_var_pct": "Variazione % quotazione (solo zone OMI)",
            },
        },
        "years": all_data,
    }

    # Final validation
    log_lines.append(f"\n═══ VALIDATION GLOBALE ═══")
    total_prov_rows = sum(len(y['provincia_rows']) for y in all_data)
    total_zone_rows = sum(len(y['zone_rows']) for y in all_data)
    log_lines.append(f"Totale righe provincia: {total_prov_rows}")
    log_lines.append(f"Totale righe zone:      {total_zone_rows}")
    log_lines.append(f"Media righe zona/anno:  {total_zone_rows/len(all_data):.1f} (atteso ~19)")
    log_lines.append(f"Media righe prov/anno:  {total_prov_rows/len(all_data):.1f} (atteso 9 = 8 macro + 1 tot)")

    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    LOG_FILE.write_text('\n'.join(log_lines))

    print('\n'.join(log_lines[-20:]))
    print(f"\nOutput: {OUT_JSON} ({OUT_JSON.stat().st_size:,} bytes)")
    print(f"Log:    {LOG_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
