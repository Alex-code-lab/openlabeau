"""Chargement minimal d'un spectre Raman (.txt).

Format attendu : une ligne d'en-tête commençant par "Pixel;",
séparateur ";", décimale ",", avec au minimum les colonnes
"Raman Shift" et "Dark Subtracted #1".

Aucune correction de baseline ici : on veut juste *voir* le spectre brut
(approche reprise de Ramanalyze-simple). Lecture robuste à l'encodage
(`errors="replace"`).
"""

import os

import numpy as np
import pandas as pd


class SpectrumLoadError(ValueError):
    """Erreur lisible lors du chargement d'un spectre Raman."""


def _find_header(lines: list[str]) -> int:
    return next(
        (
            i
            for i, line in enumerate(lines)
            if line.strip().lower().startswith("pixel;")
        ),
        0,
    )


def _pick_column(columns, *candidates):
    normalized = {str(c).strip().replace("\xa0", " ").lower(): c for c in columns}
    for cand in candidates:
        if cand in normalized:
            return normalized[cand]
    return None


def _load_spectrum_dataframe(path: str) -> pd.DataFrame:
    """Retourne un DataFrame canonique ou lève SpectrumLoadError."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    if not lines:
        raise SpectrumLoadError("fichier vide")

    header_row = _find_header(lines)
    df = pd.read_csv(
        path,
        skiprows=header_row,
        sep=";",
        decimal=",",
        encoding="utf-8",
        encoding_errors="replace",
        engine="python",
        skipinitialspace=True,
        na_values=["", " ", "   ", "\t"],
    )

    # Nettoyage des noms de colonnes (espaces, insécables).
    df.columns = [str(c).strip().replace("\xa0", " ") for c in df.columns]
    if len(df.columns) and str(df.columns[-1]).startswith("Unnamed"):
        df = df.iloc[:, :-1]

    x_col = _pick_column(df.columns, "raman shift", "raman_shift",
                         "ramanshift", "rshift")
    y_col = _pick_column(
        df.columns,
        "dark subtracted #1",
        "spectra_corrected",
        "spectra corrected",
        "intensity",
        "intensite",
        "intensité",
    )
    if x_col is None or y_col is None:
        columns = ", ".join(str(c) for c in df.columns[:8])
        raise SpectrumLoadError(
            "colonnes Raman attendues introuvables "
            "('Raman Shift' et 'Dark Subtracted #1'). "
            f"Colonnes lues : {columns or 'aucune'}"
        )

    x = pd.to_numeric(df[x_col], errors="coerce")
    y = pd.to_numeric(df[y_col], errors="coerce")
    mask = x.notna() & y.notna()
    x = x[mask].to_numpy()
    y = y[mask].to_numpy()
    if x.size == 0:
        raise SpectrumLoadError("aucune ligne numérique exploitable")

    order = np.argsort(x)
    x = x[order]
    y = y[order]

    unique_x, inverse = np.unique(x, return_inverse=True)
    if len(unique_x) < len(x):
        y_sum = np.zeros(len(unique_x))
        np.add.at(y_sum, inverse, y)
        y = y_sum / np.bincount(inverse)
        x = unique_x

    return pd.DataFrame({
        "Raman Shift": x,
        "Dark Subtracted #1": y,
        "file": os.path.basename(path),
    })


def load_spectrum_dataframe(
    path: str, *, raise_errors: bool = False
) -> pd.DataFrame | None:
    """Retourne un DataFrame canonique, ou None si le spectre est inexploitable."""
    try:
        return _load_spectrum_dataframe(path)
    except SpectrumLoadError:
        if raise_errors:
            raise
        return None
    except Exception as exc:  # noqa: BLE001
        error = SpectrumLoadError(str(exc))
        if raise_errors:
            raise error from exc
        return None


def load_spectrum(path: str, *, raise_errors: bool = False):
    """Retourne (x, y) en numpy, ou None si le fichier n'est pas exploitable."""
    df = load_spectrum_dataframe(path, raise_errors=raise_errors)
    if df is None:
        return None
    return (
        df["Raman Shift"].to_numpy(dtype=float),
        df["Dark Subtracted #1"].to_numpy(dtype=float),
    )
