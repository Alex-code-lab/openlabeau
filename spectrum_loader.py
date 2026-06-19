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


def load_spectrum_dataframe(path: str) -> pd.DataFrame | None:
    """Retourne un DataFrame canonique avec les colonnes Raman utiles."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        df = pd.read_csv(
            path,
            skiprows=_find_header(lines),
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
            return None

        x = pd.to_numeric(df[x_col], errors="coerce")
        y = pd.to_numeric(df[y_col], errors="coerce")
        mask = x.notna() & y.notna()
        x = x[mask].to_numpy()
        y = y[mask].to_numpy()
        if x.size == 0:
            return None

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

    except Exception as exc:  # noqa: BLE001
        print(f"[load_spectrum_dataframe] Erreur sur {os.path.basename(path)} : {exc}")
        return None


def load_spectrum(path: str):
    """Retourne (x, y) en numpy, ou None si le fichier n'est pas exploitable."""
    df = load_spectrum_dataframe(path)
    if df is None:
        return None
    return (
        df["Raman Shift"].to_numpy(dtype=float),
        df["Dark Subtracted #1"].to_numpy(dtype=float),
    )
