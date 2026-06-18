"""peak_selector.py
Onglet « Sélection de pics » – Workflow automatisé pour identifier les régions
spectrales les plus informatives pour la titration Raman/SERS.

Algorithme :
  1. Construction de la matrice spectrale (n_spectres × n_wavenumbers)
  2. Calcul de la variable de titration r = n(titrant) (mol)
  3. Corrélation de Spearman par wavenumber avec r
  4. Score combiné = |ρ| × dynamique spectrale → candidats
  5. Classement de toutes les paires I_A/I_B par |ρ(ratio, r)|
  6. Analyse PCA corrélée avec r
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks
from scipy.stats import spearmanr
from sklearn.decomposition import PCA

from data_processing import load_combined_df
from plotly_downloads import (
    install_plotly_download_handler,
    load_plotly_html,
    sanitize_filename,
    set_plotly_filename,
)

# ──────────────────────────────────────────────────────────────────────────────
# Fonctions d'analyse (indépendantes du widget)
# ──────────────────────────────────────────────────────────────────────────────


def _norm_col(name: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFD", name.lower().strip())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _find_col(df: pd.DataFrame, *keys: str) -> str | None:
    col_map = {_norm_col(c): c for c in df.columns}
    for key in keys:
        c = col_map.get(_norm_col(key))
        if c is not None:
            return c
    return None


def _to_float(df: pd.DataFrame, col: str) -> pd.Series:
    raw = df[col]
    if raw.dtype == object:
        raw = raw.astype(str).str.replace(",", ".").str.strip()
    return pd.to_numeric(raw, errors="coerce")


def compute_r(meta_per_spec: pd.DataFrame) -> pd.Series | None:
    """Calcule n(titrant) (mol) = C(Solution B) × V_cuvette.

    Cherche d'abord la colonne déjà calculée, puis les colonnes brutes.
    Retourne None si impossible.
    """
    # 1. Colonne directe
    direct = _find_col(meta_per_spec, "n(titrant) (mol)", "n titrant mol")
    if direct is not None:
        return _to_float(meta_per_spec, direct)

    # 2. Concentration × volume
    c_col = _find_col(meta_per_spec, "solution b", "[titrant] (m)", "c_b")
    v_col = _find_col(
        meta_per_spec, "v cuvette (µl)", "v cuvette (ul)", "v cuvette (ml)"
    )
    if c_col is None or v_col is None:
        return None

    c = _to_float(meta_per_spec, c_col)
    v = _to_float(meta_per_spec, v_col)
    v_col_norm = _norm_col(v_col)
    v_l = v * (1e-3 if "ml" in v_col_norm else 1e-6)
    return c * v_l


def build_spectral_matrix(
    combined_df: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, pd.DataFrame, np.ndarray]:
    """Construit la matrice (n_spectres × n_wavenumbers).

    Retourne (X, wavenumbers, meta_per_spec, spec_ids).
    """
    df = combined_df.copy()
    index_col = "Spectrum name" if "Spectrum name" in df.columns else "file"

    mat = df.pivot_table(
        index=index_col,
        columns="Raman Shift",
        values="Intensity_corrected",
        aggfunc="mean",
    )
    mat = mat.apply(lambda col: col.fillna(col.mean()), axis=0)

    X = mat.to_numpy(dtype=float)
    wavenumbers = mat.columns.to_numpy(dtype=float)
    spec_ids = mat.index.to_numpy()

    # index_col devient l'index du groupby ; l'exclure de meta_cols pour éviter
    # que reset_index() tente de le réinsérer alors qu'il y est déjà.
    spectral_cols = {
        "Raman Shift",
        "Intensity_corrected",
        "Dark Subtracted #1",
        "file"}
    meta_cols = [
        c for c in df.columns if c not in spectral_cols and c != index_col]
    meta_per_spec = df.groupby(
        index_col)[meta_cols].first().loc[spec_ids].reset_index()
    return X, wavenumbers, meta_per_spec, spec_ids


def normalize_matrix(X: np.ndarray, mode: int) -> np.ndarray:
    """mode 0 = aucune, 1 = L2, 2 = Z-score."""
    if mode == 1:
        norms = np.linalg.norm(X, axis=1, keepdims=True)
        norms = np.where(norms < 1e-12, 1.0, norms)
        return X / norms
    if mode == 2:
        mean = X.mean(axis=0, keepdims=True)
        std = X.std(axis=0, keepdims=True)
        std = np.where(std < 1e-12, 1.0, std)
        return (X - mean) / std
    return X.copy()


def spearman_spectrum(X: np.ndarray, r: np.ndarray) -> np.ndarray:
    """ρ de Spearman (signé) pour chaque wavenumber."""
    corr = np.zeros(X.shape[1])
    for i in range(X.shape[1]):
        col = X[:, i]
        if np.std(col) < 1e-12:
            continue
        try:
            c, _ = spearmanr(col, r)
            corr[i] = float(c) if np.isfinite(c) else 0.0
        except Exception:
            pass
    return corr


def range_score(X: np.ndarray) -> np.ndarray:
    """Score de dynamique normalisé dans [0, 1] pour chaque wavenumber."""
    rng = X.max(axis=0) - X.min(axis=0)
    mean_abs = np.abs(X).mean(axis=0) + 1e-12
    raw = rng / mean_abs
    denom = raw.max() if raw.max() > 0 else 1.0
    return raw / denom


def find_candidate_peaks(
    combined_score: np.ndarray,
    wavenumbers: np.ndarray,
    n_candidates: int = 15,
    min_distance_cm: float = 20.0,
    min_height_frac: float = 0.05,
) -> np.ndarray:
    """Sélectionne les N wavenumbers candidats par maxima locaux du score combiné.

    Garantit une séparation minimale de min_distance_cm entre candidats.
    Ignore les pics dont le score est inférieur à min_height_frac * max(score).
    """
    if len(wavenumbers) < 2:
        return wavenumbers[:1]

    delta_cm = float(np.median(np.diff(wavenumbers)))
    min_dist_idx = max(1, int(min_distance_cm / delta_cm))

    max_score = combined_score.max()
    min_h = max_score * min_height_frac if max_score > 0 else None

    peaks, _ = find_peaks(combined_score, distance=min_dist_idx, height=min_h)
    if len(peaks) == 0:
        # Fallback sans seuil de hauteur
        peaks, _ = find_peaks(combined_score, distance=min_dist_idx)
    if len(peaks) == 0:
        peaks = np.arange(len(combined_score))

    peaks_sorted = peaks[np.argsort(combined_score[peaks])[::-1]]
    selected = peaks_sorted[:n_candidates]
    return wavenumbers[selected]


def score_pairs(
    X: np.ndarray,
    wavenumbers: np.ndarray,
    r: np.ndarray,
    candidate_wns: np.ndarray,
) -> list[dict]:
    """Score toutes les paires par |ρ(I_A/I_B, r)|. Retourne une liste triée."""
    results = []
    for wn_a, wn_b in itertools.combinations(candidate_wns, 2):
        idx_a = int(np.argmin(np.abs(wavenumbers - wn_a)))
        idx_b = int(np.argmin(np.abs(wavenumbers - wn_b)))

        I_a, I_b = X[:, idx_a], X[:, idx_b]
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(np.abs(I_b) > 1e-12, I_a / I_b, np.nan)

        valid = np.isfinite(ratio) & np.isfinite(r)
        if valid.sum() < 3:
            continue

        try:
            corr, _ = spearmanr(ratio[valid], r[valid])
        except Exception:
            continue

        if not np.isfinite(corr):
            continue

        results.append(
            {
                "peak_A": round(float(wn_a), 1),
                "peak_B": round(float(wn_b), 1),
                "label": f"I {wn_a:.0f} / I {wn_b:.0f}",
                "corr": float(corr),
                "abs_corr": float(abs(corr)),
            }
        )

    return sorted(results, key=lambda d: d["abs_corr"], reverse=True)


def pca_with_r_correlation(
    X: np.ndarray,
    r: np.ndarray,
    n_components: int = 5,
) -> dict:
    """PCA + corrélation de Spearman de chaque score PC avec r."""
    n_comp = min(n_components, X.shape[0] - 1, X.shape[1])
    pca = PCA(n_components=n_comp)
    scores = pca.fit_transform(X)
    loadings = pca.components_

    corrs = []
    for k in range(n_comp):
        try:
            c, _ = spearmanr(scores[:, k], r)
        except Exception:
            c = 0.0
        corrs.append(float(c) if np.isfinite(c) else 0.0)

    return {
        "scores": scores,
        "loadings": loadings,
        "explained_variance_ratio": pca.explained_variance_ratio_,
        "corrs_with_r": corrs,
        "n_comp": n_comp,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Widget Qt
# ──────────────────────────────────────────────────────────────────────────────


class PeakSelectorTab(QWidget):
    """Onglet de sélection automatique des pics de titration Raman/SERS."""

    def __init__(self, file_picker, metadata_creator, parent=None):
        super().__init__(parent)
        self._file_picker = file_picker
        self._metadata_creator = metadata_creator
        self._combined_df: pd.DataFrame | None = None
        self._result: dict | None = None
        # PCA libre — données stockées après _run_analysis
        self._X_proc: np.ndarray | None = None
        self._wavenumbers_proc: np.ndarray | None = None
        self._r_v: np.ndarray | None = None
        self._ids_v: np.ndarray | None = None
        self._meta_v: pd.DataFrame | None = None
        self._pca_libre_pca: PCA | None = None
        self._pca_libre_scores: np.ndarray | None = None
        self._pca_libre_loadings: np.ndarray | None = None
        self._pca_libre_ev_ratio: np.ndarray | None = None
        self._setup_ui()

    # ── UI ──────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        header = QLabel(
            "<b>Sélection automatique des pics de titration</b><br>"
            "Ce workflow identifie les régions spectrales dont l'intensité co-varie de façon "
            "monotone avec la quantité de titrant (|ρ de Spearman|), puis classe les paires "
            "I<sub>A</sub>/I<sub>B</sub> par pertinence pour la détection de l'équivalence."
        )
        header.setWordWrap(True)
        header.setStyleSheet("padding:6px;")
        layout.addWidget(header)

        # ── Contrôles ────────────────────────────────────────────────────────
        ctrl_box = QGroupBox("Paramètres")
        ctrl = QFormLayout(ctrl_box)

        self.cmb_norm = QComboBox()
        self.cmb_norm.addItems(
            [
                "Aucune normalisation",
                "Normalisation L2 (par spectre)",
                "Standardisation Z-score (par wavenumber)",
            ]
        )
        ctrl.addRow("Normalisation :", self.cmb_norm)

        self.spin_window = QSpinBox()
        self.spin_window.setRange(1, 100)
        self.spin_window.setValue(10)
        self.spin_window.setSuffix(" cm⁻¹")
        ctrl.addRow("Fenêtre de lissage de ρ :", self.spin_window)

        self.spin_n_cand = QSpinBox()
        self.spin_n_cand.setRange(3, 50)
        self.spin_n_cand.setValue(15)
        ctrl.addRow("Nombre de candidats :", self.spin_n_cand)

        self.spin_n_pca = QSpinBox()
        self.spin_n_pca.setRange(2, 10)
        self.spin_n_pca.setValue(5)
        ctrl.addRow("Composantes PCA corrélée :", self.spin_n_pca)

        self.spin_n_comp_libre = QSpinBox()
        self.spin_n_comp_libre.setRange(2, 15)
        self.spin_n_comp_libre.setValue(5)
        ctrl.addRow("Composantes PCA libre :", self.spin_n_comp_libre)

        self.cmb_color = QComboBox()
        self.cmb_color.setEnabled(False)
        self.cmb_color.setToolTip(
            "Colonne utilisée pour colorier les points dans PCA — Scores"
        )
        self.cmb_color.currentIndexChanged.connect(self._on_color_changed)
        ctrl.addRow("Couleur des scores :", self.cmb_color)

        # Plage Raman (filtre les zones bruyantes / artéfacts de bord de
        # détecteur)
        wn_row = QHBoxLayout()
        self.spin_wn_min = QDoubleSpinBox()
        self.spin_wn_min.setRange(0, 9999)
        self.spin_wn_min.setValue(1000)
        self.spin_wn_min.setSuffix(" cm⁻¹")
        self.spin_wn_min.setDecimals(0)
        self.spin_wn_max = QDoubleSpinBox()
        self.spin_wn_max.setRange(0, 9999)
        self.spin_wn_max.setValue(1700)
        self.spin_wn_max.setSuffix(" cm⁻¹")
        self.spin_wn_max.setDecimals(0)
        wn_row.addWidget(QLabel("de"))
        wn_row.addWidget(self.spin_wn_min)
        wn_row.addWidget(QLabel("à"))
        wn_row.addWidget(self.spin_wn_max)
        wn_row.addStretch()
        ctrl.addRow("Plage Raman :", wn_row)

        btn_row = QHBoxLayout()
        self.btn_load = QPushButton("1. Charger les données")
        self.btn_run = QPushButton("2. Lancer l'analyse")
        self.btn_run.setEnabled(False)
        self.btn_load.clicked.connect(self._reload_data)
        self.btn_run.clicked.connect(self._run_analysis)
        btn_row.addWidget(self.btn_load)
        btn_row.addWidget(self.btn_run)
        btn_row.addStretch()
        ctrl.addRow(btn_row)

        layout.addWidget(ctrl_box)

        self.lbl_status = QLabel("Données non chargées.")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("padding:4px; color:#333;")
        self.lbl_status.setMinimumHeight(36)
        layout.addWidget(self.lbl_status)

        # ── Onglets de résultats ─────────────────────────────────────────────
        self.result_tabs = QTabWidget()

        self.view_corr = QWebEngineView()
        install_plotly_download_handler(self.view_corr)
        self.view_ratio = QWebEngineView()
        install_plotly_download_handler(self.view_ratio)
        self.view_pca = QWebEngineView()
        install_plotly_download_handler(self.view_pca)

        # ── Onglet "Paires candidates" : graphique + tableau exportable ──────
        pairs_tab = QWidget()
        pairs_layout = QVBoxLayout(pairs_tab)
        pairs_layout.setContentsMargins(0, 0, 0, 4)

        self.view_pairs = QWebEngineView()
        install_plotly_download_handler(self.view_pairs)
        pairs_layout.addWidget(self.view_pairs, stretch=3)

        export_row = QHBoxLayout()
        self.btn_export_pairs = QPushButton("Exporter tableau CSV")
        self.btn_export_pairs.setEnabled(False)
        self.btn_export_pairs.setToolTip(
            "Enregistre toutes les paires dans un fichier CSV (ouvrable dans Excel)"
        )
        self.btn_export_pairs.clicked.connect(self._export_pairs_csv)
        export_row.addWidget(self.btn_export_pairs)
        export_row.addWidget(QLabel("  (Ctrl+C pour copier la sélection)"))
        export_row.addStretch()
        pairs_layout.addLayout(export_row)

        self.table_pairs = QTableWidget()
        self.table_pairs.setColumnCount(5)
        self.table_pairs.setHorizontalHeaderLabels(
            ["Rang", "Pic A (cm⁻¹)", "Pic B (cm⁻¹)", "ρ (signé)", "|ρ|"]
        )
        self.table_pairs.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table_pairs.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.table_pairs.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.table_pairs.setAlternatingRowColors(True)
        self.table_pairs.setSortingEnabled(True)
        pairs_layout.addWidget(self.table_pairs, stretch=2)

        copy_sc = QShortcut(QKeySequence.StandardKey.Copy, self.table_pairs)
        copy_sc.activated.connect(self._copy_table_selection)

        self.result_tabs.addTab(self.view_corr, "Corrélation spectrale")
        self.result_tabs.addTab(pairs_tab, "Paires candidates")
        self.result_tabs.addTab(self.view_ratio, "Meilleur rapport")
        self.result_tabs.addTab(self.view_pca, "PCA & corrélation")

        # ── PCA libre : Scores ───────────────────────────────────────────────
        self.view_pca_scores = QWebEngineView()
        install_plotly_download_handler(self.view_pca_scores)
        self.result_tabs.addTab(self.view_pca_scores, "PCA — Scores")

        # ── PCA libre : Loadings ─────────────────────────────────────────────
        self.view_pca_loadings = QWebEngineView()
        install_plotly_download_handler(self.view_pca_loadings)
        self.result_tabs.addTab(self.view_pca_loadings, "PCA — Loadings")

        # ── PCA libre : Reconstruction ───────────────────────────────────────
        recon_tab = QWidget()
        recon_layout = QVBoxLayout(recon_tab)
        recon_layout.setContentsMargins(4, 4, 4, 4)
        recon_ctrl_row = QHBoxLayout()
        recon_ctrl_row.addWidget(QLabel("Spectre à reconstruire :"))
        self.cmb_spec_recon = QComboBox()
        self.cmb_spec_recon.setEnabled(False)
        self.cmb_spec_recon.setMinimumWidth(280)
        self.cmb_spec_recon.currentIndexChanged.connect(
            self._on_spec_recon_changed)
        recon_ctrl_row.addWidget(self.cmb_spec_recon)
        recon_ctrl_row.addStretch()
        recon_layout.addLayout(recon_ctrl_row)
        self.view_pca_recon = QWebEngineView()
        install_plotly_download_handler(self.view_pca_recon)
        recon_layout.addWidget(self.view_pca_recon)
        self.result_tabs.addTab(recon_tab, "PCA — Reconstruction")

        layout.addWidget(self.result_tabs, 1)

    # ── Chargement des données ──────────────────────────────────────────────

    def _reload_data(self):
        combined = load_combined_df(
            self, self._file_picker, self._metadata_creator)
        if combined is None:
            self._combined_df = None
            self.lbl_status.setText("Données non chargées.")
            self.btn_run.setEnabled(False)
            return

        self._combined_df = combined
        n_specs = combined["file"].nunique(
        ) if "file" in combined.columns else "?"

        self.lbl_status.setText(
            f"Données chargées : {n_specs} spectre(s). Paramétrez puis lancez l'analyse."
        )
        self.btn_run.setEnabled(True)

    # ── Pipeline d'analyse ──────────────────────────────────────────────────

    def _run_analysis(self):
        if self._combined_df is None or self._combined_df.empty:
            QMessageBox.warning(
                self, "Données manquantes", "Chargez d'abord les données."
            )
            return

        self.lbl_status.setText("Construction de la matrice spectrale…")

        try:
            X, wavenumbers, meta_per_spec, spec_ids = build_spectral_matrix(
                self._combined_df
            )
        except Exception as e:
            QMessageBox.critical(self, "Erreur matrice", str(e))
            self.lbl_status.setText("Erreur.")
            return

        # Filtre de plage Raman
        wn_min = float(self.spin_wn_min.value())
        wn_max = float(self.spin_wn_max.value())
        wn_mask = (wavenumbers >= wn_min) & (wavenumbers <= wn_max)
        if wn_mask.sum() < 5:
            QMessageBox.warning(
                self,
                "Plage Raman trop restrictive",
                f"Moins de 5 wavenumbers dans la plage [{
                    wn_min:.0f}, {
                    wn_max:.0f}] cm⁻¹.\n"
                "Élargissez la plage Raman.",
            )
            self.lbl_status.setText("Erreur : plage Raman trop restrictive.")
            return
        X = X[:, wn_mask]
        wavenumbers = wavenumbers[wn_mask]

        # Variable de titration
        r_series = compute_r(meta_per_spec)
        if r_series is None or r_series.isna().all():
            QMessageBox.warning(
                self,
                "Variable de titration introuvable",
                "Impossible de calculer n(titrant).\n"
                "Vérifiez que 'Solution B' et 'V cuvette (µL)' sont dans les métadonnées.",
            )
            self.lbl_status.setText(
                "Erreur : variable de titration introuvable.")
            return

        r = r_series.to_numpy(dtype=float)
        valid = np.isfinite(r)
        if valid.sum() < 3:
            QMessageBox.warning(
                self,
                "Données insuffisantes",
                "Moins de 3 spectres avec une valeur r valide.",
            )
            return

        X_v = X[valid]
        r_v = r[valid]
        ids_v = spec_ids[valid]
        meta_v = meta_per_spec[valid].reset_index(drop=True)

        # Normalisation
        X_proc = normalize_matrix(X_v, self.cmb_norm.currentIndex())

        # Stocker pour PCA libre (accédé par _run_pca_libre)
        self._X_proc = X_proc
        self._wavenumbers_proc = wavenumbers
        self._r_v = r_v
        self._ids_v = ids_v
        self._meta_v = meta_v

        self.lbl_status.setText("Calcul de la corrélation par wavenumber…")

        # Corrélation de Spearman
        corr_raw = spearman_spectrum(X_proc, r_v)

        # Lissage |ρ| par fenêtre glissante
        window_cm = int(self.spin_window.value())
        delta_cm = (
            float(np.median(np.diff(wavenumbers))) if len(
                wavenumbers) > 1 else 1.0
        )
        window_idx = max(1, int(window_cm / delta_cm))
        corr_smooth = uniform_filter1d(np.abs(corr_raw), size=window_idx)

        # Dynamique spectrale
        range_s = range_score(X_proc)

        # Score combiné et candidats
        combined_score = corr_smooth * range_s
        n_cand = int(self.spin_n_cand.value())
        cand_wns = find_candidate_peaks(combined_score, wavenumbers, n_cand)

        self.lbl_status.setText(
            f"{len(cand_wns)} candidats trouvés. Calcul des paires…"
        )

        # Paires
        pairs = score_pairs(X_proc, wavenumbers, r_v, cand_wns)

        # PCA
        n_pca = min(int(self.spin_n_pca.value()),
                    X_proc.shape[0] - 1, X_proc.shape[1])
        pca_res = pca_with_r_correlation(X_proc, r_v, n_components=n_pca)

        self._result = {
            "wavenumbers": wavenumbers,
            "corr_raw": corr_raw,
            "corr_smooth": corr_smooth,
            "range_scores": range_s,
            "candidates": cand_wns,
            "pairs": pairs,
            "pca": pca_res,
            "X_proc": X_proc,
            "r": r_v,
            "spec_ids": ids_v,
            "meta": meta_v,
        }

        self._plot_all()
        self._populate_pca_libre_combos()
        self._run_pca_libre()

        best = pairs[0] if pairs else None
        summary = (
            f"Analyse terminée : {
                X_proc.shape[0]} spectres × {
                X_proc.shape[1]} wavenumbers. "
            f"{len(cand_wns)} candidats, {len(pairs)} paires scorées."
        )
        if best:
            summary += (
                f" Meilleure paire : I{
                    best['peak_A']:.0f}/I{
                    best['peak_B']:.0f}"
                f" (|ρ|={best['abs_corr']:.3f})."
            )
        self.lbl_status.setText(summary)

    # ── Tracés ──────────────────────────────────────────────────────────────

    def _plot_all(self):
        r = self._result
        self._plot_corr_spectrum(
            r["wavenumbers"],
            r["corr_raw"],
            r["corr_smooth"],
            r["range_scores"],
            r["candidates"],
        )
        self._plot_pairs(r["pairs"])
        self._plot_best_ratio(
            r["X_proc"], r["wavenumbers"], r["r"], r["pairs"], r["spec_ids"]
        )
        self._plot_pca(r["pca"], r["wavenumbers"], r["r"], r["spec_ids"])

    # ── Graphique 1 : spectre de corrélation ─────────────────────────────────

    def _plot_corr_spectrum(self, wn, corr_raw, corr_smooth, rng, candidates):
        fig = go.Figure()

        # ρ brut (signé, semi-transparent)
        fig.add_trace(
            go.Scatter(
                x=wn,
                y=corr_raw,
                mode="lines",
                name="ρ de Spearman (brut, signé)",
                line=dict(color="rgba(100,149,237,0.45)", width=1),
            )
        )

        # |ρ| lissé
        fig.add_trace(
            go.Scatter(
                x=wn,
                y=corr_smooth,
                mode="lines",
                name="|ρ| lissé",
                line=dict(color="#1a4fa0", width=2),
            )
        )

        # Dynamique normalisée (axe secondaire)
        fig.add_trace(
            go.Scatter(
                x=wn,
                y=rng,
                mode="lines",
                name="Dynamique normalisée",
                line=dict(color="rgba(210,70,20,0.6)", width=1.5, dash="dot"),
                yaxis="y2",
            )
        )

        # Candidats
        for c_wn in candidates:
            fig.add_vline(
                x=float(c_wn),
                line=dict(color="green", width=1, dash="dash"),
                annotation_text=f"{c_wn:.0f}",
                annotation_position="top",
                annotation_font_size=9,
            )

        fig.add_hline(y=0, line=dict(color="gray", width=0.5))

        fig.update_layout(
            title="Corrélation spectrale avec la variable de titration",
            xaxis_title="Raman Shift (cm⁻¹)",
            yaxis_title="Corrélation de Spearman ρ",
            yaxis2=dict(
                title="Dynamique normalisée",
                overlaying="y",
                side="right",
                showgrid=False,
            ),
            width=1200,
            height=520,
            legend=dict(orientation="h", x=0.5, y=-0.2, xanchor="center"),
            margin=dict(b=110),
        )

        manip = self._get_manip_name()
        fb = (
            sanitize_filename(f"{manip}_Correlation_Spectrale")
            if manip
            else "Correlation_Spectrale"
        )
        set_plotly_filename(self.view_corr, fb)
        self.view_corr._plotly_fig = fig
        load_plotly_html(self.view_corr, fig.to_html(include_plotlyjs=True))

    # ── Graphique 2 : classement des paires ──────────────────────────────────

    def _plot_pairs(self, pairs: list[dict]):
        if not pairs:
            self.view_pairs.setHtml(
                "<p style='font-family:sans-serif;padding:20px'>"
                "Aucune paire trouvée avec les paramètres actuels.</p>"
            )
            return

        top = pairs[:25]
        labels = [f"I{p['peak_A']:.0f}/I{p['peak_B']:.0f}" for p in top]
        corrs = [p["abs_corr"] for p in top]
        colors = ["#c0392b" if p["corr"] > 0 else "#2980b9" for p in top]
        hover = [
            f"I{p['peak_A']:.0f} / I{p['peak_B']:.0f}<br>ρ = {p['corr']:+.3f}"
            for p in top
        ]

        fig = go.Figure(
            go.Bar(
                x=labels,
                y=corrs,
                marker_color=colors,
                text=[f"{c:.3f}" for c in corrs],
                textposition="outside",
                hovertext=hover,
                hoverinfo="text",
            )
        )

        fig.update_layout(
            title="Top 25 paires de pics — classées par |ρ(ratio, n(titrant))|",
            xaxis_title="Paire",
            yaxis_title="|ρ de Spearman|",
            yaxis=dict(range=[0, min(1.12, max(corrs) * 1.15)]),
            width=1200,
            height=520,
            annotations=[
                dict(
                    text=(
                        "<span style='color:#c0392b'>■</span> ρ > 0 (ratio croissant avec titrant) &nbsp;&nbsp;"
                        "<span style='color:#2980b9'>■</span> ρ < 0 (ratio décroissant)"
                    ),
                    xref="paper",
                    yref="paper",
                    x=0.5,
                    y=-0.22,
                    showarrow=False,
                    font_size=11,
                )
            ],
            margin=dict(b=110),
        )

        manip = self._get_manip_name()
        fb = (
            sanitize_filename(f"{manip}_Paires_candidats")
            if manip
            else "Paires_candidats"
        )
        set_plotly_filename(self.view_pairs, fb)
        self.view_pairs._plotly_fig = fig
        load_plotly_html(self.view_pairs, fig.to_html(include_plotlyjs=True))

        # Remplir le tableau avec toutes les paires (pas seulement le top 25)
        self.table_pairs.setSortingEnabled(False)
        self.table_pairs.setRowCount(len(pairs))
        for row_idx, p in enumerate(pairs):
            rang_item = QTableWidgetItem()
            # stocke un entier pour tri numérique
            rang_item.setData(0, row_idx + 1)
            self.table_pairs.setItem(row_idx, 0, rang_item)
            self.table_pairs.setItem(
                row_idx, 1, QTableWidgetItem(f"{p['peak_A']:.1f}"))
            self.table_pairs.setItem(
                row_idx, 2, QTableWidgetItem(f"{p['peak_B']:.1f}"))
            self.table_pairs.setItem(
                row_idx, 3, QTableWidgetItem(f"{p['corr']:+.4f}"))
            self.table_pairs.setItem(
                row_idx, 4, QTableWidgetItem(f"{p['abs_corr']:.4f}")
            )
        self.table_pairs.setSortingEnabled(True)
        self.btn_export_pairs.setEnabled(True)

    # ── Graphique 3 : meilleur rapport ───────────────────────────────────────

    def _plot_best_ratio(self, X, wn, r, pairs, spec_ids):
        if not pairs:
            self.view_ratio.setHtml(
                "<p style='font-family:sans-serif;padding:20px'>Aucune paire disponible.</p>"
            )
            return

        best = pairs[0]
        idx_a = int(np.argmin(np.abs(wn - best["peak_A"])))
        idx_b = int(np.argmin(np.abs(wn - best["peak_B"])))

        I_a, I_b = X[:, idx_a], X[:, idx_b]
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(np.abs(I_b) > 1e-12, I_a / I_b, np.nan)

        valid = np.isfinite(ratio) & np.isfinite(r)
        r_v = r[valid]
        ratio_v = ratio[valid]
        ids_v = spec_ids[valid] if spec_ids is not None else np.arange(
            len(r_v))

        sort_idx = np.argsort(r_v)
        r_sort, ratio_sort = r_v[sort_idx], ratio_v[sort_idx]

        fig = go.Figure()

        # Points
        fig.add_trace(
            go.Scatter(
                x=r_v,
                y=ratio_v,
                mode="markers",
                marker=dict(
                    size=9,
                    color=r_v,
                    colorscale="Viridis",
                    showscale=True,
                    colorbar=dict(title="n(titrant)<br>(mol)"),
                ),
                text=[str(s) for s in ids_v],
                hovertemplate="%{text}<br>n=%{x:.3e}<br>ratio=%{y:.4f}<extra></extra>",
                name="Spectres",
            )
        )

        # Tendance (moyenne mobile)
        window = max(2, len(r_sort) // 5)
        smooth = (
            pd.Series(ratio_sort)
            .rolling(window, center=True, min_periods=1)
            .mean()
            .to_numpy()
        )
        fig.add_trace(
            go.Scatter(
                x=r_sort,
                y=smooth,
                mode="lines",
                line=dict(color="red", width=2, dash="dash"),
                name="Tendance (moy. mobile)",
            )
        )

        # Top 5 autres paires en légende
        other_info = "<br>".join(
            f"#{i +
                2} I{p['peak_A']:.0f}/I{p['peak_B']:.0f}  |ρ|={p['abs_corr']:.3f}"
            for i, p in enumerate(pairs[1:5])
        )
        if other_info:
            fig.add_annotation(
                xref="paper",
                yref="paper",
                x=0.01,
                y=0.99,
                text=f"<b>Top 5 paires :</b><br>#1 (affiché)<br>{other_info}",
                showarrow=False,
                align="left",
                bgcolor="rgba(255,255,255,0.85)",
                bordercolor="gray",
                font_size=10,
            )

        fig.update_layout(
            title=(
                f"Meilleure paire : I{
                    best['peak_A']:.0f} / I{
                    best['peak_B']:.0f}"
                f"  (|ρ| = {best['abs_corr']:.3f}, ρ = {best['corr']:+.3f})"
            ),
            xaxis_title="n(titrant) (mol)",
            yaxis_title=f"I{best['peak_A']:.0f} / I{best['peak_B']:.0f}",
            xaxis_tickformat=".2e",
            width=1200,
            height=520,
        )

        manip = self._get_manip_name()
        fb = (
            sanitize_filename(f"{manip}_Meilleur_Rapport")
            if manip
            else "Meilleur_Rapport"
        )
        set_plotly_filename(self.view_ratio, fb)
        self.view_ratio._plotly_fig = fig
        load_plotly_html(self.view_ratio, fig.to_html(include_plotlyjs=True))

    # ── Graphique 4 : PCA + corrélation r ────────────────────────────────────

    def _plot_pca(self, pca_res, wn, r, spec_ids):
        scores = pca_res["scores"]
        loadings = pca_res["loadings"]
        ev_ratio = pca_res["explained_variance_ratio"]
        corrs = pca_res["corrs_with_r"]
        n_comp = pca_res["n_comp"]

        best_pc = int(np.argmax(np.abs(corrs)))
        pc_labels = [f"PC{k + 1}" for k in range(n_comp)]

        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=[
                "|ρ(PC_k, n(titrant))| — Quelle PC porte l'info de titration ?",
                f"Scores PC{best_pc +
                            1} vs n(titrant)  (|ρ|={abs(corrs[best_pc]):.3f})",
                f"Loadings PC{
                    best_pc +
                    1}  ({
                    ev_ratio[best_pc] *
                    100:.1f}% variance) — régions influentes",
                "Variance expliquée par PC (% et cumulée)",
            ],
            vertical_spacing=0.14,
            horizontal_spacing=0.10,
        )

        # 1. Corrélation PCs vs r
        bar_colors = ["#e74c3c" if k ==
                      best_pc else "#3498db" for k in range(n_comp)]
        fig.add_trace(
            go.Bar(
                x=pc_labels,
                y=[abs(c) for c in corrs],
                marker_color=bar_colors,
                text=[f"{abs(c):.3f}" for c in corrs],
                textposition="outside",
                showlegend=False,
            ),
            row=1,
            col=1,
        )

        # 2. Scores best PC vs r
        fig.add_trace(
            go.Scatter(
                x=r,
                y=scores[:, best_pc],
                mode="markers",
                marker=dict(
                    size=9,
                    color=r,
                    colorscale="Viridis",
                    showscale=False),
                text=[str(s) for s in spec_ids],
                hovertemplate="%{text}<br>n=%{x:.3e}<br>score=%{y:.3f}<extra></extra>",
                showlegend=False,
            ),
            row=1,
            col=2,
        )

        # 3. Loadings best PC
        loading_vals = loadings[best_pc]
        fig.add_trace(
            go.Scatter(
                x=wn,
                y=loading_vals,
                mode="lines",
                line=dict(color="#2ecc71", width=1.5),
                showlegend=False,
                fill="tozeroy",
                fillcolor="rgba(46,204,113,0.15)",
            ),
            row=2,
            col=1,
        )
        fig.add_hline(y=0, line_color="gray", line_width=0.5, row=2, col=1)

        # Annoter les 5 pics dominants dans les loadings
        abs_load = np.abs(loading_vals)
        top5_idx, _ = find_peaks(abs_load, distance=max(1, len(wn) // 50))
        if len(top5_idx) > 0:
            top5_idx = top5_idx[np.argsort(abs_load[top5_idx])[::-1][:5]]
            for idx in top5_idx:
                fig.add_annotation(
                    x=wn[idx],
                    y=loading_vals[idx],
                    text=f"{wn[idx]:.0f}",
                    showarrow=True,
                    arrowhead=2,
                    arrowsize=0.8,
                    font_size=9,
                    row=2,
                    col=1,
                )

        # 4. Variance cumulée
        cum_var = np.cumsum(ev_ratio) * 100
        fig.add_trace(
            go.Bar(
                x=pc_labels,
                y=ev_ratio * 100,
                marker_color="#95a5a6",
                name="Variance (%)",
                showlegend=False,
            ),
            row=2,
            col=2,
        )
        fig.add_trace(
            go.Scatter(
                x=pc_labels,
                y=cum_var,
                mode="lines+markers",
                line=dict(color="#e67e22", width=2),
                name="Cumulée (%)",
                showlegend=False,
            ),
            row=2,
            col=2,
        )

        fig.update_layout(width=1200, height=820)
        fig.update_xaxes(title_text="PC", row=1, col=1)
        fig.update_xaxes(
            title_text="n(titrant) (mol)",
            tickformat=".2e",
            row=1,
            col=2)
        fig.update_xaxes(title_text="Raman Shift (cm⁻¹)", row=2, col=1)
        fig.update_xaxes(title_text="PC", row=2, col=2)
        fig.update_yaxes(
            title_text="|ρ de Spearman|", range=[
                0, 1.05], row=1, col=1)
        fig.update_yaxes(title_text=f"Score PC{best_pc + 1}", row=1, col=2)
        fig.update_yaxes(title_text="Loading", row=2, col=1)
        fig.update_yaxes(title_text="Variance (%)", row=2, col=2)

        manip = self._get_manip_name()
        fb = (
            sanitize_filename(f"{manip}_PCA_Correlation")
            if manip
            else "PCA_Correlation"
        )
        set_plotly_filename(self.view_pca, fb)
        self.view_pca._plotly_fig = fig
        load_plotly_html(self.view_pca, fig.to_html(include_plotlyjs=True))

    # ── Tableau des paires ──────────────────────────────────────────────────

    def _export_pairs_csv(self):
        """Enregistre toutes les paires dans un fichier CSV ou Excel."""
        if self._result is None or not self._result.get("pairs"):
            return

        manip = self._get_manip_name() or "paires"
        default_name = (
            sanitize_filename(f"{manip}_paires.csv") if manip else "paires.csv"
        )

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter les paires candidates",
            default_name,
            "CSV séparateur point-virgule (*.csv);;Excel (*.xlsx)",
        )
        if not path:
            return

        pairs = self._result["pairs"]
        df = pd.DataFrame(
            [
                {
                    "Rang": i + 1,
                    "Pic A (cm-1)": p["peak_A"],
                    "Pic B (cm-1)": p["peak_B"],
                    "rho (signe)": round(p["corr"], 4),
                    "|rho|": round(p["abs_corr"], 4),
                }
                for i, p in enumerate(pairs)
            ]
        )

        try:
            if path.endswith(".xlsx"):
                df.to_excel(path, index=False)
            else:
                df.to_csv(path, index=False, sep=";")
            QMessageBox.information(
                self, "Export réussi", f"Tableau exporté :\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Erreur export", str(e))

    def _copy_table_selection(self):
        """Copie les lignes sélectionnées dans le presse-papiers (format TSV)."""
        from PySide6.QtWidgets import QApplication

        selected_rows = sorted(
            {idx.row() for idx in self.table_pairs.selectedIndexes()}
        )
        if not selected_rows:
            return

        n_cols = self.table_pairs.columnCount()
        # En-têtes
        headers = [
            self.table_pairs.horizontalHeaderItem(c).text() for c in range(n_cols)
        ]
        lines = ["\t".join(headers)]
        for row in selected_rows:
            cells = []
            for col in range(n_cols):
                item = self.table_pairs.item(row, col)
                cells.append(item.text() if item else "")
            lines.append("\t".join(cells))

        QApplication.clipboard().setText("\n".join(lines))

    # ── PCA libre ───────────────────────────────────────────────────────────

    def _populate_pca_libre_combos(self):
        """Peuple cmb_color et cmb_spec_recon après une analyse."""
        meta_v = self._meta_v
        # cmb_color : toutes les colonnes méta disponibles
        old_color = self.cmb_color.currentText()
        self.cmb_color.blockSignals(True)
        self.cmb_color.clear()
        skip = {
            "Raman Shift",
            "Intensity",
            "Intensity_corrected",
            "Dark Subtracted #1"}
        candidates = []
        if meta_v is not None:
            for col in meta_v.columns:
                if col not in skip:
                    candidates.append(col)
        if not candidates:
            candidates = ["(aucune)"]
        self.cmb_color.addItems(candidates)
        idx = self.cmb_color.findText(old_color)
        if idx >= 0:
            self.cmb_color.setCurrentIndex(idx)
        self.cmb_color.blockSignals(False)
        self.cmb_color.setEnabled(True)

        # cmb_spec_recon
        self.cmb_spec_recon.blockSignals(True)
        self.cmb_spec_recon.clear()
        if self._ids_v is not None:
            self.cmb_spec_recon.addItems([str(s) for s in self._ids_v])
        self.cmb_spec_recon.setEnabled(True)
        self.cmb_spec_recon.blockSignals(False)

    def _run_pca_libre(self):
        """Lance la PCA libre et peuple les 3 sous-onglets Scores/Loadings/Reconstruction."""
        if self._X_proc is None:
            return
        X = self._X_proc
        wn = self._wavenumbers_proc
        ids = self._ids_v
        meta = self._meta_v

        n_comp = min(
            self.spin_n_comp_libre.value(),
            X.shape[0] - 1,
            X.shape[1])
        pca = PCA(n_components=n_comp)
        scores = pca.fit_transform(X)
        loadings = pca.components_
        ev_ratio = pca.explained_variance_ratio_

        self._pca_libre_pca = pca
        self._pca_libre_scores = scores
        self._pca_libre_loadings = loadings
        self._pca_libre_ev_ratio = ev_ratio

        self._plot_pca_scores(scores, ev_ratio, ids, meta)
        self._plot_pca_loadings(loadings, wn, ev_ratio)
        self._plot_pca_recon(pca, X, wn, ids, spec_idx=0)

    def _on_color_changed(self, _idx):
        """Re-trace les scores avec la nouvelle couleur."""
        if self._pca_libre_scores is None or self._meta_v is None:
            return
        self._plot_pca_scores(
            self._pca_libre_scores, self._pca_libre_ev_ratio, self._ids_v, self._meta_v
        )

    def _on_spec_recon_changed(self, idx):
        """Re-trace la reconstruction pour le spectre sélectionné."""
        if self._pca_libre_pca is None or self._X_proc is None:
            return
        self._plot_pca_recon(
            self._pca_libre_pca,
            self._X_proc,
            self._wavenumbers_proc,
            self._ids_v,
            spec_idx=idx,
        )

    def _plot_pca_scores(self, scores, ev_ratio, ids, meta):
        """Scatter PC1 vs PC2 colorié par la colonne choisie dans cmb_color."""
        color_col = self.cmb_color.currentText()
        pc1 = scores[:, 0]
        pc2 = scores[:, 1]
        n_comp = scores.shape[1]
        pc_labels = [
            f"PC{
                k +
                1} ({
                ev_ratio[k] *
                100:.1f}%)" for k in range(n_comp)]

        color_vals = None
        color_title = color_col
        if meta is not None and color_col in meta.columns:
            raw = meta[color_col]
            num = pd.to_numeric(raw, errors="coerce")
            if num.notna().any():
                color_vals = num.fillna(0).to_numpy(dtype=float)
            else:
                color_vals = raw.fillna("").astype(str).tolist()

        fig = go.Figure()
        id_texts = (
            [str(s) for s in ids]
            if ids is not None
            else [str(i) for i in range(len(pc1))]
        )

        if color_vals is None or (
            isinstance(color_vals, list)
            and (not color_vals or isinstance(color_vals[0], str))
        ):
            # Catégoriel ou pas de couleur
            unique_cats = (
                list(dict.fromkeys(color_vals)) if color_vals is not None else []
            )
            palette = [
                "#e74c3c",
                "#3498db",
                "#2ecc71",
                "#f39c12",
                "#9b59b6",
                "#1abc9c",
                "#e67e22",
                "#34495e",
                "#e91e63",
                "#00bcd4",
            ]
            cat_color_map = {
                c: palette[i % len(palette)] for i, c in enumerate(unique_cats)
            }
            if color_vals is not None:
                for cat in unique_cats:
                    mask = [v == cat for v in color_vals]
                    fig.add_trace(
                        go.Scatter(
                            x=pc1[mask],
                            y=pc2[mask],
                            mode="markers",
                            name=str(cat),
                            marker=dict(size=10, color=cat_color_map[cat]),
                            text=[t for t, m in zip(id_texts, mask) if m],
                            hovertemplate="%{text}<br>PC1=%{x:.3f}<br>PC2=%{y:.3f}<extra></extra>",
                        )
                    )
            else:
                fig.add_trace(
                    go.Scatter(
                        x=pc1,
                        y=pc2,
                        mode="markers",
                        marker=dict(size=10),
                        text=id_texts,
                        hovertemplate="%{text}<br>PC1=%{x:.3f}<br>PC2=%{y:.3f}<extra></extra>",
                    )
                )
        else:
            fig.add_trace(
                go.Scatter(
                    x=pc1,
                    y=pc2,
                    mode="markers",
                    marker=dict(
                        size=10,
                        color=color_vals,
                        colorscale="Viridis",
                        showscale=True,
                        colorbar=dict(title=color_title),
                    ),
                    text=id_texts,
                    hovertemplate=(
                        "%{text}<br>PC1=%{x:.3f}<br>PC2=%{y:.3f}<br>"
                        + color_title
                        + "=%{marker.color:.3e}<extra></extra>"
                    ),
                )
            )

        fig.update_layout(
            title="PCA libre — Scores PC1 vs PC2",
            xaxis_title=pc_labels[0],
            yaxis_title=pc_labels[1],
            width=1200,
            height=560,
        )

        manip = self._get_manip_name()
        fb = sanitize_filename(
            f"{manip}_PCA_Scores") if manip else "PCA_Scores"
        set_plotly_filename(self.view_pca_scores, fb)
        self.view_pca_scores._plotly_fig = fig
        load_plotly_html(
            self.view_pca_scores, fig.to_html(
                include_plotlyjs=True))

    def _plot_pca_loadings(self, loadings, wn, ev_ratio):
        """Courbes des loadings pour toutes les composantes (les premières visibles)."""
        n_comp = loadings.shape[0]
        palette = [
            "#e74c3c",
            "#3498db",
            "#2ecc71",
            "#f39c12",
            "#9b59b6",
            "#1abc9c",
            "#e67e22",
            "#34495e",
            "#e91e63",
            "#00bcd4",
            "#8bc34a",
            "#ff5722",
            "#607d8b",
            "#795548",
            "#ffeb3b",
        ]
        fig = go.Figure()
        for k in range(n_comp):
            fig.add_trace(
                go.Scatter(
                    x=wn,
                    y=loadings[k],
                    mode="lines",
                    name=f"PC{k + 1} ({ev_ratio[k] * 100:.1f}%)",
                    line=dict(color=palette[k % len(palette)], width=1.5),
                    visible=True if k < 3 else "legendonly",
                )
            )
        fig.add_hline(y=0, line_color="gray", line_width=0.5)
        fig.update_layout(
            title="PCA libre — Loadings (PC1-3 visibles, autres dans la légende)",
            xaxis_title="Raman Shift (cm⁻¹)",
            yaxis_title="Loading",
            width=1200,
            height=560,
            legend=dict(title="Composante"),
        )
        manip = self._get_manip_name()
        fb = sanitize_filename(
            f"{manip}_PCA_Loadings") if manip else "PCA_Loadings"
        set_plotly_filename(self.view_pca_loadings, fb)
        self.view_pca_loadings._plotly_fig = fig
        load_plotly_html(
            self.view_pca_loadings,
            fig.to_html(
                include_plotlyjs=True))

    def _plot_pca_recon(self, pca, X, wn, ids, spec_idx=0):
        """Spectre original vs reconstruit (résidu en option) pour le spectre sélectionné."""
        if X is None or len(X) == 0:
            return
        spec_idx = max(0, min(spec_idx, X.shape[0] - 1))
        X_recon = pca.inverse_transform(pca.transform(X))
        orig = X[spec_idx]
        recon = X_recon[spec_idx]
        spec_name = str(
            ids[spec_idx]) if ids is not None else f"Spectre {spec_idx}"
        n_comp = pca.n_components_
        cum_var = float(np.sum(pca.explained_variance_ratio_)) * 100

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=wn,
                y=orig,
                mode="lines",
                name="Original",
                line=dict(color="#2c3e50", width=1.5),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=wn,
                y=recon,
                mode="lines",
                name=f"Reconstruit ({n_comp} PC, {cum_var:.1f}% var.)",
                line=dict(color="#e74c3c", width=1.5, dash="dash"),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=wn,
                y=orig - recon,
                mode="lines",
                name="Résidu",
                line=dict(color="#95a5a6", width=1),
                visible="legendonly",
            )
        )
        fig.update_layout(
            title=f"PCA libre — Reconstruction : {spec_name}",
            xaxis_title="Raman Shift (cm⁻¹)",
            yaxis_title="Intensité (normalisée)",
            width=1200,
            height=560,
        )
        manip = self._get_manip_name()
        fb = (
            sanitize_filename(f"{manip}_PCA_Reconstruction")
            if manip
            else "PCA_Reconstruction"
        )
        set_plotly_filename(self.view_pca_recon, fb)
        self.view_pca_recon._plotly_fig = fig
        load_plotly_html(
            self.view_pca_recon, fig.to_html(
                include_plotlyjs=True))

    # ── Utilitaires ─────────────────────────────────────────────────────────

    def _get_manip_name(self) -> str | None:
        md = self._metadata_creator
        if md is not None and hasattr(md, "edit_manip"):
            return md.edit_manip.text().strip() or None
        return None
