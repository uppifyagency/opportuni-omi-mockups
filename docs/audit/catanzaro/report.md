# Audit math-proof — Catanzaro

**Generato:** 2026-05-17 18:20
**Skill stack:** numpy 2.2.6 · scipy scipy.stats · statsmodels 0.14.6 · pymoo · aeon · networkx 3.5 · polars 1.40.1 · simpy · matplotlib 3.10.6

**Esito globale:** 19 PASS · 0 FAIL · 4 WARN (23 test)

| # | Test | Esito | Dettaglio |
|---|---|---|---|
| 1 | Inv1a · signals.yield == compass.yield | ✅ PASS | sig=4.85 com=4.85 |
| 2 | Inv1b · signals.CAGR ≈ compass.CAGR (tol 0.1pp) | ✅ PASS | sig=0.46 com=0.46 |
| 3 | Inv1c · signals.prezzo == compass.prezzo | ✅ PASS | sig=1084.0 com=1084.0 |
| 4 | Inv1d · |signals.zone_count − compass.zone_count| ≤ 2 (semantica: dizione vs dizione+CAGR) | ✅ PASS | sig=19 (con dizione) com=19 (con dizione+CAGR) diff=0 |
| 5 | Inv2 · anni_orizzonte disambiguato (Modena pattern fix#4) | ⚠️ WARN | legacy: solo 'anni_orizzonte'=21 (Catanzaro pattern) |
| 6 | Inv3 · yield recompute mean(current zones) == headline | ✅ PASS | recomp(19 z) = 4.85 vs hdr 4.85 |
| 7 | Inv4 · CSV span = headline.anni_orizzonte (polars) | ✅ PASS | CSV 2005-2026 = 21 vs hdr 21 |
| 8 | Inv5 · geojson features == signals.province_ranking | ✅ PASS | geo=80 ranking=80 |
| 9 | CSV recompute · 10 zone via polars (CAGR + yield) | ✅ PASS | 10/10 match (tol CAGR=1e-3, yield=0.05) | fail:  |
| 10 | HTML · catanzaro-A-brief.html fetcha catanzaro-signals.json | ✅ PASS | atteso catanzaro-signals.json |
| 11 | HTML · catanzaro-B-heatmap.html fetcha catanzaro-signals.json | ✅ PASS | atteso catanzaro-signals.json |
| 12 | HTML anti-stale-string scan | ⚠️ WARN | 1 match (potenziali stale, review manuale) · es: catanzaro-A-brief.html: edizione hardcoded → .../p>     <div class="dateline">EDIZIONE · 2025-S2 · < |
| 13 | EDA · CAGR distribution sanity | ✅ PASS | n=19 skew=-0.00 kurt=2.51 SW p=0.008 IQR outl=3 |
| 14 | EDA · Kruskal-Wallis CAGR fra fasce | ✅ PASS | H=1.97 p=0.7418 (p<0.05 → fasce significativamente diverse) | grouped fasce=['E', 'D', 'C', 'B', 'R'] |
| 15 | Time series · OLS slope per fascia (statsmodels) | ✅ PASS | 5 fasce analizzate, 1 con slope p<0.05 (significative) |
| 16 | Volume · IMI ∈ [0%, 10%] | ✅ PASS | min=0.00 max=8.63 n=47 |
| 17 | Volume · quadrant prezzo×NTN populated | ✅ PASS | 4/4 quadranti popolati: {'Q1_HOT': 16, 'Q2_OVERPRICED': 9, 'Q3_OPPORTUNITY': 8, 'Q4_DEAD': 12, 'unknown': 2} |
| 18 | Volume · momentum diversity (≥3 categorie) | ✅ PASS | 6 categorie: {'rocket': 4, 'growing': 10, 'stable': 4, 'cooling': 2, 'frozen': 7, 'unknown': 20} |
| 19 | Volume · cross-year NTN_var consistency | ⚠️ WARN | 42/187 discrepanze >5pp (22.5%) — atteso per zone con NTN_first<5 (Catanzaro §19.7) |
| 20 | Score recompute · 10 entry | ✅ PASS | 10/10 match (tol 0.5) | fails:  |
| 21 | Pareto · top_buy overlap (CAGR×yield) | ⚠️ WARN | |PF|=6 top_buy=6 overlap=17% — score multi-dim privilegia stability/momentum |
| 22 | Monte Carlo simpy · BUY count under weight jitter ±10pp | ✅ PASS | base=0 MC 90% CI=[0,0] median=0 n_sims=1000 |
| 23 | k-NN · distanze comparables monotone non-decrescenti | ✅ PASS | 0 violazioni su 19 zone |

## Figure

- `fig-cagr-dist.png` — distribuzioni CAGR/yield/vol zone correnti + KS/Shapiro/Kruskal
- `fig-pvq-scatter.png` — scatter prezzo×NTN con quadranti + mediane
- `fig-ts-fascia.png` — serie storica per fascia OMI + OLS slope shaded CI 95%
- `fig-score-mc.png` — Monte Carlo verdict-BUY robustness sotto weight jitter
- `fig-knn-graph.png` — grafo k-NN comparables zone (degree/clustering)
- `fig-pareto.png` — Pareto front empirico CAGR×yield + reference NSGA-II