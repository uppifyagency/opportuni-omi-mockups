# Calibrazione soglie BUY/WATCH/AVOID — analisi data-driven

**Data:** 2026-05-17  ·  **Script:** [`scripts/threshold-calibration.py`](../../scripts/threshold-calibration.py)

## Diagnosi

Lo score 0-100 del compass è una **media pesata di 5 componenti min-max normalizzate sul proprio pool**. Per definizione matematica:

- Una zona può avere score=100 solo se è il massimo simultaneo su tutte le 5 dimensioni (crescita, yield, stabilità, momentum, livello prezzo).
- Una zona con `cagr<0` perde 10 punti di penalty.
- Statisticamente, la distribuzione segue una media di 5 variabili uniformi normalizzate → CLT → approssimativamente normale centrata su ~50 con sd ~10-12.

**Implicazione:** soglie assolute come 65 o 70 implicano richiedere il top X% molto piccolo della distribuzione (top 7% per Modena, top 1% per Bologna, IMPOSSIBILE per Catanzaro).

## Numeri pool (estratti da `data/computed/<city>-compass.json`)

| Città | n pool | min | P25 | P50 | P75 | **P85** | P90 | P95 | max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **Modena** | 98 | 33.4 | 42.8 | 50.0 | 59.9 | **61.9** | 62.9 | 66.4 | **83.5** |
| **Bologna** | 108 | 6.0 | 40.1 | 47.4 | 55.9 | **58.6** | 59.9 | 63.8 | **69.9** |
| **Catanzaro** | 131 | 21.7 | 41.3 | 43.4 | 50.0 | **52.0** | 53.0 | 55.4 | **61.1** |

## Diagnosi delle soglie attuali

| Città | Soglia attuale BUY | Max score del pool | BUY count |
|---|---:|---:|---:|
| **Modena** | 65 | 83.5 | 7 (7%) |
| **Bologna** | 70 | 69.9 (sotto soglia!) | **0** |
| **Catanzaro** | 70 | 61.1 (sotto soglia!) | **0** |

> **Bug strutturale:** per Bologna e Catanzaro la soglia 70 è LETTERALMENTE sopra il massimo del pool. Nessuna zona può mai diventare BUY — è impossibile per costruzione, non una valutazione di mercato.

## Proposta · soglia percentile-based

**Strategia A (raccomandata):** soglie relative al pool della città.

- **BUY** = score ≥ P85 del proprio pool (top 15%)
- **WATCH** = P15 ≤ score < P85 (70% centrale)
- **AVOID** = score < P15 (bottom 15%)

**Vantaggi:**
- BUY count stabile per ogni città (~15-20 entry)
- Semantica chiara: "top tier locale"
- Non richiede assumption sulla forma della distribuzione
- Robusta al weight jitter ±10pp (Monte Carlo §I)

**Svantaggi:**
- BUY a Bologna ≠ BUY a Catanzaro in assoluto (già documentato come `pool_composition.warning` nel metadata JSON, §19.8)

## Impatto numerico

| Città | Soglia attuale | BUY ora | **Nuova soglia P85** | **BUY nuova** | Δ |
|---|---:|---:|---:|---:|---:|
| **Modena** | 65 | 7 | **61.9** | **15** | +8 |
| **Bologna** | 70 | 0 | **58.6** | **17** | +17 |
| **Catanzaro** | 70 | 0 | **52.0** | **20** | +20 |

**Totale BUY:** da **7** (con soglie attuali) a **52** (con P85). Aumento +45 entry → segnale BUY ora informativo per investitori reali.

## Implementazione

Modifica `scripts/compute-<city>-compass.py` per calcolare la soglia dinamicamente:

```python
# Sostituisce:
# BUY_THRESHOLD = 70
# AVOID_THRESHOLD = 35

# Con:
BUY_PERCENTILE = 85   # top 15%
AVOID_PERCENTILE = 15 # bottom 15%

# Dopo aver calcolato tutti gli score del pool:
pool_scores = [z['score'] for z in pool if z.get('score') is not None]
import numpy as np
buy_threshold = float(np.percentile(pool_scores, BUY_PERCENTILE))
avoid_threshold = float(np.percentile(pool_scores, AVOID_PERCENTILE))

# Aggiornare metadata.scoring:
payload["metadata"]["scoring"]["buy_threshold"] = round(buy_threshold, 1)
payload["metadata"]["scoring"]["avoid_threshold"] = round(avoid_threshold, 1)
payload["metadata"]["scoring"]["threshold_method"] = "percentile-based (P85/P15 of pool)"
```

Il JS dei mockup C-compass legge già `metadata.scoring.buy_threshold` dinamicamente (single-source-of-truth pattern, §19.1) → nessun fix lato HTML necessario.

## Visualizzazione

Vedi [`fig-threshold-calibration.png`](fig-threshold-calibration.png):
- **Pannello sinistro:** CDF degli score per le 3 città, con marker P85 e linee delle soglie attuali. Bologna/Catanzaro non superano mai la soglia 70.
- **Pannello destro:** confronto BUY count attuale (grigio) vs nuova soglia P85 (colori per città).

## Raccomandazione finale

1. **Adottare soglia percentile-based** (P85 BUY / P15 AVOID) in tutti i 3+ compute scripts compass.
2. **Documentare nel UI** il significato della soglia: "top 15% del pool [city]" sotto il KPI.
3. **Quando si compara investitore con due città**: usare il `quant_score` di `top5-investment.py` (che integra anche volume momentum/quadrant) come ranking primario, e tenere il compass verdict come complemento.

L'utente che chiedeva "perché tutto è WATCH" aveva ragione: era un artefatto della soglia, non del mercato.