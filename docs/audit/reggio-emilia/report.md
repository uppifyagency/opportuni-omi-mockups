# Audit math-proof — Reggio-Emilia

**Generato:** 2026-05-17 20:03
**Skill stack:** numpy 2.2.6 · scipy scipy.stats · statsmodels 0.14.6 · pymoo · aeon · networkx 3.5 · polars 1.40.1 · simpy · matplotlib 3.10.6

**Esito globale:** 23 PASS · 0 FAIL · 0 WARN (23 test)

| # | Test | Esito | Dettaglio |
|---|---|---|---|
| 1 | Inv1a · signals.yield == compass.yield | ✅ PASS | sig=4.9 com=4.9 |
| 2 | Inv1b · signals.CAGR ≈ compass.CAGR (tol 0.1pp) | ✅ PASS | sig=2.41 com=2.41 |
| 3 | Inv1c · signals.prezzo == compass.prezzo | ✅ PASS | sig=1347.0 com=1347.0 |
| 4 | Inv1d · |signals.zone_count − compass.zone_count| ≤ 2 (semantica: dizione vs dizione+CAGR) | ✅ PASS | sig=24 (con dizione) com=24 (con dizione+CAGR) diff=0 |
| 5 | Inv2 · anni_orizzonte disambiguato (Modena pattern fix#4) | ✅ PASS | _dataset=21 _zone_correnti=2 |
| 6 | Inv3 · yield recompute mean(current zones) == headline | ✅ PASS | recomp(24 z) = 4.9 vs hdr 4.9 |
| 7 | Inv4 · CSV span = headline.anni_orizzonte (polars) | ✅ PASS | CSV 2005-2026 = 21 vs hdr 21 |
| 8 | Inv5 · geojson features == signals.province_ranking | ✅ PASS | geo=42 ranking=42 |
| 9 | CSV recompute · 10 zone via polars (CAGR + yield) | ✅ PASS | 10/10 match (tol CAGR=1e-3, yield=0.05) | fail:  |
| 10 | HTML · reggio-emilia-A-brief.html fetcha reggio-emilia-signals.json | ✅ PASS | atteso reggio-emilia-signals.json |
| 11 | HTML · reggio-emilia-B-heatmap.html fetcha reggio-emilia-signals.json | ✅ PASS | atteso reggio-emilia-signals.json |
| 12 | HTML anti-stale-string scan | ✅ PASS | 0 pattern stale |
| 13 | EDA · CAGR distribution sanity | ✅ PASS | n=24 skew=1.45 kurt=0.62 SW p=0.000 IQR outl=5 |
| 14 | EDA · Kruskal-Wallis CAGR fra fasce | ✅ PASS | H=2.38 p=0.3042 (p<0.05 → fasce significativamente diverse) | grouped fasce=['E', 'D', 'C', 'R', 'B'] |
| 15 | Time series · OLS slope per fascia (statsmodels) | ✅ PASS | 4 fasce analizzate, 2 con slope p<0.05 (significative) |
| 16 | Volume · IMI ∈ [0%, 10%] | ✅ PASS | min=2.09 max=4.34 n=16 |
| 17 | Volume · quadrant prezzo×NTN populated | ✅ PASS | 4/4 quadranti popolati: {'Q1_HOT': 5, 'Q2_OVERPRICED': 3, 'Q3_OPPORTUNITY': 3, 'Q4_DEAD': 5, 'unknown': 0} |
| 18 | Volume · momentum diversity (≥3 categorie) | ✅ PASS | 4 categorie: {'rocket': 3, 'growing': 9, 'stable': 3, 'cooling': 1, 'frozen': 0, 'unknown': 0} |
| 19 | Volume · cross-year NTN_var consistency (gap<5pp) | ✅ PASS | 1/64 discrepanze >5pp (1.6%) |
| 20 | Score recompute · 10 entry | ✅ PASS | 10/10 match (tol 0.5) | fails:  |
| 21 | Pareto · top_buy ⊂ pool (overlap CAGR×yield ≥30%) | ✅ PASS | |PF|=9 top_buy=6 overlap=100% |
| 22 | Monte Carlo simpy · BUY count under weight jitter ±10pp | ✅ PASS | base=7 MC 90% CI=[5,14] median=7 n_sims=1000 |
| 23 | k-NN · distanze comparables monotone non-decrescenti | ✅ PASS | 0 violazioni su 24 zone |

## Figure

- `fig-cagr-dist.png` — distribuzioni CAGR/yield/vol zone correnti + KS/Shapiro/Kruskal
- `fig-pvq-scatter.png` — scatter prezzo×NTN con quadranti + mediane
- `fig-ts-fascia.png` — serie storica per fascia OMI + OLS slope shaded CI 95%
- `fig-score-mc.png` — Monte Carlo verdict-BUY robustness sotto weight jitter
- `fig-knn-graph.png` — grafo k-NN comparables zone (degree/clustering)
- `fig-pareto.png` — Pareto front empirico CAGR×yield + reference NSGA-II