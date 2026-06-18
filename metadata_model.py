# metadata_model.py
#
# Couche données pure (aucun import Qt).
# Toutes les fonctions ici sont testables sans interface graphique.

from __future__ import annotations

import re

import numpy as np
import pandas as pd
from scipy.stats import norm

# ---------------------------------------------------------------------------
# Constantes partagées
# ---------------------------------------------------------------------------

MOLAR_UNIT_FACTORS = {
    "M": 1.0,
    "mM": 1e-3,
    "µM": 1e-6,
    "nM": 1e-9,
}

NUM_DISPLAY_PRECISION = 12
DEFAULT_VTOT_UL = 3090.0
SUM_TARGET_TOL = 1e-3


# ---------------------------------------------------------------------------
# Utilitaires de conversion
# ---------------------------------------------------------------------------


def to_float(x) -> float | None:
    """Convertit une valeur (str avec virgule/espace insécable, float, NaN…) en float ou None."""
    if x is None:
        return None
    if isinstance(x, float) and pd.isna(x):
        return None
    if isinstance(x, str):
        t = x.replace("\xa0", " ").strip().replace(",", ".")
        if t == "":
            return None
        try:
            return float(t)
        except Exception:
            return None
    try:
        return float(x)
    except Exception:
        return None


def conc_to_M(val, unit) -> float:
    """
    Convertit une concentration (val, unité) en M (mol/L).

    - M / mol/L / mol.l-1       → inchangé
    - mM / mmol/L / mmol.l-1    → × 1e-3
    - µM / um / µmol/L / umol/L → × 1e-6
    - nM / nmol/L / nmol.l-1    → × 1e-9
    - % en masse                → NaN (non exploitable)
    - autres                    → valeur brute
    """
    v = to_float(val)
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return float("nan")

    u = "" if pd.isna(unit) else str(unit).strip().replace(" ", "").lower()

    if u in ("m", "mol/l", "mol.l-1"):
        return v
    if u in ("mm", "mmol/l", "mmol.l-1"):
        return v * 1e-3
    if u in ("µm", "um", "µmol/l", "umol/l"):
        return v * 1e-6
    if u in ("nm", "nmol/l", "nmol.l-1"):
        return v * 1e-9
    if "%enmasse" in u:
        return float("nan")
    return v


# ---------------------------------------------------------------------------
# Normalisation des étiquettes
# ---------------------------------------------------------------------------


def normalize_tube_label(label: str) -> str:
    """Normalise une étiquette de tube vers la forme canonique 'Tube N'."""
    s = ("" if label is None else str(label)).strip()
    if not s:
        return ""

    # A1, A01, B3 … → Tube N
    m = re.match(r"^[A-Za-z](\d{1,2})$", s)
    if m:
        return f"Tube {int(m.group(1))}"

    # Tube1 / TUBE 01 / tube   2 → Tube N
    m = re.match(r"^(?:tube)\s*(\d{1,2})$", s, flags=re.IGNORECASE)
    if m:
        return f"Tube {int(m.group(1))}"

    # juste un nombre
    m = re.match(r"^(\d{1,2})$", s)
    if m:
        return f"Tube {int(m.group(1))}"

    return s


def norm_text_key(s: str) -> str:
    """Clé de comparaison insensible à la casse et aux accents."""
    text = ("" if s is None else str(s)).strip().lower()
    for old, new in {
        "\u00a0": " ",
        "\u202f": " ",
        "’": "'",
        "‘": "'",
        "`": "'",
        "´": "'",
        "…": "...",
    }.items():
        text = text.replace(old, new)
    text = re.sub(r"\s+", " ", text)
    return (
        text.replace("é", "e")
        .replace("è", "e")
        .replace("ê", "e")
        .replace("ô", "o")
        .replace("î", "i")
        .replace("û", "u")
        .replace("à", "a")
        .replace("â", "a")
    )


def is_control_label(label: str) -> bool:
    """Vrai si le label correspond au tube 'Contrôle' (réplicat)."""
    return norm_text_key(label) in {"controle", "control"}


# ---------------------------------------------------------------------------
# Colonnes et numérotation des tubes
# ---------------------------------------------------------------------------


def get_tube_columns(df: pd.DataFrame) -> list[str]:
    """Retourne les colonnes 'Tube N' d'un DataFrame, triées par N."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return []

    tube_cols = [
        c
        for c in df.columns
        if isinstance(c, str) and c.strip().lower().startswith("tube ")
    ]

    def _tube_key(name: str) -> int:
        m = re.search(r"(\d+)", str(name))
        return int(m.group(1)) if m else 10**9

    return sorted([str(c).strip() for c in tube_cols], key=_tube_key)


def infer_n_tubes_for_mapping(df_comp: pd.DataFrame | None) -> int:
    """Déduit le nombre de tubes à partir du tableau des volumes.

    Fallback : 10.
    """
    fallback = 10
    if df_comp is None or not isinstance(
            df_comp, pd.DataFrame) or df_comp.empty:
        return fallback

    tube_cols = get_tube_columns(df_comp)
    if not tube_cols:
        return fallback

    max_n = 0
    for c in tube_cols:
        m = re.search(r"(\d+)", str(c))
        if m:
            max_n = max(max_n, int(m.group(1)))

    return max(1, max_n or len(tube_cols) or fallback)


def tube_merge_key_for_mapping(
    label: str,
    n_tubes: int | None = None,
    df_comp: pd.DataFrame | None = None,
) -> str:
    """Retourne la clé de tube pour la jointure avec le tableau des volumes.

    - "A13" / "13" / "Tube 13" → "Tube 13"
    - "Contrôle"               → "Tube N" (dernier tube)
    - autres                   → label normalisé
    """
    n = infer_n_tubes_for_mapping(
        df_comp) if n_tubes is None else max(1, int(n_tubes))
    norm = normalize_tube_label(label)
    if is_control_label(norm):
        return f"Tube {n}"
    return norm


# ---------------------------------------------------------------------------
# Calcul du tableau des concentrations
# ---------------------------------------------------------------------------


def compute_concentration_table(df_comp: pd.DataFrame) -> pd.DataFrame:
    """
    Calcule le tableau des concentrations dans chaque cuvette.

    Pour chaque tube j et réactif i :
        C_ij = C_stock_i * V_ij / V_tot_j
    """
    if df_comp is None or df_comp.empty:
        raise ValueError("Le tableau des volumes n'est pas encore défini.")

    df = df_comp.copy()

    tube_cols = [c for c in df.columns if c.lower().startswith("tube")]
    if not tube_cols:
        raise ValueError(
            "Le tableau des volumes ne contient pas de colonnes 'Tube X'.")

    vol = df[tube_cols].apply(lambda col: pd.to_numeric(col, errors="coerce"))
    vol = vol.fillna(0.0)

    # Si la colonne "Pas (µL)" est présente, les lignes avec pas > 0 stockent
    # des n_gouttes : on les reconvertit en µL pour le calcul des
    # concentrations.
    if "Pas (µL)" in df.columns:
        pas_series = pd.to_numeric(df["Pas (µL)"], errors="coerce").fillna(0.0)
        for i in df.index:
            pas = pas_series.loc[i]
            if pas > 0:
                for c in tube_cols:
                    vol.at[i, c] = vol.at[i, c] * pas

    total_ul = vol.sum(axis=0).replace(0, pd.NA)

    out_rows: list[dict] = []

    # Première ligne : volumes totaux
    row_v = {"Réactif": "V cuvette (µL)"}
    for col in tube_cols:
        v_ul = total_ul[col]
        row_v[col] = float(v_ul) if not pd.isna(v_ul) else float("nan")
    out_rows.append(row_v)

    # Lignes de concentrations
    for idx, row in df.iterrows():
        name = row.get("Réactif", f"Ligne {idx}")
        c_stock = conc_to_M(row.get("Concentration"), row.get("Unité"))

        out = {"Réactif": name}
        if pd.isna(c_stock):
            for col in tube_cols:
                out[col] = 0.0
        else:
            for col in tube_cols:
                v_ij = vol.at[idx, col]
                v_tot = total_ul[col]
                if pd.isna(v_tot) or v_tot == 0:
                    out[col] = float("nan")
                else:
                    out[col] = float(c_stock) * (float(v_ij) / float(v_tot))

        out_rows.append(out)

    return pd.DataFrame(out_rows, columns=["Réactif"] + tube_cols)


# ---------------------------------------------------------------------------
# Construction des métadonnées fusionnées
# ---------------------------------------------------------------------------


def build_merged_metadata(
    df_comp: pd.DataFrame,
    df_map: pd.DataFrame,
) -> pd.DataFrame:
    """
    Construit le DataFrame de métadonnées final (spectres ↔ concentrations).

    Paramètres
    ----------
    df_comp : tableau des volumes (contient les colonnes 'Tube N')
    df_map  : correspondance spectre ↔ tube (colonnes 'Nom du spectre', 'Tube')

    Retour
    ------
    DataFrame avec au minimum : Spectrum name, Tube, Sample description
    + colonnes de concentrations par réactif
    + [titrant] (M) / [titrant] (mM) si détecté
    """
    if df_map is None or df_map.empty:
        raise ValueError(
            "Le tableau de correspondance spectres ↔ tubes n'est pas défini."
        )

    df_map = df_map.copy()

    if not {"Nom du spectre", "Tube"}.issubset(df_map.columns):
        raise ValueError(
            "Le tableau de correspondance doit contenir les colonnes "
            "'Nom du spectre' et 'Tube'."
        )

    df_map["Nom du spectre"] = df_map["Nom du spectre"].astype(str).str.strip()
    df_map["Tube"] = df_map["Tube"].astype(str).str.strip()

    header_info: dict[str, str] = {}

    # Supprimer éventuelle ligne d'en-tête interne
    header_mask = df_map["Nom du spectre"] == "Nom du spectre"
    if header_mask.any():
        last_header_idx = header_mask[header_mask].index[-1]
        header_rows = df_map.loc[df_map.index < last_header_idx].copy()
        for _, row in header_rows.iterrows():
            key = str(row.get("Nom du spectre", "")).strip().rstrip(":")
            val = str(row.get("Tube", "")).strip()
            if key:
                header_info[key] = val
        df_map = df_map.loc[df_map.index > last_header_idx].copy()

    # Retirer lignes vides
    df_map = df_map[(df_map["Nom du spectre"] != "")
                    & (df_map["Tube"] != "")].copy()

    # Base des métadonnées
    meta = df_map.rename(columns={"Nom du spectre": "Spectrum name"})

    n_tubes = infer_n_tubes_for_mapping(df_comp)
    meta["Tube_merge"] = meta["Tube"].apply(
        lambda s: tube_merge_key_for_mapping(s, n_tubes, df_comp)
    )

    tube_to_desc = {
        "Contrôle BRB": "Contrôle BRB",
        "Contrôle": "Contrôle",
    }
    meta["Sample description"] = meta["Tube"].map(
        tube_to_desc).fillna(meta["Tube"])

    # Concentrations
    conc_df = compute_concentration_table(df_comp)

    if "Réactif" in conc_df.columns:
        tube_cols = [c for c in conc_df.columns if c != "Réactif"]

        if tube_cols:
            conc_long = conc_df.melt(
                id_vars="Réactif",
                value_vars=tube_cols,
                var_name="Tube",
                value_name="C_M",
            )
            conc_wide = conc_long.pivot(
                index="Tube",
                columns="Réactif",
                values="C_M",
            )
            conc_wide = conc_wide.apply(pd.to_numeric, errors="coerce")
            conc_wide = conc_wide.reset_index().rename(
                columns={"Tube": "Tube_merge"})
            meta = meta.merge(conc_wide, on="Tube_merge", how="left")
            meta = meta.drop(columns=["Tube_merge"])

            # Détection automatique du titrant
            titrant_candidates = [
                col
                for col in conc_wide.columns
                if (
                    "titrant" in str(col).lower()
                    or "egta" in str(col).lower()
                    or str(col).lower() in {"solution b", "solutionb", "sol b", "b"}
                )
            ]
            if titrant_candidates:
                titrant = titrant_candidates[0]
                meta[titrant] = pd.to_numeric(meta[titrant], errors="coerce")
                meta["[titrant] (M)"] = meta[titrant]
                meta["[titrant] (mM)"] = meta[titrant] * 1e3

    for key, val in header_info.items():
        meta[key] = val

    # Nettoyage final
    meta = meta[~meta["Tube"].isin(["Tube BRB", "Contrôle BRB"])].copy()
    if "Tube_merge" in meta.columns:
        meta = meta.drop(columns=["Tube_merge"])
    meta = meta.reset_index(drop=True)

    return meta


# ---------------------------------------------------------------------------
# Génération de volumes pour titration SERS
# ---------------------------------------------------------------------------


def sers_gaussian_volumes(
    *,
    n_tubes: int,
    C0_nM: float,
    V_echant_uL: float,
    C_titrant_uM: float,
    Vtot_uL: float,
    V_Solution_A1_uL: float = 100.0,
    V_Solution_C_uL: float = 30.0,
    V_Solution_D_uL: float = 750.0,
    V_Solution_E_uL: float = 750.0,
    V_Solution_F_uL: float = 60.0,
    margin_uL: float = 20.0,
    pipette_step_uL: float = 1.0,
    include_zero: bool = True,
    duplicate_last: bool = True,
    center_power: float = 1.8,
    span_frac: float = 1.0,
    max_Vtot_uL: float | None = None,
) -> tuple[pd.DataFrame, dict]:
    """
    Génère une série de volumes de titrant (Solution B) pour une titration SERS.

    Tous les tubes contiennent le même volume d'échantillon V_echant_uL
    (même nombre de moles de Cu). Les volumes sont distribués autour du
    volume d'équivalence chimique via des quantiles gaussiens déformés.

    Retour
    ------
    (df, meta) où df contient les colonnes Tube / V_B_titrant_uL / V_A_tampon_uL
    et meta contient les grandeurs de contrôle (Veq_uL, sigma_V_uL, …).
    """
    if norm is None:
        raise ImportError("scipy.stats.norm requis.")

    if n_tubes < 2:
        raise ValueError("n_tubes doit être >= 2")

    # Volume fixe identique dans tous les tubes
    V_fixe_uL = (
        float(V_echant_uL)
        + float(V_Solution_A1_uL)
        + float(V_Solution_C_uL)
        + float(V_Solution_D_uL)
        + float(V_Solution_E_uL)
        + float(V_Solution_F_uL)
    )

    # Nombre de volumes libres à placer (hors tube à 0)
    n_free = int(n_tubes) - int(include_zero)
    if n_free <= 0:
        raise ValueError("Pas assez de tubes libres")

    step = float(pipette_step_uL)

    # En mode compte-goutte (ou si max_Vtot_uL fourni), cherche le plus petit Vtot
    # (multiple du pas, entre Vtot_uL et max_Vtot_uL) qui donne assez de positions uniques
    # pour les tubes libres.  Si include_zero=True et que la grille part de 0, cette
    # position est réservée et ne compte pas pour les tubes libres.
    Vtot_uL = float(Vtot_uL)
    if max_Vtot_uL is not None and max_Vtot_uL > Vtot_uL and step > 0:
        _limit = float(max_Vtot_uL)
        _candidate = Vtot_uL
        while _candidate <= _limit:
            _V_AB_cand = _candidate - V_fixe_uL
            if _V_AB_cand > 0:
                _vmin = np.ceil(float(margin_uL) / step) * step
                _vmax = np.floor((_V_AB_cand - float(margin_uL)) / step) * step
                _n_pos = (
                    max(0, int(round((_vmax - _vmin) / step)) + 1)
                    if _vmax >= _vmin
                    else 0
                )
                # La position 0 est réservée au tube "include_zero" → ne pas la
                # compter
                _reserved = 1 if (include_zero and _vmin == 0.0) else 0
                if _n_pos - _reserved >= n_free:
                    Vtot_uL = _candidate
                    break
            _candidate += step
        else:
            Vtot_uL = _limit  # fallback : valeur max autorisée

    V_AB = Vtot_uL - V_fixe_uL
    if V_AB <= 0:
        raise ValueError("Vtot <= V_fixe")

    Vmin_uL = float(margin_uL)
    Vmax_uL = float(V_AB - margin_uL)
    if Vmax_uL < Vmin_uL:
        raise ValueError("margin_uL trop grand")

    # Équivalence chimique
    C0_M = float(C0_nM) * 1e-9
    V_echant_L = float(V_echant_uL) * 1e-6
    C_titrant_M = float(C_titrant_uM) * 1e-6
    if C_titrant_M <= 0:
        raise ValueError("C_titrant_uM doit être > 0")

    n_Cu = C0_M * V_echant_L
    Veq_uL = (n_Cu / C_titrant_M) * 1e6

    # Quantiles gaussiens
    p = (np.arange(1, n_free + 1) - 0.5) / n_free
    z = norm.ppf(p)
    zmax = np.max(np.abs(z)) if n_free > 1 else 1.0

    # Déformation pour densifier autour de Veq
    gamma = float(center_power)
    if gamma <= 0:
        raise ValueError("center_power > 0 requis")
    z = np.sign(z) * (np.abs(z) ** gamma)

    # Calcul de sigma
    span = float(span_frac)
    if span <= 0:
        raise ValueError("span_frac > 0 requis")
    sigma_V = span * min(
        max(0.0, (Vmax_uL - Veq_uL)) / zmax,
        max(0.0, (Veq_uL - Vmin_uL)) / zmax,
    )

    # Volumes titrant
    V_B_ideal = np.clip(Veq_uL + sigma_V * z, Vmin_uL, Vmax_uL)

    # Grille de positions valides (multiples du pas dans [Vmin, Vmax])
    # En mode compte-goutte le pas est grand → peu de positions → forcer l'unicité.
    # Si include_zero=True, la position 0 est réservée au tube explicite :
    # la grille des tubes libres part donc du premier multiple de pas > 0.
    vmin_snap = np.ceil(Vmin_uL / step) * step
    if include_zero and vmin_snap == 0.0:
        vmin_snap = step
    vmax_snap = np.floor(Vmax_uL / step) * step
    grid = np.arange(vmin_snap, vmax_snap + step * 0.5, step)

    if len(grid) >= len(V_B_ideal):
        # Assignation gloutonne : trier les valeurs idéales, affecter chacune
        # à la position de grille libre la plus proche.
        order = np.argsort(V_B_ideal)
        available = list(grid)
        assigned = np.zeros(len(V_B_ideal))
        for idx in order:
            v = V_B_ideal[idx]
            closest_i = min(
                range(
                    len(available)), key=lambda i: abs(
                    available[i] - v))
            assigned[idx] = available[closest_i]
            available.pop(closest_i)
        V_B_free = assigned
    else:
        # Pas assez de positions uniques : fallback arrondi classique
        V_B_free = np.round(V_B_ideal / step) * step

    V_B = []
    if include_zero:
        V_B.append(0.0)
    V_B.extend(V_B_free.tolist())

    V_B = np.sort(np.array(V_B))
    if include_zero and len(V_B) > 1:
        V_B[0] = 0.0
        if V_B[1] <= 0:
            V_B[1] = step

    # Volumes tampon A
    V_AB_real = np.round(V_AB / step) * step
    V_A = V_AB_real - V_B
    if np.any(V_A < -1e-9):
        raise ValueError(
            "Pas de pipette trop grand pour les contraintes de volume.")
    V_A = np.round(V_A / step) * step
    Vtot_real = V_fixe_uL + V_AB_real

    df = pd.DataFrame(
        {
            "Tube": np.arange(1, n_tubes + 1),
            "V_B_titrant_uL": V_B,
            "V_A_tampon_uL": V_A,
        }
    )

    meta = {
        "Veq_uL": float(Veq_uL),
        "sigma_V_uL": float(sigma_V),
        "Vmin_uL": float(Vmin_uL),
        "Vmax_uL": float(Vmax_uL),
        "V_AB_real_uL": float(V_AB_real),
        "Vtot_real_uL": float(Vtot_real),
        "center_power": float(center_power),
        "span_frac": float(span_frac),
    }

    return df, meta
