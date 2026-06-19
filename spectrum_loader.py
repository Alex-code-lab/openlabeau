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


def load_spectrum(path: str):
    """Retourne (x, y) en numpy, ou None si le fichier n'est pas exploitable."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        # Repérer la ligne d'en-tête "Pixel;" ; sinon on tente la 1re ligne.
        header_idx = next(
            (
                i
                for i, line in enumerate(lines)
                if line.strip().lower().startswith("pixel;")
            ),
            0,
        )

        df = pd.read_csv(
            path,
            skiprows=header_idx,
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

        cols = {c.lower(): c for c in df.columns}

        def pick(*candidates):
            for cand in candidates:
                if cand in cols:
                    return cols[cand]
            return None

        x_col = pick("raman shift", "raman_shift", "ramanshift", "rshift")
        y_col = pick(
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
        return x[order], y[order]

    except Exception as exc:  # noqa: BLE001
        print(f"[load_spectrum] Erreur sur {os.path.basename(path)} : {exc}")
        return None
