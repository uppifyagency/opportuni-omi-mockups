# Audit math-proof — Torino

**Generato:** 2026-05-18 22:35
**Skill stack:** numpy 2.2.6 · scipy scipy.stats · statsmodels 0.14.6 · pymoo · aeon · networkx 3.5 · polars 1.40.1 · simpy · matplotlib 3.10.6

**Esito globale:** 19 PASS · 0 FAIL · 2 WARN (21 test)

| # | Test | Esito | Dettaglio |
|---|---|---|---|
| 1 | Inv1a · signals.yield == compass.yield | ✅ PASS | sig=4.76 com=4.76 |
| 2 | Inv1b · signals.CAGR ≈ compass.CAGR (tol 0.1pp) | ✅ PASS | sig=0.61 com=0.61 |
| 3 | Inv1c · signals.prezzo == compass.prezzo | ✅ PASS | sig=2058.0 com=2058.0 |
| 4 | Inv1d · |signals.zone_count − compass.zone_count| ≤ 2 (semantica: dizione vs dizione+CAGR) | ✅ PASS | sig=47 (con dizione) com=47 (con dizione+CAGR) diff=0 |
| 5 | Inv2 · anni_orizzonte disambiguato (Modena pattern fix#4) | ✅ PASS | _dataset=21 _zone_correnti=21 |
| 6 | Inv3 · yield recompute mean(current zones) == headline | ✅ PASS | recomp(47 z) = 4.76 vs hdr 4.76 |
| 7 | Inv4 · CSV span = headline.anni_orizzonte (polars) | ✅ PASS | CSV 2005-2026 = 21 vs hdr 21 |
| 8 | Inv5 · geojson features == signals.province_ranking | ✅ PASS | geo=312 ranking=312 |
| 9 | CSV recompute · 10 zone via polars (CAGR + yield) | ✅ PASS | 10/10 match (tol CAGR=1e-3, yield=0.05) | fail:  |
| 10 | HTML · torino-A-brief.html fetcha torino-signals.json | ✅ PASS | atteso torino-signals.json |
| 11 | HTML · torino-B-heatmap.html fetcha torino-signals.json | ✅ PASS | atteso torino-signals.json |
| 12 | HTML anti-stale-string scan | ⚠️ WARN | 1 match (potenziali stale, review manuale) · es: torino-A-brief.html: anni hardcoded → ...MI</div>     <h1>Torino in <em>21 anni</em>:<br>capoluogo,  |
| 13 | EDA · CAGR distribution sanity | ✅ PASS | n=47 skew=-0.31 kurt=-0.24 SW p=0.364 IQR outl=0 |
| 14 | EDA · Kruskal-Wallis CAGR fra fasce | ✅ PASS | H=5.49 p=0.1390 (p<0.05 → fasce significativamente diverse) | grouped fasce=['D', 'C', 'B', 'E'] |
| 15 | Time series · OLS slope per fascia (statsmodels) | ✅ PASS | 4 fasce analizzate, 1 con slope p<0.05 (significative) |
| 16 | Volume signals | ⚠️ WARN | file mancante |
| 17 | Score recompute · 10 entry | ✅ PASS | 10/10 match (tol 0.5) | fails:  |
| 18 | Pareto · top_buy ⊂ pool (overlap CAGR×yield ≥30%) | ✅ PASS | |PF|=6 top_buy=6 overlap=50% |
| 19 | Monte Carlo simpy · BUY count under weight jitter ±10pp | ✅ PASS | base=125 MC 90% CI=[58,238] median=133 n_sims=1000 |
| 20 | k-NN · distanze comparables monotone non-decrescenti | ✅ PASS | 0 violazioni su 47 zone |
| 21 | k-NN · network metrics computed (networkx) | ✅ PASS | |V|=47 |E|=75 density=0.069 avg_deg=3.19 clust=0.336 fascia_assort=0.143 |

## Figure

- `fig-cagr-dist.png` — distribuzioni CAGR/yield/vol zone correnti + KS/Shapiro/Kruskal
- `fig-pvq-scatter.png` — scatter prezzo×NTN con quadranti + mediane
- `fig-ts-fascia.png` — serie storica per fascia OMI + OLS slope shaded CI 95%
- `fig-score-mc.png` — Monte Carlo verdict-BUY robustness sotto weight jitter
- `fig-knn-graph.png` — grafo k-NN comparables zone (degree/clustering)
- `fig-pareto.png` — Pareto front empirico CAGR×yield + reference NSGA-II