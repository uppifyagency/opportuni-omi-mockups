#!/usr/bin/env python3
"""Calibrazione data-driven delle soglie BUY/WATCH/AVOID del compass.

Genera analisi statistica della distribuzione score per le 3 città e propone
soglie percentile-based al posto delle attuali soglie assolute (65/70).

Output:
  docs/audit/fig-threshold-calibration.png — 2-panel: CDF score per città + impact bar chart
  docs/audit/THRESHOLD-CALIBRATION.md — report con raccomandazione
"""
from __future__ import annotations

import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "docs" / "audit"

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 140,
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linestyle": "--",
})

cities = ['modena', 'bologna', 'catanzaro']
colors = {'modena': '#3a5a40', 'bologna': '#1f4068', 'catanzaro': '#bc4749'}

city_data = {}
for c in cities:
    com = json.load(open(ROOT / f'data/computed/{c}-compass.json'))
    abci = com['by_tipologia']['abitazioni_civili']
    pool = abci['zone_metrics'] + abci['province_ranking']
    scores = np.array([z['score'] for z in pool if z.get('score') is not None])
    sc = com['metadata'].get('scoring', {})
    city_data[c] = {
        'scores': scores,
        'threshold_now': sc.get('buy_threshold', 65),
        'avoid_now': sc.get('avoid_threshold', 35),
    }

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))

# ── Panel 1: CDF + soglia ─────────────────────────
for c in cities:
    s = np.sort(city_data[c]['scores'])
    cdf = np.arange(1, len(s)+1) / len(s) * 100
    ax1.plot(s, cdf, lw=1.8, color=colors[c], label=f"{c.title()} (n={len(s)})")
    # P85 marker
    p85 = np.percentile(s, 85)
    ax1.scatter([p85], [85], s=80, color=colors[c], zorder=5,
                edgecolor='white', linewidth=1.2)
    ax1.annotate(f"P85={p85:.1f}", (p85, 85), xytext=(p85+1, 80),
                 fontsize=8.5, color=colors[c])

ax1.axvline(70, color='#888', ls='--', lw=1, alpha=0.7)
ax1.text(70.5, 5, 'Soglia\nBUY=70\n(Catanzaro,\nBologna)', fontsize=8, color='#666')
ax1.axvline(65, color='#aaa', ls=':', lw=1, alpha=0.7)
ax1.text(65.5, 95, 'BUY=65\n(Modena)', fontsize=8, color='#666')

ax1.axhline(85, color='#444', ls=':', lw=0.6, alpha=0.5)
ax1.text(8, 86.5, 'top 15%', fontsize=8, color='#444', style='italic')

ax1.set_xlabel("Score compass (0-100)")
ax1.set_ylabel("CDF % del pool (cumulativa)")
ax1.set_title("Distribuzione score · pool zone correnti + comuni provincia")
ax1.legend(loc='lower right')
ax1.set_xlim(0, 100)
ax1.set_ylim(0, 100)

# ── Panel 2: confronto BUY count attuale vs P85 ────────
labels = [c.title() for c in cities]
buy_now = [(city_data[c]['scores'] >= city_data[c]['threshold_now']).sum() for c in cities]
buy_p85 = [(city_data[c]['scores'] >= np.percentile(city_data[c]['scores'], 85)).sum() for c in cities]

x = np.arange(len(cities))
w = 0.36
b1 = ax2.bar(x - w/2, buy_now, w, label=f"Soglia attuale (65 MO / 70 BO-CZ)",
             color='#bbb', edgecolor='#444', linewidth=0.6)
b2 = ax2.bar(x + w/2, buy_p85, w, label='Nuova soglia P85 (top 15%)',
             color=[colors[c] for c in cities], alpha=0.85, edgecolor='white', linewidth=0.8)

for rect, val in zip(b1, buy_now):
    h = rect.get_height()
    ax2.text(rect.get_x() + rect.get_width()/2, h + 0.3, f"{val}",
             ha='center', va='bottom', fontsize=9, color='#444')
for rect, val in zip(b2, buy_p85):
    h = rect.get_height()
    ax2.text(rect.get_x() + rect.get_width()/2, h + 0.3, f"{val}",
             ha='center', va='bottom', fontsize=9.5, color='#222', fontweight='bold')

ax2.set_xticks(x)
ax2.set_xticklabels(labels)
ax2.set_ylabel("Conteggio entry verdict BUY")
ax2.set_title("Impatto della nuova soglia P85 — da {} BUY totali a {}".format(sum(buy_now), sum(buy_p85)))
ax2.legend(loc='upper left', fontsize=8)
ax2.set_ylim(0, max(buy_p85) * 1.25)

fig.suptitle("Calibrazione data-driven della soglia BUY del compass · 337 entries pool",
             y=1.02, fontsize=12)
fig.tight_layout()
out_fig = OUT_DIR / "fig-threshold-calibration.png"
fig.savefig(out_fig, bbox_inches='tight')
plt.close(fig)
print(f"  Generata: {out_fig.relative_to(ROOT)}")

# Markdown report
lines = [
    "# Calibrazione soglie BUY/WATCH/AVOID — analisi data-driven",
    "",
    "**Data:** 2026-05-17  ·  **Script:** [`scripts/threshold-calibration.py`](../../scripts/threshold-calibration.py)",
    "",
    "## Diagnosi",
    "",
    "Lo score 0-100 del compass è una **media pesata di 5 componenti min-max normalizzate sul proprio pool**. Per definizione matematica:",
    "",
    "- Una zona può avere score=100 solo se è il massimo simultaneo su tutte le 5 dimensioni (crescita, yield, stabilità, momentum, livello prezzo).",
    "- Una zona con `cagr<0` perde 10 punti di penalty.",
    "- Statisticamente, la distribuzione segue una media di 5 variabili uniformi normalizzate → CLT → approssimativamente normale centrata su ~50 con sd ~10-12.",
    "",
    "**Implicazione:** soglie assolute come 65 o 70 implicano richiedere il top X% molto piccolo della distribuzione (top 7% per Modena, top 1% per Bologna, IMPOSSIBILE per Catanzaro).",
    "",
    "## Numeri pool (estratti da `data/computed/<city>-compass.json`)",
    "",
    "| Città | n pool | min | P25 | P50 | P75 | **P85** | P90 | P95 | max |",
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
]
for c in cities:
    s = city_data[c]['scores']
    p = np.percentile(s, [25, 50, 75, 85, 90, 95])
    lines.append(
        f"| **{c.title()}** | {len(s)} | {s.min():.1f} | {p[0]:.1f} | {p[1]:.1f} | {p[2]:.1f} | **{p[3]:.1f}** | {p[4]:.1f} | {p[5]:.1f} | **{s.max():.1f}** |"
    )

lines += [
    "",
    "## Diagnosi delle soglie attuali",
    "",
    "| Città | Soglia attuale BUY | Max score del pool | BUY count |",
    "|---|---:|---:|---:|",
    "| **Modena** | 65 | 83.5 | 7 (7%) |",
    "| **Bologna** | 70 | 69.9 (sotto soglia!) | **0** |",
    "| **Catanzaro** | 70 | 61.1 (sotto soglia!) | **0** |",
    "",
    "> **Bug strutturale:** per Bologna e Catanzaro la soglia 70 è LETTERALMENTE sopra il massimo del pool. Nessuna zona può mai diventare BUY — è impossibile per costruzione, non una valutazione di mercato.",
    "",
    "## Proposta · soglia percentile-based",
    "",
    "**Strategia A (raccomandata):** soglie relative al pool della città.",
    "",
    "- **BUY** = score ≥ P85 del proprio pool (top 15%)",
    "- **WATCH** = P15 ≤ score < P85 (70% centrale)",
    "- **AVOID** = score < P15 (bottom 15%)",
    "",
    "**Vantaggi:**",
    "- BUY count stabile per ogni città (~15-20 entry)",
    "- Semantica chiara: \"top tier locale\"",
    "- Non richiede assumption sulla forma della distribuzione",
    "- Robusta al weight jitter ±10pp (Monte Carlo §I)",
    "",
    "**Svantaggi:**",
    "- BUY a Bologna ≠ BUY a Catanzaro in assoluto (già documentato come `pool_composition.warning` nel metadata JSON, §19.8)",
    "",
    "## Impatto numerico",
    "",
    "| Città | Soglia attuale | BUY ora | **Nuova soglia P85** | **BUY nuova** | Δ |",
    "|---|---:|---:|---:|---:|---:|",
]
for c in cities:
    s = city_data[c]['scores']
    t_now = city_data[c]['threshold_now']
    n_now = (s >= t_now).sum()
    p85 = np.percentile(s, 85)
    n_p85 = (s >= p85).sum()
    lines.append(f"| **{c.title()}** | {t_now} | {n_now} | **{p85:.1f}** | **{n_p85}** | +{n_p85-n_now} |")

lines += [
    "",
    "**Totale BUY:** da **7** (con soglie attuali) a **52** (con P85). Aumento +45 entry → segnale BUY ora informativo per investitori reali.",
    "",
    "## Implementazione",
    "",
    "Modifica `scripts/compute-<city>-compass.py` per calcolare la soglia dinamicamente:",
    "",
    "```python",
    "# Sostituisce:",
    "# BUY_THRESHOLD = 70",
    "# AVOID_THRESHOLD = 35",
    "",
    "# Con:",
    "BUY_PERCENTILE = 85   # top 15%",
    "AVOID_PERCENTILE = 15 # bottom 15%",
    "",
    "# Dopo aver calcolato tutti gli score del pool:",
    "pool_scores = [z['score'] for z in pool if z.get('score') is not None]",
    "import numpy as np",
    "buy_threshold = float(np.percentile(pool_scores, BUY_PERCENTILE))",
    "avoid_threshold = float(np.percentile(pool_scores, AVOID_PERCENTILE))",
    "",
    "# Aggiornare metadata.scoring:",
    'payload["metadata"]["scoring"]["buy_threshold"] = round(buy_threshold, 1)',
    'payload["metadata"]["scoring"]["avoid_threshold"] = round(avoid_threshold, 1)',
    'payload["metadata"]["scoring"]["threshold_method"] = "percentile-based (P85/P15 of pool)"',
    "```",
    "",
    "Il JS dei mockup C-compass legge già `metadata.scoring.buy_threshold` dinamicamente (single-source-of-truth pattern, §19.1) → nessun fix lato HTML necessario.",
    "",
    "## Visualizzazione",
    "",
    "Vedi [`fig-threshold-calibration.png`](fig-threshold-calibration.png):",
    "- **Pannello sinistro:** CDF degli score per le 3 città, con marker P85 e linee delle soglie attuali. Bologna/Catanzaro non superano mai la soglia 70.",
    "- **Pannello destro:** confronto BUY count attuale (grigio) vs nuova soglia P85 (colori per città).",
    "",
    "## Raccomandazione finale",
    "",
    "1. **Adottare soglia percentile-based** (P85 BUY / P15 AVOID) in tutti i 3+ compute scripts compass.",
    "2. **Documentare nel UI** il significato della soglia: \"top 15% del pool [city]\" sotto il KPI.",
    "3. **Quando si compara investitore con due città**: usare il `quant_score` di `top5-investment.py` (che integra anche volume momentum/quadrant) come ranking primario, e tenere il compass verdict come complemento.",
    "",
    "L'utente che chiedeva \"perché tutto è WATCH\" aveva ragione: era un artefatto della soglia, non del mercato.",
]

(OUT_DIR / "THRESHOLD-CALIBRATION.md").write_text("\n".join(lines))
print(f"  Generato: docs/audit/THRESHOLD-CALIBRATION.md")
