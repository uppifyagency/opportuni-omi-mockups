# Audit math-proof — Bologna

**Generato:** 2026-05-17 18:20
**Skill stack:** numpy 2.2.6 · scipy scipy.stats · statsmodels 0.14.6 · pymoo · aeon · networkx 3.5 · polars 1.40.1 · simpy · matplotlib 3.10.6

**Esito globale:** 23 PASS · 0 FAIL · 2 WARN (25 test)

| # | Test | Esito | Dettaglio |
|---|---|---|---|
| 1 | Inv1a · signals.yield == compass.yield | ✅ PASS | sig=4.71 com=4.71 |
| 2 | Inv1b · signals.CAGR ≈ compass.CAGR (tol 0.1pp) | ✅ PASS | sig=0.2 com=0.17 |
| 3 | Inv1c · signals.prezzo == compass.prezzo | ✅ PASS | sig=2864.0 com=2864.0 |
| 4 | Inv1d · |signals.zone_count − compass.zone_count| ≤ 2 (semantica: dizione vs dizione+CAGR) | ✅ PASS | sig=32 (con dizione) com=31 (con dizione+CAGR) diff=1 |
| 5 | Inv1d UX · zone con dizione ma senza CAGR | ⚠️ WARN | 1 zone visualizzabili ma non rankabili: ['R1'] |
| 6 | Inv2 · anni_orizzonte disambiguato (Modena pattern fix#4) | ✅ PASS | _dataset=21 _zone_correnti=21 |
| 7 | Inv3 · yield recompute mean(current zones) == headline | ✅ PASS | recomp(31 z) = 4.71 vs hdr 4.71 |
| 8 | Inv4 · CSV span = headline.anni_orizzonte (polars) | ✅ PASS | CSV 2005-2026 = 21 vs hdr 21 |
| 9 | Inv5 · geojson features == signals.province_ranking | ✅ PASS | geo=55 ranking=55 |
| 10 | CSV recompute · 10 zone via polars (CAGR + yield) | ✅ PASS | 10/10 match (tol CAGR=1e-3, yield=0.05) | fail:  |
| 11 | HTML · bologna-A-brief.html fetcha bologna-signals.json | ✅ PASS | atteso bologna-signals.json |
| 12 | HTML · bologna-B-heatmap.html fetcha bologna-signals.json | ✅ PASS | atteso bologna-signals.json |
| 13 | HTML anti-stale-string scan | ⚠️ WARN | 1 match (potenziali stale, review manuale) · es: bologna-A-brief.html: edizione hardcoded → .../p>     <div class="dateline">EDIZIONE · 2025-S2 · <sp |
| 14 | EDA · CAGR distribution sanity | ✅ PASS | n=31 skew=-0.83 kurt=1.50 SW p=0.158 IQR outl=3 |
| 15 | EDA · Kruskal-Wallis CAGR fra fasce | ✅ PASS | H=9.19 p=0.0564 (p<0.05 → fasce significativamente diverse) | grouped fasce=['D', 'E', 'B', 'C', 'R'] |
| 16 | Time series · OLS slope per fascia (statsmodels) | ✅ PASS | 5 fasce analizzate, 1 con slope p<0.05 (significative) |
| 17 | Volume · IMI ∈ [0%, 10%] | ✅ PASS | min=0.84 max=3.63 n=34 |
| 18 | Volume · quadrant prezzo×NTN populated | ✅ PASS | 4/4 quadranti popolati: {'Q1_HOT': 7, 'Q2_OVERPRICED': 9, 'Q3_OPPORTUNITY': 10, 'Q4_DEAD': 6, 'unknown': 2} |
| 19 | Volume · momentum diversity (≥3 categorie) | ✅ PASS | 5 categorie: {'rocket': 0, 'growing': 5, 'stable': 15, 'cooling': 9, 'frozen': 4, 'unknown': 1} |
| 20 | Volume · cross-year NTN_var consistency (gap<5pp) | ✅ PASS | 3/168 discrepanze >5pp (1.8%) |
| 21 | Score recompute · 10 entry | ✅ PASS | 10/10 match (tol 0.5) | fails:  |
| 22 | Pareto · top_buy ⊂ pool (overlap CAGR×yield ≥30%) | ✅ PASS | |PF|=5 top_buy=6 overlap=33% |
| 23 | Monte Carlo simpy · BUY count under weight jitter ±10pp | ✅ PASS | base=0 MC 90% CI=[0,3] median=1 n_sims=1000 |
| 24 | k-NN · distanze comparables monotone non-decrescenti | ✅ PASS | 0 violazioni su 32 zone |
| 25 | k-NN · network metrics computed (networkx) | ✅ PASS | |V|=32 |E|=84 density=0.169 avg_deg=5.25 clust=0.505 fascia_assort=0.165 |

## Figure

- `fig-cagr-dist.png` — distribuzioni CAGR/yield/vol zone correnti + KS/Shapiro/Kruskal
- `fig-pvq-scatter.png` — scatter prezzo×NTN con quadranti + mediane
- `fig-ts-fascia.png` — serie storica per fascia OMI + OLS slope shaded CI 95%
- `fig-score-mc.png` — Monte Carlo verdict-BUY robustness sotto weight jitter
- `fig-knn-graph.png` — grafo k-NN comparables zone (degree/clustering)
- `fig-pareto.png` — Pareto front empirico CAGR×yield + reference NSGA-II