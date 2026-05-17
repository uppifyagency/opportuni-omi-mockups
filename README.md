# Opportuni — OMI Province Mockups

Tre dashboard HTML statiche per analizzare il mercato immobiliare di una **intera provincia italiana**, alimentate da dati pubblici OMI (Agenzia delle Entrate) con 20+ anni di storia.

**Province incluse:**
- **Modena** (`F257`, ISTAT 036) — 47 comuni
- **Catanzaro** (`C352`, ISTAT 079) — 80 comuni
- **Bologna** (`A944`, ISTAT 037) — 55 comuni
- **Reggio Emilia** (`H223`, ISTAT 035) — 42 comuni

Stack: Python stdlib + HTML/CSS/JS vanilla + MapLibre GL per i mockup; per l'audit math-proof, numpy/scipy/statsmodels/pymoo/networkx/polars/simpy/matplotlib. **Nessun framework UI**, nessun build step, nessuna API key. Costo zero.

> **Audit math-proof:** ogni numero esposto è ricalcolabile dal CSV grezzo Sagona. Il protocollo (10 gruppi di test, 6 figure publication-quality per città) è descritto in [`REPLICATE-FOR-OTHER-PROVINCE.md` §20](REPLICATE-FOR-OTHER-PROVINCE.md). Esito attuale: **64 PASS · 0 FAIL · 6 WARN** su 70 test (Modena 22/0/0 · Bologna 23/0/2 · Catanzaro 19/0/4) — vedi [`docs/audit/REPORT-CROSS-CITY.md`](docs/audit/REPORT-CROSS-CITY.md).
>
> **Audit cross-mockup v3 (2026-05-17):** 4 sub-agenti hanno analizzato i 12 mockup HTML e trovato 44 candidati bug → cross-verificati matematicamente → **39 reali, tutti fixati** (3 falsi positivi + 2 non-bug runtime). 7 pattern di copy-paste cross-city + 6 anti-pattern statistici documentati in [`REPLICATE-FOR-OTHER-PROVINCE.md` §24](REPLICATE-FOR-OTHER-PROVINCE.md). **Per ogni nuova città §24 è obbligatorio** dopo §20.

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

- [Modena · A](http://localhost:8765/mockups/investor-A-brief.html) · [B](http://localhost:8765/mockups/investor-B-heatmap.html) · [C](http://localhost:8765/mockups/investor-C-compass.html)
- [Bologna · A](http://localhost:8765/mockups/bologna-A-brief.html) · [B](http://localhost:8765/mockups/bologna-B-heatmap.html) · [C](http://localhost:8765/mockups/bologna-C-compass.html)
- [Catanzaro · A](http://localhost:8765/mockups/catanzaro-A-brief.html) · [B](http://localhost:8765/mockups/catanzaro-B-heatmap.html) · [C](http://localhost:8765/mockups/catanzaro-C-compass.html)
- [Reggio Emilia · A](http://localhost:8765/mockups/reggio-emilia-A-brief.html) · [B](http://localhost:8765/mockups/reggio-emilia-B-heatmap.html) · [C](http://localhost:8765/mockups/reggio-emilia-C-compass.html)

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

In sintesi (esempio: aggiungere Padova, Belfiore `G224`, ISTAT `028`):

```bash
# 1. Confini comuni (CC-BY openpolis)
curl -sL -o data/geojson/padova-province-comuni.geojson \
  "https://raw.githubusercontent.com/openpolis/geojson-italy/master/geojson/limits_P_28_municipalities.geojson"

# 2. Backfill prezzi OMI per provincia (~50 min, una tantum)
python3 -c "import json; print(' '.join(sorted({f['properties']['com_catasto_code'] for f in json.load(open('data/geojson/padova-province-comuni.geojson'))['features']})))" \
  | xargs python3 scripts/sagona-backfill.py

# 3. Zone OMI del capoluogo
python3 scripts/geopoi-zone-extract.py \
  --codcom G224 --prov PD --semestre 20252 \
  --prezzi-csv data/sagona-backfill/prezzi.csv \
  --out data/geojson/padova-zone-omi.geojson

# 4. Compute (fork degli script Modena, parametrizza poi — vedi REPLICATE §5)
cp scripts/compute-bologna-signals.py scripts/compute-padova-signals.py
# edit: bologna → padova, A944 → G224
python3 scripts/compute-padova-signals.py
python3 scripts/compute-compass.py --city padova --codcom G224

# 5. Duplica i mockup HTML cambiando: codice comune, nome città, map center
for variant in A-brief B-heatmap C-compass; do
  cp mockups/bologna-${variant}.html mockups/padova-${variant}.html
done
# edit: Bologna → Padova, A944 → G224, bologna- → padova-, map center [11.30,44.45] → [11.88,45.41]

# 6. Audit OBBLIGATORIO §20 (math-proof)
python3 scripts/audit-math-proof.py --city padova
# Atteso: PASS=tutto, FAIL=0

# 7. Anti-pattern check §24 (checklist grep di 1 minuto, copia-incolla da REPLICATE §24.6)
# Cattura copy-paste cross-city, JSON key sbagliate, P25/P75 senza disclaimer,
# slogan off-by-one, slice(-3) su stale, sum-check fallito, ecc.
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

Funziona end-to-end per **Modena · Bologna · Catanzaro · Reggio Emilia**. Tutti i 12 mockup hanno passato:

- L'audit math-proof §20 (64/70 PASS · 0 FAIL · 6 WARN su dati limitati)
- L'audit cross-mockup v3 §24 (44 candidati bug → 39 reali fixati, 0 residui)
- Syntax check JS su tutti i 12 file (`node --check` passa)

## Contribuire — aggiungi la tua provincia

Aggiungere una provincia è il primo "good first issue" naturale del progetto. Tre dashboard, un workflow da seguire, **~30 minuti di lavoro umano** + ~50 min di backfill unattended (1× per provincia).

### Tre passi base

1. **Leggi [REPLICATE-FOR-OTHER-PROVINCE.md](REPLICATE-FOR-OTHER-PROVINCE.md)** — è il file mastro, autosufficiente (~2.800 righe).
2. **Segui §1–§20** (data → compute → mockups → audit math-proof). Senza §20 PASS, non si va avanti.
3. **Esegui §24** (anti-pattern check post-replica). Cattura i 13 bug pattern tipici di copy-paste cross-city e visualizzazione fuorviante.

### Cosa fare (in due righe)

- **Rispetta la pipeline**: dati grezzi → JSON pre-computati → mockup statici. Il frontend non fa aritmetica.
- **Apri una PR** con: `<city>-A/B/C.html` + `data/computed/<city>-*.json` + `data/geojson/<city>-*.geojson` + il report `docs/audit/REPORT-<city>.md` generato da §20 + screenshot dei 3 mockup serviti via `python3 -m http.server`.

### Cosa NON fare (errori reali pescati nell'audit v3)

| ❌ Anti-pattern | ✅ Fix corretto |
|---|---|
| Lasciare `'CATANZARO CAPOLUOGO'` hardcoded nel template della tua città | Sostituisci col nome esatto da `<city>-volume-signals.json` |
| Lasciare "Appennino bolognese" o altro toponimo non tuo nei deck | Verifica con grep `grep -niE "appennino \|cintura" mockups/<city>-*.html` |
| Usare `h.anni_orizzonte` (non esiste in tutti gli schema) | Usa fallback `h.anni_orizzonte_dataset \|\| h.anni_orizzonte \|\| '—'` |
| Etichettare la legenda heatmap "min/max" quando in realtà usa P25/P75 (50% dati saturati) | Usa P5/P95 (10% saturati) + tooltip onesto con veri min/max — template §24.4 |
| Filtrare `p.cagr && p.cagr > 0` (esclude silenziosamente `0.0`) | `p.cagr != null && p.cagr > 0` + esponi `nFlat` esplicito |
| `pr.slice(-3)` senza filtrare `stale=true` | `pr.filter(p => !p.stale).slice(-3)` |
| Slogan "vent'anni" su dataset 21-anni, "volumi raddoppiati" su +90% | Numeri precisi o qualitativi onesti |
| Usare "crescita reale" per un CAGR nominale | "crescita nominale" + "(non deflazionata)" |
| Confrontare fascia B (21y) con fascia R (2y) senza disclaimer | Aggiungi `(2005-2026)` esplicito per ogni fascia |
| Presentare outlier su n=2 osservazioni come "top growth" senza warning | `(orizzonte breve: ${anni} anni, segnale provvisorio)` se `anni < 5` |

L'elenco completo (13 pattern con esempi + checklist grep di 1 minuto) è in [REPLICATE-FOR-OTHER-PROVINCE.md §24](REPLICATE-FOR-OTHER-PROVINCE.md).

### Cosa NON fare con i sub-agenti AI

Se usi sub-agenti AI per analizzare i mockup (come ho fatto io), tieni a mente:

- **Mai fidarsi di `wc -l = 0` per affermare "JSON vuoto"**: i JSON pre-computati sono minified su una singola riga (250-400 KB di contenuto valido). Valida sempre con `python3 -c "import json; json.load(open('file.json'))"` o `stat -f %z file.json`.
- **Considera la logica runtime**: i mockup C ricalcolano score/verdict con penalty (es. `CAGR_NEGATIVE_PENALTY=−10`). Un sub-agente che legge solo il JSON statico può segnalare "bug" che in realtà sono già gestiti a runtime.
- **Cross-verifica matematica obbligatoria**: ~30% dei findings di sub-agenti `general-purpose` sono falsi positivi o non-bug. Riproduci il calcolo con `python3` su dati reali prima di applicare il fix.

### Cosa puoi modificare (e cosa no)

| Area | Modificabile in PR | Note |
|---|---|---|
| Nuovi `mockups/<city>-*.html` | ✅ Sì | Sono indipendenti dalle altre città |
| Nuovi `scripts/compute-<city>-*.py` | ✅ Sì | Fork degli script esistenti, parametrizza poi |
| Nuovi `data/{computed,geojson,volumi}/<city>-*` | ✅ Sì | Output deterministico della pipeline |
| Modifiche cross-city ai mockup esistenti | ⚠️ Solo se i 12 mockup esistenti continuano a passare §24 dopo il cambio | Mostra prima/dopo screenshot |
| Cambi alla pipeline `compute-*.py` di altre città | ⚠️ Solo per fix bug documentati | Mostra diff dei JSON output |
| Cambi a `REPLICATE-FOR-OTHER-PROVINCE.md` | ⚠️ Solo per chiarimenti + nuovi anti-pattern scoperti | Mantieni la struttura §1–§24 |

### Province "primo issue" suggerite

Province con buona copertura OMI + zone capoluogo numerose + accessibili a un nuovo contributore:

- **Padova** (`G224`, ISTAT 028) — 102 comuni, ~25 zone OMI capoluogo
- **Bari** (`A662`, ISTAT 072) — 41 comuni, ~30 zone OMI
- **Palermo** (`G273`, ISTAT 082) — 82 comuni, ~40 zone OMI
- **Verona** (`L781`, ISTAT 023) — 98 comuni, ~25 zone OMI
- **Genova** (`D969`, ISTAT 010) — 67 comuni, ~30 zone OMI (interessante per il terreno collinare → distribuzione CAGR ampia)

Apri un issue PRIMA di iniziare per evitare doppi lavori.

## License

MIT — vedi [`LICENSE`](LICENSE). I dati derivati restano CC-BY come le fonti.
