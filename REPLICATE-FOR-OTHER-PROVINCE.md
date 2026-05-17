# Come replicare Mockup A + B + C per un'altra provincia italiana

**Target di esempio nel doc:** Catanzaro (capoluogo `C352`, provincia ISTAT `079`).
**Tempo realistico:** 30 minuti di lavoro umano + ~22 minuti di backfill Sagona unattended (+ ~2h opzionali per pipeline volumi NTN/IMI da PDF AdE — sezione §13).
**Costo:** 0 € (tutte fonti pubbliche).

Questo file è autosufficiente. Un agente che lo legge ha tutto per fare il job senza tornare indietro. **Aggiornato post-audit Modena fix #1–#8** (yield filter, anni_orizzonte disambiguation, anti-stale-string — vedi §15, §17, §18).

---

## 1. Cosa stai replicando

Tre dashboard HTML statiche servite da `python3 -m http.server`, alimentate da **dati ufficiali OMI** (Agenzia delle Entrate) per **una intera provincia italiana** con 20+ anni di storia. Tipologia di default: `abitazioni_civili acquisto`.

- **Mockup A — Investor Brief** ([mockups/investor-A-brief.html](mockups/investor-A-brief.html)): tabella ranking densa, 3 segnali narrativi, KPI strip, sparkline SVG inline. Stile editorial bloomberg-lite light. Legge `<city>-signals.json`.
- **Mockup B — Heat Map First** ([mockups/investor-B-heatmap.html](mockups/investor-B-heatmap.html)): mappa provincia + mappa zone capoluogo. Hero MapLibre, sparkline grid, insight cards. Legge `<city>-signals.json` + 2 GeoJSON.
- **Mockup C — Investment Compass** ([mockups/investor-C-compass.html](mockups/investor-C-compass.html)): score composito 0-100 con 6 componenti (growth, yield, stability, momentum, level, liquidity), verdict BUY/WATCH/AVOID, weight sliders runtime, anomaly detection, k-NN comparables, what-if simulator. Legge `<city>-compass.json` + `<city>-volume-signals.json`.

Ogni numero è **pre-computato in Python** e validato con asserts prima del rendering. Il frontend non fa aritmetica.

---

## 2. Architettura del progetto (mental model)

```
┌──────────────────────────────────────────────────────────┐
│  TRE SORGENTI DATI ESTERNE (tutte pubbliche)             │
│                                                          │
│  1. Sagona API (3eurotools.it) — wrapper OMI Ag.Entrate │
│  2. GeoPOI (Ag.Entrate) — poligoni zone OMI capoluogo   │
│  3. openpolis/geojson-italy — confini comuni provincia  │
└──────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────┐
│  3 SCRIPT PYTHON (in scripts/)                           │
│                                                          │
│  ETL                                                     │
│  ├ sagona-backfill.py        → prezzi.csv               │
│  └ geopoi-zone-extract.py    → <city>-zone-omi.geojson  │
│                                                          │
│  COMPUTE                                                 │
│  └ compute-modena-signals.py → modena-signals.json      │
│         (CAGR, yield, volatilità, top growth/decline,    │
│          fascia series, province ranking, asserts)       │
└──────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────┐
│  2 DASHBOARD HTML STATICHE (in mockups/)                 │
│                                                          │
│  Mockup A — Investor Brief                              │
│  Mockup B — Heat Map First                              │
│  Entrambi fetchano dai JSON pre-computati.              │
└──────────────────────────────────────────────────────────┘
                            ↓
              python3 -m http.server 8765
                     (light HTTP)
```

**Principio chiave:** la pipeline è **idempotente e cache-aware**. Ogni script ricostruisce il proprio output partendo dal cache. Rieseguire non costa niente. Backfilling è la sola operazione costosa, ~22 min wall-clock per provincia, una tantum.

---

## 3. Sorgenti dati — anatomia

### 3.1 Sagona API (prezzi OMI per comune)

**Endpoint:** `GET https://3eurotools.it/api-quotazioni-immobiliari-omi/ricerca`

| Param | Esempio | Note |
|---|---|---|
| `codice_comune` | `C352` (Catanzaro), `F257` (Modena) | Belfiore 4 char, **case-sensitive** |
| `anno` | `2015` | Opzionale, backfill storico |

**Rate limit:** 100 req credito + ricarica 1 req / 3 sec. Lo script usa `DELAY_SECONDS = 3.5` per stare sotto.

**Response shape:** un singolo GET ritorna TUTTO il comune × tutte le zone × tutte le tipologie × entrambe le operazioni.

```json
{
  "B3": {
    "negozi": {
      "stato_di_conservazione_mediano_della_zona": "normale",
      "prezzo_acquisto_min": 1175.0,
      "prezzo_acquisto_max": 2325.0,
      "prezzo_acquisto_medio": 1750.0,
      "prezzo_affitto_min": 11.6, …
    },
    "uffici": { … },
    "abitazioni_civili": { … }
  },
  "C9": { … }, …
}
```

Documentazione completa in [SAGONA.md](SAGONA.md).

### 3.2 GeoPOI Agenzia Entrate (poligoni zone OMI)

**NON pubblicato come bulk download.** Reverse-engineered via DevTools.

Due endpoint interni:
```
GET /servizi/geopoi_omi/zoneomi.php?richiesta=3&codcom=<X>
    → JSON {LINK_ZONA, FASCIA, ZONA, DIZIONE} per ogni zona OMI

GET /servizi/geopoi_omi/perimetri.php?id=1&prov=<P>&codcom=<X>&semestre=<YYYYS>&formato=kml
    → KMZ (ZIP di KML) con i poligoni
```

**Gotcha critico #1:** parametro `semestre` va in formato **compatto** `20242` (anno+semestre concatenati), NON `2024/2`. Se sbagli, ritorna KMZ di 106 byte vuoto.

**Gotcha critico #2:** **OMI rinumera le zone ad ogni semestre.** Tra `20241` e `20242` Modena è passata da 19 a 20 zone, con codici diversi (C7→C9, C8→C10, D26→D34, ecc.). **Usa sempre il semestre più recente disponibile** (al 2026 il più recente è `20252`) altrimenti i codici GeoPOI non si allineano con i codici Sagona current e l'intersezione del join si riduce drammaticamente. Test rapido: `curl ...&semestre=20252` deve ritornare KMZ non vuoto; se sì, è il semestre corrente.

**Param `prov`:** **sigla provincia maiuscola** (es. `MO` per Modena, `CZ` per Catanzaro). Non confondere con codice ISTAT.

### 3.3 openpolis/geojson-italy (confini comuni)

Pattern URL fisso:
```
https://raw.githubusercontent.com/openpolis/geojson-italy/master/geojson/
    limits_P_<NUM>_municipalities.geojson
```

Dove `<NUM>` è il codice provincia ISTAT **senza zero-padding**:
- Modena 036 → `limits_P_36_municipalities.geojson`
- Catanzaro 079 → `limits_P_79_municipalities.geojson`

Properties chiave per ogni feature:
- `com_catasto_code` (Belfiore — quello che ci serve per Sagona)
- `com_istat_code` (codice ISTAT)
- `name` (denominazione)
- `prov_acr` (sigla)

Licenza: CC-BY.

---

## 4. Pipeline step-by-step — replica per Catanzaro

### Step 0 · Verifica ambiente

```bash
cd "/Users/vladvrinceanu/Desktop/PROGETTI ANTYGRAVITY/CLI-Everything/opportuni-poc"
python3 --version   # 3.10+ ok
which curl          # serve
```

Nessun pacchetto Python esterno necessario — solo stdlib.

### Step 1 · Scarica confini provincia Catanzaro

```bash
mkdir -p data/geojson
curl -sL -o data/geojson/catanzaro-province-comuni.geojson \
  "https://raw.githubusercontent.com/openpolis/geojson-italy/master/geojson/limits_P_79_municipalities.geojson"

# Verifica: deve essere ~200 KB, non 14 byte ("404: Not Found")
ls -la data/geojson/catanzaro-province-comuni.geojson
```

Estrai la lista dei codici Belfiore di tutta la provincia:
```bash
python3 -c "
import json
d = json.load(open('data/geojson/catanzaro-province-comuni.geojson'))
print(f'Comuni provincia Catanzaro: {len(d[\"features\"])}')
codes = sorted({f['properties']['com_catasto_code'] for f in d['features']})
print(' '.join(codes))
" > /tmp/catanzaro-codes.txt
cat /tmp/catanzaro-codes.txt
```

### Step 2 · Backfill Sagona per tutta la provincia

```bash
# 80 comuni × 11 anni × 3.5s ≈ ~50 minuti
xargs python3 scripts/sagona-backfill.py < /tmp/catanzaro-codes.txt 2>&1 | tail -20
```

**⚠️ Gotcha shell-splitting:** NON fare `python3 ... $(cat /tmp/catanzaro-codes.txt)` — la shell può collassare tutto in una singola stringa. **Usare sempre `xargs`** (testato e funziona).

Output:
- `data/sagona-backfill/cache/<CODICE>_<ANNO>.json` (cached, idempotente)
- `data/sagona-backfill/prezzi.csv` (CSV flat con tutte le righe)

**Verifica:**
```bash
tail -n +2 data/sagona-backfill/prezzi.csv | cut -d, -f2 | sort -u | wc -l
# Deve essere ≈ numero comuni Catanzaro
```

### Step 3 · Scarica zone OMI capoluogo (Catanzaro città, codice C352)

```bash
# Sceglie il semestre più recente. 20242 = 2024/2.
python3 scripts/geopoi-zone-extract.py \
  --codcom C352 --prov CZ --semestre 20242 \
  --prezzi-csv data/sagona-backfill/prezzi.csv \
  --out data/geojson/catanzaro-zone-omi.geojson
```

**Output atteso (esempio Modena):**
```
==> zoneomi.php (lista zone C352)
    zone trovate: ~20
==> perimetri.php (KMZ C352 sem 20242)
    KMZ size: ~50,000 bytes
    KML interno: C352 - Comune di CATANZARO 2024-2.kml (~180 KB)
==> Parse KML
    placemark estratti: ~20
==> Join prezzi
    zone con prezzi: ~20
==> Scritto data/geojson/catanzaro-zone-omi.geojson
```

**Se il KMZ è 106 byte:** hai sbagliato il formato semestre. Riprova con `20241` o `20231`. Il formato `2024/2` non funziona.

### Step 4 · Compute layer (signals)

Lo script attuale `scripts/compute-modena-signals.py` è hardcoded su `F257`/Modena. Va parametrizzato. Tre approcci:

**A. Quick: fork + sed (più veloce, sporco)**
```bash
cp scripts/compute-modena-signals.py scripts/compute-catanzaro-signals.py
sed -i '' 's/F257/C352/g; s/PROVINCE_GEOJSON.*/PROVINCE_GEOJSON = ROOT \/ "data" \/ "geojson" \/ "catanzaro-province-comuni.geojson"/; s/ZONE_GEOJSON.*/ZONE_GEOJSON = ROOT \/ "data" \/ "geojson" \/ "catanzaro-zone-omi.geojson"/; s/modena-signals/catanzaro-signals/g' \
  scripts/compute-catanzaro-signals.py

python3 scripts/compute-catanzaro-signals.py
```

**B. Clean: parametrizza con argparse (raccomandato)**

Edita `compute-modena-signals.py` per accettare:
```python
ap.add_argument("--codcom", default="F257")
ap.add_argument("--prov-geojson", default="data/geojson/modena-province-comuni.geojson")
ap.add_argument("--zone-geojson", default="data/geojson/modena-zone-omi.geojson")
ap.add_argument("--out", default="data/computed/modena-signals.json")
```

E sostituisci le costanti hardcoded `"F257"` con `args.codcom`. ~10 righe modificate.

**C. Compute-compass.py (nuovo, già parametrizzabile)**

Lo script più nuovo `compute-compass.py` (vedi todo list "Mockup C") è quasi pronto per essere parametrizzato — fa già anche multi-tipologia. Considerare.

**Validazione:** lo script Python ha `asserts` interni che bloccano se CAGR è fuori [-20%, +20%], yield fuori [0.5%, 20%], volatilità > 50%. Se fallisce → c'è un comune con dati anomali, da indagare.

### Step 5 · Adatta i due mockup per Catanzaro

Sono **HTML statici hardcoded** per Modena. Vanno duplicati e modificati. ~15 minuti per entrambi.

Cose da cambiare (ricerca/sostituzione):

| File | Cercare | Sostituire con |
|---|---|---|
| `mockups/investor-A-brief.html` | `Modena` (titoli, testi) | `Catanzaro` |
| | `F257` | `C352` |
| | `modena-signals.json` | `catanzaro-signals.json` |
| | `modena-province-comuni.geojson` | `catanzaro-province-comuni.geojson` |
| `mockups/investor-B-heatmap.html` | (idem sopra) | |
| | `modena-zone-omi.geojson` | `catanzaro-zone-omi.geojson` |
| | `[10.93, 44.55]` (map center provincia) | centro Catanzaro: `[16.59, 38.91]` |
| | `[10.92, 44.66]` (map center città) | centro Catanzaro: `[16.59, 38.91]` |
| | `zoom: 8.45/11.7` (provincia/zone) | Calabria è più stretta verticalmente, prova zoom `9.0` e `12.0` |

**Tip rapido:** duplica i file con suffix:
```bash
cp mockups/investor-A-brief.html mockups/catanzaro-A-brief.html
cp mockups/investor-B-heatmap.html mockups/catanzaro-B-heatmap.html
# Poi sed o edit manuale sui campi sopra
```

**Cosa NON va cambiato:** la logica JS, la struttura HTML, i CSS (incluse OKLCH palette, font, layout). Tutto il visual stack è province-agnostic.

### Step 6 · Aggiornare le 3 "narrative" hardcoded

I 3 segnali in Mockup A e i 3 insight in Mockup B hanno **testi parzialmente hardcoded** che richiamano osservazioni Modena ("Cognento outlier", "Pianura sale, Appennino scende"). Vanno rivisti per Catanzaro.

**File:** `mockups/catanzaro-A-brief.html` e `mockups/catanzaro-B-heatmap.html`

Sezione `<div class="signal">` (A) e `<div class="insight">` (B). Quattro pattern da considerare:

1. **Riscrittura semi-manuale** dopo aver visto i dati Catanzaro: leggi `cat data/computed/catanzaro-signals.json | python3 -m json.tool | head -60`, individua i 3 segnali dominanti, riscrivi gli HTML.

2. **Generazione data-driven (più robusta, già fatta in parte):** in Mockup A il "Signal #3 Pianura sale" è già auto-generato da JS dai dati. Rendi auto-generati anche #1 (fascia comparison: top fascia vs bottom fascia) e #2 (top outlier per CAGR). Questo rende lo stesso mockup riutilizzabile per qualsiasi provincia senza altre modifiche.

3. **Insight ad hoc:** se Catanzaro ha un pattern peculiare (es. costa vs entroterra), aggiungi un quarto signal dedicato.

4. **Caveat geografici:** controlla che le zone OMI di Catanzaro abbiano ancora la stessa codifica `B/C/D/E/R` (fasce). Sì, è lo standard OMI italiano.

### Step 7 · Verifica visiva

```bash
cd opportuni-poc
python3 -m http.server 8765 &
open http://localhost:8765/mockups/catanzaro-A-brief.html
open http://localhost:8765/mockups/catanzaro-B-heatmap.html
```

**Checklist:**
- [ ] Header titolo dice "Catanzaro"
- [ ] KPI numerici plausibili (CAGR `-3% ≤ x ≤ +3%`, yield `3-8%`, prezzo `€500-3000`)
- [ ] Tabella provincia ha **tutti i comuni** (verifica conteggio vs openpolis)
- [ ] Mappa provincia (Mockup B) mostra la sagoma corretta della Calabria centrale
- [ ] Mappa zone capoluogo mostra i poligoni di Catanzaro città (no aree fuori)
- [ ] Hover popup → DIZIONE corretta (es. "CAPOLUOGO - CENTRO STORICO")
- [ ] Insight automatici hanno senso (verifica top growth / decline / fascia split)

---

## 5. Script chiave — cosa fanno

### `scripts/sagona-backfill.py` (idempotente, cache-aware)

- Args: lista codici Belfiore (es. `C352 D976 …`)
- Default anni: `[2005, 2008, 2010, 2012, 2014, 2016, 2018, 2020, 2022, 2024, current]`
- Per ogni (codice, anno): se cache JSON esiste, skip; altrimenti GET Sagona + sleep 3.5s
- Append a CSV unico `data/sagona-backfill/prezzi.csv` (ricostruito ogni run sui file cache, quindi safe da rilanciare)

**Schema CSV output:**
```
anno, comune_catasto, zona, fascia, tipo_immobile, operazione,
stato_conservazione, prezzo_min, prezzo_max, prezzo_medio
```

⚠️ **Bug noto, fixato:** parser CSV lato HTML deve splittare con `/\r?\n/` non `'\n'`. Vedi commento in `mockups/investor-A-brief.html` riga ~640.

### `scripts/geopoi-zone-extract.py` (reverse-engineered)

- Args: `--codcom`, `--prov`, `--semestre`, `--prezzi-csv`, `--out`
- Chiama 2 endpoint GeoPOI in sequenza (lista zone + KMZ poligoni)
- Estrae KMZ (zipfile), parsa KML (xml.etree.ElementTree)
- Joina con metadati zone + prezzi correnti dal CSV
- Emette GeoJSON enriched con `zona`, `fascia`, `dizione`, prezzi attuali per tipologia

**Output per zona di esempio:**
```json
{
  "type": "Feature",
  "geometry": { "type": "Polygon", "coordinates": [...] },
  "properties": {
    "zona": "B3",
    "fascia": "B",
    "dizione": "CAPOLUOGO - CENTRO STORICO",
    "abitazioni_civili_acquisto_medio": 2500.0,
    "negozi_acquisto_medio": 1750.0,
    …
  }
}
```

### `scripts/compute-modena-signals.py` (compute layer Mockup A+B)

- Aggregato per fascia (robust a renaming zone tra semestri)
- Per ogni zona current: CAGR full-span, recent slope, volatility, yield lordo, sparkline normalizzata
- Per ogni comune provincia: stesso compute (aggregato sulle zone)
- Top 5: growth, decline, yield, volatile
- Asserts su tutti i campi (CAGR ∈ [-20%, +20%], yield ∈ [0.5%, 20%], vol ∈ [0%, 50%])

**⚠ Invarianti matematiche obbligatorie** (verificate post-fix #3/#4, vedi §17):

1. **`yield_medio_pct`** = media yield SOLO delle **zone correnti** (quelle con `dizione`). Le zone storiche hanno `prezzo_attuale` fermo al loro ultimo anno (es. 2012) — includerle inquina la media con prezzi vecchi. Per Modena: 4.99 % (sbagliato, 51 zone miste) vs 5.28 % (corretto, 20 zone correnti). Filtra `z.get("dizione")` PRIMA della media.

2. **`anni_orizzonte`** è ambiguo per design e va **disambiguato in due campi distinti**:
   - `anni_orizzonte_dataset` = max(ultimo_anno) − min(primo_anno) su TUTTE le zone (= span fascia, es. 21 per Modena 2005–2026)
   - `anni_orizzonte_zone_correnti` = max − min sui `spark_years` delle SOLE zone con `dizione` (= finestra CAGR utile, es. 12 per Modena 2014–2026)

   Non esporre un solo campo `anni_orizzonte` — i lettori del JSON non sanno quale dei due ottengono.

3. **Coerenza signals ↔ compass**: i due script (`compute-<city>-signals.py` e `compute-compass.py`) DEVONO produrre identici: `yield_*_pct`, `*_cagr_avg_pct`, `prezzo_*`. Doublecheck script in §17 verifica l'eguaglianza.

### `scripts/compute-compass.py` (compute layer Mockup C, ESTESO)

In aggiunta al precedente:
- Score composito 0-100 (growth 30% + yield 25% + stability 20% + momentum 15% + level 10%)
- Verdict BUY (score ≥ 65) / WATCH (35-64) / AVOID (< 35)
- Anomaly detection (zona che diverge dalla sua fascia > 1.5σ)
- Comparable zones (k-NN su 4 feature normalizzate)
- Multi-tipologia: emette JSON con `by_tipologia.{abitazioni_civili|abitazioni_signorili|negozi|uffici|magazzini}`

---

## 6. Caveat operativi

### CRLF in CSV
Il CSV nasce con line endings `\r\n` (default Python `csv`). Se parsi in JS con `csv.split('\n')`, l'ultima colonna ha `\r` attaccato → tutto si rompe silenziosamente. Usare **sempre** `csv.split(/\r?\n/)` lato JS + `.map(c => c.trim())` sui cells.

### Shell splitting di liste di codici
`python3 ... $(cat /tmp/codes.txt)` può collassare la lista in una stringa. Usare `xargs`:
```bash
xargs python3 scripts/sagona-backfill.py < /tmp/codes.txt
```

### Semestre Sagona/GeoPOI in formato diverso
- Sagona accetta `anno=2024` (solo anno)
- GeoPOI vuole `semestre=20242` (anno+semestre compatto)
- Mai `2024/2`

### Rinominazioni zone OMI nel tempo
Le zone OMI vengono periodicamente ridenominate (es. Modena passa da 27 zone nel 2005 a 19 zone nel 2014). Il compute layer aggrega per **fascia** (B/C/D/E/R) che è stabile, per evitare falsi crolli/crescite dovuti al ribattezzamento.

### Rate limit Sagona — stalli imprevisti
Il `DELAY_SECONDS = 3.5` rispetta il limite dichiarato, ma in pratica può comunque verificarsi uno stallo temporaneo (~5-10 min). Il backfill è cache-aware → basta rilanciare e riprende.

### MapLibre paint spec non accetta OKLCH
Le CSS variables OKLCH nei paint MapLibre rompono (validator rifiuta). Usare hex/rgb per stroke/fill nelle layer. Le var OKLCH stanno solo in CSS-land.

### Popolazione del comune capoluogo
Le 13 zone "correnti" di Modena (quelle con `dizione` set nel GeoJSON GeoPOI 2024/1) sono **un sottoinsieme** delle 51 zone totali nel CSV (che include 22 anni di nomi diversi). Il `zone_count_current` è quello che compare in dashboard. Per Catanzaro il numero sarà diverso.

---

## 7. Estensioni interessanti per Catanzaro (raccomandazioni)

### a. Costa vs entroterra
Catanzaro ha una geografia molto stratificata: comuni sul Tirreno (Lamezia, Falerna), comuni sulle Sila (Taverna, Sersale), comuni sul Mar Ionio (Soverato, Botricello). Aggiungi un quarto insight che cluster i comuni per quota o per appartenenza geografica (costa/collina/montagna). Lo puoi fare con i dati di OpenStreetMap (POI altimetria) o con tag manuale.

### b. Effetto turismo
Comuni con flussi turistici (Capo Vaticano, Tropea, Soverato — anche se sono in altre province) hanno tipicamente prezzi affitti molto sopra la media. Il compute layer attuale già scopre questi outlier via yield z-score. Aggiungi un'insight dedicata "comuni a vocazione turistica".

### c. ZES (Zona Economica Speciale)
La Calabria ha una ZES costiera con incentivi fiscali. Verifica se le zone OMI dentro la ZES mostrano pattern differenti — anomalia rispetto alla fascia.

### d. Aeroporto Lamezia
Lamezia Terme è un nodo logistico. Verifica se i comuni in raggio 20km dall'aeroporto hanno trend differenti dal resto della provincia.

---

## 8. Validation checklist finale

Prima di consegnare:

- [ ] `data/sagona-backfill/cache/` contiene `N comuni × 11 anni` file
- [ ] `data/sagona-backfill/prezzi.csv` ha almeno `25.000 righe` per una provincia media
- [ ] `data/geojson/catanzaro-province-comuni.geojson` ha le features attese (N comuni)
- [ ] `data/geojson/catanzaro-zone-omi.geojson` ha almeno 5-10 zone (capoluogo medio)
- [ ] `data/computed/catanzaro-signals.json` ha `headline`, `top_growth`, `top_decline`, `zone_metrics`, `province_ranking` non vuoti
- [ ] Il compute script ha printato `✓ all asserts pass`
- [ ] Apri Mockup A e B in browser, nessun errore console
- [ ] KPI sono numericamente plausibili
- [ ] Mappa B vista provincia mostra la Calabria centrale correttamente
- [ ] Mappa B vista zone mostra il capoluogo Catanzaro correttamente
- [ ] Tabella provincia in A ha tutti i comuni della provincia
- [ ] I 3 insight automatici sono coerenti con i dati osservati

---

## 9. Cosa NON è incluso nel pacchetto base (per consapevolezza)

- **AVM (valutazione automatica indirizzo):** richiede geocoding via Nominatim — non incluso
- **Mortgage affordability:** richiede integrazione tassi BdI — non incluso
- **Predictive forecasting:** modelli ARIMA/Prophet — non incluso (esiste un compute-compass.py che è il primo step)
- **Listing-vs-OMI gap:** scraping Idealista/Immobiliare.it — non incluso (legalità grigia)
- **Score composito + verdict BUY/WATCH/AVOID:** **disponibile** in `compute-compass.py` ma non collegato ai Mockup A e B. È la base del Mockup C in corso.

---

## 10. Riferimenti

- **Sagona API:** https://3eurotools.it/api-quotazioni-immobiliari-omi (autore D. Sagona, free, attribuzione richiesta)
- **GeoPOI Agenzia Entrate:** https://www1.agenziaentrate.gov.it/servizi/geopoi_omi/ (endpoint interni reverse-engineered, ad uso "lettura" trasparente)
- **openpolis/geojson-italy:** https://github.com/openpolis/geojson-italy (CC-BY)
- **OMI dati ufficiali Excel (fallback):** https://www.agenziaentrate.gov.it/portale/web/guest/schede/fabbricatiterreni/omi/banche-dati-omi
- **ISTAT codici comuni:** https://www.istat.it/it/archivio/6789
- **Doc Sagona master:** [SAGONA.md](SAGONA.md) — completo, con 13 sezioni, comandi copia-incolla, workaround

---

## 11. Codici utili — Catanzaro

Per non perdere tempo a cercarli:

- **Catanzaro città** — Belfiore: **`C352`** — ISTAT: `079028`
- **Provincia di Catanzaro** — ISTAT: `079` — openpolis: `limits_P_79_municipalities.geojson`
- **Sigla provincia:** `CZ`
- **Centro mappa coords (lat/lon → MapLibre wants lon/lat):** `[16.59, 38.91]`
- **Numero comuni nella provincia (al 2024):** ~80 (verifica esatta nel GeoJSON openpolis dopo download)

Codici Belfiore altri capoluoghi calabresi (utili se vuoi estendere):
- Reggio Calabria: `H224` (provincia 080, codice openpolis 80)
- Cosenza: `D086` (provincia 078, codice openpolis 78)
- Crotone: `D122` (provincia 101, codice openpolis 101)
- Vibo Valentia: `F537` (provincia 102, codice openpolis 102)

---

## 12. Comandi tutti in una shot — quick-start Catanzaro

Sequenza completa, copia-incolla, ~50 min wall-clock (dei quali 50 sono di backfill unattended):

```bash
cd "/Users/vladvrinceanu/Desktop/PROGETTI ANTYGRAVITY/CLI-Everything/opportuni-poc"

# 1. Confini provincia
curl -sL -o data/geojson/catanzaro-province-comuni.geojson \
  "https://raw.githubusercontent.com/openpolis/geojson-italy/master/geojson/limits_P_79_municipalities.geojson"

# 2. Estrai codici Belfiore
python3 -c "
import json
d = json.load(open('data/geojson/catanzaro-province-comuni.geojson'))
print(' '.join(sorted({f['properties']['com_catasto_code'] for f in d['features']})))
" > /tmp/catanzaro-codes.txt

# 3. Backfill (~50 min se 80 comuni)
xargs python3 scripts/sagona-backfill.py < /tmp/catanzaro-codes.txt

# 4. Zone OMI capoluogo
python3 scripts/geopoi-zone-extract.py \
  --codcom C352 --prov CZ --semestre 20242 \
  --prezzi-csv data/sagona-backfill/prezzi.csv \
  --out data/geojson/catanzaro-zone-omi.geojson

# 5. Compute signals (fork+sed o parametrizza compute-modena-signals.py prima)
# Quick fork:
cp scripts/compute-modena-signals.py scripts/compute-catanzaro-signals.py
# Modifica manualmente: F257 → C352, modena-* → catanzaro-*, paths
# Poi:
python3 scripts/compute-catanzaro-signals.py

# 6. Duplica + adatta mockup
cp mockups/investor-A-brief.html mockups/catanzaro-A-brief.html
cp mockups/investor-B-heatmap.html mockups/catanzaro-B-heatmap.html
# Edit manuale: Modena → Catanzaro, F257 → C352, paths JSON+GeoJSON,
# center coord mappa [10.93,44.55] → [16.59,38.91], zoom

# 7. Serve + apri
python3 -m http.server 8765 &
open http://localhost:8765/mockups/catanzaro-A-brief.html
open http://localhost:8765/mockups/catanzaro-B-heatmap.html
```

Fine. Stessa pipeline funziona per qualsiasi provincia italiana sostituendo: codice provincia openpolis + sigla provincia + codice catastale capoluogo + denominazione + coordinate centro.

---

## 13. Estensione: dati volumi scambi (NTN/IMI) da PDF AdE — replica per Catanzaro

### Cosa aggiunge
Storico **6 anni di volumi transazioni** (NTN = Numero Transazioni Normalizzate) + **IMI** (Intensità Mercato Immobiliare = NTN/Stock %) **per zona OMI capoluogo + macroaree provincia**. Permette di calcolare `liquidity_score`, `momentum_tag` 🚀/↗/→/↘/💀 e `price_volume_quadrant` (HOT/OVERPRICED/OPPORTUNITY/DEAD) usati nel Mockup C.

**Output finale aggiuntivo:** `data/computed/<city>-volume-signals.json` (~50 KB), join-able con `<city>-signals.json` via zone code (con mapping OLD→NEW per zone rinominate fra semestri).

### Sorgente: Statistiche Regionali AdE
- **Documento ufficiale:** `Statistiche Regionali Sintetiche - Settore Residenziale - <REGIONE>`
- **Convenzione filename:** `sr<YEAR_PUBBLICAZIONE>_<regione>.pdf` (es. `sr2024_calabria.pdf`)
- **Publication lag:** **`SR<YEAR>.pdf contiene dati anno <YEAR-1>`**. Quindi per coprire 2018-2023 servono `SR2019…SR2024`.
- **Hosting AdE ufficiale:** https://www.agenziaentrate.gov.it/portale/web/guest/schede/fabbricatiterreni/omi/pubblicazioni/rapporti-immobiliari-residenziali (richiede navigazione manuale).
- **Mirror non-ufficiale (più facile):** `https://www.inumeridibolognametropolitana.it/sites/default/files/banche-dati/dati-osservatorio-mercato-immobiliare/sr<YEAR>_<regione>.pdf` — funziona per Emilia-Romagna confermato. **Per altre regioni: verificare**, fallback navigation manuale AdE.

### Step 1 — Download PDF
```bash
mkdir -p data/volumi
cd data/volumi
# Per Modena (Emilia-Romagna): tutti gli anni con un loop
for Y in 2019 2020 2021 2022 2023 2024; do
  curl -sL -o "sr${Y}_emilia_romagna.pdf" \
    "https://www.inumeridibolognametropolitana.it/sites/default/files/banche-dati/dati-osservatorio-mercato-immobiliare/sr${Y}_emilia_romagna.pdf"
done

# Per Catanzaro (Calabria): stessa logica, sostituisci regione
for Y in 2019 2020 2021 2022 2023 2024; do
  curl -sL -o "sr${Y}_calabria.pdf" \
    "https://www.inumeridibolognametropolitana.it/sites/default/files/banche-dati/dati-osservatorio-mercato-immobiliare/sr${Y}_calabria.pdf"
done
```

**Se il mirror non ha la regione:** scaricare manualmente dal portale AdE e copiare i 6 PDF in `data/volumi/sr<YEAR>_<regione>.pdf`.

### Step 2 — Setup parser
```bash
pip install pdfplumber  # estrazione tabelle PDF (NON usare pypdf, peggiore su tabelle)
```

### Step 3 — Adattare il parser

Il parser canonico vive in `scripts/parse-volumi-ade-final.py`. **CRITICO: il formato tabellare delle SR cambia ogni 1-2 anni.** Per Modena ho costruito una `COL_MAPS` (dict `{year: {section: {col_idx: field}}}`) con 6 mapping distinti per i 6 PDF Emilia-Romagna.

**Per Catanzaro DEVI rifare la `COL_MAPS` da zero**, perché le SR delle altre regioni potrebbero avere layout simili **ma non identici** (la struttura della provincia + numero righe macroaree è province-specific).

Workflow consigliato:

#### 3a. Inspezione manuale prima riga PDF
```bash
# Per ogni anno, dump le prime tabelle delle pagine "La provincia - Catanzaro"
python3 -c "
import pdfplumber, re
pdf = pdfplumber.open('data/volumi/sr2019_calabria.pdf')
for i, p in enumerate(pdf.pages):
    txt = (p.extract_text() or '')[:200]
    if re.search(r'La provincia\s*[-–]\s*Catanzaro', txt, re.I):
        print(f'PAGE {i+1}: {txt[:100]}')
        for j, t in enumerate(p.extract_tables() or []):
            print(f'  Table[{j}] rows={len(t)}, first 3 rows:')
            for r in t[:3]: print(f'    {r}')
        break
"
```

Ripeti per `sr2020`, `sr2021`, … fino a `sr2024`. **Annota** per ogni anno: qual è il pos. della colonna `NTN`, `IMI%`, `IMI diff`, `Quota`, `Quotazione €/m²`, ecc.

#### 3b. Adattare `COL_MAPS` per Catanzaro
Fork `scripts/parse-volumi-ade-final.py` → `scripts/parse-volumi-ade-catanzaro.py`. Aggiorna:

1. **Province name:** `Modena` → `Catanzaro` (regex search "La provincia - Catanzaro" / "Il comune - Catanzaro")
2. **Filename pattern:** `sr*_emilia_romagna.pdf` → `sr*_calabria.pdf`
3. **MACROAREE_KNOWN set:** dovrebbe essere riscritto per Catanzaro. Esempi possibili (verifica nei PDF):
   ```python
   MACROAREE_KNOWN = {
       "CATANZARO CAPOLUOGO",
       "FASCIA IONICA",
       "FASCIA TIRRENICA",
       "PRESILA",
       "SILA",
       # ... aggiungi tutte quelle che trovi
       "CATANZARO",  # totale provincia
   }
   ```
4. **`COL_MAPS`:** rebuild da inspezione 3a. Importante: i campi canonici devono restare gli stessi (`ntn`, `ntn_var_pct`, `imi_pct`, `imi_diff`, `quota_pct`, `quotazione_eur_mq`, `quotazione_var_pct`) così il compute layer downstream funziona invariato.

### Step 4 — Eseguire parser + cross-validation
```bash
python3 scripts/parse-volumi-ade-catanzaro.py
# Output: data/volumi/catanzaro-volumi-timeseries.json
```

**Validation gates obbligatorie** (sono già nel parser-final, devono passare):
- [ ] IMI ∈ [0%, 10%] per tutte le righe (oltre 10% = parsing error)
- [ ] NTN ≥ 0 per tutte le righe
- [ ] `sum(NTN macroaree) ≈ NTN_provincia_totale` per ciascun anno (gap < 1%)
- [ ] Almeno 4 anni con cross-check passato
- [ ] N zone/anno costante (per Modena = 19, per Catanzaro sarà diverso ma deve essere stabile)

### Step 5 — Mapping codici zone OLD→NEW
**Critico per dashboard temporal.** I codici zona OMI cambiano fra semestri (es. Modena: `C7/C8/D26-D33/E10` nel 2018 → `B3/C9-C11/D29-D36/E11` nel 2024). Per Catanzaro **devi costruire manualmente il mapping** `data/volumi/zone-mapping-old-new-catanzaro.json`:

```bash
# 1. Estrai zone OLD (dai PDF) e NEW (da Sagona):
python3 -c "
import json
v = json.load(open('data/volumi/catanzaro-volumi-timeseries.json'))
old = sorted(set((r['zona'], r.get('denominazione','')) for r in v['zone_series']))
print('=== OLD zones from PDF ===')
for code, name in old: print(f'  {code:6s}  {name}')

s = json.load(open('data/computed/catanzaro-signals.json'))
print('=== NEW zones from Sagona ===')
for z in sorted(s['zone_metrics'], key=lambda r: r['zona']):
    print(f'  {z[\"zona\"]:6s}  {z.get(\"dizione\",\"\")}')
"
```

2. Match per DENOMINAZIONE (più stabile dei codici). Per le ambiguità (split/merge), annota `rel: split` o `rel: merged` nel JSON di mapping. Usa lo schema di `data/volumi/zone-mapping-old-new.json` (Modena) come template.

### Step 6 — Compute volume signals
```bash
# Fork dello script Modena
cp scripts/compute-volume-signals.py scripts/compute-volume-signals-catanzaro.py
# Modifica path: VOL_JSON, MAP_JSON, SIG_JSON, OUT_JSON → versioni catanzaro
python3 scripts/compute-volume-signals-catanzaro.py
# Output: data/computed/catanzaro-volume-signals.json
```

Validation:
- [ ] `momentum_tag` distribution: almeno 3-4 categorie diverse rappresentate (non tutte "stable")
- [ ] `liquidity_score` ∈ [0, 100], distribuzione non degenerata (sd > 10)
- [ ] `price_volume_quadrant`: 4 quadranti tutti popolati o spiegato perché no

### Step 7 — Integrare nel Mockup C Catanzaro

(Una volta che Mockup C Modena è stabile, il pattern è ridurre tutto a sostituzione path JSON + denominazione provincia.)

### Tempo stimato: ~2h per Catanzaro (inclusa rebuild `COL_MAPS`)

| Step | Tempo | Skill richiesta |
|------|-------|-----------------|
| 1. Download 6 PDF | 5 min | curl |
| 2. Setup pdfplumber | 2 min | pip |
| 3a. Inspezione manuale 6 layout | 30 min | reading tables, paziente |
| 3b. COL_MAPS adattate | 30 min | Python dict editing |
| 4. Run parser + fix errors | 20 min | debugging |
| 5. Mapping zone OLD→NEW | 20 min | conoscenza topografia Catanzaro |
| 6. Compute volume signals | 5 min | run script |
| 7. Integrazione Mockup C | dipende | frontend |

### Caveat critici
1. **`COL_MAPS` non è generalizzabile fra regioni**: layout cambia. Devi rifarlo per Calabria.
2. **Header detection può fallire**: la v3 del parser tentava header-aware ma falliva su PDF con header multi-riga. La v-final usa **column-index espliciti per anno** — più rigido ma più affidabile. **Rispetta questo principio per Catanzaro.**
3. **Zone OMI con renumerazione**: i codici zone cambiano fra `2024/1` (semestre 20241) e `2024/2` (semestre 20242). Per Catanzaro verifica entrambi e mappa manualmente.
4. **Phantom NTN=0 in ultimo anno**: zone deprecate/rinominate possono apparire con NTN=0 nell'anno di rename. Il compute layer ha una regola "skip trailing zeros if prev > 5" — riusabile per Catanzaro.

### File aggiunti dal sub-progetto Volumi
```
data/volumi/
├ sr2019_calabria.pdf … sr2024_calabria.pdf   (6 PDF)
├ catanzaro-volumi-timeseries.json            (parser output)
├ parse-log-final.txt                          (audit log)
└ zone-mapping-old-new-catanzaro.json         (manual mapping)

scripts/
├ parse-volumi-ade-catanzaro.py               (fork del parser Modena)
└ compute-volume-signals-catanzaro.py         (fork del compute layer)

data/computed/
└ catanzaro-volume-signals.json               (joined output finale)
```

---

## 14. Integrazione Mockup C (Compass) — Score Liquidity + Volume signals

Una volta che `<city>-volume-signals.json` esiste, il Mockup C può integrarlo come **6° componente score "Liquidità"** + badge `momentum_tag` 🚀↗→↘💀 + badge `price_volume_quadrant` HOT/OVERPRICED/OPPORTUNITY/DEAD su ogni cella zona.

### Pattern integration (riassunto, dettagli in `mockups/investor-C-compass.html`)

#### 14.1 Stato + index NEW→volume
```javascript
const state = {
  data: null,
  volumeData: null,
  volByNewZone: {},   // index: NEW zone code → volume entry
  weights: { growth: 30, yield: 25, stability: 15, momentum: 15, level: 5, liquidity: 10 },
};
const SCORE_KEYS = ['growth','yield','stability','momentum','level','liquidity'];
```

#### 14.2 Boot non-blocking
```javascript
async function boot() {
  state.data = await (await fetch('../data/computed/<city>-compass.json')).json();
  try {
    state.volumeData = await (await fetch('../data/computed/<city>-volume-signals.json')).json();
    injectLiquidityIntoCompass();
  } catch (e) {
    console.warn('Volume signals not available, liquidity disabled:', e.message);
  }
  // ... continue boot
}
```

**Il try/catch è importante**: una città senza PDF AdE (mock-only) deve continuare a funzionare con 5 componenti invece di 6.

#### 14.3 `injectLiquidityIntoCompass()` — il join logic
- Indicizza `volByNewZone[newCode] = entry` (gestendo split: una OLD → N NEW, e merge: N OLD → 1 NEW tenendo quella con NTN più alto)
- Per ogni `zone_metrics` entry, attacca `score_components.liquidity = liquidity_score/100` e `volume_info = {...}`
- Per `province_ranking` entries, lascia `liquidity = null` (PDF AdE non ha dati per-comune-non-capoluogo)

#### 14.4 `recomputeScore` agnostico al numero di componenti
```javascript
function recomputeScore(entry, weights) {
  const c = entry.score_components;
  let s = 0, w = 0;
  for (const k of SCORE_KEYS) {
    if (c[k] != null) { s += weights[k] * c[k]; w += weights[k]; }
  }
  if (w === 0) return null;
  let score = s / w * 100;
  if (entry.cagr != null && entry.cagr < 0) score -= 10;  // value-trap penalty
  return Math.max(0, Math.min(100, score));
}
```

Il `for-loop su SCORE_KEYS` + skip-if-null gestisce automaticamente entries senza liquidity (comuni provincia).

#### 14.5 UI sliders — un singolo `<input>` in più
```html
<div class="w-row">
  <label><span class="nm">Liquidità</span><span class="pct" id="w-liquidity-pct">10%</span></label>
  <input type="range" min="0" max="60" value="10" id="w-liquidity">
</div>
```

`readWeights()` e `bindWeights()` iterano su `SCORE_KEYS` invece di hardcodare i 5 — automatico.

#### 14.6 Badge momentum + quadrant nel rendering zone
```javascript
const MOMENTUM_VIZ = {
  rocket:  { emoji: '🚀', color: 'var(--up)' },
  growing: { emoji: '↗',  color: 'var(--up)' },
  stable:  { emoji: '→',  color: 'var(--ink-mid)' },
  cooling: { emoji: '↘',  color: 'var(--watch)' },
  frozen:  { emoji: '💀', color: 'var(--down)' },
};
const QUADRANT_VIZ = {
  Q1_HOT:         { tag: 'HOT',         color: 'oklch(78% 0.15 30)' },
  Q2_OVERPRICED:  { tag: 'OVERPRICED',  color: 'oklch(72% 0.13 70)' },
  Q3_OPPORTUNITY: { tag: 'OPPORTUNITY', color: 'oklch(70% 0.15 145)' },
  Q4_DEAD:        { tag: 'DEAD',        color: 'oklch(65% 0.05 0)' },
};
```

E nel rendering di ogni spark-cell, aggiungi una riga finale che mostra emoji + NTN_last + NTN-CAGR + quadrant badge + IMI%.

### Validation
- Apri Mockup C
- KPI panel mostra "Score 0-100 calcolato come media pesata di **sei** componenti" (non cinque)
- I sliders sono 6, non 5
- Ogni spark-cell zona ha una riga sotto la sparkline con emoji momentum + NTN/IMI numeri
- Il `verdict` BUY/WATCH/AVOID cambia muovendo lo slider "Liquidità"
- Province ranking table: le righe comuni hanno barretta liquidity grigia/tratteggiata (= dati n.d.)
- Tip console: `console.log(Object.keys(state.volByNewZone).length)` dovrebbe = numero zone correnti

---

## 15. ⚠ Truthfulness gotchas — da non rifare per Catanzaro

Durante audit Modena ho trovato e corretto bug di **veridicità** nei mockup che valgono come warning generali.

### 15.1 Mai hardcodare narrative numeriche
**Esempio bug Modena (corretto):** Mockup A signal #2 diceva *letteralmente* "Frazione suburbana, fascia E. La sola zona con crescita > 0.8% l'anno in 21 anni — **quattro volte la media Modena (+0.25%/yr)**." I numeri erano scritti a mano e diversi dalla realtà (media vera = 0.7%/yr, multiplo vero 1.17×, non 4×).

**Regola:** ogni numero in copia DEVE essere uno `<span id="...">…</span>` riempito da JS leggendo il JSON. Mai "+0.25%" letterale.

### 15.2 Mai hardcodare conteggi
**Bug Modena (corretto):** "Le 13 zone OMI" / "diciannove zone" — entrambi sbagliati dopo la rinumerazione GeoPOI. Conteggio attuale = 20.

**Regola:** sempre `${h.zone_count_current}` dinamico.

### 15.3 Label "X anni" da disambiguare

Il dataset Modena ha **range** 2005-2026 (21 anni) MA la copertura per-entity varia:

- Fascia (B/C/D/E/R aggregata): 21 anni completi → `headline.anni_orizzonte_dataset`
- Comune provincia: 0–22 anni, dipende dall'apparizione nel CSV OMI → `province_ranking[].anni_coperti`
- Zona OMI capoluogo: max 12 anni (2014-2026), 7 datapoint semestrali → `headline.anni_orizzonte_zone_correnti`

Scrivere "CAGR 21 anni" è una **bugia statistica** quando il CAGR è computato per zona (7 datapoint × 12 anni).

**Regola per altre province:** usa label specifiche, **lette dai due campi disambiguati**:

- "CAGR · copertura completa" per comuni provincia → `${p.anni_coperti}` per riga
- "CAGR · 2014–2026" o "CAGR · 12 anni max" per zone capoluogo → `${h.anni_orizzonte_zone_correnti}`
- "CAGR · 21 anni" SOLO per le fasce aggregate → `${h.anni_orizzonte_dataset}`

**Anti-pattern reale (Mockup B Modena, fix #5):** popup mostrava `Δ 21y` hardcoded ma i comuni hanno coperture diverse (20–22 anni). Soluzione: `Δ ${p.anni_coperti - 1}y` dinamico per riga.

**Anti-pattern reale (dashboard hero, fix #7):** testo "misurato in venti anni" hardcoded. 2026−2005=21 → "ventun". Span derivato da `currentYear - years[0]` con dict `numWordIt`.

### 15.4 Coerenza claim verbale ↔ valori
Se il deck dice "due decenni" e i dati coprono 21 anni, OK (round). Se dice "ventidue anni" e i dati ne hanno 7 per entity, NO.

### 15.5 Unità inconsistenti nei JSON
Un bug del compute layer originale: `headline.modena_cagr_avg_pct = 0.7` (già percentuale) vs `zone_metrics[].cagr_full = 0.0082` (frazionale → ×100 = 0.82%). Il JS renderer compensa con `* 100`, ma è una landmine.

**Raccomandazione Catanzaro:** nel `compute-catanzaro-signals.py` scegli UNA unità (frazionale OR percentuale) e attienitici per TUTTI i campi CAGR.

---

## 16. Checklist completa post-implementazione (Modena come reference)

Quando il pacchetto Catanzaro è pronto, queste devono passare tutte:

### Dati base (Mockup A + B)
- [ ] `data/sagona-backfill/prezzi.csv` ≥ 25k righe
- [ ] `data/geojson/catanzaro-province-comuni.geojson` con N comuni reali
- [ ] `data/geojson/catanzaro-zone-omi.geojson` con N zone reali
- [ ] `data/computed/catanzaro-signals.json` con tutte le sezioni non vuote
- [ ] Asserts del compute script tutti ✓

### Volumi (estensione Mockup C — opzionale ma raccomandata)
- [ ] 6 PDF SR<YEAR>_calabria.pdf in `data/volumi/`
- [ ] `parse-volumi-ade-catanzaro.py` con COL_MAPS adattate per i 6 layout
- [ ] `data/volumi/catanzaro-volumi-timeseries.json` con cross-check NTN macroaree=totale gap <1%
- [ ] `data/volumi/zone-mapping-old-new-catanzaro.json` con mapping manuale
- [ ] `data/computed/catanzaro-volume-signals.json` con liquidity_score distribuito (sd>10)
- [ ] IMI di tutte le zone ∈ [0%, 10%]

### Mockup

- [ ] Tutti i 3 mockup HTTP 200
- [ ] Tutti i 3 mockup: braces/parens/brackets balanced (sanity syntax)
- [ ] Nessun numero hardcoded di copia (audit grep `\+\d+\.\d+%` nel `<body>` → solo `…` placeholder + span)
- [ ] Conteggi zone/comuni dinamici (`${...}` non hardcoded)
- [ ] Label "X anni" specifici per scala (fascia/comune/zona)
- [ ] Console browser DevTools: 0 errori
- [ ] Slider liquidità muove i verdict in tempo reale (test interattivo manuale)

---

## 17. Doublecheck script — verifica matematica indipendente

Dopo aver rigenerato i JSON, prima di considerare il pacchetto pronto, **ri-calcola ogni headline number direttamente dal CSV grezzo** e asserta l'eguaglianza con il JSON. Questo cattura: regressioni nel compute layer, drift fra `signals.py` e `compass.py`, parsing CSV rotto.

**Script eseguibile pronto:** [`scripts/doublecheck-city.py`](scripts/doublecheck-city.py) — parametrizzato per città, contiene già il profilo Modena come reference.

```bash
python3 scripts/doublecheck-city.py --city modena
# ═══ MODENA math invariants ═══
#   signals ↔ compass equality  ✓
#   anni_orizzonte_* disambiguated  ✓
#   recompute yield mean(20 current zones) = 5.28  ✓
#   CSV span 2005-2026 = 21  ✓
#   47 comuni provincia in geojson + ranking  ✓
```

**Cosa verifica (5 invarianti):**

1. **Eguaglianza signals ↔ compass** sui numeri condivisi (`yield_*_pct`, `*_cagr_avg_pct`, `prezzo_*`, `zone_count`)
2. **`anni_orizzonte_*` disambiguato** — il vecchio campo ambiguo `anni_orizzonte` NON deve esistere; devono esistere `_dataset` e `_zone_correnti` (vedi §15.3 e fix #4)
3. **Yield filter (fix #3)** — ricalcolo indipendente `mean(yield_lordo_pct)` solo su zone con `dizione` deve combaciare con `headline.yield_medio_pct`
4. **Span dataset** — `max(year) - min(year)` direttamente dal CSV deve combaciare con `anni_orizzonte_dataset`
5. **Conteggio comuni provincia** — features del GeoJSON ≡ entries in `province_ranking`

**Replica per Catanzaro:** apri lo script, copia la entry `"modena"` del dict `PROFILES`, rinominala in `"catanzaro"`, aggiorna i 7 `expected_*` con i valori dopo la prima rigenerazione (li trovi nello stdout di `compute-catanzaro-signals.py`). Poi:

```bash
python3 scripts/doublecheck-city.py --city catanzaro
```

**Quando rilanciarlo:**

- Dopo ogni rigenerazione JSON (compute layer touch)
- Pre-commit / pre-deploy
- Quando un mockup mostra un numero "strano" — primo sospetto è drift compute

## 18. Anti-stale-string grep audit

I bug #1, #2, #5, #6, #7, #8 dell'audit Modena sono tutti la **stessa famiglia**: numero/testo hardcoded in HTML che diverge dai dati. Audit grep da eseguire prima di considerare i mockup pronti:

```bash
cd opportuni-poc

# 1. Conteggi numerici di copia (probabile hardcoded)
grep -nE '>\s*(1[0-9]|20|21|22|venti|ventun|ventidue)\s*(zone|comuni|anni|datapoint)' \
  mockups/<city>-*.html dashboard-<city>.html 2>/dev/null

# 2. Edizioni hardcoded tipo "2024-S1", "20241", "2023/2"
grep -nE 'EDIZIONE\s*[·•-]\s*(20[0-9]{2})' \
  mockups/<city>-*.html dashboard-<city>.html 2>/dev/null

# 3. Picchi/range €X.XXX hardcoded
grep -nE '€\s*[0-9]\.[0-9]{3}\s*(\)|nel|/)' \
  mockups/<city>-*.html dashboard-<city>.html 2>/dev/null

# 4. Etichette Δ con anno hardcoded (es. "Δ 21y")
grep -nE 'Δ\s*[0-9]+y' \
  mockups/<city>-*.html dashboard-<city>.html 2>/dev/null

# 5. Anni in parole hardcoded
grep -nE '(venti|trenta|quaranta|cinquanta|sessanta) anni' \
  mockups/<city>-*.html dashboard-<city>.html 2>/dev/null
```

Ogni match → o è davvero hardcoded (BUG) o è un placeholder con id (`<span id="...">N</span>` riempito da JS, OK).

**Regola d'oro:** se il numero rappresenta un dato che cambia da una città all'altra o da una rigenerazione all'altra → DEVE essere `<span id="…">…</span>` letto da JSON. Mai letterale.

### Pattern di soluzione canonico (riusabile)

```html
<!-- HTML: placeholder + fallback statico ragionevole -->
… <span id="hl-span-years">ventun</span> anni …
```

```javascript
// JS: derivazione dal JSON
const numWordIt = (n) => ({
  18:'diciotto', 19:'diciannove', 20:'venti', 21:'ventun',
  22:'ventidue', 23:'ventitré', 24:'ventiquattro', 25:'venticinque',
}[n] || String(n));
document.getElementById('hl-span-years').textContent =
  numWordIt(h.anni_orizzonte_dataset);
```

Salvabile come snippet boilerplate per ogni numero in copia di un nuovo mockup.

---

## 19. ⚠ Audit pre-UI cleanup — lezioni dalla sessione 2026-05-14 (Catanzaro)

**Contesto:** dopo aver generato i 3 mockup di Catanzaro (A-brief, B-heatmap, C-compass) replicando il template Modena, un audit critico ha rivelato **11 problemi nei dati + 5 problemi UI + 3 problemi residui** che NON sono visibili senza una verifica esplicita. Tutti sono stati risolti con math-proof differenziale. Questa sezione documenta in ordine cronologico ogni scoperta, perché è importante per le prossime città, e come prevenirla / risolverla.

**Regola d'oro generale:** dopo il primo run della pipeline NON aprire la UI. Prima fai un audit dei JSON output (sezione §17 + cose nuove qui sotto), poi tocca la UI solo se i dati sorgente sono puliti. La UI è un amplificatore di errori a monte.

### 19.1 — Fase Audit: incoerenze Python ↔ JS che generano verdict diversi

**Scoperta 1 — Discrepanza soglia BUY Python (65) vs JS (70).** Il `compute-*-compass.py` può aver soglia diversa dal `recomputeScore()` in `mockups/<city>-C-compass.html`. Risultato: una zona con score 67 ha `verdict:"BUY"` nel JSON ma diventa "WATCH" alla rilettura runtime. Il KPI "Candidati BUY" diventa inconsistente.

**Scoperta 2 — Pesi Python vs caption UI.** Tipicamente:
- Python: `{growth:0.30, yield:0.25, stability:0.20, momentum:0.15, level:0.10}`
- JS DEFAULT_WEIGHTS: `{growth:35, yield:30, stability:15, momentum:15, level:5}`
- Caption UI: "Default 35/30/15/15/5"

All'apertura il `score` nel JSON è stato calcolato con i pesi Python, poi il JS lo ricalcola live con i suoi → il numero mostrato non è quello del JSON.

**Scoperta 3 — Penalty `−10` se CAGR<0 solo nel JS.** Python emette `score` raw, JS lo penalizza. Conteggio BUY divergente fra `headline.n_buy_zone` (Python) e i rendering runtime.

**Cosa fare per le prossime città:**

1. **Single source of truth nel metadata del JSON.** Emetti scoring config dal Python:

```python
# In compute-<city>-compass.py
WEIGHTS_DEFAULT = {"growth":0.35,"yield":0.30,"stability":0.15,"momentum":0.15,"level":0.05}
BUY_THRESHOLD = 70
AVOID_THRESHOLD = 35
CAGR_NEGATIVE_PENALTY = 10

# nel payload finale:
"metadata": {
    "scoring": {
        "weights_default": WEIGHTS_DEFAULT,
        "buy_threshold": BUY_THRESHOLD,
        "avoid_threshold": AVOID_THRESHOLD,
        "cagr_negative_penalty": CAGR_NEGATIVE_PENALTY,
    }
}
```

2. **Nel JS, leggi da metadata, non hardcodare:**

```javascript
const FALLBACK_WEIGHTS = { growth:35, yield:30, stability:15, momentum:15, level:5 };
function getScoring() {
  const m = (state.data?.metadata?.scoring) || {};
  const weights = m.weights_default
    ? Object.fromEntries(Object.entries(m.weights_default).map(([k,v]) => [k, Math.round(v*100)]))
    : FALLBACK_WEIGHTS;
  return {
    weights,
    buyThreshold:  m.buy_threshold ?? 70,
    avoidThreshold: m.avoid_threshold ?? 35,
    cagrPenalty: m.cagr_negative_penalty ?? 10,
  };
}
function recomputeVerdict(score) {
  const sc = getScoring();
  return score >= sc.buyThreshold ? 'BUY' : score < sc.avoidThreshold ? 'AVOID' : 'WATCH';
}
```

3. **Python applica la stessa penalty:**

```python
def compute_score(z, pool_stats):
    # ... (norm di growth/yield/stab/mom/level)
    score = weighted_sum / total_w * 100
    if z.get("cagr") is not None and z["cagr"] < 0:
        score = max(0, score - CAGR_NEGATIVE_PENALTY)  # ALLINEA AL JS
    return {"score": round(score, 1), ...}
```

4. **Caption UI reattivo (no più hardcoded):**

```javascript
function updateWeightsCaption() {
  const sc = getScoring(), w = sc.weights;
  document.getElementById('weights-sub-caption').innerHTML =
    `Default <strong>${w.growth}/${w.yield}/${w.stability}/${w.momentum}/${w.level}</strong> · BUY soglia <strong>≥ ${sc.buyThreshold}</strong> · penalty <strong>−${sc.cagrPenalty}</strong>`;
}
```

**Math proof:** sul magazzini-tipologia di Catanzaro, BUY count passa da 13 (Python soglia 65, no penalty) → 9 (Python soglia 70 + penalty) = match esatto JS.

---

### 19.2 — Fase Audit: hardcoded thresholds dimenticati

**Scoperta 4 — `is_stale = ultimo_anno < 2020` hardcoded.** Catanzaro ha 1 comune stale, altre province ne avranno diversi. Da estrarre come parametro:

```python
STALE_YEAR_THRESHOLD = 2020  # in cima al file
# ...
is_stale = ultimo_anno_dati < STALE_YEAR_THRESHOLD
```

**Scoperta 7 — Trailing-zero heuristic threshold `5` hardcoded in 2 punti.** In `compute-volume-signals-<city>.py` la magic number `5` (per "se prev_NTN > 5 trim trailing zeros") compariva sia per `zone_metrics` sia per `aggregated_by_new`. Estraila in costante modulo:

```python
TRAILING_ZERO_PREV_THRESHOLD = 5
LOW_SAMPLE_NTN_THRESHOLD = 5  # FIX P5: aggiungi anche questa
# uso:
while rows[-1].get('ntn') in (0, None) and (rows[-2].get('ntn') or 0) > TRAILING_ZERO_PREV_THRESHOLD:
    rows.pop()
```

Per province con NTN naturalmente piccoli (Sud Italia, rurali) la soglia `5` può fallire diversamente — discuti prima di applicarla.

---

### 19.3 — Fase Audit: CONTAMINAZIONE PARSER CROSS-PROVINCIA (bug silente critico)

**Scoperta 10 — Il parser ingerisce zone di altre province** se queste compaiono in pagine adiacenti del PDF (es. Cosenza viene subito dopo Catanzaro nel PDF Calabria, e ha lo stesso codice `R2`). Il `range(p_com, p_com+10)` può sconfinare nella provincia successiva alfabetica.

**Sintomo concreto su Catanzaro:**
- R2/2019 nel timeseries aveva `denominazione: 'ZONA RURALE - C.DA GUARASSANO, BADESSA, TIMPONE DEGLI ULIVI'` (toponimo di Cosenza, NON di Catanzaro)
- Quotazione 0 (errore stampa AdE quella riga)
- NTN 12 (di Cosenza), mentre la vera R2 Catanzaro aveva NTN 1

**Come l'abbiamo scoperta:** abbiamo notato che la denominazione R2/2019 NON era coerente con altre annate (2017→"ZONA RURALE TRA BARONE E S.MARIA", 2019→"GUARASSANO"…). Inoltre il parser dichiarava "anomalia: quotazione = 0".

**Anche E1 (Donnici) era contaminazione:** "SUBURBANA DONNICI INFERIORE E SUPERIORE" è frazione di **Cosenza**, NON di Catanzaro. Aveva 1 sola riga (anno 2019), facilmente scambiata per dato residuale legittimo.

**Fix obbligatorio nel parser (FIX P1):**

```python
def find_capoluogo_pages(pdf, capoluogo_name, other_provinces):
    """Trova p_prov, p_com della capoluogo + p_boundary = inizio provincia successiva."""
    p_prov = p_com = p_boundary = None
    for i, page in enumerate(pdf.pages):
        if i < 5: continue  # skip indice
        text = (page.extract_text() or "")[:2000]
        if p_prov is None and re.search(rf'(La provincia|Provincia)\s*[-–]\s*{capoluogo_name}', text, re.I):
            p_prov = i; continue
        if p_com is None and re.search(rf'(Il comune|Comune)\s*[-–]\s*{capoluogo_name}', text, re.I):
            p_com = i; continue
        # BOUNDARY: cerca QUALSIASI provincia diversa dalla nostra
        if p_com is not None and p_boundary is None:
            m = re.search(r'(La provincia|Il comune)\s*[-–]\s*(\w+)', text, re.I)
            if m and m.group(2).lower() != capoluogo_name.lower():
                p_boundary = i  # PRIMA pagina della prossima provincia
    if p_boundary is None:
        p_boundary = len(pdf.pages)
    return p_prov, p_com, p_boundary

# Poi parse_zone() deve essere STRICT:
def parse_zone(pdf, p_com, p_boundary, ...):
    for pi in range(p_com, p_boundary):  # NON p_com+10!
        # ... extract ...
```

**Test obbligatorio dopo il fix:**

```python
# Per ogni anno, verifica che la denominazione delle zone OMI sia coerente toponomasticamente.
# Se R2/anno_X ha toponimo che non matcha R2/anni_precedenti → flag rosso, indaga.
```

**Math proof su Catanzaro:**
- Pre-fix: 222 zone rows, 48 zone distinte, quotazione min 0
- Post-fix: 221 zone rows (E1 sparita = era Cosenza), 47 zone distinte, quotazione min 439
- R2/2019: NTN 12→1, q 0→449, deno "GUARASSANO"→"BARONE E S.MARIA"

**Per la prossima città:** PRIMA cosa, dopo aver runnato il parser, esegui questo check:

```bash
python3 -c "
import json, re
from collections import defaultdict
v = json.loads(open('data/volumi/<city>-volumi-timeseries.json').read())
by_zona = defaultdict(list)
for r in v['zone_series']:
    by_zona[r['zona']].append((r['year'], (r.get('denominazione') or '').strip()))
print('Zone con denominazione discontinua fra anni — possibile cross-contamination:')
for zona, items in sorted(by_zona.items()):
    fps = {re.sub(r'[^\\w\\s]','',d.upper()).split()[0] if d else '' for _,d in items}
    if len(fps) > 1:
        print(f'  {zona}: {sorted(fps)}')
"
```

---

### 19.4 — Fase Audit: anno specifico mancante per scelta editoriale AdE

**Scoperta 11 — SR2019.pdf di Calabria/Catanzaro NON contiene zone OMI singole per il capoluogo.** Le 28 zone OMI sono state aggregate in 5 macroaree urbane comunali (Centro / Semicentro / Prima Periferia / Zona Ovest / Zona Nord). Il parser legittimamente ritorna `zone=0` per quell'anno — **NON è bug, è scelta editoriale AdE**.

Verifica: il PDF stesso ammette nel testo
> *"le 28 zone OMI in cui è suddiviso il territorio sono state aggregate in 10 macroaree 'urbane'"*

**Conseguenza non ovvia:** la serie zone OMI ha un buco nell'anno 2018 (data_year di SR2019). Le altre annate hanno tutte le zone.

**Math fact fondamentale (verificato in sessione):**
> **CAGR `(NTN_last/NTN_first)^(1/years) - 1` dipende SOLO da first, last, years. I valori intermedi NON entrano nel calcolo. Quindi il buco non impatta il CAGR né i verdict BUY/AVOID.**

Δ CAGR pre/post iniezione 2018 = 0.000 esatto su 27 zone OLD + 16 zone NEW. Verificato.

**Cosa cambia col buco 2018:** sparkline UI ha gap visivo, volatilità CV calcolata su un punto in meno, cross-year validation (declared `ntn_var_pct` di SR2020 confronta 2019 vs 2018 mancante) genera ~39 issue spurie.

**Soluzione: macroaree-downscaling (opzionale ma raccomandata).** Lo script `inject-2018-from-macroaree.py` ricostruisce NTN per zona OLD:

```
NTN_2018(zona) = NTN_2017(zona) × (NTN_2018(macroarea) / NTN_2017(macroarea))
```

I 5 fattori macroarea estratti dai PDF SR2018+SR2019 per Catanzaro:
- CENTRO: 177/116 = 1.5259
- PRIMA PERIFERIA: 102/49 = 2.0816
- SEMICENTRO: 8/7 = 1.1429
- ZONA NORD: 13/15 = 0.8667
- ZONA OVEST: 139/153 = 0.9085
- TOTALE_COMUNE: 439/340 = 1.2912 (fallback per zone Lido/rurali fuori dalle 5 macroaree)

Ogni zona OLD ottiene `_interpolated: true` come flag → la UI mostra badge `◐ 2018 stim` (tratteggio dotted) invece di `○ gap 2018`. Vedi `scripts/inject-2018-from-macroaree.py` per il pattern completo.

**Generalizzabile?** Sì, ma DIPENDE dalla provincia. SR2019 Calabria ha questo formato; altri SR potrebbero avere lo stesso problema in altri anni. **Check obbligatorio:**

```bash
# Per ogni SR<year>.pdf, verifica se contiene zone OMI singole per il capoluogo
python3 -c "
import pdfplumber, re, sys
fn = sys.argv[1]; cap = sys.argv[2]
with pdfplumber.open(fn) as pdf:
    has_zones = any(re.search(rf'\\b[B-E]\\d{{1,2}}\\b.*{cap}', (p.extract_text() or '')) for p in pdf.pages[5:])
    print(f'{fn}: zone OMI present? {has_zones}')
" data/volumi/sr2019_calabria.pdf Catanzaro
```

Se False → preparati ad aggregare via macroaree.

---

### 19.5 — Fase Audit: zone NTN-micro generano CAGR senza significato statistico

**Scoperta 15 — 11 zone su 48 con NTN_first<5.** Esempio Catanzaro:
- C1: NTN_first=3 (anno 2016) → CAGR statisticamente bullshit
- R1: NTN_first=1 → CAGR +21.9% è rumore
- E5, R4, R5 con NTN_first=1 nel 2024 → 0 storia

**Fix (P5):** flag esplicito nel JSON output:

```python
LOW_SAMPLE_NTN_THRESHOLD = 5
low_sample = ntn_first is not None and ntn_first < LOW_SAMPLE_NTN_THRESHOLD

zone_metric = {..., 'low_sample': low_sample, ...}
```

**Nel JS, badge:**

```javascript
if (vol.low_sample)
  parts.push('<span class="dq dq-lowsample" title="NTN_first<5: CAGR statisticamente debole">⚠ micro</span>');
```

**Non rimuovere dal pool — solo flaggare.** L'utente deve sapere che quella zona ha CAGR fragile, non escluderla dalla vista.

---

### 19.6 — Fase Audit: zone con quote omesse dall'ultimo anno AdE

**Scoperta 13 — D14 mancante in SR2025 (data_year=2024).** AdE ha pubblicato 18 zone NEW invece di 19. La zona "S.MARIA - LE FONTANE (BARONE)" è stata omessa probabilmente per soppressione statistica (NTN troppo basso).

**Fix (P6):** flag specifico nel JSON aggregated_by_new:

```python
aggregated = {
    ...
    'is_d14_missing_2024': (nw == 'D14') and (2024 not in valid_years),
}
```

**Generalizzazione:** per ogni capoluogo, dopo il parsing, log esplicito delle zone NEW che NON hanno dato sull'anno corrente:

```python
LATEST_YEAR = max(years_covered)
new_zones_in_geojson = {f['properties']['zona'] for f in geojson['features']}
new_zones_in_latest = {r['zona'] for r in zone_series if r['year']==LATEST_YEAR}
omitted = new_zones_in_geojson - new_zones_in_latest
if omitted:
    log.append(f"⚠ Zone NEW omesse da SR{LATEST_YEAR+1}.pdf: {sorted(omitted)}")
```

---

### 19.7 — Fase Audit: NTN var % >500% sono dati reali ma artefatti

**Scoperta 14 — C1=+809%, D9=+600%.** Il parser flagga ma mantiene. Le righe sono REALI nel PDF (AdE le stampa così) — significano che NTN nell'anno precedente era <1. Matematicamente var ((curr - prev) / prev) esplode con prev piccolo. Non sono bug parser.

**Fix (P7):** **mantieni** i valori NTN/IMI/quotazione validi, ma quarantina la var% in `_anomalies` separato:

```python
NTN_VAR_QUARANTINE_THRESHOLD = 500.0
def is_anomaly_row(r):
    v = r.get('ntn_var_pct')
    return v is not None and abs(v) > NTN_VAR_QUARANTINE_THRESHOLD

zone_anomalies = [r for r in zone_all if is_anomaly_row(r)]

payload = {
    ...
    "zone_series": zone_all,  # tutte le righe restano qui
    "_anomalies": {
        "zone": zone_anomalies,
        "_doc": "Righe con |NTN_var|>500%: artefatto NTN<1 nell'anno precedente. NTN/IMI/quotazione validi, solo var% inaffidabile.",
    }
}
```

**Nel mockup:** non visualizzare la var% per quelle righe specifiche, ma il NTN e IMI sì.

---

### 19.8 — Fase Audit: pool eterogeneo zone+comuni nella stessa scala min-max

**Scoperta 5 — `pool = current_zones + prov_list` normalizza zone OMI capoluogo (19 zone B/C/D fascia) insieme a 80 comuni provincia.** Una zona B Centro Storico e un comune di 800 abitanti finiscono nella stessa scala 0-1 per CAGR/yield/prezzo. Eterogeneo per definizione.

**Fix (P8):** documentare nel metadata + warning pannello UI:

```python
"metadata": {
    "pool_composition": {
        "current_zones_count": "zone OMI capoluogo con dizione valorizzata",
        "province_ranking_count": "comuni provincia con CAGR≥2 anni dati",
        "warning": "Pool combina zone OMI capoluogo + comuni provincia nella stessa normalizzazione min-max. Score relativi al pool: BUY qui NON paragonabile in assoluto con altre province.",
    }
}
```

UI mostra disclaimer:
> *BUY/AVOID sono **relativi al pool [Catanzaro]**. Una zona BUY qui significa "top tier locale", non confrontabile con altre province.*

**Decisione di prodotto:** se vuoi confronti italici inter-provincia → serve benchmark assoluto (yield ≥ 5%, CAGR ≥ 2%). Decisione di prodotto, non tecnica.

---

### 19.9 — Fase Audit: mapping OLD→NEW fatto a tavolino è inaffidabile

**Scoperta 8 — `_method: "ispezione manuale denominazioni + spatial reasoning"`.** Il mapping codici OLD (pre-2024) → NEW (2024+) basato solo sul "ragionare guardando i toponimi" produce errori sistematici. Verificato su Catanzaro:

**D9 (CZ Lido a monte SS106) → D15 SBAGLIATO.** Mapping a tavolino plausibile (D15 = "Catanzaro Est fino a SS106"). Ma:
- q(D9 2023) = 763 €/m² · q(D15 2024) = 1103 €/m² → **+44.6% in 1 anno** = impossibile in real estate
- q(D22 2024) = 1054 €/m² → **+38.1%** = comunque impossibile
- Nessuna NEW 2024 ha quotazione coerente con D9 (la più vicina sarebbe R4 a 774 ma geograficamente non plausibile)

**Conclusione:** D9 era zona micro (single-digit NTN 2016-2023) probabilmente SMEMBRATA in più NEW. Mapping 1:1 → falso. Soluzione: `rel: "unknown"`.

**D10 (Giovino-Bellino) → D22 SBAGLIATO ma plausibile.** La quotazione D22 vs D10 è coerente (-11%) ma geograficamente:
- Giovino @ (38.835, 16.645) — frazione marina sul Lungomare
- D22 = "Catanzaro Est a monte Santo Janni" — zona INTERNA, non costiera

**Vera mapping verificata via geocoding Nominatim + point-in-polygon:**
- Giovino → cade dentro poligono NEW **D20** (Lungo Mare Catanzaro Lido) ✓
- Bellino → cade in **R4** (Territorio Rurale Est)

**Metodologia raccomandata per le prossime città (Indagine #1 del 2026-05-14):**

```python
# 1. Geocoda ogni toponimo specifico di una zona OLD ambigua via Nominatim
import requests
def geocode(query, bbox_provincia):
    r = requests.get('https://nominatim.openstreetmap.org/search',
        params={'q': query, 'format': 'json', 'bounded': 1,
                'viewbox': f'{bbox_provincia[2]},{bbox_provincia[1]},{bbox_provincia[3]},{bbox_provincia[0]}'},
        headers={'User-Agent': 'opportuni-poc/1.0'}, timeout=10)
    return r.json()[0] if r.json() else None

# 2. Per ogni risultato (lat,lon), point-in-polygon sul GeoJSON delle NEW
import json
g = json.loads(open('data/geojson/<city>-zone-omi.geojson').read())
def pip(lon, lat, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi,yi = poly[i]; xj,yj = poly[j]
        if ((yi>lat)!=(yj>lat)) and (lon < (xj-xi)*(lat-yi)/(yj-yi+1e-30)+xi):
            inside = not inside
        j = i
    return inside
def find_zone(lon, lat):
    for f in g['features']:
        geom = f['geometry']
        polys = [geom['coordinates'][0]] if geom['type']=='Polygon' else [p[0] for p in geom['coordinates']]
        for poly in polys:
            if pip(lon, lat, poly): return f['properties']['zona']
    return None

# 3. Se più toponimi della stessa zona OLD cadono in NEW diverse → SPLIT (segnala)
# 4. Se tutti cadono nella stessa NEW → confidence:medium (high serve verifica documentale aggiuntiva)
```

**Confidence ladder (post-verifica geocoding):**
- `high`: ≥2 toponimi distinti che cadono nella stessa NEW + denominazione coerente
- `medium`: 1 toponimo geocodato + match denominazione, OPPURE 2 toponimi nella stessa NEW ma altri ambigui
- `low`: solo ragionamento testuale, no geocoding (= status "tavolino")
- `unknown`: toponimi non geocodabili pubblicamente O cadono in NEW diverse senza supporto a un mapping 1:1

**Toponimi non geocodabili via OSM/Nominatim:** contrade rurali storiche minori (es. Catanzaro "Soverito", "Visconte", "Cuticchietto" di D13). Servono fonti offline:
- Mappa storica OMI capoluogo (PDF AdE archive)
- Comune · Settore Urbanistica (richiesta scritta)
- Conoscenza locale (residente)

Documentare nel mapping JSON quali zone sono unknown + lasciare flag `unknown` nei badge UI.

---

### 19.10 — Phase Cleanup: ordinamento corretto degli script di pipeline

Dopo i fix, l'ordine corretto per Catanzaro (e prossime città) è:

```bash
# 1. Parse PDF AdE → timeseries grezzo (FIX P1, P7, P11)
python3 scripts/parse-volumi-ade-<city>.py

# 2. Iniezione anno mancante (se applicabile — vedi §19.4)
python3 scripts/inject-<year>-from-macroaree.py   # OPZIONALE

# 3. Compute signals base (FIX P3, P5, P6, P11)
python3 scripts/compute-<city>-signals.py
python3 scripts/compute-volume-signals-<city>.py

# 4. Compute compass (FIX P4, P8, P9)
python3 scripts/compute-<city>-compass.py
```

**Per la prossima città:** aggiungi un target Makefile dedicato:

```makefile
etl-catanzaro:
	python3 scripts/parse-volumi-ade-catanzaro.py
	python3 scripts/inject-2018-from-macroaree.py
	python3 scripts/compute-catanzaro-signals.py
	python3 scripts/compute-volume-signals-catanzaro.py
	python3 scripts/compute-catanzaro-compass.py
	@echo "✓ Catanzaro ETL completato"
```

---

### 19.11 — Phase UI: cosa fa la UI dei dati post-fix

Una volta che il JSON sorgente è pulito, la UI integra:

**UI-1: scoring DA metadata, NON hardcoded.** Vedi §19.1.

**UI-2: badges qualità dati su ogni zona.** Mostrali nel sparkline grid + lane rows + popup mappa:

```html
<!-- CSS -->
<style>
.dq { display:inline-block; padding:2px 7px; border-radius:2px; font:9.5px var(--mono);
      letter-spacing:.06em; margin-left:4px; border:1px dashed; cursor:help; }
.dq-lowsample  { color:oklch(50% 0.12 50);  border-color:oklch(70% 0.12 50);  background:oklch(97% 0.03 50); }
.dq-gap2018    { color:oklch(50% 0.10 250); border-color:oklch(70% 0.10 250); background:oklch(97% 0.03 250); }
.dq-interp     { color:oklch(45% 0.08 180); border-color:oklch(65% 0.08 180); background:oklch(97% 0.025 180); border-style:dotted; }
.dq-no<year>   { color:oklch(45% 0.16 30);  border-color:oklch(70% 0.15 30);  background:oklch(97% 0.04 30); }
.dq-unknown    { color:oklch(40% 0.005 75); border-color:oklch(60% 0.005 75); background:oklch(95% 0.005 75); }
</style>
```

```javascript
function dqBadgesHtml(vol) {
  if (!vol) return '';
  const out = [];
  if (vol.low_sample)            out.push('<span class="dq dq-lowsample" title="NTN_first<5">⚠ micro</span>');
  if (vol.has_2018_gap)          out.push('<span class="dq dq-gap2018" title="Manca 2018">○ gap 2018</span>');
  else if (vol.has_2018_interpolated)
                                  out.push('<span class="dq dq-interp" title="2018 stimato">◐ 2018 stim</span>');
  if (vol.is_<zone>_missing_<year>)
                                  out.push('<span class="dq dq-no24" title="Omessa AdE">⊘ no <year></span>');
  if (vol.rel === 'unknown')     out.push('<span class="dq dq-unknown" title="Mapping non risolto">? unknown</span>');
  return out.join('');
}
```

**UI-3: pannello "Qualità dati" in fondo alla pagina C-compass.** Aggrega counters + warning pool relativo. Pattern in `mockups/catanzaro-C-compass.html` → `renderDataQualityPanel()`.

**UI-4 (B-heatmap) + UI-5 (A-brief):** propagano gli stessi badge nei popup mappa e nel footer.

---

### 19.12 — Math proof obbligatorio prima di chiudere la sessione

Prima di consegnare i mockup, esegui questo blocco di test differenziale (template adattabile a qualsiasi città):

```python
# scripts/audit-math-proof.py
import json, re, subprocess

cp = json.loads(open('data/computed/<city>-compass.json').read())
vs = json.loads(open('data/computed/<city>-volume-signals.json').read())

# Test 1: single source of truth scoring presente
assert 'scoring' in cp['metadata'], "metadata.scoring mancante"
sc = cp['metadata']['scoring']
assert sc['buy_threshold'] is not None
assert sc['cagr_negative_penalty'] is not None

# Test 2: flag qualità dati presenti
agg = vs['aggregated_by_new_zone']
for z in agg:
    for field in ['n_obs', 'has_2018_gap', 'low_sample', 'confidence', 'rel']:
        assert field in z, f"Zona {z['zona_new']} senza {field}"

# Test 3: BUY count Python = BUY count rescore JS-style
def rescore_js(e, weights, penalty):
    c = e.get('score_components') or {}
    s = w = 0
    for k, wj in weights.items():
        if c.get(k) is not None: s += wj*c[k]; w += wj
    if w == 0: return None
    score = s/w*100
    if e.get('cagr') is not None and e['cagr'] < 0: score -= penalty
    return max(0, min(100, score))

W = {k: v*100 for k, v in sc['weights_default'].items()}
for tipo in cp['by_tipologia']:
    pool = cp['by_tipologia'][tipo]['zone_metrics'] + cp['by_tipologia'][tipo]['province_ranking']
    py_buy = sum(1 for z in pool if z.get('verdict') == 'BUY')
    js_buy = sum(1 for z in pool if (rescore_js(z, W, sc['cagr_negative_penalty']) or 0) >= sc['buy_threshold'])
    assert py_buy == js_buy, f"{tipo}: Python BUY={py_buy} != JS BUY={js_buy}"

# Test 4: nessuna cross-contamination (denominazioni coerenti per zona)
ts = json.loads(open('data/volumi/<city>-volumi-timeseries.json').read())
from collections import defaultdict
by_zona = defaultdict(list)
for r in ts['zone_series']:
    by_zona[r['zona']].append((r['year'], (r.get('denominazione') or '').upper()))
for zona, items in by_zona.items():
    first_tokens = {re.sub(r'[^\w]', ' ', d).split()[0] if d else '' for _, d in items}
    assert len(first_tokens) <= 1 or '' in first_tokens, f"Zona {zona} con denominazioni discontinue: {first_tokens}"

# Test 5: CAGR invarianza iniezione anno mancante (se applicabile)
# Salva volume-signals, riinietta, riconfronta
# (vedi `python3 scripts/inject-<year>-from-macroaree.py` + diff)

print("✓ tutti i test math-proof passano")
```

**Senza questo audit, è impossibile dire "i mockup sono affidabili per decisioni reali".** I numeri possono SEMBRARE giusti e ESSERE contaminati. La sessione 2026-05-14 di Catanzaro è stata istruttiva proprio perché ogni problema era visivamente invisibile finché non abbiamo cercato la prova matematica.

---

### 19.13 — Riepilogo nuove costanti & flag da emettere obbligatoriamente

| Costante / flag | Scope | Significato | Dove implementato |
|---|---|---|---|
| `WEIGHTS_DEFAULT` | Python compass | Pesi default normalizzati | `compute-<city>-compass.py` |
| `BUY_THRESHOLD` | Python + JS via metadata | Soglia verdict BUY | `metadata.scoring.buy_threshold` |
| `AVOID_THRESHOLD` | idem | Soglia verdict AVOID | idem |
| `CAGR_NEGATIVE_PENALTY` | idem | Penalty score se CAGR<0 | idem |
| `TRAILING_ZERO_PREV_THRESHOLD` | Python volume | Soglia trim trailing zero NTN | `compute-volume-signals-<city>.py` |
| `LOW_SAMPLE_NTN_THRESHOLD` | idem | Flag micro-NTN | idem |
| `NTN_VAR_QUARANTINE_THRESHOLD` | Python parser | Soglia quarantine var% | `parse-volumi-ade-<city>.py` |
| `STALE_YEAR_THRESHOLD` | Python signals | Cutoff comuni stale | `compute-<city>-signals.py` |
| `low_sample` | flag su zona | NTN_first<threshold | volume-signals.json |
| `has_2018_gap` | flag su zona | Anno mancante non ricostruibile | idem |
| `has_2018_interpolated` | flag su zona | Anno ricostruito via macroaree | idem |
| `is_<zone>_missing_<year>` | flag specifico | Zona omessa dall'ultimo SR | idem |
| `interpolated` | flag su row series | Punto serie ricostruito | idem |
| `confidence` | flag su mapping | high/medium/low/none | mapping JSON + aggregated_by_new |
| `rel` | flag su mapping | direct/renamed/merged_into/reclassified/unknown | idem |

---

### 19.14 — Anti-pattern da NON ripetere su nuove città

1. **❌ NON aprire la UI prima di un audit dei JSON.** I numeri sbagliati sembrano giusti.
2. **❌ NON hardcodare soglie/pesi/penalty nel JS** se non sono ALSO nel JSON metadata.
3. **❌ NON considerare il parser sicuro** finché non hai verificato che `denominazione` di ogni zona è coerente tra anni.
4. **❌ NON marcare un mapping `confidence:high` senza geocoding evidence.**
5. **❌ NON eliminare righe con var%>500% dal timeseries** — quarantinale ma mantieni NTN/IMI.
6. **❌ NON assumere che il CAGR sia compromesso da un anno mancante** — math proof: dipende solo da first/last/years.
7. **❌ NON fidarti del "compute layer signals"** se non emette gli stessi flag del "volume-signals" — coerenza inter-script obbligatoria.
8. **❌ NON ignorare zone con NTN_first<5** — non escluderle, ma flaggale come `low_sample`.
9. **❌ NON usare CAGR come unico segnale BUY** se la zona ha confidence:low|none o low_sample:true.
10. **❌ NON mostrare KPI assoluti senza warning pool relativo** — l'utente investitore tenderà a confrontarli inter-provincia.

---

### 19.15 — Tempo & costo addizionale stimato per le prossime città

| Attività audit | Effort | Note |
|---|---|---|
| §19.3 detection cross-contamination | 30 min | Script check denominazioni + fix parser boundary |
| §19.4 detection anno mancante PDF | 15 min | Check `has_zones` per ogni SR.pdf |
| §19.4 macroaree-downscaling injection | 1h | Solo se anno mancante in formato macroaree |
| §19.7 quarantine anomalies | 15 min | Logica banale, costanti |
| §19.5 low_sample flag | 10 min | Solo flag + condizioni |
| §19.6 missing-latest-year flag | 10 min | Detect + flag |
| §19.9 verifica mapping ambigui via geocoding | 30-60 min | Dipende da quante zone "renamed_low"/"unknown" |
| §19.1 + §19.2 allineamento soglie/pesi | 20 min | Single source of truth pattern |
| §19.11 propagazione badges UI | 30 min | CSS + dqBadgesHtml in 3 mockup |
| §19.12 math proof script | 30 min | Adattare audit-math-proof.py |
| **TOTALE** | **~4-5h** | aggiunte ai 30 min replica base + 2h volumi (sezione §13) |

Investimento alto ma una tantum per provincia. Costo zero in € (tutto pubblico).

---
