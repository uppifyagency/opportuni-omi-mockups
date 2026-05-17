# HANDOFF — opportuni-poc

**Per:** chiunque (umano o agente AI) raccolga il progetto da qui in avanti.
**Versione:** 2026-05-17 · post-fix `threshold-scientific` (Jenks natural breaks).
**Repo target:** [`uppifyagency/opportuni-omi-mockups`](https://github.com/uppifyagency/opportuni-omi-mockups).
**Working directory:** `/Users/vladvrinceanu/Desktop/PROGETTI ANTYGRAVITY/CLI-Everything/opportuni-poc/`

---

## 0. Cosa stai prendendo in mano (TL;DR)

Tre dashboard HTML statiche (`A-brief`, `B-heatmap`, `C-compass`) × quattro province italiane (**Modena**, **Bologna**, **Catanzaro**, **Reggio Emilia**) alimentate da dati ufficiali OMI (Agenzia delle Entrate), con 20+ anni di storia di prezzi al m². Tutto in Python stdlib + HTML/CSS/JS vanilla + MapLibre GL. Nessuna API key, nessun build step, costo zero.

Sopra la pipeline c'è un **audit math-proof automatizzato** (`scripts/audit-math-proof.py`) che verifica con 10 gruppi di test scientifici la veridicità di ogni numero esposto nei mockup.

Sotto la pipeline c'è una **calibrazione scientifica delle soglie BUY/AVOID** del compass (`scripts/_threshold_lib.py`): metodo principale Jenks natural breaks (k=3), con esposizione trasparente di Otsu, GMM e P85 come alternative.

---

## 1. Storia recente (cosa abbiamo fatto)

Cronologia delle iterazioni significative:

### 2026-05-14 · prima generazione
- Pipeline base Modena + Catanzaro: 6 mockup, signals + compass + volume signals.
- Documento di replica `REPLICATE-FOR-OTHER-PROVINCE.md` (§1-19).
- Lezioni dell'audit Catanzaro: cross-contamination parser PDF, low_sample NTN<5, mapping OLD→NEW con confidence ladder, soglie/pesi single-source-of-truth.

### 2026-05-17 mattina · estensione a Bologna
- Bologna A944, ISTAT 037: 55 comuni, 34 zone OMI capoluogo. Pipeline replicata in ~50 min.
- Backfill Sagona (605 file), GeoPOI 2025-S2, PDF SR Emilia-Romagna riutilizzati.
- 3 mockup Bologna creati come fork da Catanzaro template.

### 2026-05-17 pomeriggio · audit math-proof scientifico
- Script `scripts/audit-math-proof.py` (10 gruppi di test, 6 figure publication-quality per città).
- Integrate **7 skill** dal repo [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills): statsmodels, pymoo, aeon, networkx, polars, simpy, matplotlib.
- Esito: 64 PASS · 0 FAIL · 6 WARN su 70 test (cross-city).
- **Bug reale individuato e fixato**: Catanzaro yield headline 4.80% → 4.85% (filtro `dizione` mancante).
- **Bug infrastrutturale**: CSV `prezzi.csv` sovrascritto dal backfill Bologna → ricostruito da TUTTA la cache JSON (91k righe, 182 comuni).

### 2026-05-17 sera · copy professionale italiano
- Riscritto il copy dei 9 mockup (3 viste × 3 città + 3 RE) con registro Treccani-colloquiale, zero AI slop.
- Eliminate residue copia-incolla cross-città (es. "mercato del Sud" su Bologna, "due Calabrie" su Bologna, "Tirreno-Ionio" su Bologna).
- Brand: "Mockup A" → "Brief immobiliare", "Mockup C" → "Bussola di investimento".

### 2026-05-17 notte · calibrazione soglie scientifica
- Diagnosi: la soglia BUY=70 era **letteralmente irraggiungibile** per Bologna (max 69.9) e Catanzaro (max 61.1). Lo score è una media pesata di componenti normalizzate min-max → distribuzione centrata su ~50.
- **Prima iterazione**: soglia P85 percentile-based (euristica). Funziona ma è arbitraria.
- **Seconda iterazione (corrente)**: confronto rigoroso fra 6 metodi (Otsu, GMM k=3, Jenks k=3, KDE valley, P85, bootstrap CI 95%). Vedi `docs/audit/THRESHOLD-SCIENTIFIC-ANALYSIS.md`.
- **Decisione finale: Jenks natural breaks (k=3)** — k-means 1D ottimo, standard GIS per dati immobiliari. Tutte le alternative esposte in `metadata.scoring.alternative_thresholds`.
- Nuovo tag **`emerging`** = potenziale crescita (score in P50-P85, prezzo<mediana, CAGR>0): identifica zone "early entry" economicamente accessibili.

---

## 2. Stato attuale del prodotto

### Quattro province attive

| Provincia | Belfiore | ISTAT | Comuni | Zone OMI capoluogo | Yield medio | CAGR medio | Prezzo medio €/m² |
|---|:---:|:---:|---:|---:|---:|---:|---:|
| **Modena** | F257 | 036 | 47 | 20 | 5.28% | +0.25%/yr | 1.761 |
| **Bologna** | A944 | 037 | 55 | 32 | 4.71% | +0.20%/yr | 2.864 |
| **Catanzaro** | C352 | 079 | 80 | 19 | 4.85% | +0.46%/yr | 1.084 |
| **Reggio Emilia** | H223 | 035 | 42 | 24 | 5.50% | +0.10%/yr | ~1.500 |

### Distribuzione verdict (abitazioni civili, soglie Jenks)

| Provincia | Soglia BUY | Soglia AVOID | BUY | EMERGING | AVOID |
|---|---:|---:|---:|---:|---:|
| Modena | 65.5 | 50.1 | 2 | 6 | 25 |
| Bologna | 51.9 | 36.6 | 38 | 2 | 11 |
| Catanzaro | 46.5 | 32.2 | 37 | 9 | 4 |
| Reggio Emilia | 49.3 | 35.8 | 7 | 3 | 40 |

Le soglie sono **per-pool** (BUY a Modena ≠ BUY a Bologna in assoluto, documentato in `pool_composition.warning`).

---

## 3. Skill scientifiche che usiamo

**Sorgente:** [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) — repo con 137 skill scientifiche Markdown, licenze MIT/BSD.

### Skill operative

| Skill | Pacchetto Python | Uso nel progetto |
|---|---|---|
| **statsmodels** | `statsmodels` | OLS slope+CI 95%+p-value per fascia, ADF stationarity, Ljung-Box autocorrelation, Kruskal-Wallis |
| **scipy.stats** | `scipy` | Shapiro-Wilk normality, gaussian_kde, find_peaks, percentili |
| **sklearn.mixture** | `scikit-learn` | Gaussian Mixture Model (k=3) per cluster naturali score |
| **jenkspy** | `jenkspy` | Jenks natural breaks (k=3) — soglia BUY/AVOID principale |
| **pymoo** | `pymoo` | Pareto front validation (CAGR×yield max) vs top_buy empirico |
| **aeon** | `aeon` | Time series anomaly detection (matrix profile) — riservata per sample futuri ≥30 anni |
| **networkx** | `networkx` | Grafo k-NN comparables: density, clustering coef, fascia assortativity |
| **polars** | `polars` | CSV processing 90k+ righe veloce per recompute indipendente |
| **simpy** | `simpy` | Discrete-event Monte Carlo (1000 sim weight-jitter ±10pp robustness) |
| **matplotlib + seaborn** | `matplotlib`, `seaborn` | 18+ figure publication-quality (6 × 4 città + analisi metodologica) |
| **exploratory-data-analysis** | (workflow) | Markdown report auto-generation |

### Installazione one-shot

```bash
python3 -m pip install --user numpy scipy matplotlib seaborn pandas \
    statsmodels pymoo aeon networkx polars simpy scikit-learn jenkspy pdfplumber
```

Verifica:
```bash
python3 -c "
import numpy, scipy, matplotlib, statsmodels, pymoo, aeon, networkx, polars, simpy, sklearn, jenkspy, pdfplumber
print('OK')
"
```

### Quando consultare il repo K-Dense-AI

- Apri [`scientific-skills/<skill-name>/SKILL.md`](https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/scientific-skills) di una delle skill già usate per dettagli su API avanzate.
- Apri il README principale del repo per cercare nuove skill (es. PyMC per Bayesian, qiskit per quantistica) se servono per una nuova feature.

---

## 4. Architettura del codice

```
opportuni-poc/
├── data/
│   ├── geojson/                    # Confini provincia + zone OMI capoluogo (per città)
│   ├── sagona-backfill/
│   │   ├── cache/                  # JSON cache per (Belfiore × anno), idempotente
│   │   └── prezzi.csv              # CSV flat, ~91k righe, ricostruibile da cache
│   ├── volumi/                     # PDF SR AdE + JSON timeseries NTN/IMI (per città)
│   │   └── zone-mapping-old-new-<city>.json    # mapping OLD→NEW zone OMI
│   └── computed/                   # Output finali pronti per mockup
│       ├── <city>-signals.json
│       ├── <city>-compass.json
│       ├── <city>-volume-signals.json
│       └── <city>-zone-series.json
├── scripts/                        # Python stdlib + scientific libs
│   ├── _threshold_lib.py           # ★ Helper Jenks/Otsu/GMM/P85 condiviso
│   ├── sagona-backfill.py          # ETL prezzi OMI
│   ├── geopoi-zone-extract.py      # ETL zone OMI capoluogo
│   ├── parse-volumi-ade-<city>.py  # Parser PDF AdE per città
│   ├── compute-<city>-signals.py   # Compute headline + ranking
│   ├── compute-<city>-compass.py   # Compute score + verdict + EMERGING
│   ├── compute-volume-signals-<city>.py  # Volume momentum + quadrant
│   ├── audit-math-proof.py         # ★ Audit 10 gruppi test
│   ├── threshold-scientific-analysis.py  # ★ Confronto 6 metodi soglia
│   ├── threshold-calibration.py    # Analisi P85 baseline (legacy)
│   ├── top5-investment.py          # Ranking quant top-5 per città
│   └── doublecheck-city.py         # Doublecheck legacy (5 invarianti)
├── mockups/                        # HTML statici (3 viste × 4 città)
│   ├── investor-{A-brief,B-heatmap,C-compass}.html       # Modena
│   ├── bologna-{A-brief,B-heatmap,C-compass}.html
│   ├── catanzaro-{A-brief,B-heatmap,C-compass}.html
│   └── reggio-emilia-{A-brief,B-heatmap,C-compass}.html
├── docs/
│   └── audit/                      # Output dell'audit
│       ├── REPORT-CROSS-CITY.md
│       ├── THRESHOLD-SCIENTIFIC-ANALYSIS.md  # ★ Confronto 6 metodi
│       ├── THRESHOLD-CALIBRATION.md          # Analisi P85 baseline
│       ├── fig-threshold-methods-*.png       # 5 figure
│       └── <city>/                            # Report + figure + top5 per città
├── REPLICATE-FOR-OTHER-PROVINCE.md  # Documento di replica (20 sezioni)
├── HANDOFF.md                       # ★ Questo file
└── data/computed/<city>-*.json      # JSON pronti per mockup
```

★ = file aggiunti/modificati nelle ultime iterazioni 2026-05-17

---

## 5. Regole d'oro (cosa NON fare e cosa fare)

### ❌ Cose da NON fare mai

1. **Non aprire la UI prima dell'audit dei JSON.** I numeri sbagliati sembrano giusti finché non li ricalcoli indipendentemente.
2. **Non hardcodare numeri di copy nei mockup.** Ogni numero in copia deve essere un `<span id="…">…</span>` riempito da JS dal JSON. Mai literali "21 anni" o "20 zone" — diventeranno stale.
3. **Non considerare il parser PDF "sicuro" finché non hai verificato la coerenza di `denominazione` di ogni zona fra anni.** Cross-contamination con province adiacenti è il bug silente più tossico (§19.3 di REPLICATE).
4. **Non eliminare righe `var%>500%`** dal timeseries volumi: quarantinale ma mantieni NTN/IMI/quotazione.
5. **Non considerare scientifica una soglia arbitraria.** Una scelta è scientifica solo se è (a) confrontata con alternative, (b) giustificata da un criterio matematico (varianza intra-classe, log-likelihood, ecc.) e (c) le alternative sono esposte trasparentemente.
6. **Non mostrare KPI assoluti inter-provincia senza warning pool relativo.** BUY a Modena ≠ BUY a Bologna. Documentato in `pool_composition.warning`.
7. **Non commetter i PDF AdE nel repo** se sono troppo grandi (>4MB ciascuno) — usa il mirror inumeridibolognametropolitana.it o il link diretto AdE.
8. **Non amplificare le falsità.** Se un numero ha qualità dubbia, usa flag espliciti: `low_sample`, `data_quality: limited`, `confidence: low|none`, `rel: unknown`.

### ✅ Cose da fare sempre

1. **Esegui l'audit math-proof prima di consegnare.** `python3 scripts/audit-math-proof.py --city <city>` → 0 FAIL obbligatorio.
2. **Tutte le soglie/pesi/penalty in `metadata.scoring`.** Single source of truth Python↔JS. Il JS DEVE leggere da metadata, mai hardcodare.
3. **Espandi soglie alternative.** Per ogni nuova soglia (es. liquidity threshold), esponi anche Otsu/GMM/P85 nel JSON per trasparenza.
4. **Documenta il "perché" delle decisioni di prodotto.** Es. "abbiamo scelto Jenks invece di P85 perché è ottimale sotto k-means 1D" (vedi `THRESHOLD-SCIENTIFIC-ANALYSIS.md`).
5. **Per ogni numero in copia: `<span id>` letto da JS.** Vedi pattern §15 e §18 di REPLICATE.
6. **Per ogni nuova città: profilo nel `PROFILES` dict** di `audit-math-proof.py` + voce nel `REPLICATE` + voce in questo HANDOFF.
7. **Italiano del copy: registro Treccani-colloquiale.** Niente "esplora", "scopri", "all'avanguardia". Niente em-dash gratuiti, niente triplets vacui. Sì a punti e virgola, parentetiche complesse, sincerità sui limiti del dato.
8. **Cluster geografici specifici per provincia.** Non riusare "Tirreno-Ionio" per Bologna o "Pianura-Appennino" per Catanzaro. Adatta al territorio.

---

## 6. Procedure operative

### 6.1 — Aggiungere una nuova provincia (da zero a math-proof, ~50 min)

```bash
# Variabili: <city>=nuovacitta, <belfiore>=XXXX, <istat>=NNN, <prov_sigla>=XX, <regione>=nome_regione

# 1. Confini provincia
curl -sL -o data/geojson/<city>-province-comuni.geojson \
  "https://raw.githubusercontent.com/openpolis/geojson-italy/master/geojson/limits_P_<istat senza zero>_municipalities.geojson"

# 2. Estrai codici Belfiore
python3 -c "
import json
d = json.load(open('data/geojson/<city>-province-comuni.geojson'))
print(' '.join(sorted({f['properties']['com_catasto_code'] for f in d['features']})))
" > /tmp/<city>-codes.txt

# 3. Backfill Sagona (~22 min wall-clock, idempotente, cache JSON in data/sagona-backfill/cache/)
xargs python3 scripts/sagona-backfill.py < /tmp/<city>-codes.txt

# 3b. CRITICO: rebuild CSV da TUTTA la cache (altrimenti sovrascrive province precedenti)
python3 -c "
import csv, json, re
from pathlib import Path
cache_dir = Path('data/sagona-backfill/cache')
csv_path = Path('data/sagona-backfill/prezzi.csv')
all_rows = []
for fp in sorted(cache_dir.glob('*.json')):
    m = re.match(r'(\w+)_(current|\d+)\.json', fp.name)
    if not m: continue
    codice, anno_s = m.groups()
    anno = 2026 if anno_s == 'current' else int(anno_s)
    try: data = json.loads(fp.read_text())
    except: continue
    if not isinstance(data, dict): continue
    for zona, tipologie in data.items():
        if not isinstance(tipologie, dict): continue
        fascia = zona[0] if zona else ''
        for tipo, prices in tipologie.items():
            if not isinstance(prices, dict): continue
            stato = prices.get('stato_di_conservazione_mediano_della_zona')
            for op, prefix in (('acquisto','prezzo_acquisto'),('affitto','prezzo_affitto')):
                pmin=prices.get(f'{prefix}_min'); pmax=prices.get(f'{prefix}_max'); pmed=prices.get(f'{prefix}_medio')
                if pmin is None and pmax is None and pmed is None: continue
                all_rows.append({'anno': anno, 'comune_catasto': codice, 'zona': zona,
                                 'fascia': fascia, 'tipo_immobile': tipo, 'operazione': op,
                                 'stato_conservazione': stato, 'prezzo_min': pmin, 'prezzo_max': pmax, 'prezzo_medio': pmed})
fieldnames = ['anno','comune_catasto','zona','fascia','tipo_immobile','operazione','stato_conservazione','prezzo_min','prezzo_max','prezzo_medio']
with csv_path.open('w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=fieldnames); w.writeheader(); w.writerows(all_rows)
print(f'Rebuilt: {len(all_rows):,} rows, {len({r[\"comune_catasto\"] for r in all_rows})} comuni')
"

# 4. Zone OMI capoluogo (GeoPOI 2025-S2, ultimo semestre)
python3 scripts/geopoi-zone-extract.py \
  --codcom <belfiore> --prov <prov_sigla> --semestre 20252 \
  --prezzi-csv data/sagona-backfill/prezzi.csv \
  --out data/geojson/<city>-zone-omi.geojson

# 5. PDF SR AdE (se la regione non è già in data/volumi/)
mkdir -p data/volumi
for Y in 2019 2020 2021 2022 2023 2024; do
  curl -sL -o data/volumi/sr${Y}_<regione>.pdf \
    "https://www.inumeridibolognametropolitana.it/sites/default/files/banche-dati/dati-osservatorio-mercato-immobiliare/sr${Y}_<regione>.pdf"
done

# 6. Fork scripts compute (signals, compass, parser-volumi, volume-signals)
cp scripts/compute-bologna-signals.py scripts/compute-<city>-signals.py
cp scripts/compute-bologna-compass.py scripts/compute-<city>-compass.py
cp scripts/parse-volumi-ade-bologna.py scripts/parse-volumi-ade-<city>.py
cp scripts/compute-volume-signals-bologna.py scripts/compute-volume-signals-<city>.py
# Edit: sostituisci "bologna" → "<city>", "A944" → "<belfiore>", "BO" → "<prov_sigla>",
#       "Bologna" → "<NomeCittà>", "emilia_romagna" → "<regione>", MACROAREE_KNOWN secondo PDF

# 7. Compute pipeline
python3 scripts/compute-<city>-signals.py
python3 scripts/compute-<city>-compass.py            # ★ usa _threshold_lib (Jenks)
python3 scripts/parse-volumi-ade-<city>.py
python3 scripts/compute-volume-signals-<city>.py

# 8. Fork mockup (3 viste)
cp mockups/bologna-A-brief.html mockups/<city>-A-brief.html
cp mockups/bologna-B-heatmap.html mockups/<city>-B-heatmap.html
cp mockups/bologna-C-compass.html mockups/<city>-C-compass.html
# Edit: "Bologna" → "<NomeCittà>", "A944" → "<belfiore>", coords mappa, cluster geografici

# 9. AUDIT MATH-PROOF (★ OBBLIGATORIO)
# 9a. Aggiungi <city> al PROFILES di scripts/audit-math-proof.py:
#     "<city>": {"capoluogo": "<belfiore>", "prov_sigla": "<prov_sigla>"}
python3 scripts/audit-math-proof.py --city <city>
# → 0 FAIL obbligatorio. WARN ≤4 accettabili (documentate ognuna).

# 10. Verifica visiva
python3 -m http.server 8765 &
open http://localhost:8765/mockups/<city>-A-brief.html
open http://localhost:8765/mockups/<city>-B-heatmap.html
open http://localhost:8765/mockups/<city>-C-compass.html
```

### 6.2 — Workflow di sviluppo quotidiano

```bash
# Modificare un compute script
$EDITOR scripts/compute-<city>-compass.py

# Rigenerare il JSON
python3 scripts/compute-<city>-compass.py

# Re-audit
python3 scripts/audit-math-proof.py --city <city>

# Refresh mockup
open http://localhost:8765/mockups/<city>-C-compass.html
```

### 6.3 — Quando aggiungere un nuovo tipo di test all'audit

Apri `scripts/audit-math-proof.py`. Pattern:

```python
def test_my_new_check(rep, sig, com, out_dir, city):
    """Descrizione test."""
    # ... logica ...
    rep.add("Nome test · descrizione breve",
            condition_passed,
            f"dettaglio numerico {x}/{n}")
    # Se è informativo non blocker:
    rep.warn("Nome test", "dettaglio")
```

Aggiungi chiamata in `main()` dopo gli altri test. Aggiorna `REPORT-CROSS-CITY.md` con il nuovo gruppo.

### 6.4 — Quando proporre una nuova soglia / metrica

1. **Mai a tavolino.** Apri uno script di analisi (template: `scripts/threshold-scientific-analysis.py`).
2. **Confronta ≥3 metodi alternativi.** Esempio per una soglia: Otsu, Jenks, percentile, GMM.
3. **Esponi alternative in `metadata.scoring`** del JSON.
4. **Genera figura comparativa** in `docs/audit/`.
5. **Scrivi reasoning** in `docs/audit/<METRIC-NAME>-ANALYSIS.md`.
6. **Aggiorna HANDOFF.md + REPLICATE** se è una decisione metodologica permanente.

---

## 7. Cosa è ancora da fare (TODO operativo)

### Priorità ALTA
- [ ] **Badge `EMERGING` nei 12 mockup C-compass.** Già presente nel JSON come `top_emerging` e `n_emerging_zone/_provincia`, ma non visualizzato. CSS + render nel JS.
- [ ] **`EDIZIONE · 2025-S2` hardcoded** in Bologna/Catanzaro/RE: dovrebbe leggere da `metadata.semestre` del GeoJSON GeoPOI.
- [ ] **Audit colori mappe** (heatmap B + compass C): verificare che i colori rendano il dato (verde = positivo, rosso = negativo) e non siano statici/sbagliati.
- [ ] **Sezione §20 di REPLICATE** da aggiornare con Jenks (è ferma alla versione P85).

### Priorità MEDIA
- [ ] **Patch `sagona-backfill.py`** per costruire il CSV da TUTTA la cache, non solo dai codici argv (evita bug "CSV sovrascritto").
- [ ] **`anni_orizzonte` legacy in Catanzaro signals.** Migrare a `_dataset` + `_zone_correnti` come Modena/Bologna.
- [ ] **Tag liquidity nel score compass**: già implementato in `compute-volume-signals` ma non integrato nel score formula del compass. Aggiungere `liquidity` come 6° componente con peso ~10%.
- [ ] **Bootstrap CI per yield/CAGR** invece dei soli MC weight-jitter — quantifica incertezza statistica delle metriche headline.

### Priorità BASSA (estensioni)
- [ ] **PyMC Bayesian model** per stima yield futuro con prior bibliografica.
- [ ] **Aeon matrix profile** per anomaly detection sui timeseries fascia (≥30 anni).
- [ ] **Geocoding validation Nominatim** per ogni `dizione` zona OMI.
- [ ] **NSGA-II reference Pareto front** (pymoo) sul problema "selezionare N zone per portafoglio bilanciato".
- [ ] **Score liquidity quadrant×momentum integrato** come 6° dimensione dello score compass.

---

## 8. File chiave da NON dimenticare

| File | Cosa è | Quando toccarlo |
|---|---|---|
| `scripts/_threshold_lib.py` | Helper Jenks/Otsu/GMM/P85 per soglie | Mai (è già stabile). Toccato solo se si aggiunge un metodo. |
| `scripts/audit-math-proof.py` | Audit 10 gruppi test | Quando si aggiunge una nuova città (PROFILES dict) o un nuovo test |
| `scripts/threshold-scientific-analysis.py` | Confronto 6 metodi soglia | Per validare la scelta del metodo principale |
| `REPLICATE-FOR-OTHER-PROVINCE.md` | Guida replica step-by-step | Quando si aggiunge una procedura standard |
| `HANDOFF.md` (questo file) | Onboarding rapido | Quando il prodotto cambia in modo strutturale |
| `docs/audit/REPORT-CROSS-CITY.md` | Sintesi audit multi-città | Dopo ogni esecuzione audit completa |
| `docs/audit/THRESHOLD-SCIENTIFIC-ANALYSIS.md` | Diagnosi soglie 6 metodi | Quando si rivaluta la scelta della soglia |

---

## 9. Comandi rapidi cheat-sheet

```bash
# Avvio server HTTP per mockup
cd opportuni-poc && python3 -m http.server 8765

# Apri i 12 mockup (4 città × 3 viste)
for c in investor bologna catanzaro reggio-emilia; do
  for v in A-brief B-heatmap C-compass; do
    open "http://localhost:8765/mockups/${c}-${v}.html"
  done
done

# Audit math-proof per tutte le città
for c in modena bologna catanzaro reggio-emilia; do
  python3 scripts/audit-math-proof.py --city $c | tail -5
done

# Confronto scientifico soglie (6 metodi × 4 città)
python3 scripts/threshold-scientific-analysis.py

# Rigenera tutti i compass JSON con Jenks
python3 scripts/compute-compass.py            # Modena
python3 scripts/compute-bologna-compass.py
python3 scripts/compute-catanzaro-compass.py
python3 scripts/compute-reggio-emilia-compass.py

# Top 5 investment per città
for c in modena bologna catanzaro reggio-emilia; do
  python3 scripts/top5-investment.py --city $c | tail -20
done

# Push a GitHub (sync da opportuni-poc/ → opportuni-omi-mockups/ → push)
cd ../opportuni-omi-mockups
cp ../opportuni-poc/mockups/*.html mockups/
cp ../opportuni-poc/scripts/*.py scripts/
cp -r ../opportuni-poc/data/computed/*.json data/computed/
cp ../opportuni-poc/REPLICATE-FOR-OTHER-PROVINCE.md .
cp ../opportuni-poc/HANDOFF.md .
git add -A && git commit -m "feat: aggiornamento <descrizione>" && git push origin main
```

---

## 10. Contatti & riferimenti

- **Skill source:** [github.com/K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills)
- **Repo target:** [github.com/uppifyagency/opportuni-omi-mockups](https://github.com/uppifyagency/opportuni-omi-mockups)
- **Sagona API:** [3eurotools.it/api-quotazioni-immobiliari-omi](https://3eurotools.it/api-quotazioni-immobiliari-omi) — wrapper OMI Agenzia delle Entrate, free
- **GeoPOI AdE:** [www1.agenziaentrate.gov.it/servizi/geopoi_omi/](https://www1.agenziaentrate.gov.it/servizi/geopoi_omi/) — endpoint reverse-engineered (vedi `SAGONA.md`)
- **OMI banche dati:** [www.agenziaentrate.gov.it](https://www.agenziaentrate.gov.it/portale/web/guest/schede/fabbricatiterreni/omi/banche-dati-omi)
- **openpolis/geojson-italy:** [github.com/openpolis/geojson-italy](https://github.com/openpolis/geojson-italy) (CC-BY)
- **ISTAT codici comuni:** [istat.it](https://www.istat.it/it/archivio/6789)

---

## 11. Quando hai dubbi

1. **Sui numeri**: ricalcola dal CSV grezzo. Pattern in `audit-math-proof.py` test Gruppo B (polars 10 zone sample).
2. **Sulla scelta del metodo statistico**: confronta ≥3 alternative, esponi in JSON, scrivi reasoning.
3. **Sulla soglia di un cutoff**: applica Jenks come default. Se Jenks non funziona (pool <10), fallback a P85.
4. **Sul copy italiano**: registro Treccani-colloquiale. Lessico preciso, niente buzzword.
5. **Sull'audit**: `python3 scripts/audit-math-proof.py --city <city>` deve dare 0 FAIL prima di consegnare.

---

*Questo HANDOFF è un documento vivo. Aggiornalo dopo ogni iterazione significativa. Se cambi metodologia, aggiorna anche §5 (regole d'oro) e §3 (skill).*
