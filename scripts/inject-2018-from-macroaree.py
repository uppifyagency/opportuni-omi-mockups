#!/usr/bin/env python3
"""inject-2018-from-macroaree.py — colma il buco zone OMI 2018 di Catanzaro.

Contesto:
  AdE SR2019 (data_year=2018) ha pubblicato il comune di Catanzaro NON a livello
  zona OMI singola (come gli altri 8 anni), ma aggregato in 5 macroaree urbane
  comunali (Centro / Semicentro / Prima Periferia / Zona Ovest / Zona Nord).

  Le 5 macroaree danno NTN totale 439 (2018) vs 340 (2017) = +29.1% comunale.
  Per ricostruire il NTN 2018 di ogni singola zona OLD:
     NTN_2018(zona) = NTN_2017(zona) × (NTN_2018(macroarea) / NTN_2017(macroarea))

Output:
  Aggiorna data/volumi/catanzaro-volumi-timeseries.json aggiungendo
  righe year=2018 con flag `_interpolated: true` per ogni zona OLD mappata.

IMPORTANTE:
  Il CAGR (last/first)^(1/years) - 1 è MATEMATICAMENTE INVARIANTE rispetto ai
  valori intermedi. Iniettare 2018 NON cambia il CAGR di nessuna zona. Migliora:
    - continuità sparkline UI
    - volatilità CV (+1 punto serie)
    - cross-year validation (issues drop ~75%)
    - momentum tag su finestre ricenti

Run:
  python3 scripts/inject-2018-from-macroaree.py
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TS_JSON = ROOT / "data" / "volumi" / "catanzaro-volumi-timeseries.json"

# Fattori macroarea NTN 2018/2017 (estratti da SR2018.pdf e SR2019.pdf, parsed)
MACROAREA_FACTOR = {
    'CENTRO':          177 / 116,   # 1.5259
    'SEMICENTRO':      8 / 7,       # 1.1429
    'PRIMA PERIFERIA': 102 / 49,    # 2.0816
    'ZONA OVEST':      139 / 153,   # 0.9085
    'ZONA NORD':       13 / 15,     # 0.8667
    'TOTALE_COMUNE':   439 / 340,   # 1.2912 (fallback per zone Lido/rurali)
}

# Mapping zona OLD → macroarea (basato su denominazione + fascia OMI Catanzaro)
ZONE_TO_MACROAREA = {
    # B-fascia (centro storico/città) → CENTRO
    'B1': 'CENTRO', 'B2': 'CENTRO', 'B3': 'CENTRO', 'B4': 'CENTRO',
    'B5': 'CENTRO', 'B6': 'CENTRO', 'B7': 'CENTRO',
    # C-fascia (semicentro) → SEMICENTRO
    'C1': 'SEMICENTRO', 'C2': 'SEMICENTRO', 'C3': 'SEMICENTRO',
    'C4': 'SEMICENTRO', 'C5': 'SEMICENTRO',
    # D-fascia urbana — assegnazione per denominazione
    'D1':  'ZONA OVEST',        # Piano Casa, CZ Sala (ovest)
    'D2':  'PRIMA PERIFERIA',   # Cava, Campagnella (verificato spazialmente: D22)
    'D3':  'PRIMA PERIFERIA',   # Siano (est)
    'D4':  'PRIMA PERIFERIA',   # Pontegrande - Pitera (sud)
    'D5':  'PRIMA PERIFERIA',   # Pistoia
    'D6':  'PRIMA PERIFERIA',   # S.Maria centro
    'D7':  'PRIMA PERIFERIA',   # Corvo
    'D11': 'ZONA NORD',         # Gagliano (NW)
    'D12': 'PRIMA PERIFERIA',   # S.Elia
    # Zone Lido/rurali → fallback TOTALE_COMUNE (non coperte dalle 5 macroaree urbane)
    'D8':  'TOTALE_COMUNE',
    'D9':  'TOTALE_COMUNE',
    'D10': 'TOTALE_COMUNE',
    'D13': 'TOTALE_COMUNE',
    'E3':  'ZONA OVEST',        # Insediamenti produttivi - Università (ovest)
    'R1':  'TOTALE_COMUNE',
    'R2':  'PRIMA PERIFERIA',   # Zona rurale fra Barone e S.Maria
    'R3':  'TOTALE_COMUNE',
}


def linear_interp(v_prev, v_next):
    """Interpolazione lineare semplice per imi_pct (i valori cambiano lentamente)."""
    if v_prev is None and v_next is None:
        return None
    if v_prev is None:
        return v_next
    if v_next is None:
        return v_prev
    return (v_prev + v_next) / 2.0


def main():
    ts = json.loads(TS_JSON.read_text())
    rows = ts['zone_series']

    # Indicizza zone OLD per anno
    from collections import defaultdict
    by_zona = defaultdict(dict)
    for r in rows:
        by_zona[r['zona']][r['year']] = r

    new_rows_2018 = []
    skipped = []
    for zona, macroarea in ZONE_TO_MACROAREA.items():
        years = by_zona.get(zona, {})
        if not years:
            skipped.append((zona, 'no rows'))
            continue
        # Se 2018 esiste già (non dovrebbe per Catanzaro città, ma safety):
        if 2018 in years:
            skipped.append((zona, '2018 already present'))
            continue
        r2017 = years.get(2017)
        r2019 = years.get(2019)
        if not r2017 or r2017.get('ntn') is None:
            skipped.append((zona, 'no NTN 2017'))
            continue
        ntn17 = r2017['ntn']
        factor = MACROAREA_FACTOR[macroarea]
        ntn18 = round(ntn17 * factor, 1)

        # imi_pct: interp lineare tra 2017 e 2019
        imi17 = r2017.get('imi_pct')
        imi19 = r2019.get('imi_pct') if r2019 else None
        imi18 = linear_interp(imi17, imi19)
        if imi18 is not None:
            imi18 = round(imi18, 3)

        # quotazione: assumiamo costante (varia poco, e i dati 2017→2019 nei nostri
        # PDF mostrano sostanziale stabilità — vedi B6: 918 in 2017, 918 in 2019)
        q17 = r2017.get('quotazione_eur_mq')
        q19 = r2019.get('quotazione_eur_mq') if r2019 else None
        q18 = linear_interp(q17, q19)

        # var pct: declared = (n18/n17 - 1)*100
        var_pct = round((ntn18 / ntn17 - 1) * 100, 1) if ntn17 > 0 else None

        new_rows_2018.append({
            "year": 2018,
            "level": "zona",
            "zona": zona,
            "denominazione": r2017.get('denominazione'),
            "ntn": ntn18,
            "ntn_var_pct": var_pct,
            "imi_pct": imi18,
            "quotazione_eur_mq": q18,
            "quotazione_var_pct": 0.0,
            "_interpolated": True,
            "_interp_source": f"macroarea-downscaling[{macroarea}] factor={factor:.4f}",
        })

    rows.extend(new_rows_2018)

    # Update metadata
    ts.setdefault('metadata', {})['interpolation_2018'] = {
        '_doc': 'Righe 2018 ricostruite via macroaree-downscaling (vedi scripts/inject-2018-from-macroaree.py)',
        '_method': 'NTN_2018(zona) = NTN_2017(zona) × (NTN_2018_macroarea / NTN_2017_macroarea)',
        '_caveat': 'CAGR MATEMATICAMENTE INVARIANTE rispetto a questa iniezione (dipende solo da first, last, years_span)',
        'macroarea_factors': MACROAREA_FACTOR,
        'zone_to_macroarea': ZONE_TO_MACROAREA,
        'n_rows_injected': len(new_rows_2018),
        'n_rows_skipped': len(skipped),
        'skipped_reasons': dict(skipped) if skipped else {},
    }

    # Sort by zona, year per stabilità output
    ts['zone_series'] = sorted(rows, key=lambda r: (r['zona'], r['year']))

    TS_JSON.write_text(json.dumps(ts, indent=2, ensure_ascii=False))
    print(f"✓ Iniettate {len(new_rows_2018)} righe 2018 in {TS_JSON.name}")
    print(f"  skipped: {len(skipped)}")
    for z, reason in skipped:
        print(f"     {z}: {reason}")
    print(f"\nMath proof: CAGR di ogni zona OLD invariante (dipende solo da first/last/years_span).")
    print(f"Beneficio: sparkline UI continue, cross-year validation issues attesi drop ~75%.")


if __name__ == "__main__":
    main()
