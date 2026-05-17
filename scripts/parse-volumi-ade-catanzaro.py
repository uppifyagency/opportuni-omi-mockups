#!/usr/bin/env python3
"""Parser Statistiche Regionali AdE — Calabria → Provincia di Catanzaro.

Fork di parse-volumi-ade-final.py (Modena) con adattamenti:
  - MACROAREE_KNOWN: 10 macroaree CZ + alias "CATANZARO" / "TOTALE PROVINCIA"
  - Normalizzazione varianti dei nomi (S.Eufemia / S. Eufemia, –/-)
  - Find pages: skip indice (i<5) per evitare match falso nel TOC
  - Zone OMI: range esteso p_com+0..+10 (per Catanzaro le zone sono in pagine ~+5..+8)
  - COL_MAPS per 9 anni (2017→2025)
  - Validation: stessa logica Modena, asserts allentati per provincia piccola

Output: data/volumi/catanzaro-volumi-timeseries.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "data" / "volumi"
OUT_JSON = PDF_DIR / "catanzaro-volumi-timeseries.json"
LOG_FILE = PDF_DIR / "parse-log-catanzaro.txt"

# FIX P7: soglia per quarantinare righe con NTN_var % oltre la quale il dato
# è quasi sicuramente artefatto di un NTN < 1 nell'anno precedente (variazioni reali
# nel real estate residenziale non superano mai i +500%/anno su volumi normali).
NTN_VAR_QUARANTINE_THRESHOLD = 500.0

# Le 10 macroaree provinciali di Catanzaro + alias totale.
# Tutte le varianti vengono normalizzate a una forma canonica (vedi normalize_macroarea).
MACROAREE_CANON = {
    "ASSE S. EUFEMIA - CZ",
    "BASSO IONIO CATANZARESE",
    "CATANZARO CAPOLUOGO",
    "COSTA DI CAPO SUVERO",
    "COSTA DI SOVERATO",
    "FOCI TACINA, CORACE E VALLE SIMERI",
    "GOLFO DI SQUILLACE - ZONA MONTANA",
    "LAMEZIA TERME",
    "PRESILA - REVENTINO",
    "ZONA PARCO ARCHEOLOGICO \"SCHILLACIUM\"",
}
PROVINCE_TOTAL_NAMES = {"CATANZARO", "TOTALE PROVINCIA"}


def normalize_macroarea(name: str) -> str | None:
    """Normalizza varianti spazi/dashes in forma canonica."""
    if not name: return None
    s = re.sub(r'\s+', ' ', str(name).strip().upper().replace('\n', ' '))
    # Unify dash em/en/hyphen
    s = s.replace('–', '-').replace('—', '-')
    # Unify "S.EUFEMIA" vs "S. EUFEMIA"
    s = re.sub(r'\bS\.(?=[A-Z])', 'S. ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    # Map alias Catanzaro variants
    if s in ('ASSE S. EUFEMIA - CATANZARO', 'ASSE S. EUFEMIA -CATANZARO'):
        return 'ASSE S. EUFEMIA - CZ'
    if s in MACROAREE_CANON or s in PROVINCE_TOTAL_NAMES:
        return s
    # Fuzzy: rimuovi spazi extra/punti e riconfronta
    s2 = re.sub(r'[.\s]+', ' ', s).strip()
    for canon in MACROAREE_CANON | PROVINCE_TOTAL_NAMES:
        canon2 = re.sub(r'[.\s]+', ' ', canon).strip()
        if s2 == canon2:
            return canon
    return None


# ─── COLUMN MAPS PER YEAR (verified empirically on Calabria PDFs) ───────
# Format: {sr_year: {'provincia': {col_idx: field}, 'zone': {col_idx: field}}}
# field names canonici (stessi di Modena): ntn, ntn_var_pct, imi_pct, imi_diff, quota_pct
COL_MAPS = {
    2017: {  # dati 2016 — dense 6 cols
        'provincia': {1: 'ntn', 2: 'ntn_var_pct', 3: 'quota_pct', 4: 'imi_pct', 5: 'imi_diff'},
        'zone':      {2: 'ntn', 3: 'ntn_var_pct', 4: 'imi_pct', 5: 'quotazione_eur_mq', 6: 'quotazione_var_pct'},
    },
    2018: {  # dati 2017
        'provincia': {1: 'ntn', 2: 'ntn_var_pct', 3: 'quota_pct', 4: 'imi_pct', 5: 'imi_diff'},
        'zone':      {2: 'ntn', 3: 'ntn_var_pct', 4: 'imi_pct', 5: 'quotazione_eur_mq', 6: 'quotazione_var_pct'},
    },
    2019: {  # dati 2018
        'provincia': {1: 'ntn', 2: 'ntn_var_pct', 3: 'quota_pct', 4: 'imi_pct', 5: 'imi_diff'},
        'zone':      {2: 'ntn', 3: 'ntn_var_pct', 4: 'imi_pct', 5: 'quotazione_eur_mq', 6: 'quotazione_var_pct'},
    },
    2020: {  # dati 2019 — sparse 11 cols con None tra valori
        'provincia': {1: 'ntn', 4: 'ntn_var_pct', 6: 'quota_pct', 8: 'imi_pct', 10: 'imi_diff'},
        'zone':      {2: 'ntn', 5: 'ntn_var_pct', 7: 'imi_pct', 9: 'quotazione_eur_mq', 11: 'quotazione_var_pct'},
    },
    2021: {  # dati 2020 — dense 6 cols, ordine [NTN, NTN_var, IMI, IMI_diff, Quota]
        'provincia': {1: 'ntn', 2: 'ntn_var_pct', 3: 'imi_pct', 4: 'imi_diff', 5: 'quota_pct'},
        'zone':      {2: 'ntn', 3: 'ntn_var_pct', 4: 'imi_pct', 5: 'quotazione_eur_mq', 6: 'quotazione_var_pct'},
    },
    2022: {  # dati 2021 — sparse
        'provincia': {1: 'ntn', 2: 'ntn_var_pct', 5: 'imi_diff', 8: 'imi_pct', 10: 'quota_pct'},
        'zone':      {2: 'ntn', 3: 'ntn_var_pct', 4: 'imi_pct', 5: 'quotazione_eur_mq', 6: 'quotazione_var_pct'},
    },
    2023: {  # dati 2022 — 9 cols mix
        'provincia': {1: 'ntn', 2: 'ntn_var_pct', 5: 'imi_pct', 6: 'imi_diff', 7: 'quota_pct'},
        'zone':      {2: 'ntn', 3: 'ntn_var_pct', 4: 'imi_pct', 5: 'quotazione_eur_mq', 6: 'quotazione_var_pct'},
    },
    2024: {  # dati 2023 — sparse 10 cols
        'provincia': {1: 'ntn', 2: 'ntn_var_pct', 5: 'imi_pct', 6: 'imi_diff', 9: 'quota_pct'},
        'zone':      {2: 'ntn', 3: 'ntn_var_pct', 4: 'imi_pct', 5: 'quotazione_eur_mq', 6: 'quotazione_var_pct'},
    },
    2025: {  # dati 2024 — 8 cols
        'provincia': {1: 'ntn', 2: 'ntn_var_pct', 5: 'imi_pct', 6: 'imi_diff', 7: 'quota_pct'},
        'zone':      {2: 'ntn', 3: 'ntn_var_pct', 4: 'imi_pct', 5: 'quotazione_eur_mq', 6: 'quotazione_var_pct'},
    },
}


def parse_italian_number(s):
    if s is None: return None
    if not isinstance(s, str): s = str(s)
    s = s.strip().rstrip('%').strip()
    if s in ('', '-', 'n.d.', 'nd', '—', '–'): return None
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


def find_catanzaro_pages(pdf):
    """Find pages 'La provincia – Catanzaro', 'Il comune – Catanzaro', e il boundary
    della provincia successiva (Cosenza/Crotone/Reggio C./Vibo) per evitare
    cross-contamination cross-provincia (FIX P1).

    Returns: (p_prov, p_com, p_boundary)
    p_boundary = indice 0-based della PRIMA pagina della provincia successiva.
    Lo zone parser deve scansionare strettamente [p_com, p_boundary).
    """
    p_prov, p_com, p_boundary = None, None, None
    for i, page in enumerate(pdf.pages):
        if i < 5: continue
        try:
            text = (page.extract_text() or "")[:2000]
        except Exception:
            continue
        if p_prov is None and re.search(r'(La provincia|Provincia)\s*[-–]\s*Catanzaro', text, re.I):
            p_prov = i
            continue
        if p_com is None and re.search(r'(Il comune|Comune)\s*[-–]\s*Catanzaro', text, re.I):
            p_com = i
            continue
        if p_com is not None and p_boundary is None:
            m = re.search(r'(La provincia|Provincia|Il comune|Comune)\s*[-–]\s*(\w+)', text, re.I)
            if m and m.group(2).lower() != 'catanzaro':
                p_boundary = i
    if p_boundary is None:
        p_boundary = len(pdf.pages)
    return p_prov, p_com, p_boundary


def parse_provincia(pdf, page_idx, sr_year, data_year, log):
    """Estrae righe macroaree dalla pagina della provincia."""
    rows = []
    col_map = COL_MAPS[sr_year]['provincia']
    # Try 3 pages (some tabular layouts span)
    for pi in [page_idx, page_idx + 1, page_idx + 2]:
        if pi >= len(pdf.pages): continue
        for table in pdf.pages[pi].extract_tables() or []:
            if not table or len(table) < 2: continue
            for tr in table:
                if not tr or not tr[0]: continue
                canon = normalize_macroarea(tr[0])
                if canon is None: continue
                level = 'macroarea' if canon in MACROAREE_CANON else 'provincia'
                row = {
                    "year": data_year,
                    "level": level,
                    "name": canon,
                }
                for col_idx, field in col_map.items():
                    if col_idx < len(tr):
                        row[field] = parse_italian_number(tr[col_idx])
                if row.get('ntn') is not None:
                    rows.append(row)
    # Dedup per (year, name) — preferisci la riga con più campi non-null
    by_key = {}
    for r in rows:
        k = (r['year'], r['name'])
        prev = by_key.get(k)
        if prev is None or sum(1 for v in r.values() if v is not None) > sum(1 for v in prev.values() if v is not None):
            by_key[k] = r
    return list(by_key.values())


def parse_zone(pdf, page_idx, page_boundary, sr_year, data_year, log):
    """Estrae righe zone OMI. Per Catanzaro le tabelle sono sparse su 4-8 pagine dopo 'Il comune'.
    page_boundary = indice 0-based della prima pagina della provincia successiva (FIX P1).
    """
    rows = []
    col_map = COL_MAPS[sr_year]['zone']
    # FIX P1: scansiona STRETTAMENTE [page_idx, page_boundary) — niente sconfinamento Cosenza
    for pi in range(page_idx, page_boundary):
        for table in pdf.pages[pi].extract_tables() or []:
            if not table or len(table) < 2: continue
            for tr in table:
                if not tr or not tr[0]: continue
                first = str(tr[0]).strip()
                if not re.match(r'^[A-Z]\d{1,2}$', first): continue
                cell1 = (tr[1] or "").strip().replace('\n', ' ') if len(tr) > 1 else ""
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
    # Dedup per (year, zona)
    by_key = {}
    for r in rows:
        k = (r['year'], r['zona'])
        prev = by_key.get(k)
        if prev is None or sum(1 for v in r.values() if v is not None) > sum(1 for v in prev.values() if v is not None):
            by_key[k] = r
    return list(by_key.values())


def assert_row_sane(row, log):
    """Per-row asserts: NTN ≥ 0, IMI ∈ [0,10], var ∈ [-90, +500], quotazione ∈ [200, 10000]."""
    issues = []
    nm = row.get('zona') or row.get('name')
    if row.get('ntn') is not None and row['ntn'] < 0:
        issues.append(f"NTN<0 {nm}={row['ntn']}")
    if row.get('imi_pct') is not None and not (0 <= row['imi_pct'] <= 10):
        issues.append(f"IMI fuori [0,10] {nm}={row['imi_pct']}")
    if row.get('ntn_var_pct') is not None and not (-100 <= row['ntn_var_pct'] <= 500):
        issues.append(f"NTN_var fuori [-100,500] {nm}={row['ntn_var_pct']}")
    if row.get('quotazione_eur_mq') is not None and not (200 <= row['quotazione_eur_mq'] <= 10000):
        issues.append(f"Quotazione fuori [200,10000] {nm}={row['quotazione_eur_mq']}")
    for i in issues: log.append(f"    ⚠ {i}")
    return len(issues)


def parse_year(pdf_path, log):
    sr_year = int(re.search(r'sr(\d{4})', pdf_path.name).group(1))
    data_year = sr_year - 1
    log.append(f"\n═══ SR{sr_year} → data_year={data_year} ═══")
    pdf = pdfplumber.open(str(pdf_path))
    p_prov, p_com, p_boundary = find_catanzaro_pages(pdf)
    if p_prov is None:
        log.append(f"  ✗ 'La provincia - Catanzaro' page not found")
        pdf.close()
        return None
    log.append(f"  pages: prov@{p_prov+1}, com@{p_com+1 if p_com else 'none'}, boundary@{p_boundary+1} (next-province start)")

    prov = parse_provincia(pdf, p_prov, sr_year, data_year, log)
    zone = parse_zone(pdf, p_com or p_prov, p_boundary, sr_year, data_year, log) if p_com is not None else []

    issues_count = 0
    for r in prov + zone:
        issues_count += assert_row_sane(r, log)
    log.append(f"  ✓ parsed prov={len(prov)} (macroaree={sum(1 for r in prov if r['level']=='macroarea')}), zone={len(zone)}, sanity_issues={issues_count}")

    # Cross-check NTN totale provincia = sum macroaree
    macros = [r for r in prov if r['level'] == 'macroarea']
    tot = next((r for r in prov if r['level'] == 'provincia'), None)
    if tot and macros and tot.get('ntn'):
        s = sum(r.get('ntn') or 0 for r in macros)
        gap_pct = abs(s - tot['ntn']) / tot['ntn'] * 100 if tot['ntn'] else 0
        mark = "✓" if gap_pct < 2 else "⚠"
        log.append(f"  {mark} cross-check NTN: sum_macroaree={s:.0f} totale={tot['ntn']:.0f} gap={gap_pct:.2f}%")

    pdf.close()
    return {"data_year": data_year, "provincia": prov, "zone": zone}


def cross_year_validation(prov_series, zone_series, log):
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
                if gap > 8:  # tolerance maggiore per CZ (NTN piccoli, normalization più rumorosa)
                    issues += 1
                    if issues <= 10:
                        log.append(f"  ⚠ {name} {prev_y}→{curr_y}: declared={declared_var:+.1f}% computed={computed_var:+.1f}% gap={gap:.1f}pp")
    log.append(f"  Total var-consistency issues (>8pp gap): {issues}")
    return issues


def main():
    log = ["═══ PARSE-VOLUMI CATANZARO (Calabria SR 2017→2025) ═══"]
    pdfs = sorted(PDF_DIR.glob("sr*_calabria.pdf"))
    log.append(f"PDF count: {len(pdfs)}")

    prov_all, zone_all, years = [], [], []
    for p in pdfs:
        r = parse_year(p, log)
        if r:
            prov_all.extend(r['provincia'])
            zone_all.extend(r['zone'])
            years.append(r['data_year'])

    log.append(f"\n═══ GLOBAL STATS ═══")
    log.append(f"Years covered: {sorted(set(years))} ({len(set(years))} years)")
    log.append(f"Provincia rows: {len(prov_all)} (avg {len(prov_all)/max(len(years),1):.1f}/yr)")
    log.append(f"Zone rows:      {len(zone_all)} (avg {len(zone_all)/max(len(years),1):.1f}/yr)")

    log.append(f"\nCoverage per anno:")
    for y in sorted(set(years)):
        np_ = sum(1 for r in prov_all if r['year'] == y)
        nz = sum(1 for r in zone_all if r['year'] == y)
        prov_macros = sorted({r['name'] for r in prov_all if r['year'] == y and r['level'] == 'macroarea'})
        has_total = any(r['year'] == y and r['level'] == 'provincia' for r in prov_all)
        log.append(f"  {y}: prov={np_} (totale={'sì' if has_total else 'NO'}, macroaree={len(prov_macros)}), zone={nz}")

    macro_set = sorted({r['name'] for r in prov_all if r['level'] == 'macroarea'})
    zone_set = sorted({r['zona'] for r in zone_all})
    log.append(f"\nMacroaree distinte ({len(macro_set)}): {macro_set}")
    missing = sorted(MACROAREE_CANON - set(macro_set))
    if missing:
        log.append(f"⚠ Missing macroaree: {missing}")
    log.append(f"\nZone OMI distinte ({len(zone_set)}): {zone_set}")

    log.append(f"\nValue ranges:")
    for field in ['ntn', 'imi_pct', 'ntn_var_pct', 'quotazione_eur_mq']:
        vals = [r[field] for r in prov_all + zone_all if r.get(field) is not None]
        if vals:
            log.append(f"  {field}: min={min(vals):.2f} max={max(vals):.2f} (n={len(vals)})")

    cross_year_validation(prov_all, zone_all, log)

    # FIX P7: separa righe con var % > threshold in _anomalies (sono reali nel PDF
    # ma generano outlier statistici causati da NTN < 1 nell'anno precedente).
    def is_anomaly_row(r):
        v = r.get('ntn_var_pct')
        return v is not None and abs(v) > NTN_VAR_QUARANTINE_THRESHOLD

    zone_anomalies = [r for r in zone_all if is_anomaly_row(r)]
    prov_anomalies = [r for r in prov_all if is_anomaly_row(r)]
    log.append(f"\n═══ FIX P7: QUARANTINE NTN_VAR > {NTN_VAR_QUARANTINE_THRESHOLD}% ═══")
    log.append(f"  Zone anomalies (mantenute in _anomalies, escluse da zone_series): {len(zone_anomalies)}")
    for r in zone_anomalies:
        log.append(f"    {r['zona']}/{r['year']}: NTN={r.get('ntn')} var={r.get('ntn_var_pct')}%")
    log.append(f"  Prov anomalies: {len(prov_anomalies)}")
    # NOTA: NON rimuoviamo da prov/zone_all — il dato NTN/IMI/quotazione resta valido,
    # è solo il var % a essere artefatto. La quarantine produce un campo separato
    # `_anomalies` che la UI può scegliere se nascondere/etichettare.

    payload = {
        "metadata": {
            "source": "Statistiche Regionali OMI Agenzia Entrate (Calabria SR 2017-2025)",
            "url_pattern": "https://www.agenziaentrate.gov.it/portale/documents/.../SR<YEAR>_Calabria.pdf",
            "publication_lag_note": "SR<YEAR>.pdf contiene i dati dell'anno <YEAR>-1",
            "years_covered": sorted(set(years)),
            "parser_version": "catanzaro-v2 (FIX P1 boundary + P7 anomalies + P11 const)",
            "fixes_applied": {
                "P1_cross_provincia_boundary": "parse_zone strettamente entro [p_com, p_boundary)",
                "P7_ntn_var_quarantine_threshold": NTN_VAR_QUARANTINE_THRESHOLD,
            },
            "metric_keys": {
                "ntn": "Numero Transazioni Normalizzate (volume scambi residenziali)",
                "ntn_var_pct": "Variazione % NTN vs anno precedente",
                "imi_pct": "Intensità Mercato Immobiliare (NTN/Stock immobili %)",
                "imi_diff": "Δ punti % IMI vs anno precedente",
                "quota_pct": "Quota % macroarea sul totale provincia",
                "quotazione_eur_mq": "Quotazione media €/m² (solo zone OMI)",
                "quotazione_var_pct": "Variazione % quotazione (solo zone OMI)",
            },
        },
        "provincia_series": prov_all,
        "zone_series": zone_all,
        "_anomalies": {
            "_doc": f"Righe con |NTN_var_pct| > {NTN_VAR_QUARANTINE_THRESHOLD}%: var è artefatto di NTN<1 nell'anno precedente (variazioni reali in real estate residenziale non superano +500%/anno). Le altre metriche (NTN, IMI, quotazione) sono valide.",
            "zone": zone_anomalies,
            "provincia": prov_anomalies,
        },
    }

    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    LOG_FILE.write_text('\n'.join(log))
    print('\n'.join(log))
    print(f"\n→ {OUT_JSON} ({OUT_JSON.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
