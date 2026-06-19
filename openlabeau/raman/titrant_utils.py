"""Outils d'ajustement sigmoïde pour le suivi de pics Raman."""

import warnings

import numpy as np

def sigmoid(x, A, B, k, x_eq):
    """Sigmoïde logistique numériquement stable (pas d'overflow exp)."""
    z = np.clip(-k * (np.asarray(x, dtype=float) - x_eq), -500.0, 500.0)
    return A + B / (1.0 + np.exp(z))


def transition_bounds(popt, frac=0.95):
    """Début et fin de la transition d'une sigmoïde ajustée.

    Renvoie (x_debut, x_fin) : les abscisses où le signal a parcouru `frac`
    (ex. 95 %) de son changement total. Symétrique autour de x_eq. None si non
    calculable.
    """
    A, B, k, x_eq = popt
    if k == 0 or not (0.0 < frac < 1.0):
        return None
    d = np.log(frac / (1.0 - frac)) / abs(k)
    return float(x_eq - d), float(x_eq + d)


def fit_sigmoid(xs, ys):
    """Ajuste une sigmoïde sur (xs, ys). Renvoie popt [A, B, k, x_eq] ou None.

    Robuste : gère les courbes croissantes ET décroissantes en essayant
    plusieurs amorçages et en gardant le meilleur (moindres carrés).
    """
    pts = [(x, y) for x, y in zip(xs, ys) if y is not None and np.isfinite(y)]
    if len(pts) < 4:
        return None
    xa = np.array([p[0] for p in pts], dtype=float)
    ya = np.array([p[1] for p in pts], dtype=float)
    if np.ptp(xa) == 0:
        return None
    try:
        from scipy.optimize import curve_fit
    except Exception:  # noqa: BLE001
        return None

    span_x = float(np.ptp(xa)) or 1.0
    y_lo, y_hi = float(ya.min()), float(ya.max())
    rng = (y_hi - y_lo) or 1.0
    mid = len(ya) // 2
    decreasing = ya[mid:].mean() < ya[:mid].mean()
    x0 = float(np.median(xa))
    k0 = 4.0 / span_x
    guesses = [[y_lo, rng, k0, x0], [y_hi, -rng, k0, x0]]
    if decreasing:
        guesses.reverse()

    best, best_sse = None, np.inf
    for p0 in guesses:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                popt, _ = curve_fit(sigmoid, xa, ya, p0=p0, maxfev=20000)
        except Exception:  # noqa: BLE001
            continue
        sse = float(np.sum((sigmoid(xa, *popt) - ya) ** 2))
        if sse < best_sse:
            best, best_sse = popt, sse
    return best
