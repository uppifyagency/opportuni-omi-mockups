# Audit math-proof — Firenze

**Generato:** 2026-05-19 08:27
**Skill stack:** numpy 2.2.6 · scipy scipy.stats · statsmodels 0.14.6 · pymoo · aeon · networkx 3.5 · polars 1.40.1 · simpy · matplotlib 3.10.6

**Esito globale:** 23 PASS · 0 FAIL · 1 WARN (24 test)

| # | Test | Esito | Dettaglio |
|---|---|---|---|
| 1 | Inv1a · signals.yield == compass.yield | ✅ PASS | sig=4.16 com=4.16 |
| 2 | Inv1b · signals.CAGR ≈ compass.CAGR (tol 0.1pp) | ✅ PASS | sig=0.29 com=0.29 |
| 3 | Inv1c · signals.prezzo == compass.prezzo | ✅ PASS | sig=2958.0 com=2958.0 |
| 4 | Inv1d · |signals.zone_count − compass.zone_count| ≤ 2 (semantica: dizione vs dizione+CAGR) | ✅ PASS | sig=34 (con dizione) com=34 (con dizione+CAGR) diff=0 |
| 5 | Inv2 · anni_orizzonte disambiguato (Modena pattern fix#4) | ✅ PASS | _dataset=21 _zone_correnti=21 |
| 6 | Inv3 · yield recompute mean(current zones) == headline | ✅ PASS | recomp(34 z) = 4.16 vs hdr 4.16 |
| 7 | Inv4 · CSV span = headline.anni_orizzonte (polars) | ✅ PASS | CSV 2005-2026 = 21 vs hdr 21 |
| 8 | Inv5 · geojson features == signals.province_ranking | ✅ PASS | geo=41 ranking=41 |
| 9 | CSV recompute · 10 zone via polars (CAGR + yield) | ✅ PASS | 10/10 match (tol CAGR=1e-3, yield=0.05) | fail:  |
| 10 | HTML · firenze-A-brief.html fetcha firenze-signals.json | ✅ PASS | atteso firenze-signals.json |
| 11 | HTML · firenze-B-heatmap.html fetcha firenze-signals.json | ✅ PASS | atteso firenze-signals.json |
| 12 | HTML anti-stale-string scan | ⚠️ WARN | 1 match (potenziali stale, review manuale) · es: firenze-A-brief.html: anni hardcoded → ...I</div>     <h1>Firenze in <em>21 anni</em>:<br>capoluogo, |
| 13 | EDA · CAGR distribution sanity | ✅ PASS | n=34 skew=1.56 kurt=3.47 SW p=0.001 IQR outl=3 |
| 14 | EDA · Kruskal-Wallis CAGR fra fasce | ✅ PASS | H=1.07 p=0.5847 (p<0.05 → fasce significativamente diverse) | grouped fasce=['C', 'D', 'B', 'R', 'E'] |
| 15 | Time series · OLS slope per fascia (statsmodels) | ✅ PASS | 4 fasce analizzate, 1 con slope p<0.05 (significative) |
| 16 | Volume · IMI ∈ [0%, 10%] | ✅ PASS | min=1.70 max=2.60 n=34 |
| 17 | Volume · quadrant prezzo×NTN populated | ✅ PASS | 4/4 quadranti popolati: {'Q1_HOT': 11, 'Q2_OVERPRICED': 6, 'Q3_OPPORTUNITY': 6, 'Q4_DEAD': 11, 'unknown': 0} |
| 18 | Volume · momentum diversity (≥3 categorie) | ✅ PASS | 3 categorie: {'rocket': 0, 'growing': 2, 'stable': 19, 'cooling': 13, 'frozen': 0, 'unknown': 0} |
| 19 | Volume · cross-year NTN_var consistency (gap<5pp) | ✅ PASS | 2/203 discrepanze >5pp (1.0%) |
| 20 | Score recompute · 10 entry | ✅ PASS | 10/10 match (tol 0.5) | fails:  |
| 21 | Pareto · top_buy ⊂ pool (overlap CAGR×yield ≥30%) | ✅ PASS | |PF|=7 top_buy=6 overlap=67% |
| 22 | Monte Carlo simpy · BUY count under weight jitter ±10pp | ✅ PASS | base=15 MC 90% CI=[12,24] median=16 n_sims=1000 |
| 23 | k-NN · distanze comparables monotone non-decrescenti | ✅ PASS | 0 violazioni su 34 zone |
| 24 | k-NN · network metrics computed (networkx) | ✅ PASS | |V|=34 |E|=63 density=0.112 avg_deg=3.71 clust=0.366 fascia_assort=0.237 |

## Figure

- `fig-cagr-dist.png` — distribuzioni CAGR/yield/vol zone correnti + KS/Shapiro/Kruskal
- `fig-pvq-scatter.png` — scatter prezzo×NTN con quadranti + mediane
- `fig-ts-fascia.png` — serie storica per fascia OMI + OLS slope shaded CI 95%
- `fig-score-mc.png` — Monte Carlo verdict-BUY robustness sotto weight jitter
- `fig-knn-graph.png` — grafo k-NN comparables zone (degree/clustering)
- `fig-pareto.png` — Pareto front empirico CAGR×yield + reference NSGA-II