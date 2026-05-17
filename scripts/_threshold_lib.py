"""Helper condiviso per calibrazione data-driven della soglia BUY/AVOID compass.

Implementa il metodo scientifico Jenks natural breaks (k=3) come metodo principale,
con esposizione trasparente di Otsu, GMM e P85 come metodi alternativi in metadata.

Vedi `docs/audit/THRESHOLD-SCIENTIFIC-ANALYSIS.md` per la diagnosi statistica completa
e il confronto fra i 6 metodi su 4 città (Modena, Bologna, Catanzaro, Reggio Emilia).
"""
from __future__ import annotations

import warnings
from typing import Optional

import numpy as np

warnings.filterwarnings("ignore", category=UserWarning)


def jenks_natural_breaks(scores: list[float], n_classes: int = 3) -> Optional[tuple[float, float]]:
    """Jenks natural breaks (k-means 1D ottimo).
    Standard GIS per classificazione valori immobiliari.
    Restituisce (buy_threshold, avoid_threshold).
    """
    try:
        import jenkspy
    except ImportError:
        return None
    valid = [s for s in scores if s is not None]
    if len(valid) < n_classes * 3:
        return None
    breaks = jenkspy.jenks_breaks(valid, n_classes=n_classes)
    # breaks = [min, b1, b2, max] per n_classes=3
    return float(breaks[2]), float(breaks[1])


def otsu_threshold(scores: list[float], nbins: int = 64) -> Optional[float]:
    """Otsu: massimizza varianza inter-classe (bipartition)."""
    valid = np.array([s for s in scores if s is not None])
    if len(valid) < 10:
        return None
    hist, bin_edges = np.histogram(valid, bins=nbins)
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    total = hist.sum()
    if total == 0:
        return None
    p = hist / total
    cum_p = np.cumsum(p)
    cum_mu = np.cumsum(p * bin_centers)
    mu_T = cum_mu[-1]
    denom = cum_p * (1 - cum_p)
    denom = np.where(denom > 0, denom, np.inf)
    sigma_b_squared = (mu_T * cum_p - cum_mu) ** 2 / denom
    return float(bin_centers[np.argmax(sigma_b_squared)])


def gmm_buy_threshold(scores: list[float], n_components: int = 3, seed: int = 42) -> Optional[float]:
    """Gaussian Mixture Model k=3 → soglia BUY = intersezione gaussiane top-2."""
    try:
        from sklearn.mixture import GaussianMixture
    except ImportError:
        return None
    valid = np.array([s for s in scores if s is not None])
    if len(valid) < n_components * 3:
        return None
    X = valid.reshape(-1, 1)
    gmm = GaussianMixture(n_components=n_components, random_state=seed,
                          covariance_type='full', n_init=5).fit(X)
    order = np.argsort(gmm.means_.ravel())
    means = gmm.means_.ravel()[order]
    stds = np.sqrt(gmm.covariances_.ravel()[order])
    m1, s1, m2, s2 = means[1], stds[1], means[2], stds[2]
    a = 1/(2*s1**2) - 1/(2*s2**2)
    b = m2/s2**2 - m1/s1**2
    c = m1**2/(2*s1**2) - m2**2/(2*s2**2) - np.log(s2/s1)
    if abs(a) < 1e-9:
        return float((m1 + m2) / 2)
    roots = np.roots([a, b, c])
    valid_roots = [r.real for r in roots if abs(r.imag) < 1e-6 and m1 < r.real < m2]
    return float(valid_roots[0]) if valid_roots else float((m1 + m2) / 2)


def percentile_threshold(scores: list[float], p: float = 85) -> Optional[float]:
    valid = [s for s in scores if s is not None]
    if len(valid) < 10:
        return None
    return float(np.percentile(valid, p))


def bootstrap_p85_ci(scores: list[float], n_boot: int = 1000, ci: float = 0.95, seed: int = 42) -> Optional[tuple[float, float, float]]:
    valid = np.array([s for s in scores if s is not None])
    if len(valid) < 10:
        return None
    rng = np.random.default_rng(seed)
    boot = np.array([np.percentile(rng.choice(valid, size=len(valid), replace=True), 85)
                      for _ in range(n_boot)])
    return float(np.mean(boot)), float(np.percentile(boot, (1-ci)/2*100)), float(np.percentile(boot, (1+ci)/2*100))


# ── Public API ──────────────────────────────────────────────────


# Soglie fallback (usate solo se Jenks fallisce per pool troppo piccolo)
FALLBACK_BUY = 60.0
FALLBACK_AVOID = 35.0
MIN_POOL_SIZE = 10


def calibrate_thresholds(scores: list[float]) -> dict:
    """Calcola TUTTE le soglie e restituisce il pacchetto completo.

    Metodo principale: Jenks natural breaks (k=3).
    Fallback: se Jenks non disponibile (jenkspy mancante), usa P85/P15.
    Espone tutti i metodi in `alternative_thresholds` per trasparenza scientifica.

    Returns:
        dict con keys:
            buy_threshold, avoid_threshold (le soglie da USARE)
            method_used (stringa)
            alternative_thresholds (tutti i metodi computati)
            pool_n, pool_stats
    """
    valid = [s for s in scores if s is not None]
    pool_n = len(valid)

    if pool_n < MIN_POOL_SIZE:
        return {
            "buy_threshold": FALLBACK_BUY,
            "avoid_threshold": FALLBACK_AVOID,
            "method_used": "fallback_constant",
            "method_reason": f"pool n={pool_n} < {MIN_POOL_SIZE}",
            "alternative_thresholds": {},
            "pool_n": pool_n,
        }

    # Computa TUTTI i metodi
    alts = {}
    jenks = jenks_natural_breaks(valid)
    if jenks is not None:
        alts["jenks_k3"] = {"buy": round(jenks[0], 2), "avoid": round(jenks[1], 2),
                            "n_buy": int(sum(1 for s in valid if s >= jenks[0])),
                            "n_avoid": int(sum(1 for s in valid if s < jenks[1]))}
    otsu = otsu_threshold(valid)
    if otsu is not None:
        alts["otsu"] = {"buy": round(otsu, 2),
                        "n_buy": int(sum(1 for s in valid if s >= otsu))}
    gmm = gmm_buy_threshold(valid)
    if gmm is not None:
        alts["gmm_k3"] = {"buy": round(gmm, 2),
                          "n_buy": int(sum(1 for s in valid if s >= gmm))}
    p85 = percentile_threshold(valid, 85)
    p15 = percentile_threshold(valid, 15)
    if p85 is not None:
        alts["p85"] = {"buy": round(p85, 2), "avoid": round(p15, 2) if p15 else None,
                       "n_buy": int(sum(1 for s in valid if s >= p85))}
    boot = bootstrap_p85_ci(valid)
    if boot is not None:
        alts["p85_bootstrap"] = {"mean": round(boot[0], 2), "ci95_low": round(boot[1], 2), "ci95_high": round(boot[2], 2)}

    # Decisione metodo principale
    if jenks is not None:
        buy_t, avoid_t = jenks
        method = "jenks_natural_breaks_k3"
        reason = "k-means 1D ottimo, standard GIS per dati immobiliari"
    elif p85 is not None and p15 is not None:
        buy_t, avoid_t = p85, p15
        method = "percentile_p85_p15"
        reason = "fallback (jenkspy non disponibile)"
    else:
        buy_t, avoid_t = FALLBACK_BUY, FALLBACK_AVOID
        method = "fallback_constant"
        reason = "tutti i metodi falliti"

    arr = np.array(valid)
    return {
        "buy_threshold": round(buy_t, 2),
        "avoid_threshold": round(avoid_t, 2),
        "method_used": method,
        "method_reason": reason,
        "alternative_thresholds": alts,
        "pool_n": pool_n,
        "pool_stats": {
            "mean": round(float(arr.mean()), 2),
            "sd": round(float(arr.std(ddof=1)), 2),
            "min": round(float(arr.min()), 2),
            "max": round(float(arr.max()), 2),
            "p50": round(float(np.percentile(arr, 50)), 2),
        },
    }
