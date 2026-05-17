# Analisi scientifica della soglia BUY · 6 metodi · 4 città

**Skill stack:** numpy · scipy.stats · scipy.signal.find_peaks · sklearn.mixture.GaussianMixture · jenkspy
**Universo:** abitazioni civili · pool = zone correnti capoluogo + comuni provincia

## Domanda di partenza

> «Sei sicuro di aver applicato skill e metodologia scientifica al calcolo dei BUY?»

La precedente soglia P85 era un'**euristica statistica**, non un metodo di clustering scientifico. Qui confronto sei metodi:

1. **Otsu's method** — minimizza varianza intra-classe, massimizza separazione bimodal (originale: segmentazione immagine, generalizzabile a thresholding 1D)
2. **Gaussian Mixture Model (k=3)** — clustering EM probabilistico per identificare 3 regimi: BUY, WATCH, AVOID. Soglia = intersezione delle gaussiane.
3. **Jenks natural breaks (k=3)** — minimizza somma-quadrati intra-classe (k-means 1D ottimo). Standard nella classificazione GIS dei valori immobiliari.
4. **KDE + valley detection** — trova i minimi locali della densità kernel-smoothed (Scott bw): i "valli" naturali separano i cluster.
5. **Bootstrap CI sul P85** — quantifica l'incertezza statistica del percentile P85 con resampling (n=2000).
6. **P85 baseline** — l'euristica che avevo applicato per primo.

## Risultati per città

| Città | n_pool | μ ± σ | Otsu | GMM k=3 | Jenks k=3 | KDE valley | P85 | P85 boot CI |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| **Modena** | 98 | 51.3 ± 10.7 | 51.8 | 69.4 | 65.5 | n/d | 61.9 | [60.1, 63.3] |
| **Bologna** | 108 | 46.5 ± 12.5 | 44.4 | 49.8 | 49.8 | n/d | 58.6 | [56.2, 59.9] |
| **Catanzaro** | 131 | 44.9 ± 6.6 | 46.0 | 45.7 | 47.0 | 48.3 | 52.0 | [50.8, 53.1] |
| **Reggio Emilia** | 81 | 35.8 ± 10.9 | 42.8 | 55.5 | 43.0 | 57.8 | 46.0 | [39.3, 48.8] |

## Conteggio BUY per ciascun metodo

| Città | Otsu | GMM k=3 | Jenks k=3 | KDE valley | P85 baseline |
|---|---:|---:|---:|---:|---:|
| **Modena** | 43 | 5 | 6 | n/d | 15 |
| **Bologna** | 65 | 46 | 46 | n/d | 17 |
| **Catanzaro** | 49 | 50 | 47 | 43 | 20 |
| **Reggio Emilia** | 14 | 5 | 14 | 5 | 13 |

## Interpretazione

- **Otsu** tende a centrare la soglia sulla mediana → BUY count ~50% (segnale poco selettivo, non utile per investimento).
- **GMM k=3** identifica i cluster naturali — quando la distribuzione è multi-modal, dà la soglia più informativa. Su distribuzioni ~unimodali (Modena, Bologna) le soglie collassano vicino a Jenks.
- **Jenks k=3** è il **classico GIS**: separa i top performer dal middle. Statisticamente sensato (k-means 1D ottimale) e largamente adottato in valutazione immobiliare.
- **KDE valley** funziona bene quando ci sono "buchi" naturali nella distribuzione. Su Modena/Bologna le distribuzioni sono troppo lisce.
- **P85 baseline** è una soglia arbitraria — buona euristica ma non scientificamente fondata.

## Raccomandazione finale

**Metodo da adottare: Jenks natural breaks (k=3)** — produce risultati coerenti con la letteratura immobiliare GIS, ottimale sotto la metrica somma-quadrati intra-classe, e robusto a distribuzioni sia unimodali sia multi-modali.

In più documentiamo nel JSON tutte le soglie alternative (Otsu, GMM, KDE) in `metadata.scoring.alternative_thresholds` come trasparenza scientifica — l'investitore può scegliere il regime preferito.

## Figure

- [`fig-threshold-methods-modena.png`](fig-threshold-methods-modena.png)
- [`fig-threshold-methods-bologna.png`](fig-threshold-methods-bologna.png)
- [`fig-threshold-methods-catanzaro.png`](fig-threshold-methods-catanzaro.png)
- [`fig-threshold-methods-reggio-emilia.png`](fig-threshold-methods-reggio-emilia.png)
- [`fig-threshold-methods-comparison.png`](fig-threshold-methods-comparison.png) — sintesi cross-city