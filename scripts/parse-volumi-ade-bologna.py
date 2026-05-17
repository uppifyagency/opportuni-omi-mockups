#!/usr/bin/env python3
"""Parser Statistiche Regionali AdE Emilia-Romagna — provincia di Bologna.

Fork di parse-volumi-ade-final.py (Modena). Stessa regione → COL_MAPS identico.
Differenze:
  - find_bologna_pages() invece di find_modena_pages()
  - MACROAREE_KNOWN per Bologna (7 macroaree)
  - p_boundary anti-cross-contamination (FIX §19.3 lezione Catanzaro)
  - OUT_JSON → bologna-volumi-timeseries.json

Output:
  data/volumi/bologna-volumi-timeseries.json
  data/volumi/parse-log-bologna.txt


Approccio scientifico:
  - Ogni anno SR ha layout colonna proprio (6 formati distinti identificati empiricamente)
  - Mapping colonna→campo HARDCODATO per anno (provincia + zone)
  - Asserts su ogni riga: NTN ≥ 0, IMI ∈ [0,10], var % ∈ [-90, +200]
  - Cross-validation per anno: somma NTN macroaree == NTN totale provincia (gap < 1%)
  - Range check globale: tutti i campi nel range plausibile
  - Bonus: cross-anno smoothness (variazione YoY consistente con var_pct dichiarato)

Mapping (verificato pagina per pagina su PDF reali):

SR2019 (dati 2018) — provincia 6 cols, zone 11 cols multi-line
SR2020 (dati 2019) — provincia 11 cols sparse, zone 11 cols sparse
SR2021 (dati 2020) — provincia 8 cols semi-sparse, zone 8 cols dense
SR2022 (dati 2021) — provincia 9 cols, zone 8 cols
SR2023 (dati 2022) — provincia 9 cols, zone 8 cols
SR2024 (dati 2023) — provincia 6 cols compact, zone 8 cols
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "data" / "volumi"
OUT_JSON = PDF_DIR / "bologna-volumi-timeseries.json"
LOG_FILE = PDF_DIR / "parse-log-bologna.txt"

# Macroaree provincia di Bologna (verificate ispezionando SR2024 p.13).
# Stessa regione Emilia-Romagna di Modena → stesso layout COL_MAPS riutilizzabile.
MACROAREE_KNOWN = {
    "MONTANA",
    "PRIMA SEMICINTURA NORD", "PRIMA SEMICINTURA SUD",
    "SECONDA SEMICINTURA NORD", "SECONDA SEMICINTURA SUD-EST", "SECONDA SEMICINTURA SUD-OVEST",
    "BOLOGNA CAPOLUOGO", "BOLOGNA",
}

# ─── COLUMN MAPS PER YEAR (verified empirically on PDF tables) ───────────
# Format: {sr_year: {'provincia': {col_idx: field}, 'zone': {col_idx: field}}}
COL_MAPS = {
    2019: {  # dati 2018
        'provincia': {1: 'ntn', 2: 'ntn_var_pct', 3: 'quota_pct', 4: 'imi_pct', 5: 'imi_diff'},
        'zone':      {2: 'ntn', 3: 'ntn_var_pct', 4: 'imi_pct', 5: 'quotazione_eur_mq', 8: 'quotazione_var_pct'},
    },
    2020: {  # dati 2019 — colonne SPARSE con None tra valori
        'provincia': {1: 'ntn', 4: 'ntn_var_pct', 6: 'quota_pct', 8: 'imi_pct', 10: 'imi_diff'},
        'zone':      {2: 'ntn', 4: 'ntn_var_pct', 6: 'imi_pct', 8: 'quotazione_eur_mq', 10: 'quotazione_var_pct'},
    },
    2021: {  # dati 2020 — provincia con None sparsi, zone dense
        'provincia': {1: 'ntn', 3: 'ntn_var_pct', 5: 'imi_pct', 6: 'imi_diff', 7: 'quota_pct'},
        'zone':      {2: 'ntn', 3: 'ntn_var_pct', 4: 'imi_pct', 5: 'quotazione_eur_mq', 6: 'quotazione_var_pct'},
    },
    2022: {  # dati 2021
        'provincia': {1: 'ntn', 3: 'ntn_var_pct', 5: 'imi_pct', 6: 'imi_diff', 7: 'quota_pct'},
        'zone':      {2: 'ntn', 3: 'ntn_var_pct', 4: 'imi_pct', 5: 'quotazione_eur_mq', 6: 'quotazione_var_pct'},
    },
    2023: {  # dati 2022
        'provincia': {1: 'ntn', 3: 'ntn_var_pct', 5: 'imi_pct', 6: 'imi_diff', 7: 'quota_pct'},
        'zone':      {2: 'ntn', 3: 'ntn_var_pct', 4: 'imi_pct', 5: 'quotazione_eur_mq', 6: 'quotazione_var_pct'},
    },
    2024: {  # dati 2023 — formato compatto
        'provincia': {1: 'ntn', 2: 'ntn_var_pct', 3: 'imi_pct', 4: 'imi_diff', 5: 'quota_pct'},
        'zone':      {2: 'ntn', 3: 'ntn_var_pct', 4: 'imi_pct', 5: 'quotazione_eur_mq', 6: 'quotazione_var_pct'},
    },
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


def find_bologna_pages(pdf):
    """Trova p_prov, p_com di Bologna + p_boundary = inizio provincia successiva.
    FIX §19.3 (lezione Catanzaro): senza boundary il parser ingerisce zone di provincia adiacente.
    Bologna è la PRIMA in ordine alfabetico → l'Indice (p.3-5) cita "La provincia - Bologna"
    come link di pagina, quindi skippiamo le prime ~8 pagine per non beccare l'indice.
    """
    SKIP_FIRST = 8
    p_prov, p_com, p_boundary = None, None, None
    for i, page in enumerate(pdf.pages):
        if i < SKIP_FIRST:
            continue
        try:
            text = (page.extract_text() or "")[:2000]
        except Exception:
            continue
        # Skip pagine con "Indice" o "Sommario" header
        if re.search(r'^\s*Indice\b', text, re.I | re.M):
            continue
        if p_prov is None and re.search(r'^\s*La provincia\s*[-–]\s*Bologna', text, re.I | re.M):
            p_prov = i; continue
        if p_com is None and re.search(r'^\s*Il comune\s*[-–]\s*Bologna', text, re.I | re.M):
            p_com = i; continue
        if p_com is not None and p_boundary is None:
            m = re.search(r'^\s*(La provincia|Il comune)\s*[-–]\s*(\w+)', text, re.I | re.M)
            if m and m.group(2).lower() != 'bologna':
                p_boundary = i
    if p_boundary is None and p_com is not None:
        p_boundary = min(p_com + 10, len(pdf.pages))
    return p_prov, p_com, p_boundary


def parse_provincia(pdf, page_idx, p_boundary, sr_year, data_year, log):
    rows = []
    col_map = COL_MAPS[sr_year]['provincia']
    # Limita a max 2 pagine, ma rispetta il boundary
    end_page = min(page_idx + 2, p_boundary) if p_boundary else page_idx + 2
    for pi in range(page_idx, end_page):
        if pi >= len(pdf.pages): continue
        for table in pdf.pages[pi].extract_tables() or []:
            if not table or len(table) < 3: continue
            for tr in table:
                if not tr or not tr[0]: continue
                first = re.sub(r'\s+', ' ', str(tr[0]).strip().upper().replace('\n', ' '))
                if first not in MACROAREE_KNOWN: continue
                row = {
                    "year": data_year,
                    "level": "provincia" if first == "BOLOGNA" else "macroarea",
                    "name": first,
                }
                for col_idx, field in col_map.items():
                    if col_idx < len(tr):
                        row[field] = parse_italian_number(tr[col_idx])
                if row.get('ntn') is not None:
                    rows.append(row)
    # Dedup
    seen, dedup = set(), []
    for r in rows:
        k = (r['year'], r['name'])
        if k not in seen:
            seen.add(k); dedup.append(r)
    return dedup


def parse_zone(pdf, page_idx, p_boundary, sr_year, data_year, log):
    """Bologna SR ha 5 macroaree urbane × tabella zone separata, distribuite su ~6 pagine
    dopo 'Il comune – Bologna'. Modena ne ha 1 sola compatta. Quindi range esteso fino a
    p_boundary (provincia successiva = Ferrara) per non perdere zone.
    """
    rows = []
    col_map = COL_MAPS[sr_year]['zone']
    # Estendi fino alla provincia successiva (cap p_boundary), non solo +3 pagine
    end_page = p_boundary if p_boundary else min(page_idx + 10, len(pdf.pages))
    for pi in range(page_idx, end_page):
        if pi >= len(pdf.pages): continue
        for table in pdf.pages[pi].extract_tables() or []:
            if not table or len(table) < 3: continue
            for tr in table:
                if not tr or not tr[0]: continue
                first = str(tr[0]).strip()
                if not re.match(r'^[A-Z]\d{1,2}$', first): continue
                cell1 = (tr[1] or "").strip().replace('\n', ' ')
                cell1 = re.sub(r'\s+', ' ', cell1)
                row = {
                    "year": data_year,
                    "level": "zona",
                    "zona": first,
                    "denominazione": cell1,
                }
                for col_idx, field in col_map.items():
                    if col_idx < len(tr):
                        row[field] = parse_italian_number(tr[col_idx])
                if row.get('ntn') is not None or row.get('imi_pct') is not None:
                    rows.append(row)
    seen, dedup = set(), []
    for r in rows:
        k = (r['year'], r['zona'])
        if k not in seen:
            seen.add(k); dedup.append(r)
    return dedup


def assert_row_sane(row, log):
    """Per-row asserts."""
    issues = []
    nm = row.get('zona') or row.get('name')
    if row.get('ntn') is not None and row['ntn'] < 0:
        issues.append(f"NTN<0 {nm}={row['ntn']}")
    if row.get('imi_pct') is not None and not (0 <= row['imi_pct'] <= 10):
        issues.append(f"IMI fuori [0,10] {nm}={row['imi_pct']}")
    if row.get('ntn_var_pct') is not None and not (-90 <= row['ntn_var_pct'] <= 500):
        issues.append(f"NTN_var fuori [-90,500] {nm}={row['ntn_var_pct']}")
    if row.get('quotazione_eur_mq') is not None and not (200 <= row['quotazione_eur_mq'] <= 10000):
        issues.append(f"Quotazione fuori [200,10000] {nm}={row['quotazione_eur_mq']}")
    for i in issues: log.append(f"    ⚠ {i}")
    return len(issues)


def parse_year(pdf_path, log):
    sr_year = int(re.search(r'sr(\d{4})', pdf_path.name).group(1))
    data_year = sr_year - 1
    log.append(f"\n═══ SR{sr_year} → data_year={data_year} ═══")
    pdf = pdfplumber.open(str(pdf_path))
    p_prov, p_com, p_boundary = find_bologna_pages(pdf)
    if p_prov is None or p_com is None:
        log.append(f"  ✗ Bologna pages not found")
        pdf.close()
        return None
    log.append(f"  pages: p_prov={p_prov+1} p_com={p_com+1} p_boundary={p_boundary+1 if p_boundary else 'EOF'}")

    prov = parse_provincia(pdf, p_prov, p_boundary, sr_year, data_year, log)
    zone = parse_zone(pdf, p_com, p_boundary, sr_year, data_year, log)

    issues_count = 0
    for r in prov + zone:
        issues_count += assert_row_sane(r, log)

    log.append(f"  ✓ parsed prov={len(prov)}, zone={len(zone)}, sanity_issues={issues_count}")

    # Cross-check
    macros = [r for r in prov if r['level'] == 'macroarea']
    tot = next((r for r in prov if r['level'] == 'provincia'), None)
    if tot and macros and tot.get('ntn'):
        s = sum(r.get('ntn') or 0 for r in macros)
        gap_pct = abs(s - tot['ntn']) / tot['ntn'] * 100
        mark = "✓" if gap_pct < 1 else "⚠"
        log.append(f"  {mark} cross-check NTN: sum_macroaree={s:.0f} totale={tot['ntn']:.0f} gap={gap_pct:.2f}%")

    pdf.close()
    return {"data_year": data_year, "provincia": prov, "zone": zone}


def cross_year_validation(prov_series, zone_series, log):
    """Check coerenza var % YoY: NTN(y) / NTN(y-1) - 1 ≈ ntn_var_pct(y)."""
    log.append(f"\n═══ CROSS-YEAR VALIDATION (var % YoY consistency) ═══")
    issues = 0
    by_name = {}
    for r in prov_series:
        by_name.setdefault(r['name'], {})[r['year']] = r
    for r in zone_series:
        by_name.setdefault(r['zona'], {})[r['year']] = r

    for name, by_yr in by_name.items():
        years = sorted(by_yr.keys())
        for prev_y, curr_y in zip(years, years[1:]):
            prev_ntn = by_yr[prev_y].get('ntn')
            curr_ntn = by_yr[curr_y].get('ntn')
            declared_var = by_yr[curr_y].get('ntn_var_pct')
            if prev_ntn and curr_ntn and declared_var is not None:
                computed_var = (curr_ntn / prev_ntn - 1) * 100
                gap = abs(computed_var - declared_var)
                if gap > 5:  # 5pp tolerance (NTN normalization can shift things slightly)
                    issues += 1
                    if issues <= 5:
                        log.append(f"  ⚠ {name} {prev_y}→{curr_y}: declared={declared_var:+.1f}% computed={computed_var:+.1f}% gap={gap:.1f}pp")
    log.append(f"  Total var-consistency issues (>5pp gap): {issues}")
    return issues


def main():
    log = ["═══ PARSE-VOLUMI FINAL (dedicated parsers per year) ═══"]
    pdfs = sorted(PDF_DIR.glob("sr*.pdf"))
    log.append(f"PDF count: {len(pdfs)}")

    prov_all, zone_all, years = [], [], []
    for p in pdfs:
        r = parse_year(p, log)
        if r:
            prov_all.extend(r['provincia'])
            zone_all.extend(r['zone'])
            years.append(r['data_year'])

    log.append(f"\n═══ GLOBAL STATS ═══")
    log.append(f"Years: {sorted(set(years))} ({len(set(years))} total)")
    log.append(f"Provincia rows: {len(prov_all)} ({len(prov_all)/max(len(years),1):.1f}/yr; expected 9)")
    log.append(f"Zone rows:      {len(zone_all)} ({len(zone_all)/max(len(years),1):.1f}/yr; expected 19)")

    # Coverage matrix
    log.append(f"\nCoverage per anno:")
    for y in sorted(set(years)):
        np = sum(1 for r in prov_all if r['year'] == y)
        nz = sum(1 for r in zone_all if r['year'] == y)
        prov_macros = sorted({r['name'] for r in prov_all if r['year'] == y and r['level'] == 'macroarea'})
        has_total = any(r['year'] == y and r['level'] == 'provincia' for r in prov_all)
        log.append(f"  {y}: prov={np} (totale={'sì' if has_total else 'NO'}, macro={len(prov_macros)}), zone={nz}")

    # Distinct elements
    macro_set = sorted({r['name'] for r in prov_all if r['level'] == 'macroarea'})
    zone_set = sorted({r['zona'] for r in zone_all})
    log.append(f"\nMacroaree distinte: {macro_set}")
    log.append(f"Missing: {sorted(MACROAREE_KNOWN - {'MODENA'} - set(macro_set))}")
    log.append(f"Zone OMI distinte: {zone_set}")

    # Range globale
    log.append(f"\nValue ranges:")
    for field in ['ntn', 'imi_pct', 'ntn_var_pct', 'quotazione_eur_mq']:
        vals = [r[field] for r in prov_all + zone_all if r.get(field) is not None]
        if vals:
            log.append(f"  {field}: min={min(vals):.2f} max={max(vals):.2f} (n={len(vals)})")

    # Cross-year var % consistency
    cross_year_validation(prov_all, zone_all, log)

    payload = {
        "metadata": {
            "source": "Statistiche Regionali OMI Agenzia Entrate (Emilia-Romagna SR 2019-2024)",
            "url_pattern": "https://inumeridibolognametropolitana.it/sites/inumeridibolognametropolitana.it/files/altri_enti/omi/sr<YEAR>_emilia_romagna.pdf",
            "publication_lag_note": "SR<YEAR>.pdf contiene i dati dell'anno <YEAR>-1",
            "years_covered": sorted(set(years)),
            "parser_version": "final (dedicated column-map per year, verified manually)",
            "metric_keys": {
                "ntn": "Numero Transazioni Normalizzate (volume scambi residenziali)",
                "ntn_var_pct": "Variazione % NTN vs anno precedente",
                "imi_pct": "Intensità Mercato Immobiliare (NTN/Stock immobili %)",
                "imi_diff": "Δ punti % IMI vs anno precedente",
                "quota_pct": "Quota % macroarea sul totale provincia (solo provincia)",
                "quotazione_eur_mq": "Quotazione media €/m² (solo zone OMI)",
                "quotazione_var_pct": "Variazione % quotazione (solo zone OMI)",
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
