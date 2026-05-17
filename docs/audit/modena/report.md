# Audit math-proof — Modena

**Generato:** 2026-05-17 18:20
**Skill stack:** numpy 2.2.6 · scipy scipy.stats · statsmodels 0.14.6 · pymoo · aeon · networkx 3.5 · polars 1.40.1 · simpy · matplotlib 3.10.6

**Esito globale:** 22 PASS · 0 FAIL · 0 WARN (22 test)

| # | Test | Esito | Dettaglio |
|---|---|---|---|
| 1 | Inv1a · signals.yield == compass.yield | ✅ PASS | sig=5.28 com=5.28 |
| 2 | Inv1b · signals.CAGR ≈ compass.CAGR (tol 0.1pp) | ✅ PASS | sig=0.25 com=0.25 |
| 3 | Inv1c · signals.prezzo == compass.prezzo | ✅ PASS | sig=1761.0 com=1761.0 |
| 4 | Inv1d · |signals.zone_count − compass.zone_count| ≤ 2 (semantica: dizione vs dizione+CAGR) | ✅ PASS | sig=20 (con dizione) com=20 (con dizione+CAGR) diff=0 |
| 5 | Inv2 · anni_orizzonte disambiguato (Modena pattern fix#4) | ✅ PASS | _dataset=21 _zone_correnti=12 |
| 6 | Inv3 · yield recompute mean(current zones) == headline | ✅ PASS | recomp(20 z) = 5.28 vs hdr 5.28 |
| 7 | Inv4 · CSV span = headline.anni_orizzonte (polars) | ✅ PASS | CSV 2005-2026 = 21 vs hdr 21 |
| 8 | Inv5 · geojson features == signals.province_ranking | ✅ PASS | geo=47 ranking=47 |
| 9 | CSV recompute · 10 zone via polars (CAGR + yield) | ✅ PASS | 10/10 match (tol CAGR=1e-3, yield=0.05) | fail:  |
| 10 | HTML anti-stale-string scan | ✅ PASS | 0 pattern stale |
| 11 | EDA · CAGR distribution sanity | ✅ PASS | n=20 skew=1.00 kurt=0.92 SW p=0.003 IQR outl=4 |
| 12 | EDA · Kruskal-Wallis CAGR fra fasce | ✅ PASS | H=3.40 p=0.1827 (p<0.05 → fasce significativamente diverse) | grouped fasce=['D', 'C', 'E', 'R', 'B'] |
| 13 | Time series · OLS slope per fascia (statsmodels) | ✅ PASS | 5 fasce analizzate, 1 con slope p<0.05 (significative) |
| 14 | Volume · IMI ∈ [0%, 10%] | ✅ PASS | min=1.58 max=6.29 n=19 |
| 15 | Volume · quadrant prezzo×NTN populated | ✅ PASS | 4/4 quadranti popolati: {'Q1_HOT': 7, 'Q2_OVERPRICED': 3, 'Q3_OPPORTUNITY': 3, 'Q4_DEAD': 6, 'unknown': 0} |
| 16 | Volume · momentum diversity (≥3 categorie) | ✅ PASS | 4 categorie: {'rocket': 3, 'growing': 3, 'stable': 11, 'cooling': 2, 'frozen': 0, 'unknown': 0} |
| 17 | Volume · cross-year NTN_var consistency (gap<5pp) | ✅ PASS | 4/94 discrepanze >5pp (4.3%) |
| 18 | Score recompute · 10 entry | ✅ PASS | 10/10 match (tol 0.5) | fails:  |
| 19 | Pareto · top_buy ⊂ pool (overlap CAGR×yield ≥30%) | ✅ PASS | |PF|=7 top_buy=6 overlap=50% |
| 20 | Monte Carlo simpy · BUY count under weight jitter ±10pp | ✅ PASS | base=3 MC 90% CI=[4,8] median=5 n_sims=1000 |
| 21 | k-NN · distanze comparables monotone non-decrescenti | ✅ PASS | 0 violazioni su 20 zone |
| 22 | k-NN · network metrics computed (networkx) | ✅ PASS | |V|=20 |E|=33 density=0.174 avg_deg=3.30 clust=0.395 fascia_assort=0.214 |

## Figure

- `fig-cagr-dist.png` — distribuzioni CAGR/yield/vol zone correnti + KS/Shapiro/Kruskal
- `fig-pvq-scatter.png` — scatter prezzo×NTN con quadranti + mediane
- `fig-ts-fascia.png` — serie storica per fascia OMI + OLS slope shaded CI 95%
- `fig-score-mc.png` — Monte Carlo verdict-BUY robustness sotto weight jitter
- `fig-knn-graph.png` — grafo k-NN comparables zone (degree/clustering)
- `fig-pareto.png` — Pareto front empirico CAGR×yield + reference NSGA-II