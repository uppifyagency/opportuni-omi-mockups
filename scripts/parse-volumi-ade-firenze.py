#!/usr/bin/env python3
"""Parser Statistiche Regionali AdE Toscana - provincia di Firenze.

Fork di parse-volumi-ade-reggio-emilia.py. Differenze fondamentali:
  - regione TOSCANA → COL_MAPS Firenze-specific (verificate empiricamente)
  - MACROAREE_PROV_KNOWN: 8 macroaree provinciali + 4 alias totale
  - MACROAREE_URBANE_KNOWN: 9 macroaree urbane Firenze (no OMI zone codes come Reggio)
  - parse_macroaree_urbane invece di parse_zone con regex `^[A-Z]\d+$`
    (Firenze SR aggrega zone OMI in macroaree URBANE NAMED, non codici)
  - quotazione_eur_mq: tabella SEPARATA per Firenze (estratta separatamente)

Per il mapping con zone OMI Sagona (codici come B3/C9/D34): vedi
  data/volumi/zone-mapping-old-new-firenze.json (mapping macroarea→[OMI zone codes])
  costruito manualmente dopo lo scarico Sagona+GeoPOI.

Output:
  data/volumi/firenze-volumi-timeseries.json
  data/volumi/parse-log-firenze.txt

COL_MAPS verificate su 7 PDF reali (sr2019..sr2025):

  PROVINCIA
    2019: 6 cols  {1:ntn, 2:var, 3:quota, 4:imi, 5:diff}
    2020: 11 cols sparse {1:ntn, 4:var, 6:quota, 8:imi, 10:diff}
    2021: 8 cols  {1:ntn, 2:var, 5:imi, 6:diff, 7:quota}
    2022: 6 cols  {1:ntn, 2:var, 3:imi, 4:diff, 5:quota}
    2023: 9 cols  {1:ntn, 2:var, 5:imi, 6:diff, 7:quota}
    2024: 6 cols  {1:ntn, 2:var, 3:imi, 4:diff, 5:quota}
    2025: 6 cols  {1:ntn, 2:var, 3:imi, 4:diff, 5:quota}

  COMUNE (macroaree urbane)
    2019: 6 cols  {1:ntn, 2:var, 3:quota, 4:imi, 5:diff}
    2020: 10 cols sparse {1:ntn, 3:var, 5:quota, 7:imi, 9:diff}
    2021: 11 cols sparse {1:ntn, 2:var, 5:imi, 6:diff, 9:quota}
    2022: 6 cols  {1:ntn, 2:var, 3:imi, 4:diff, 5:quota}
    2023: 7 cols  {1:ntn, 2:var, 3:imi, 4:diff, 5:quota}
    2024: 6 cols  {1:ntn, 2:var, 3:imi, 4:diff, 5:quota}
    2025: 6 cols  {1:ntn, 2:var, 3:imi, 4:diff, 5:quota}
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "data" / "volumi"
OUT_JSON = PDF_DIR / "firenze-volumi-timeseries.json"
LOG_FILE = PDF_DIR / "parse-log-firenze.txt"

# Macroaree provincia Firenze (verificate ispezionando sr2024 p.15).
# FIRENZE CAPOLUOGO compare come riga provincia da sr2024 in poi (negli anni precedenti
# il capoluogo era separato in tabelle dedicate). Il parser ingerisce qualsiasi alias presente.
MACROAREE_PROV_KNOWN = {
    "ALTO MUGELLO",
    "BASSO MUGELLO",
    "CHIANTI",
    "CINTURA FIORENTINA",
    "EMPOLESE VAL D'ELSA",
    "PIANA",
    "VALDARNO",
    "FIRENZE CAPOLUOGO",
}
# Alias totale provincia: variano per anno
PROV_TOTAL_ALIASES = {
    "FIRENZE",
    "FIRENZE PROVINCIA",
    "PROVINCIA DI FIRENZE",
    "TOTALE PROVINCIA",
}

# Macroaree urbane comune Firenze (verificate sr2024 p.19).
# 9 macroaree + "ND" (zone non determinate, da ignorare) + totale "FIRENZE".
MACROAREE_URBANE_KNOWN = {
    "CENTRO STORICO",
    "COLLINE DI PREGIO A NORD-EST",
    "COLLINE DI PREGIO A SUD",
    "EUROPA – BELLARIVA – VARLUNGO",
    "GALLUZZO – LE DUE STRADE",
    "ISOLOTTO – PONTE A GREVE",
    "NOVOLI – CASTELLO – RIFREDI",
    "PERETOLA – OSMANNORO",
    "SEMICENTRALE E CENTRALE DI PREGIO",
}
COMUNE_TOTAL_ALIASES = {"FIRENZE", "FIRENZE COMUNE"}

# ─── COLUMN MAPS PER YEAR (verified empirically) ───────────
COL_MAPS = {
    2019: {
        'provincia':       {1: 'ntn', 2: 'ntn_var_pct', 3: 'quota_pct', 4: 'imi_pct', 5: 'imi_diff'},
        'macroaree_urb':   {1: 'ntn', 2: 'ntn_var_pct', 3: 'quota_pct', 4: 'imi_pct', 5: 'imi_diff'},
    },
    2020: {
        'provincia':       {1: 'ntn', 4: 'ntn_var_pct', 6: 'quota_pct', 8: 'imi_pct', 10: 'imi_diff'},
        'macroaree_urb':   {1: 'ntn', 3: 'ntn_var_pct', 5: 'quota_pct', 7: 'imi_pct', 9: 'imi_diff'},
    },
    2021: {
        'provincia':       {1: 'ntn', 2: 'ntn_var_pct', 5: 'imi_pct', 6: 'imi_diff', 7: 'quota_pct'},
        'macroaree_urb':   {1: 'ntn', 2: 'ntn_var_pct', 5: 'imi_pct', 6: 'imi_diff', 9: 'quota_pct'},
    },
    2022: {
        'provincia':       {1: 'ntn', 2: 'ntn_var_pct', 3: 'imi_pct', 4: 'imi_diff', 5: 'quota_pct'},
        'macroaree_urb':   {1: 'ntn', 2: 'ntn_var_pct', 3: 'imi_pct', 4: 'imi_diff', 5: 'quota_pct'},
    },
    2023: {
        'provincia':       {1: 'ntn', 2: 'ntn_var_pct', 5: 'imi_pct', 6: 'imi_diff', 7: 'quota_pct'},
        'macroaree_urb':   {1: 'ntn', 2: 'ntn_var_pct', 3: 'imi_pct', 4: 'imi_diff', 5: 'quota_pct'},
    },
    2024: {
        'provincia':       {1: 'ntn', 2: 'ntn_var_pct', 3: 'imi_pct', 4: 'imi_diff', 5: 'quota_pct'},
        'macroaree_urb':   {1: 'ntn', 2: 'ntn_var_pct', 3: 'imi_pct', 4: 'imi_diff', 5: 'quota_pct'},
    },
    2025: {
        'provincia':       {1: 'ntn', 2: 'ntn_var_pct', 3: 'imi_pct', 4: 'imi_diff', 5: 'quota_pct'},
        'macroaree_urb':   {1: 'ntn', 2: 'ntn_var_pct', 3: 'imi_pct', 4: 'imi_diff', 5: 'quota_pct'},
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


def normalize_name(s):
    """Uppercase + collapse whitespace + normalize apostrophes and dashes."""
    if s is None: return ""
    s = re.sub(r'\s+', ' ', str(s).strip().upper().replace('\n', ' '))
    s = s.replace('’', "'").replace('‘', "'")
    # Normalize various dash characters to en-dash (which is what Firenze PDFs use)
    s = s.replace('—', '–').replace('-', '-')
    return s


def find_firenze_pages(pdf):
    """Find p_prov, p_com per Firenze + p_boundary = start of next province (Grosseto in Toscana).
    Toscana province alphabetical: Arezzo, Firenze, Grosseto, Livorno, Lucca, Massa-Carrara, Pisa, Pistoia, Prato, Siena.
    Firenze è la 2a → boundary è Grosseto.
    """
    SKIP_FIRST = 8
    p_prov, p_com, p_boundary = None, None, None
    re_prov = re.compile(r'^\s*La provincia\s*[-–]\s*Firenze', re.I | re.M)
    re_com  = re.compile(r'^\s*Il comune\s*[-–]\s*Firenze', re.I | re.M)
    for i, page in enumerate(pdf.pages):
        if i < SKIP_FIRST:
            continue
        try:
            text = (page.extract_text() or "")[:2000]
        except Exception:
            continue
        if re.search(r'^\s*Indice\b', text, re.I | re.M):
            continue
        if p_prov is None and re_prov.search(text):
            p_prov = i; continue
        if p_com is None and re_com.search(text):
            p_com = i; continue
        if p_com is not None and p_boundary is None:
            m = re.search(r'^\s*(La provincia|Il comune)\s*[-–]\s*(\w+)', text, re.I | re.M)
            if m and m.group(2).lower() != 'firenze':
                p_boundary = i
    if p_boundary is None and p_com is not None:
        p_boundary = min(p_com + 10, len(pdf.pages))
    return p_prov, p_com, p_boundary


def parse_provincia(pdf, page_idx, p_boundary, sr_year, data_year, log):
    rows = []
    col_map = COL_MAPS[sr_year]['provincia']
    end_page = min(page_idx + 2, p_boundary) if p_boundary else page_idx + 2
    for pi in range(page_idx, end_page):
        if pi >= len(pdf.pages): continue
        for table in pdf.pages[pi].extract_tables() or []:
            if not table or len(table) < 3: continue
            for tr in table:
                if not tr or not tr[0]: continue
                first = normalize_name(tr[0])
                is_macro = first in MACROAREE_PROV_KNOWN
                is_total = first in PROV_TOTAL_ALIASES
                if not (is_macro or is_total): continue
                row = {
                    "year": data_year,
                    "level": "provincia" if is_total else "macroarea",
                    "name": first if is_macro else "FIRENZE PROVINCIA",
                }
                for col_idx, field in col_map.items():
                    if col_idx < len(tr):
                        row[field] = parse_italian_number(tr[col_idx])
                if row.get('ntn') is not None:
                    rows.append(row)
    seen, dedup = set(), []
    for r in rows:
        k = (r['year'], r['name'])
        if k not in seen:
            seen.add(k); dedup.append(r)
    return dedup


def parse_macroaree_urbane(pdf, page_idx, p_boundary, sr_year, data_year, log):
    """Firenze SR comune: tabella macroaree urbane (9 named macroaree + totale).
    A differenza di Reggio/Bologna che usano codici OMI (B1, C2, ...), Firenze
    aggrega le zone OMI in macroaree denominate (CENTRO STORICO, NOVOLI, ecc.)."""
    rows = []
    col_map = COL_MAPS[sr_year]['macroaree_urb']
    end_page = p_boundary if p_boundary else min(page_idx + 10, len(pdf.pages))
    for pi in range(page_idx, end_page):
        if pi >= len(pdf.pages): continue
        for table in pdf.pages[pi].extract_tables() or []:
            if not table or len(table) < 3: continue
            for tr in table:
                if not tr or not tr[0]: continue
                first = normalize_name(tr[0])
                is_macro = first in MACROAREE_URBANE_KNOWN
                is_total = first in COMUNE_TOTAL_ALIASES
                if not (is_macro or is_total): continue
                row = {
                    "year": data_year,
                    "level": "comune" if is_total else "macroarea_urbana",
                    "macroarea": first if is_macro else "FIRENZE COMUNE",
                }
                for col_idx, field in col_map.items():
                    if col_idx < len(tr):
                        row[field] = parse_italian_number(tr[col_idx])
                if row.get('ntn') is not None:
                    rows.append(row)
    seen, dedup = set(), []
    for r in rows:
        k = (r['year'], r['macroarea'])
        if k not in seen:
            seen.add(k); dedup.append(r)
    return dedup


def parse_quotazioni_urbane(pdf, page_idx, p_boundary, sr_year, data_year, log):
    """Tabella separata (cols=3): Macroarea | Quotazione €/m² | Variazione %.
    Trovata in sr2019..sr2025 sulla pagina del comune. Estratta separatamente per
    consentire join volumi NTN ↔ prezzi nel mockup C."""
    rows = []
    end_page = p_boundary if p_boundary else min(page_idx + 10, len(pdf.pages))
    for pi in range(page_idx, end_page):
        if pi >= len(pdf.pages): continue
        for table in pdf.pages[pi].extract_tables() or []:
            if not table or len(table) < 3: continue
            hdr = ' '.join(str(c or '') for c in table[0]).upper()
            # Identifica la tabella quotazioni dalla header
            if 'QUOTAZIONE' not in hdr and 'EUR' not in hdr and '€/M' not in hdr.replace(' ',''):
                continue
            for tr in table:
                if not tr or not tr[0]: continue
                first = normalize_name(tr[0])
                if first not in MACROAREE_URBANE_KNOWN and first not in COMUNE_TOTAL_ALIASES:
                    continue
                # Trova il primo numero plausibile (€/m²) e il secondo (var%)
                vals = [parse_italian_number(c) for c in tr[1:]]
                vals = [v for v in vals if v is not None]
                if not vals: continue
                q = next((v for v in vals if 500 <= v <= 15000), None)
                v_pct = next((v for v in vals if -50 <= v <= 50 and v != q), None)
                if q is None: continue
                rows.append({
                    "year": data_year,
                    "macroarea": first if first in MACROAREE_URBANE_KNOWN else "FIRENZE COMUNE",
                    "quotazione_eur_mq": q,
                    "quotazione_var_pct": v_pct,
                })
    seen, dedup = set(), []
    for r in rows:
        k = (r['year'], r['macroarea'])
        if k not in seen:
            seen.add(k); dedup.append(r)
    return dedup


def assert_row_sane(row, log):
    issues = []
    nm = row.get('macroarea') or row.get('name')
    if row.get('ntn') is not None and row['ntn'] < 0:
        issues.append(f"NTN<0 {nm}={row['ntn']}")
    if row.get('imi_pct') is not None and not (0 <= row['imi_pct'] <= 10):
        issues.append(f"IMI fuori [0,10] {nm}={row['imi_pct']}")
    if row.get('ntn_var_pct') is not None and not (-90 <= row['ntn_var_pct'] <= 500):
        issues.append(f"NTN_var fuori [-90,500] {nm}={row['ntn_var_pct']}")
    if row.get('quotazione_eur_mq') is not None and not (200 <= row['quotazione_eur_mq'] <= 15000):
        issues.append(f"Quotazione fuori [200,15000] {nm}={row['quotazione_eur_mq']}")
    for i in issues: log.append(f"    ⚠ {i}")
    return len(issues)


def parse_year(pdf_path, log):
    sr_year = int(re.search(r'sr(\d{4})', pdf_path.name).group(1))
    data_year = sr_year - 1
    log.append(f"\n═══ SR{sr_year} → data_year={data_year} ═══")
    pdf = pdfplumber.open(str(pdf_path))
    p_prov, p_com, p_boundary = find_firenze_pages(pdf)
    if p_prov is None or p_com is None:
        log.append(f"  ✗ Firenze pages not found")
        pdf.close()
        return None
    log.append(f"  pages: p_prov={p_prov+1} p_com={p_com+1} p_boundary={p_boundary+1 if p_boundary else 'EOF'}")

    prov = parse_provincia(pdf, p_prov, p_boundary, sr_year, data_year, log)
    macro_urb = parse_macroaree_urbane(pdf, p_com, p_boundary, sr_year, data_year, log)
    quot_urb = parse_quotazioni_urbane(pdf, p_com, p_boundary, sr_year, data_year, log)

    # Join quotazioni in macro_urb rows
    quot_idx = {(r['year'], r['macroarea']): r for r in quot_urb}
    for r in macro_urb:
        q = quot_idx.get((r['year'], r['macroarea']))
        if q:
            r['quotazione_eur_mq'] = q['quotazione_eur_mq']
            r['quotazione_var_pct'] = q['quotazione_var_pct']

    issues_count = 0
    for r in prov + macro_urb:
        issues_count += assert_row_sane(r, log)

    log.append(f"  ✓ parsed prov={len(prov)}, macroaree_urb={len(macro_urb)}, quotazioni={len(quot_urb)}, issues={issues_count}")

    # Cross-check NTN: sum macroaree ≈ totale provincia
    macros = [r for r in prov if r['level'] == 'macroarea' and r['name'] != 'FIRENZE CAPOLUOGO']
    tot = next((r for r in prov if r['level'] == 'provincia'), None)
    cap = next((r for r in prov if r['name'] == 'FIRENZE CAPOLUOGO'), None)
    if tot and macros and tot.get('ntn'):
        s = sum(r.get('ntn') or 0 for r in macros)
        if cap: s += cap.get('ntn') or 0
        gap_pct = abs(s - tot['ntn']) / tot['ntn'] * 100
        mark = "✓" if gap_pct < 5 else "⚠"
        log.append(f"  {mark} cross-check NTN provincia: sum={s:.0f} totale={tot['ntn']:.0f} gap={gap_pct:.2f}%")

    # Cross-check NTN comune: sum macroaree_urbane ≈ totale FIRENZE COMUNE
    macros_urb = [r for r in macro_urb if r['level'] == 'macroarea_urbana']
    tot_com = next((r for r in macro_urb if r['level'] == 'comune'), None)
    if tot_com and macros_urb and tot_com.get('ntn'):
        s = sum(r.get('ntn') or 0 for r in macros_urb)
        gap_pct = abs(s - tot_com['ntn']) / tot_com['ntn'] * 100
        mark = "✓" if gap_pct < 5 else "⚠"
        log.append(f"  {mark} cross-check NTN comune: sum={s:.0f} totale={tot_com['ntn']:.0f} gap={gap_pct:.2f}%")

    pdf.close()
    return {"data_year": data_year, "provincia": prov, "macroaree_urbane": macro_urb}


def cross_year_validation(prov_series, macro_urb_series, log):
    log.append(f"\n═══ CROSS-YEAR VALIDATION (var % YoY consistency) ═══")
    issues = 0
    by_name = {}
    for r in prov_series:
        by_name.setdefault(r['name'], {})[r['year']] = r
    for r in macro_urb_series:
        by_name.setdefault(r['macroarea'], {})[r['year']] = r

    for name, by_yr in by_name.items():
        years = sorted(by_yr.keys())
        for prev_y, curr_y in zip(years, years[1:]):
            prev_ntn = by_yr[prev_y].get('ntn')
            curr_ntn = by_yr[curr_y].get('ntn')
            declared_var = by_yr[curr_y].get('ntn_var_pct')
            if prev_ntn and curr_ntn and declared_var is not None:
                computed_var = (curr_ntn / prev_ntn - 1) * 100
                gap = abs(computed_var - declared_var)
                if gap > 5:
                    issues += 1
                    if issues <= 8:
                        log.append(f"  ⚠ {name} {prev_y}→{curr_y}: declared={declared_var:+.1f}% computed={computed_var:+.1f}% gap={gap:.1f}pp")
    log.append(f"  Total var-consistency issues (>5pp gap): {issues}")
    return issues


def main():
    log = ["═══ PARSE-VOLUMI-FIRENZE (Toscana SR 2019-2025) ═══"]
    pdfs = sorted(PDF_DIR.glob("sr*_toscana.pdf"))
    log.append(f"PDF count: {len(pdfs)}")

    prov_all, macro_urb_all, years = [], [], []
    for p in pdfs:
        r = parse_year(p, log)
        if r:
            prov_all.extend(r['provincia'])
            macro_urb_all.extend(r['macroaree_urbane'])
            years.append(r['data_year'])

    log.append(f"\n═══ GLOBAL STATS ═══")
    log.append(f"Years: {sorted(set(years))} ({len(set(years))} total)")
    log.append(f"Provincia rows: {len(prov_all)} ({len(prov_all)/max(len(years),1):.1f}/yr)")
    log.append(f"Macroaree urbane rows: {len(macro_urb_all)} ({len(macro_urb_all)/max(len(years),1):.1f}/yr; expected ~10)")

    log.append(f"\nCoverage per anno:")
    for y in sorted(set(years)):
        np = sum(1 for r in prov_all if r['year'] == y)
        nm = sum(1 for r in macro_urb_all if r['year'] == y)
        prov_macros = sorted({r['name'] for r in prov_all if r['year'] == y and r['level'] == 'macroarea'})
        has_total = any(r['year'] == y and r['level'] == 'provincia' for r in prov_all)
        log.append(f"  {y}: prov={np} (totale={'sì' if has_total else 'NO'}, macro={len(prov_macros)}), macro_urb={nm}")

    macro_set = sorted({r['name'] for r in prov_all if r['level'] == 'macroarea'})
    urb_set = sorted({r['macroarea'] for r in macro_urb_all if r['level'] == 'macroarea_urbana'})
    log.append(f"\nMacroaree provincia distinte: {macro_set}")
    log.append(f"Missing macroaree provincia: {sorted(MACROAREE_PROV_KNOWN - set(macro_set))}")
    log.append(f"Macroaree urbane distinte: {urb_set}")
    log.append(f"Missing macroaree urbane: {sorted(MACROAREE_URBANE_KNOWN - set(urb_set))}")

    log.append(f"\nValue ranges:")
    for field in ['ntn', 'imi_pct', 'ntn_var_pct', 'quotazione_eur_mq']:
        vals = [r[field] for r in prov_all + macro_urb_all if r.get(field) is not None]
        if vals:
            log.append(f"  {field}: min={min(vals):.2f} max={max(vals):.2f} (n={len(vals)})")

    cross_year_validation(prov_all, macro_urb_all, log)

    payload = {
        "metadata": {
            "source": "Statistiche Regionali OMI Agenzia Entrate (Toscana SR 2019-2025)",
            "url_pattern": "https://www.agenziaentrate.gov.it/portale/documents/20143/<docid>/SR<YEAR>_Toscana.pdf",
            "publication_lag_note": "SR<YEAR>.pdf contiene i dati dell'anno <YEAR>-1",
            "years_covered": sorted(set(years)),
            "parser_version": "firenze v1 (column-map per year + named macroaree urbane)",
            "note_structurale": "A differenza di Modena/Bologna/Reggio, Firenze SR aggrega zone OMI in macroaree urbane denominate. Mapping macroarea→[OMI zone codes] in zone-mapping-old-new-firenze.json (manuale).",
            "metric_keys": {
                "ntn": "Numero Transazioni Normalizzate",
                "ntn_var_pct": "Variazione % NTN vs anno precedente",
                "imi_pct": "Intensità Mercato Immobiliare (NTN/Stock %)",
                "imi_diff": "Δ punti % IMI vs anno precedente",
                "quota_pct": "Quota % macroarea sul totale (provincia o comune)",
                "quotazione_eur_mq": "Quotazione media €/m² (macroaree urbane only)",
                "quotazione_var_pct": "Variazione % quotazione",
            },
        },
        "provincia_series": prov_all,
        "macroaree_urbane_series": macro_urb_all,
    }

    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    LOG_FILE.write_text('\n'.join(log))
    print('\n'.join(log))
    print(f"\n→ {OUT_JSON} ({OUT_JSON.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
