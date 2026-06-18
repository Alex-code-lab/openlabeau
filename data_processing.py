# data_processing.py

import os

import numpy as np
import pandas as pd
from pybaselines import Baseline


def load_spectrum_file(
    path: str, poly_order: int = 5, apply_baseline: bool = True
) -> pd.DataFrame | None:
    """
    Charge un fichier .txt de spectroscopie Raman, applique une correction de baseline,
    et retourne un DataFrame avec colonnes utiles.

    Args:
        path: chemin vers le fichier .txt
        poly_order: ordre du polynôme pour la baseline

    Returns:
        DataFrame avec colonnes ["Raman Shift", "Dark Subtracted #1", "Intensity_corrected", "file"]
        ou None si erreur / format non reconnu.
    """
    try:
        # --- Lecture brute + repérage de la ligne "Pixel;" ---
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        header_idx = next(
            i for i, line in enumerate(lines) if line.strip().startswith("Pixel;")
        )

        df = pd.read_csv(
            path,
            skiprows=header_idx,
            sep=";",
            decimal=",",
            encoding="utf-8",
            skipinitialspace=True,
            na_values=["", " ", "   ", "\t"],
            keep_default_na=True,
        )

        # Supprimer dernière colonne si vide / Unnamed
        if len(df.columns) > 0 and str(df.columns[-1]).startswith("Unnamed"):
            df = df.iloc[:, :-1]

        # Nettoyage des noms de colonnes (espaces, insécables, etc.)
        df.columns = [str(c).strip().replace("\xa0", " ") for c in df.columns]

        # Conversion numérique des colonnes texte
        for col in df.columns:
            if df[col].dtype == "object":
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # -------------------------------------------------------
        # 1) Harmonisation des noms de colonnes spectrales
        # -------------------------------------------------------
        cols_lower = {c.lower(): c for c in df.columns}

        # a) Colonne Raman Shift
        if "Raman Shift" not in df.columns:
            # Cherche des variantes possibles
            for cand in ["raman shift", "raman_shift", "rshift", "ramanshift"]:
                if cand in cols_lower:
                    df["Raman Shift"] = df[cols_lower[cand]]
                    break

        # b) Colonne Dark Subtracted #1 (intensité brute utilisée pour
        # baseline)
        if "Dark Subtracted #1" not in df.columns:
            for cand in [
                "spectra_corrected",
                "spectra corrected",
                "intensity",
                "intensite",
            ]:
                if cand in cols_lower:
                    df["Dark Subtracted #1"] = df[cols_lower[cand]]
                    break

        # Si après harmonisation on n'a toujours pas les colonnes, on abandonne
        if not {"Raman Shift", "Dark Subtracted #1"}.issubset(set(df.columns)):
            # Debug minimal dans la console
            print(
                f"[load_spectrum_file] Colonnes requises absentes pour {path}. "
                f"Colonnes présentes : {list(df.columns)}"
            )
            return None

        # -------------------------------------------------------
        # 2) Construction du DataFrame de travail
        # -------------------------------------------------------
        temp = df[["Raman Shift", "Dark Subtracted #1"]].copy()
        temp = temp.dropna(subset=["Raman Shift", "Dark Subtracted #1"])

        if temp.empty:
            print(
                f"[load_spectrum_file] Données vides après dropna pour {path}")
            return None

        x = temp["Raman Shift"].values
        y = temp["Dark Subtracted #1"].values

        # Tri par shift croissant
        order = np.argsort(x)
        x = x[order]
        y = y[order]

        # Validation : plage physiquement raisonnable (cm⁻¹)
        if x.min() < -200 or x.max() > 10000:
            print(
                f"[load_spectrum_file] Valeurs de Raman Shift suspectes pour {path} "
                f"(min={x.min():.1f}, max={x.max():.1f} cm⁻¹)"
            )

        # Déduplication : si plusieurs points ont le même shift, on conserve la
        # moyenne
        unique_x, inverse = np.unique(x, return_inverse=True)
        if len(unique_x) < len(x):
            n_dup = len(x) - len(unique_x)
            print(
                f"[load_spectrum_file] {n_dup} doublon(s) de Raman Shift détecté(s) "
                f"dans {path} — moyennage appliqué."
            )
            y_dedup = np.zeros(len(unique_x))
            np.add.at(y_dedup, inverse, y)
            counts = np.bincount(inverse)
            y = y_dedup / counts
            x = unique_x

        # Baseline correction (optionnelle)
        if apply_baseline:
            try:
                baseline_fitter = Baseline(x)
                baseline, _ = baseline_fitter.modpoly(y, poly_order=poly_order)
                ycorr = y - baseline
            except Exception as be:
                print(
                    f"[load_spectrum_file] Échec baseline pour {path} : {be}")
                baseline = np.zeros_like(y)
                ycorr = y
        else:
            # Pas de baseline : on garde le signal brut
            baseline = np.zeros_like(y)
            ycorr = y

        out = pd.DataFrame(
            {
                "Raman Shift": x,
                "Dark Subtracted #1": y,
                "Intensity_corrected": ycorr,
                "file": os.path.basename(path),
            }
        )

        return out.dropna(subset=["Intensity_corrected"])

    except Exception as e:
        print(f"Erreur lors du chargement de {path}: {e}")
        return None


def build_combined_dataframe_from_df(
    txt_files: list[str],
    metadata_df: pd.DataFrame,
    poly_order: int = 5,
    exclude_brb: bool = True,
    apply_baseline: bool = True,
) -> pd.DataFrame:
    """
    Construit le DataFrame fusionné (spectres + métadonnées) à partir
    d'un DataFrame de métadonnées déjà chargé.

    Args:
        txt_files: liste des chemins vers les fichiers .txt
        metadata_df: DataFrame contenant au moins la colonne 'Spectrum name'
        poly_order: ordre du polynôme pour la baseline
        exclude_brb: si True, supprime les échantillons "Cuvette BRB"

    Returns:
        combined_df: DataFrame fusionné prêt pour l'analyse
    """
    all_data = []
    for path in txt_files:
        temp = load_spectrum_file(
            path, poly_order=poly_order, apply_baseline=apply_baseline
        )
        if temp is not None:
            all_data.append(temp)

    if not all_data:
        raise ValueError("Aucun spectre valide n'a été chargé.")

    spectra_df = pd.concat(all_data, ignore_index=True)
    spectra_df["Spectrum name"] = spectra_df["file"].str.replace(
        ".txt", "", regex=False
    )

    combined_df = pd.merge(
        spectra_df,
        metadata_df,
        on="Spectrum name",
        how="left")

    if exclude_brb and "Sample description" in combined_df.columns:
        combined_df = combined_df[
            ~combined_df["Sample description"].isin(
                ["Tube BRB", "BRB", "Cuvette BRB", "Contrôle BRB"]
            )
        ].copy()
    return combined_df


def build_combined_dataframe_from_ui(
    txt_files: list[str],
    metadata_creator,
    poly_order: int = 5,
    exclude_brb: bool = True,
    apply_baseline: bool = True,
) -> pd.DataFrame:
    """Construit le DataFrame combiné (spectres + métadonnées) à partir des éléments UI."""
    if metadata_creator is None or not hasattr(
        metadata_creator, "build_merged_metadata"
    ):
        raise ValueError(
            "metadata_creator manquant ou incompatible (build_merged_metadata introuvable)."
        )

    merged_meta = metadata_creator.build_merged_metadata()
    return build_combined_dataframe_from_df(
        txt_files,
        merged_meta,
        poly_order=poly_order,
        exclude_brb=exclude_brb,
        apply_baseline=apply_baseline,
    )


def load_combined_df(
    parent, file_picker, metadata_creator, **kwargs
) -> "pd.DataFrame | None":
    """Charge le DataFrame combiné en gérant toutes les erreurs via QMessageBox.

    Retourne le DataFrame, ou None si une erreur s'est produite
    (le message d'erreur a déjà été affiché à l'utilisateur).

    kwargs sont transmis à build_combined_dataframe_from_ui
    (poly_order, exclude_brb, apply_baseline).
    """
    from PySide6.QtWidgets import QMessageBox

    if metadata_creator is None or not hasattr(
        metadata_creator, "build_merged_metadata"
    ):
        QMessageBox.warning(
            parent,
            "Métadonnées manquantes",
            "L'onglet Métadonnées n'est pas correctement initialisé.\n"
            "Créez d'abord les tableaux de compositions et de correspondance.",
        )
        return None

    txt_files = []
    if file_picker is not None and hasattr(file_picker, "get_selected_files"):
        txt_files = file_picker.get_selected_files()
    if not txt_files:
        QMessageBox.warning(
            parent,
            "Fichiers manquants",
            "Aucun fichier .txt sélectionné.\n"
            "Allez dans l'onglet Fichiers et ajoutez des spectres.",
        )
        return None

    try:
        metadata_creator.build_merged_metadata()
    except Exception as e:
        QMessageBox.critical(
            parent,
            "Erreur métadonnées",
            f"Impossible de construire les métadonnées fusionnées :\n{e}",
        )
        return None

    opts = dict(poly_order=5, exclude_brb=True, apply_baseline=True)
    opts.update(kwargs)
    try:
        return build_combined_dataframe_from_ui(
            txt_files, metadata_creator, **opts)
    except Exception as e:
        QMessageBox.critical(
            parent,
            "Échec assemblage",
            f"Impossible d'assembler les données spectres + métadonnées :\n{e}",
        )
        return None
