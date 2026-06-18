#!/usr/bin/env python3
"""
analyses_paires.py
------------------
Analyse cross-manip : identifie les paires de pics Raman les plus robustes,
c'est-à-dire celles qui donnent un bon |rho| de Spearman dans plusieurs
manipulations différentes.

Format attendu du fichier Excel (une seule feuille) :
  Ligne 1 (index 0) : noms des manips, répétés/fusionnés tous les 5 colonnes
                      ex:  GC561 | (vide) | (vide) | (vide) | (vide) | GC562 | ...
  Ligne 2 (index 1) : en-têtes de colonnes répétés pour chaque manip
                      ex:  Rang | Pic A (cm-1) | Pic B (cm-1) | rho (signe) | |rho|
  Lignes 3+ (index 2+) : données des paires

Usage :
  python analyses_paires.py fichier.xlsx
  python analyses_paires.py fichier.xlsx --tolerance 20 --top 5 --min-manips 2 --export
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ─── Paramètres par défaut ──────────────────────────────────────────────────
TOLERANCE_CM = 15.0  # deux pics ≤ TOLERANCE cm⁻¹ d'écart = "même pic"
N_TOP = 5  # nombre de meilleures paires à afficher
MIN_MANIPS = 2  # une paire doit apparaître dans au moins N manips


# ─── Chargement ─────────────────────────────────────────────────────────────


def load_excel(path: str) -> dict:
    """
    Lit le fichier Excel au format bloc horizontal.
    Retourne un dict {nom_manip: DataFrame} avec colonnes normalisées.
    """
    raw = pd.read_excel(path, header=None)
    if raw.empty:
        raise ValueError("Le fichier Excel est vide.")

    # Ligne 0 : noms des manips (cellules fusionnées → premier nom, NaN
    # ensuite)
    manip_row = raw.iloc[0].tolist()

    # Repérer les colonnes de début de chaque manip (cellule non-vide)
    manip_starts = []
    for idx, val in enumerate(manip_row):
        if pd.notna(val) and str(val).strip():
            manip_starts.append((str(val).strip(), idx))

    if not manip_starts:
        raise ValueError(
            "Impossible de trouver les noms de manips dans la première ligne.\n"
            "Vérifiez que la ligne 1 contient bien les noms (ex: GC561, GC562…)."
        )

    # Ligne 1 : noms de colonnes
    header_row = raw.iloc[1].tolist()

    data_per_manip = {}
    for i, (manip_name, start_col) in enumerate(manip_starts):
        end_col = start_col + 5
        sub = raw.iloc[2:, start_col:end_col].copy()

        # Récupérer les en-têtes de cette manip
        cols = []
        for j, c in enumerate(header_row[start_col:end_col]):
            cols.append(str(c).strip() if pd.notna(c) else f"col_{j}")
        sub.columns = cols

        sub = sub.dropna(how="all").reset_index(drop=True)

        # Convertir toutes les colonnes en numérique (sauf si elles restent
        # str)
        for col in sub.columns:
            sub[col] = pd.to_numeric(sub[col], errors="coerce")

        data_per_manip[manip_name] = sub

    return data_per_manip


# ─── Reconnaissance des colonnes ────────────────────────────────────────────


def _role(col_name: str) -> str | None:
    """Identifie le rôle d'une colonne par mots-clés (insensible à la casse)."""
    c = col_name.lower()
    if "pic a" in c or "peak_a" in c or "peak a" in c:
        return "pic_a"
    if "pic b" in c or "peak_b" in c or "peak b" in c:
        return "pic_b"
    # |rho| avant rho signé (pour ne pas confondre)
    if "|rho|" in c or "|ρ|" in c or "abs_corr" in c or "abs rho" in c:
        return "abs_rho"
    if "rho" in c or "ρ" in c:
        return "rho_signed"
    return None


def extract_pairs(df: pd.DataFrame, manip_name: str) -> pd.DataFrame:
    """
    Extrait pic_a, pic_b, abs_rho depuis un DataFrame de manip.
    Normalise l'ordre (pic_a ≤ pic_b) pour faciliter la comparaison.
    """
    col_map = {}
    for col in df.columns:
        r = _role(col)
        if r and r not in col_map:  # premier match gagne
            col_map[r] = col

    missing = [r for r in ("pic_a", "pic_b", "abs_rho") if r not in col_map]
    if missing:
        raise ValueError(
            f"Manip '{manip_name}' — colonnes non reconnues : {missing}\n"
            f"Colonnes disponibles : {list(df.columns)}\n"
            "Renommez ou ajustez la fonction _role() dans le script."
        )

    result = pd.DataFrame(
        {
            "pic_a": pd.to_numeric(df[col_map["pic_a"]], errors="coerce"),
            "pic_b": pd.to_numeric(df[col_map["pic_b"]], errors="coerce"),
            "abs_rho": pd.to_numeric(df[col_map["abs_rho"]], errors="coerce"),
        }
    ).dropna()

    # Normaliser : pic_a ≤ pic_b (I800/I1200 == I1200/I800 pour la comparaison)
    swap = result["pic_a"] > result["pic_b"]
    result.loc[swap, ["pic_a", "pic_b"]
               ] = result.loc[swap, ["pic_b", "pic_a"]].values

    return result.reset_index(drop=True)


# ─── Correspondance cross-manip ──────────────────────────────────────────────


def _close(a1, b1, a2, b2, tol: float) -> bool:
    """Deux paires sont 'identiques' si |ΔA| ≤ tol ET |ΔB| ≤ tol."""
    return abs(a1 - a2) <= tol and abs(b1 - b2) <= tol


def find_cross_manip_best(
    data_per_manip: dict,
    tolerance: float = TOLERANCE_CM,
    n_top: int = N_TOP,
    min_manips: int = MIN_MANIPS,
) -> tuple[list, list]:
    """
    Pour chaque paire de chaque manip, cherche ses équivalentes dans les autres manips.
    Score = (nb de manips, |rho| moyen, |rho| minimum).
    Retourne les n_top meilleures paires et la liste des noms de manips.
    """
    manip_names = list(data_per_manip.keys())

    # Extraire les paires de chaque manip
    pairs_per_manip: dict[str, pd.DataFrame] = {}
    for manip, df in data_per_manip.items():
        try:
            pairs_per_manip[manip] = extract_pairs(df, manip)
        except ValueError as e:
            print(f"[AVERTISSEMENT] {e}\n  → Manip ignorée.\n")

    if not pairs_per_manip:
        raise RuntimeError(
            "Aucune manip valide — vérifiez la structure du fichier.")

    # Construire la liste plate de toutes les paires
    all_entries = []
    for manip, pairs in pairs_per_manip.items():
        for _, row in pairs.iterrows():
            all_entries.append(
                {
                    "manip": manip,
                    "pic_a": float(row["pic_a"]),
                    "pic_b": float(row["pic_b"]),
                    "abs_rho": float(row["abs_rho"]),
                }
            )

    # Pour chaque paire, chercher ses correspondantes dans les autres manips
    results = []
    for entry in all_entries:
        manip_rhos = {entry["manip"]: entry["abs_rho"]}

        for other_manip, pairs_df in pairs_per_manip.items():
            if other_manip == entry["manip"]:
                continue
            for _, row in pairs_df.iterrows():
                if _close(
                    entry["pic_a"],
                    entry["pic_b"],
                    float(row["pic_a"]),
                    float(row["pic_b"]),
                    tolerance,
                ):
                    # Garder le meilleur |rho| trouvé dans cette manip
                    val = float(row["abs_rho"])
                    if np.isfinite(val) and (
                        other_manip not in manip_rhos or val > manip_rhos[other_manip]
                    ):
                        manip_rhos[other_manip] = val

        n_m = len(manip_rhos)
        mean_rho = float(np.mean(list(manip_rhos.values())))
        min_rho = float(np.min(list(manip_rhos.values())))

        results.append(
            {
                "pic_a": round(entry["pic_a"]),
                "pic_b": round(entry["pic_b"]),
                "n_manips": n_m,
                "mean_abs_rho": round(mean_rho, 4),
                "min_abs_rho": round(min_rho, 4),
                "detail": {m: round(v, 4) for m, v in manip_rhos.items()},
            }
        )

    # Trier : d'abord par nombre de manips (desc), puis par |rho| moyen (desc)
    results.sort(key=lambda x: (-x["n_manips"], -x["mean_abs_rho"]))

    # Dédupliquer : ne garder qu'un représentant par groupe de paires proches
    unique: list[dict] = []
    for r in results:
        already = any(
            _close(r["pic_a"], r["pic_b"], u["pic_a"], u["pic_b"], tolerance)
            for u in unique
        )
        if not already:
            unique.append(r)

    # Filtrer par nombre minimum de manips
    filtered = [r for r in unique if r["n_manips"] >= min_manips]

    return filtered[:n_top], manip_names


# ─── Affichage ───────────────────────────────────────────────────────────────


def print_results(top_pairs: list, manip_names: list,
                  n_top: int, tolerance: float):
    line = "=" * 62
    print(f"\n{line}")
    print(f"  ANALYSE CROSS-MANIP — TOP {n_top} PAIRES ROBUSTES")
    print(line)
    print(
        f"  Manips analysées ({
            len(manip_names)}) : {
            ', '.join(manip_names)}")
    print(f"  Tolérance d'appariement : ±{tolerance:.0f} cm⁻¹")
    print()

    if not top_pairs:
        print("  Aucune paire commune trouvée.")
        print(
            f"  → Essayez d'augmenter --tolerance (actuellement {
                tolerance:.0f} cm⁻¹)"
        )
        print(f"  → Ou réduisez --min-manips (actuellement {MIN_MANIPS})")
        print(line)
        return

    for i, p in enumerate(top_pairs, 1):
        star = "★" if p["n_manips"] == len(manip_names) else " "
        print(f"  {star} #{i}  I{p['pic_a']:.0f} / I{p['pic_b']:.0f}")
        print(
            f"       Présente dans {p['n_manips']}/{len(manip_names)} manip(s)")
        print(
            f"       |ρ| moyen = {
                p['mean_abs_rho']:.4f}   |ρ| minimum = {
                p['min_abs_rho']:.4f}"
        )
        print(f"       Détail :")
        for manip in manip_names:
            rho_val = p["detail"].get(manip)
            if rho_val is not None:
                print(f"         {manip:<20s}  |ρ| = {rho_val:.4f}")
            else:
                print(
                    f"         {
                        manip:<20s}  —   (paire absente du classement)")
        print()

    print("  ★ = présente dans TOUTES les manips")
    print(line)


# ─── Export Excel ────────────────────────────────────────────────────────────


def export_results(top_pairs: list, manip_names: list, output_path: str):
    rows = []
    for i, p in enumerate(top_pairs, 1):
        row: dict = {
            "Rang": i,
            "Pic A (cm-1)": p["pic_a"],
            "Pic B (cm-1)": p["pic_b"],
            "Nb manips": p["n_manips"],
            "|rho| moyen": p["mean_abs_rho"],
            "|rho| minimum": p["min_abs_rho"],
        }
        for manip in manip_names:
            row[f"|rho| {manip}"] = p["detail"].get(manip, "—")
        rows.append(row)

    df_out = pd.DataFrame(rows)
    df_out.to_excel(output_path, index=False)
    print(f"\n  Résultats exportés → {output_path}")


# ─── Point d'entrée ──────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Trouve les meilleures paires Raman communes à plusieurs manips.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "fichier",
        nargs="?",
        help="Chemin vers le fichier Excel (demandé interactivement si absent)",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=TOLERANCE_CM,
        help=f"Tolérance en cm⁻¹ pour apparier deux pics (défaut : {TOLERANCE_CM})",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=N_TOP,
        help=f"Nombre de meilleures paires à afficher (défaut : {N_TOP})",
    )
    parser.add_argument(
        "--min-manips",
        type=int,
        default=MIN_MANIPS,
        dest="min_manips",
        help=f"Nombre minimum de manips où la paire doit figurer (défaut : {MIN_MANIPS})",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Exporter les résultats dans un fichier Excel (nom_fichier_cross_manip.xlsx)",
    )
    args = parser.parse_args()

    # ── Chemin du fichier ──
    if args.fichier:
        file_path = args.fichier.strip().strip('"')
    else:
        file_path = input("Chemin du fichier Excel : ").strip().strip('"')

    if not Path(file_path).exists():
        print(f"Erreur : fichier introuvable → {file_path}")
        sys.exit(1)

    # ── Chargement ──
    print(f"\nChargement de : {file_path}")
    data = load_excel(file_path)
    print(f"Manips détectées ({len(data)}) : {', '.join(data.keys())}")

    for manip, df in data.items():
        print(f"  {manip} : {len(df)} paires chargées")

    # ── Analyse ──
    top, manip_names = find_cross_manip_best(
        data,
        tolerance=args.tolerance,
        n_top=args.top,
        min_manips=args.min_manips,
    )

    print_results(top, manip_names, args.top, args.tolerance)

    # ── Export optionnel ──
    if args.export and top:
        out_path = Path(file_path).stem + "_cross_manip.xlsx"
        export_results(top, manip_names, out_path)


if __name__ == "__main__":
    main()
