# Opportuni — OMI Province Mockups

Tre dashboard HTML statiche per analizzare il mercato immobiliare di una **intera provincia italiana**, alimentate da dati pubblici OMI (Agenzia delle Entrate) con 20+ anni di storia.

**Province incluse:**
- **Modena** (`F257`, ISTAT 036) — 47 comuni
- **Catanzaro** (`C352`, ISTAT 079) — 80 comuni
- **Bologna** (`A944`, ISTAT 037) — 55 comuni
- **Reggio Emilia** (`H223`, ISTAT 035) — in lavorazione

Stack: Python stdlib + HTML/CSS/JS vanilla + MapLibre GL per i mockup; per l'audit math-proof, numpy/scipy/statsmodels/pymoo/networkx/polars/simpy/matplotlib. **Nessun framework UI**, nessun build step, nessuna API key. Costo zero.

> **Audit math-proof:** ogni numero esposto è ricalcolabile dal CSV grezzo Sagona. Il protocollo (10 gruppi di test, 6 figure publication-quality per città) è descritto in [`REPLICATE-FOR-OTHER-PROVINCE.md` §20](REPLICATE-FOR-OTHER-PROVINCE.md). Esito attuale: **64 PASS · 0 FAIL · 6 WARN** su 70 test (Modena 22/0/0 · Bologna 23/0/2 · Catanzaro 19/0/4) — vedi [`docs/audit/REPORT-CROSS-CITY.md`](docs/audit/REPORT-CROSS-CITY.md).

## I tre mockup

| Mockup | File | Cosa mostra |
|---|---|---|
| **A — Investor Brief** | `mockups/*-A-brief.html` | Tabella ranking densa, 3 segnali narrativi, KPI strip, sparkline SVG. Stile editorial bloomberg-lite. |
| **B — Heat Map First** | `mockups/*-B-heatmap.html` | Mappa provincia + mappa zone capoluogo. Hero MapLibre, sparkline grid, insight cards. |
| **C — Investment Compass** | `mockups/*-C-compass.html` | Score composito 0–100 con 6 componenti (growth, yield, stability, momentum, level, liquidity), verdict BUY/WATCH/AVOID, weight sliders runtime, anomaly detection, k-NN comparables, what-if simulator. |

Ogni numero è **pre-computato in Python** e validato con assert prima del rendering. Il frontend non fa aritmetica.

## Avvio veloce (zero setup)

```bash
git clone https://github.com/uppifyagency/opportuni-omi-mockups.git
cd opportuni-omi-mockups
python3 -m http.server 8765
```

Poi apri:
- http://localhost:8765/mockups/investor-A-brief.html (Modena)
- http://localhost:8765/mockups/investor-B-heatmap.html
- http://localhost:8765/mockups/investor-C-compass.html
- http://localhost:8765/mockups/catanzaro-A-brief.html
- http://localhost:8765/mockups/catanzaro-B-heatmap.html
- http://localhost:8765/mockups/catanzaro-C-compass.html

I JSON pre-computati in `data/computed/` e i GeoJSON in `data/geojson/` sono già pronti — i mockup funzionano out-of-the-box.

In alternativa:

```bash
make serve   # python3 -m http.server 8765
make open    # apre i 6 mockup nel browser
```

## Architettura

```
┌──────────────────────────────────────────────────────────┐
│  3 SORGENTI DATI ESTERNE (tutte pubbliche, CC-BY)        │
│  1. Sagona API (3eurotools.it) — wrapper OMI Ag.Entrate │
│  2. GeoPOI (Ag.Entrate) — poligoni zone OMI capoluogo   │
│  3. openpolis/geojson-italy — confini comuni provincia  │
│  4. AdE PDF "Statistiche Regionali" — volumi NTN/IMI    │
└──────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────┐
│  SCRIPT PYTHON (in scripts/, solo stdlib)                │
│  ETL                                                     │
│  ├ sagona-backfill.py        → prezzi.csv               │
│  ├ geopoi-zone-extract.py    → <city>-zone-omi.geojson  │
│  └ parse-volumi-ade*.py      → <city>-volumi.json       │
│  COMPUTE                                                 │
│  ├ compute-modena-signals.py     → modena-signals.json  │
│  ├ compute-catanzaro-signals.py  → catanzaro-signals.json│
│  ├ compute-compass.py            → <city>-compass.json  │
│  └ compute-volume-signals*.py    → <city>-volume-signals.json│
└──────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────┐
│  6 DASHBOARD HTML STATICHE (mockups/, nessun framework)  │
│  python3 -m http.server 8765                             │
└──────────────────────────────────────────────────────────┘
```

## Rigenerare i dati o aggiungere una provincia

Tutto il workflow è documentato passo-passo in **[REPLICATE-FOR-OTHER-PROVINCE.md](REPLICATE-FOR-OTHER-PROVINCE.md)** (76KB, autosufficiente).

In sintesi (esempio: aggiungere Bologna, Belfiore `A944`, ISTAT `037`):

```bash
# 1. Confini comuni (CC-BY openpolis)
curl -sL -o data/geojson/bologna-province-comuni.geojson \
  "https://raw.githubusercontent.com/openpolis/geojson-italy/master/geojson/limits_P_37_municipalities.geojson"

# 2. Backfill prezzi OMI per provincia (~50 min, una tantum)
python3 -c "import json; print(' '.join(sorted({f['properties']['com_catasto_code'] for f in json.load(open('data/geojson/bologna-province-comuni.geojson'))['features']})))" \
  | xargs python3 scripts/sagona-backfill.py

# 3. Zone OMI del capoluogo
python3 scripts/geopoi-zone-extract.py \
  --codcom A944 --prov BO --semestre 20252 \
  --prezzi-csv data/sagona-backfill/prezzi.csv \
  --out data/geojson/bologna-zone-omi.geojson

# 4. Compute (richiede edit minore degli script — vedi REPLICATE doc)
python3 scripts/compute-bologna-signals.py
python3 scripts/compute-compass.py --city bologna --codcom A944

# 5. Duplica i mockup HTML cambiando: codice comune, nome città, map center
cp mockups/investor-A-brief.html mockups/bologna-A-brief.html
# (edit Modena → Bologna, F257 → A944, modena- → bologna-, map center)
```

Per la pipeline volumi (NTN/IMI da PDF AdE) vedi sezione §13 di REPLICATE.

## Layout repo

```
opportuni-omi-mockups/
├── README.md                        ← stai leggendo questo
├── REPLICATE-FOR-OTHER-PROVINCE.md  ← workflow completo, 76KB, autosufficiente
├── SAGONA.md                        ← reverse-engineering dell'API Sagona
├── Makefile
├── requirements.txt                 ← solo stdlib (vuoto, presente per convenzione)
├── LICENSE                          ← MIT
├── mockups/                         ← 6 HTML statici (Modena + Catanzaro × A/B/C)
├── scripts/                         ← Python ETL + compute (stdlib only)
├── data/
│   ├── computed/                    ← JSON pre-computati che alimentano i mockup
│   ├── geojson/                     ← zone OMI + confini comuni (CC-BY)
│   ├── sagona-backfill/             ← prezzi.csv + cache API per riproducibilità
│   ├── volumi/                      ← PDF AdE + JSON timeseries NTN/IMI
│   └── _research/                   ← note di ricerca (toponimi 2018, reconstructed series)
└── docs/                            ← decision memo, design doc di contesto
```

## Sorgenti dati e licenze

Tutti i dataset usati sono **pubblici e free**:

| Fonte | Licenza | Cosa fornisce |
|---|---|---|
| [Sagona OMI API](https://3eurotools.it/api-quotazioni-immobiliari-omi) | Free, ~20 req/min | Prezzi OMI per comune × zona × tipologia × anno |
| [GeoPOI Agenzia Entrate](https://wwwt.agenziaentrate.gov.it/geopoi_omi/) | Pubblico (reverse-engineered) | Poligoni KMZ delle zone OMI del capoluogo |
| [openpolis/geojson-italy](https://github.com/openpolis/geojson-italy) | CC-BY | Confini ISTAT dei comuni per provincia |
| [AdE — Statistiche Regionali OMI](https://www.agenziaentrate.gov.it/portale/web/guest/schede/fabbricatiterreni/omi/pubblicazioni/statistiche-regionali) | Pubblico | PDF annuali con volumi NTN/IMI per macroarea |

Output del repo: codice MIT, dati derivati restano CC-BY per chain-of-custody.

## Stato

Funziona end-to-end per Modena e Catanzaro. Mockup C ha già passato il giro di audit con 8 fix (yield filter, anni_orizzonte disambiguation, anti-stale-string — vedi §15/§17/§18 di REPLICATE).

## Contributing

PR benvenute. Aggiungere una provincia nuova è il primo "good first issue" naturale: segui REPLICATE-FOR-OTHER-PROVINCE.md e apri PR con `<city>-A/B/C.html` + i JSON computati + i GeoJSON.

## License

MIT — vedi `LICENSE`.
