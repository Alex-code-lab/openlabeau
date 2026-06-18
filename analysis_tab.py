from __future__ import annotations

import itertools
import os
from typing import List, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from PySide6.QtCore import Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from scipy.optimize import curve_fit

from data_processing import load_combined_df
from plotly_downloads import (
    install_plotly_download_handler,
    load_plotly_html,
    sanitize_filename,
    set_plotly_filename,
)


class AnalysisTab(QWidget):
    analysis_status_changed = Signal(bool)

    """
    Onglet Analyse – utilise le fichier combiné créé dans l'onglet Métadonnées
    pour extraire les intensités au voisinage de pics d'intérêt et calculer
    les rapports d'intensité.

    ➜ Ici, on reconstruit le fichier combiné à partir des spectres .txt sélectionnés
    et des tableaux créés dans `MetadataCreatorWidget` (onglet Métadonnées).
    """

    def __init__(self, file_picker, metadata_creator, parent=None):
        super().__init__(parent)
        self._file_picker = file_picker
        self._metadata_creator = metadata_creator
        self._combined_df: Optional[pd.DataFrame] = None
        self._peaks: List[int] = []
        # paires pré-enregistrées (si preset fixe)
        self._pairs: List[tuple] = []
        self._peak_intensities: Optional[pd.DataFrame] = None
        self._ratios_long: Optional[pd.DataFrame] = None
        # Indique que l'analyse doit être (re)lancée (données ou paramètres
        # modifiés)
        self._analysis_dirty: bool = True
        self._analysis_done = False
        self._sigmoid_params = None  # (A, B, k, x_eq)
        self._sigmoid_cov = None
        self._sigmoid_results = {}  # ratio_name -> {"params": popt, "cov": pcov}

        # --- UI ---
        layout = QVBoxLayout(self)

        header = QLabel(
            "<b>Analyse de pics</b><br>\n"
            "Cette page reconstruit automatiquement les données à partir des fichiers Raman sélectionnés et des métadonnées chargées."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        # état (fichier combiné présent / absent)
        self.lbl_status = QLabel(
            "Données combinées : chargement automatique lors de l'analyse"
        )
        layout.addWidget(self.lbl_status)

        # Options d'analyse (présets de pics + tolérance)
        opts = QHBoxLayout()
        opts.addWidget(QLabel("Longueur d'onde du spectromètre :"))
        self.cmb_presets = QComboBox(self)
        self.cmb_presets.addItems(
            [
                "532 nm — paires pré-enregistrées",
                "785 nm (412,444,471,547,1561)",
                "Personnalisé",
            ]
        )
        self.cmb_presets.currentIndexChanged.connect(self._on_preset_changed)
        opts.addWidget(self.cmb_presets)

        # Paramètres pour mode personnalisé
        opts.addWidget(QLabel("Laser (nm) :"))
        self.spin_laser_nm = QDoubleSpinBox(self)
        self.spin_laser_nm.setRange(0.0, 2000.0)
        self.spin_laser_nm.setDecimals(2)
        self.spin_laser_nm.setSingleStep(1.0)
        self.spin_laser_nm.setValue(532.0)
        self.spin_laser_nm.setEnabled(False)
        opts.addWidget(self.spin_laser_nm)

        opts.addWidget(
            QLabel("Pics à étudier (Raman Shift en cm⁻¹, séparés par des virgules) :")
        )
        self.edit_custom_waves = QLineEdit(self)
        self.edit_custom_waves.setPlaceholderText("ex : 1231, 1327, 1450")
        self.edit_custom_waves.setEnabled(False)
        opts.addWidget(self.edit_custom_waves)

        opts.addSpacerItem(
            QSpacerItem(20, 10, QSizePolicy.Expanding, QSizePolicy.Minimum)
        )
        opts.addWidget(QLabel("Tolérance (cm⁻¹) :"))
        self.spin_tol = QDoubleSpinBox(self)
        self.spin_tol.setDecimals(2)
        self.spin_tol.setRange(0.0, 50.0)
        self.spin_tol.setSingleStep(0.1)
        self.spin_tol.setValue(5.0)
        opts.addWidget(self.spin_tol)
        layout.addLayout(opts)

        # Boutons d'action
        actions = QHBoxLayout()
        self.btn_analyze = QPushButton("Analyser les pics", self)
        self.btn_export = QPushButton("Exporter résultats (Excel)…", self)
        self.btn_export.setEnabled(False)
        self.btn_analyze.clicked.connect(self._run_analysis)
        self.btn_export.clicked.connect(self._export_results)
        # Tout changement de paramètres d'analyse => il faudra relancer
        # l'analyse
        self.spin_tol.valueChanged.connect(self._on_analysis_param_changed)
        self.cmb_presets.currentIndexChanged.connect(
            self._on_analysis_param_changed)
        if hasattr(self, "spin_laser_nm"):
            self.spin_laser_nm.valueChanged.connect(
                self._on_analysis_param_changed)
        if hasattr(self, "edit_custom_waves"):
            self.edit_custom_waves.textChanged.connect(
                self._on_analysis_param_changed)
        actions.addWidget(self.btn_analyze)
        actions.addWidget(self.btn_export)
        layout.addLayout(actions)

        # Bouton pour afficher / masquer le tableau des intensités
        self.btn_toggle_table = QPushButton(
            "Afficher le tableau des intensités", self)
        self.btn_toggle_table.clicked.connect(self._toggle_table_visibility)
        layout.addWidget(self.btn_toggle_table)

        # Aperçu des résultats (table des intensités de pics)
        self.lbl_table_title = QLabel("<b>Aperçu – Intensités extraites</b>")
        layout.addWidget(self.lbl_table_title)
        self.table = QTableWidget(self)
        # Configuration pour navigation sur tout le fichier
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        layout.addWidget(self.table, 0)

        # Masquer la table et son titre par défaut pour laisser plus de place
        # au graphique
        self.lbl_table_title.setVisible(False)
        self.table.setVisible(False)

        # Graphique des ratios
        graph_header = QHBoxLayout()
        graph_header.addWidget(
            QLabel(
                "<b>Graphique – Rapports d’intensité Raman selon [titrant]</b>")
        )
        graph_header.addStretch()
        self.btn_save_graph = QPushButton("Enregistrer le graphique…", self)
        self.btn_save_graph.setEnabled(False)
        self.btn_save_graph.clicked.connect(self._save_graph)
        graph_header.addWidget(self.btn_save_graph)
        layout.addLayout(graph_header)
        self.plot_view = QWebEngineView(self)
        install_plotly_download_handler(self.plot_view)
        layout.addWidget(self.plot_view, 1)

        # --- Fit sigmoïde (équivalence) ---
        fit_layout = QHBoxLayout()

        fit_layout.addWidget(QLabel("Ajuster le ratio de longueur d'onde :"))
        self.cmb_fit_ratio = QComboBox(self)
        fit_layout.addWidget(self.cmb_fit_ratio)

        self.btn_fit_sigmoid = QPushButton(
            "Ajustement mathématique de la courbe", self)
        self.btn_fit_sigmoid.clicked.connect(self._fit_sigmoid)
        fit_layout.addWidget(self.btn_fit_sigmoid)

        self.btn_show_equivalence = QPushButton("Afficher l'équivalence", self)
        self.btn_show_equivalence.clicked.connect(self._show_equivalence)
        self.btn_show_equivalence.setEnabled(False)
        fit_layout.addWidget(self.btn_show_equivalence)

        layout.addLayout(fit_layout)

        # Init valeurs
        self._on_preset_changed(self.cmb_presets.currentIndex())
        # Figure Plotly actuellement affichée (pour overlay fit)
        self._current_fig = None  # figure Plotly actuellement affichée
        self._base_x_range = (
            # plage X de la courbe initiale (pour la conserver lors des fits)
            None
        )
        # Couleurs initiales des boutons
        self._refresh_button_states()

    @staticmethod
    def _sigmoid(x, A, B, k, x_eq):
        return A + B / (1 + np.exp(-k * (x - x_eq)))

    def _get_manip_name(self) -> str | None:
        md = self._metadata_creator
        if md is not None and hasattr(md, "edit_manip"):
            return md.edit_manip.text().strip() or None
        return None

    def _fit_sigmoid(self):
        if self._ratios_long is None or self._ratios_long.empty:
            QMessageBox.warning(
                self, "Aucune donnée", "Aucun ratio disponible pour le fit."
            )
            return

        if self._current_fig is None:
            QMessageBox.warning(
                self,
                "Graphique manquant",
                "Aucun graphique n'est actuellement affiché.",
            )
            return

        ratio_name = self.cmb_fit_ratio.currentText()
        if not ratio_name:
            QMessageBox.warning(
                self, "Ratio manquant", "Veuillez sélectionner un ratio à ajuster."
            )
            return

        # ========== 1) Sécuriser la sélection des données (tri + copie) ======
        df = (
            self._ratios_long[self._ratios_long["Ratio"] == ratio_name]
            .dropna(subset=["n(titrant) (mol)", "Value"])
            .sort_values("n(titrant) (mol)")
            .copy()
        )

        if len(df) < 5:
            QMessageBox.warning(
                self,
                "Données insuffisantes",
                "Pas assez de points pour un fit sigmoïde.",
            )
            return

        x = df["n(titrant) (mol)"].to_numpy(dtype=float)
        y = df["Value"].to_numpy(dtype=float)
        x_min = float(np.nanmin(x))
        x_max = float(np.nanmax(x))
        x_span = x_max - x_min
        if (not np.isfinite(x_span)) or x_span <= 0:
            x_span = max(1.0, abs(x_min) if np.isfinite(x_min) else 1.0)
        x_center = 0.5 * (x_min + x_max)
        x_scale = x_span if x_span > 0 else 1.0
        y_min = float(np.nanmin(y))
        y_max = float(np.nanmax(y))
        y_span = y_max - y_min
        if (not np.isfinite(y_span)) or y_span <= 0:
            QMessageBox.warning(
                self,
                "Données insuffisantes",
                "Les valeurs du ratio sont quasi constantes, le fit sigmoïde est indéterminé.",
            )
            return

        fig = self._current_fig

        # ========== 2) Supprimer les anciens fits / points du même ratio =====
        # Supprimer les anciens fits / annotations pour ce ratio
        fig.data = tuple(
            tr
            for tr in fig.data
            if not (
                isinstance(tr.name, str)
                and (
                    f"Fit sigmoïde – {ratio_name}" in tr.name
                    or f"Points utilisés – {ratio_name}" in tr.name
                    or f"Équivalence – {ratio_name}" in tr.name
                )
            )
        )
        # Supprimer les annotations liées à ce ratio
        if hasattr(fig.layout, "annotations") and fig.layout.annotations:
            fig.layout.annotations = tuple(
                ann
                for ann in fig.layout.annotations
                if ratio_name not in str(getattr(ann, "text", ""))
            )

        # ========== 3) Afficher explicitement les points utilisés pour le fit
        # Affichage explicite des points utilisés pour le fit (debug visuel)
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="markers",
                marker=dict(size=10, symbol="x"),
                name=f"Points utilisés – {ratio_name}",
            )
        )

        # ========== 4) (Option sécurité) Forcer un refit réel même si données
        # Sécurité : conversion explicite en float64 pour éviter tout cache
        # implicite
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)

        # Estimations initiales (espace normalisé pour stabiliser le fit)
        A0 = y_min
        B0 = y_span
        corr = np.corrcoef(x, y)[0, 1] if len(x) > 1 else 1.0
        sign = -1.0 if (np.isfinite(corr) and corr < 0) else 1.0
        k0 = sign * 8.0
        y_mid = A0 + 0.5 * B0
        try:
            idx_mid = int(np.nanargmin(np.abs(y - y_mid)))
            xeq0 = float((x[idx_mid] - x_center) / x_scale)
        except Exception:
            xeq0 = 0.0

        def _sigmoid_scaled(x_scaled, A, B, k, x_eq_scaled):
            return A + B / (1 + np.exp(-k * (x_scaled - x_eq_scaled)))

        try:
            popt_scaled, pcov_scaled = curve_fit(
                _sigmoid_scaled,
                (x - x_center) / x_scale,
                y,
                p0=[A0, B0, k0, xeq0],
                maxfev=20000,
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Échec du fit", f"Impossible d'ajuster la sigmoïde :\n{e}"
            )
            return

        k_orig = float(popt_scaled[2]) / x_scale
        x_eq_orig = x_center + x_scale * float(popt_scaled[3])
        popt = np.array(
            [popt_scaled[0], popt_scaled[1], k_orig, x_eq_orig], dtype=float
        )
        if pcov_scaled is not None:
            scale = np.diag([1.0, 1.0, 1.0 / x_scale, x_scale])
            pcov = scale @ pcov_scaled @ scale
        else:
            pcov = None

        self._sigmoid_params = popt
        self._sigmoid_cov = pcov
        self.btn_show_equivalence.setEnabled(True)
        # Enregistrer le résultat du fit par ratio
        self._sigmoid_results[ratio_name] = {"params": popt, "cov": pcov}

        # -------- Courbe de fit avec plage étendue pour afficher toute la sigm
        # Point d’équivalence (point d’inflexion) : coordonnées exactes
        x_eq = float(popt[3])
        y_eq = self._sigmoid(x_eq, *popt)
        k = float(popt[2])
        if np.isfinite(k) and k != 0:
            half_span_k = 6.0 / abs(k)  # ~de 0.25% à 99.75%
        else:
            half_span_k = 0.0
        half_span = max(x_span, half_span_k)
        if (not np.isfinite(half_span)) or half_span <= 0:
            half_span = max(1.0, abs(x_eq) if np.isfinite(x_eq) else 1.0)

        x_fit_min = min(x_min, x_eq - half_span)
        x_fit_max = max(x_max, x_eq + half_span)
        x_fit = np.linspace(x_fit_min, x_fit_max, 1000)
        y_fit = self._sigmoid(x_fit, *popt)

        # -------- Ajout du point d'équivalence (croix) --------

        # Courbe de fit
        fig.add_trace(
            go.Scatter(
                x=x_fit,
                y=y_fit,
                mode="lines",
                name=f"Fit sigmoïde – {ratio_name}",
                line=dict(dash="dash", width=3),
            )
        )

        # Marqueur du point d’équivalence (croix)
        fig.add_trace(
            go.Scatter(
                x=[x_eq],
                y=[y_eq],
                mode="markers",
                name=f"Équivalence – {ratio_name}",
                marker=dict(
                    symbol="x",
                    size=14,
                    color="red",
                    line=dict(
                        width=3)),
            )
        )

        # Ligne verticale équivalence (sans annotation automatique)
        fig.add_vline(
            x=x_eq,
            line_dash="dot",
            line_color="red",
        )

        # Annotation lisible empilée verticalement (coordonnées papier)
        n_annot = len(self._sigmoid_results)  # 1, 2, 3...
        y_paper = 1.0 - 0.06 * (n_annot - 1)
        if y_paper < 0.05:
            y_paper = 0.05

        fig.add_annotation(
            x=x_eq,
            y=y_paper,
            xref="x",
            yref="paper",
            text=f"Équiv. {ratio_name} : {x_eq:.3e}",
            showarrow=False,
            xanchor="left",
            bgcolor="rgba(255,255,255,0.85)",
            bordercolor="rgba(0,0,0,0.25)",
            borderwidth=1,
        )

        if self._base_x_range is not None:
            fig.update_xaxes(range=list(self._base_x_range), autorange=False)

        # Conserver le nom de fichier attendu même après ajout des fits
        manip_name = self._get_manip_name()
        if manip_name:
            file_base = f"{manip_name}_Rapport_Intensite"
        else:
            file_base = "Rapport_Intensite"
        set_plotly_filename(self.plot_view, file_base)
        self.plot_view._plotly_fig = fig
        config = {
            "toImageButtonOptions": {
                "filename": sanitize_filename(file_base) or "Rapport_Intensite"
            }
        }
        load_plotly_html(
            self.plot_view, fig.to_html(include_plotlyjs=True, config=config)
        )

    def _show_equivalence(self):
        if not getattr(self, "_sigmoid_results", None):
            QMessageBox.information(
                self,
                "Aucune équivalence",
                "Aucun fit sigmoïde n’a encore été effectué.",
            )
            return

        lines = ["Points d’équivalence (points d’inflexion) :\n"]
        for ratio_name, res in self._sigmoid_results.items():
            popt = res.get("params")
            pcov = res.get("cov")
            if popt is None:
                continue

            x_eq = float(popt[3])

            if pcov is not None:
                try:
                    err = np.sqrt(np.diag(pcov))
                    xeq_err = float(err[3])
                    lines.append(
                        f"• {ratio_name} : x_eq = {
                            x_eq:.3e} ± {
                            xeq_err:.1e} mol"
                    )
                except Exception:
                    lines.append(f"• {ratio_name} : x_eq = {x_eq:.3e} mol")
            else:
                lines.append(f"• {ratio_name} : x_eq = {x_eq:.3e} mol")

        QMessageBox.information(self, "Équivalences", "\n".join(lines))

    def _refresh_button_states(self) -> None:
        """Met à jour la couleur des boutons selon l'état du fichier combiné et de l'analyse."""
        red = "background-color: #d9534f; color: white; font-weight: 600;"
        green = "background-color: #5cb85c; color: white; font-weight: 600;"

        combined_ready = (
            self._combined_df is not None
            and isinstance(self._combined_df, pd.DataFrame)
            and not self._combined_df.empty
        )

        analysis_ready = (
            combined_ready
            and (self._analysis_dirty is False)
            and (self._ratios_long is not None)
            and isinstance(self._ratios_long, pd.DataFrame)
            and (not self._ratios_long.empty)
        )

        # Bouton analyse : vert seulement si l'analyse a été faite et est à
        # jour
        self.btn_analyze.setStyleSheet(green if analysis_ready else red)
        self.btn_analyze.setToolTip(
            "Vert = analyse à jour"
            if analysis_ready
            else (
                "Rouge = lancez ou relancez l'analyse ; les données seront chargées automatiquement"
            )
        )
        if getattr(self, "_analysis_done", None) != analysis_ready:
            self._analysis_done = analysis_ready
            self.analysis_status_changed.emit(analysis_ready)

    def _on_analysis_param_changed(self, *args) -> None:
        """Marque l'analyse comme à relancer si un paramètre change."""
        self._analysis_dirty = True
        self._refresh_button_states()

    def mark_analysis_stale(self) -> None:
        self._analysis_dirty = True
        self._refresh_button_states()

    # ---------- Helpers ----------
    def _on_preset_changed(self, idx: int):
        """
        Met à jour la liste des pics en fonction du preset sélectionné.

        idx = 0 : preset 532 nm
        idx = 1 : preset 785 nm
        idx = 2 : mode personnalisé (défini par l'utilisateur)
        """
        if idx == 0:
            # 532 nm – paires pré-enregistrées
            self._pairs = [
                (1364, 1538),
                (1364, 1409),
                (1364, 1500),
                (1361, 1631),
                (1364, 1580),
                (1234, 1256),
            ]
            # Extraire les pics uniques nécessaires pour ces paires
            self._peaks = sorted({p for pair in self._pairs for p in pair})
            # Désactiver les champs personnalisés
            if hasattr(self, "spin_laser_nm"):
                self.spin_laser_nm.setEnabled(False)
            if hasattr(self, "edit_custom_waves"):
                self.edit_custom_waves.setEnabled(False)
        elif idx == 1:
            # 785 nm – jeu de pics par défaut
            self._pairs = []
            self._peaks = [412, 444, 471, 547, 1561]
            # Désactiver les champs personnalisés
            if hasattr(self, "spin_laser_nm"):
                self.spin_laser_nm.setEnabled(False)
            if hasattr(self, "edit_custom_waves"):
                self.edit_custom_waves.setEnabled(False)
        else:
            # Mode personnalisé : on laisse _peaks vide ici,
            # il sera calculé dans _run_analysis à partir des λ fournies.
            self._pairs = []
            self._peaks = []
            # Activer les champs personnalisés
            if hasattr(self, "spin_laser_nm"):
                self.spin_laser_nm.setEnabled(True)
            if hasattr(self, "edit_custom_waves"):
                self.edit_custom_waves.setEnabled(True)

    def _reload_combined(self) -> bool:
        """Reconstruit le DataFrame combiné à partir des métadonnées et fichiers .txt."""
        combined = load_combined_df(
            self, self._file_picker, self._metadata_creator)
        self._analysis_dirty = True
        self._peak_intensities = None
        self._ratios_long = None
        self.btn_export.setEnabled(False)
        self.btn_save_graph.setEnabled(False)
        if combined is None:
            self._combined_df = None
            self.lbl_status.setText("Données combinées : non chargées ✗")
            self._refresh_button_states()
            return False
        else:
            self._combined_df = combined
            self.lbl_status.setText(
                "Données combinées : chargées automatiquement ✓")
        self._refresh_button_states()
        return True

    def _set_preview(
        self, df: pd.DataFrame, n: int = 20
    ):  # n conservé pour compat, ignoré ici
        # Afficher TOUT le DataFrame avec défilement et tri
        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setRowCount(len(df))
        self.table.setColumnCount(len(df.columns))
        self.table.setHorizontalHeaderLabels([str(c) for c in df.columns])
        for i in range(len(df)):
            for j, col in enumerate(df.columns):
                self.table.setItem(i, j, QTableWidgetItem(str(df.iloc[i, j])))
        # Ajuster les largeurs de colonnes au contenu
        self.table.resizeColumnsToContents()
        self.table.setSortingEnabled(True)

    def _toggle_table_visibility(self):
        """Affiche ou masque le tableau des intensités pour laisser plus de place au graphique."""
        is_visible = self.table.isVisible()
        # Bascule visibilité
        self.table.setVisible(not is_visible)
        if hasattr(self, "lbl_table_title"):
            self.lbl_table_title.setVisible(not is_visible)
        # Met à jour le texte du bouton
        if not is_visible:
            self.btn_toggle_table.setText("Masquer le tableau des intensités")
        else:
            self.btn_toggle_table.setText("Afficher le tableau des intensités")

    # ---------- Analyse ----------
    def _run_analysis(self):
        if not self._reload_combined():
            return

        # On travaille sur une copie locale pour ne pas modifier le fichier
        # combiné global
        df = self._combined_df.copy()

        required = {"Raman Shift", "Intensity_corrected", "file"}
        if not required.issubset(df.columns):
            QMessageBox.critical(
                self,
                "Colonnes manquantes",
                "Le fichier combiné doit contenir : Raman Shift, Intensity_corrected, file.",
            )
            return

        # Exclure de l'analyse les spectres dont le nom se termine par BI ou BR,
        # mais conserver ceux qui se terminent par BRB.
        # On utilise 'Spectrum name' si disponible.
        if "Spectrum name" in df.columns:
            sn = df["Spectrum name"].astype(str)
            mask_bi_br = sn.str.match(r".*(BI|BR)$")
            mask_brb = sn.str.endswith("BRB")
            # garder tout ce qui n'est pas BI/BR, ou qui est BRB
            df = df[~mask_bi_br | mask_brb].copy()

        # Si mode "Personnalisé" : interpréter directement la saisie comme des
        # décalages Raman (cm⁻¹)
        if self.cmb_presets.currentIndex() == 2:
            text = (
                self.edit_custom_waves.text()
                if hasattr(self, "edit_custom_waves")
                else ""
            )
            if not text.strip():
                QMessageBox.warning(
                    self,
                    "Paramètre manquant",
                    "En mode personnalisé, veuillez saisir au moins un pic à étudier\n"
                    "(Raman Shift en cm⁻¹, séparés par des virgules).",
                )
                return

            # Parsing des valeurs en cm⁻¹
            raw_tokens = [
                t.strip() for t in text.replace(";", ",").split(",") if t.strip()
            ]
            custom_peaks = []
            for token in raw_tokens:
                token_clean = token.replace(",", ".")
                try:
                    rs = float(token_clean)
                    custom_peaks.append(int(round(rs)))
                except ValueError:
                    continue

            if not custom_peaks:
                QMessageBox.warning(
                    self,
                    "Paramètres invalides",
                    "Aucun Raman Shift valide n'a été trouvé dans le champ personnalisé.\n"
                    "Utilisez des valeurs numériques en cm⁻¹, séparées par des virgules.",
                )
                return

            self._peaks = custom_peaks

        peaks = self._peaks
        tol = float(self.spin_tol.value())

        # Calcul des intensités max autour de chaque pic, par fichier
        results: List[dict] = []
        for fname, group in df.groupby("file"):
            spectrum = group.sort_values("Raman Shift")
            record = {"file": fname}
            for target in peaks:
                window = spectrum[
                    (spectrum["Raman Shift"] >= target - tol)
                    & (spectrum["Raman Shift"] <= target + tol)
                ]
                if not window.empty:
                    record[f"I_{target}"] = float(
                        window["Intensity_corrected"].max())
                else:
                    record[f"I_{target}"] = np.nan
            results.append(record)

        peak_intensities = pd.DataFrame(results)

        # Calcul des ratios : paires pré-enregistrées si disponibles, sinon
        # toutes les combinaisons
        pair_list = (
            self._pairs if self._pairs else list(
                itertools.combinations(peaks, 2))
        )
        for a, b in pair_list:
            col_a, col_b = f"I_{a}", f"I_{b}"
            if col_a in peak_intensities.columns and col_b in peak_intensities.columns:
                peak_intensities[f"ratio_I_{a}_I_{b}"] = (
                    peak_intensities[col_a] / peak_intensities[col_b]
                )

        # Joindre aux métadonnées (si colonnes présentes)
        if "Spectrum name" not in peak_intensities.columns:
            peak_intensities["Spectrum name"] = peak_intensities["file"].str.replace(
                ".txt", "", regex=False
            )
        meta_cols = [
            c for c in df.columns if c not in {"Raman Shift", "Intensity_corrected"}
        ]
        metadata_df = (
            df[meta_cols].drop_duplicates(
                subset=["Spectrum name"], keep="first")
            if "Spectrum name" in df.columns
            else None
        )
        merged = (
            peak_intensities.merge(metadata_df, on="Spectrum name", how="left")
            if metadata_df is not None
            else peak_intensities.copy()
        )

        # Calcul strict de l'abscisse (règle métier) :
        # n(titrant) = C_final(Solution B) * V_cuvette(L)
        # où C_final(Solution B) est la concentration finale en cuvette issue
        # du tableau des volumes.
        def _to_num(s: pd.Series) -> pd.Series:
            return pd.to_numeric(
                s.astype(str).str.replace(",", "."), errors="coerce")

        def _norm_col_name(c: str) -> str:
            return (
                str(c)
                .strip()
                .lower()
                .replace("é", "e")
                .replace("è", "e")
                .replace("ê", "e")
                .replace("μ", "µ")
            )

        col_by_norm = {_norm_col_name(c): c for c in merged.columns}

        tit_col = None
        for key in ("solution b", "[titrant] (m)"):
            if key in col_by_norm:
                tit_col = col_by_norm[key]
                break

        if tit_col is None:
            QMessageBox.critical(
                self,
                "Données titrant manquantes",
                "Impossible de calculer l'axe X : colonne 'Solution B' (ou '[titrant] (M)') introuvable.",
            )
            return

        if "v cuvette (µl)" in col_by_norm:
            v_l = _to_num(merged[col_by_norm["v cuvette (µl)"]]) * 1e-6
        elif "v cuvette (ul)" in col_by_norm:
            v_l = _to_num(merged[col_by_norm["v cuvette (ul)"]]) * 1e-6
        elif "v cuvette (ml)" in col_by_norm:
            v_l = _to_num(merged[col_by_norm["v cuvette (ml)"]]) * 1e-3
        else:
            QMessageBox.critical(
                self,
                "Volume cuvette manquant",
                "Impossible de calculer l'axe X : colonne 'V cuvette (µL)' (ou mL) introuvable.",
            )
            return

        c = _to_num(merged[tit_col])
        merged["n(titrant) (mol)"] = c * v_l
        merged["titrant_column"] = tit_col

        if merged["n(titrant) (mol)"].notna().sum() == 0:
            QMessageBox.critical(
                self,
                "Calcul impossible",
                "La quantité de titrant n'a pas pu être calculée (valeurs non numériques pour 'Solution B' ou volume).",
            )
            return

        # Mise en forme long pour les ratios
        ratio_cols = [c for c in merged.columns if c.startswith("ratio_I_")]
        id_vars = [
            c
            for c in ["file", "Spectrum name", "Sample description", "n(titrant) (mol)"]
            if c in merged.columns
        ]
        df_ratios = (
            merged.melt(
                id_vars=id_vars,
                value_vars=ratio_cols,
                var_name="Ratio",
                value_name="Value",
            )
            if ratio_cols
            else None
        )

        # Mémoriser + aperçu
        self._peak_intensities = merged
        self._ratios_long = df_ratios
        self._set_preview(merged)
        self.btn_export.setEnabled(True)
        self.btn_save_graph.setEnabled(True)
        self._analysis_dirty = False
        self._refresh_button_states()
        # Réinitialiser état du fit sigmoïde
        self._sigmoid_params = None
        self._sigmoid_cov = None
        self.btn_show_equivalence.setEnabled(False)
        self._sigmoid_results = {}

        # --- Tracé interactif (équivalent au ggplot fourni) ---
        if (
            df_ratios is not None
            and not df_ratios.empty
            and "n(titrant) (mol)" in df_ratios.columns
        ):
            # Mettre à jour la liste des ratios disponibles pour le fit
            self.cmb_fit_ratio.blockSignals(True)
            self.cmb_fit_ratio.clear()
            for r in sorted(df_ratios["Ratio"].unique()):
                self.cmb_fit_ratio.addItem(r)
            self.cmb_fit_ratio.blockSignals(False)

            df_plot = df_ratios.sort_values(["Ratio", "n(titrant) (mol)"])

            # Palette de couleurs plus riche et contrastée pour éviter les répétitions trop rapides
            # On concatène plusieurs palettes qualitatives de Plotly pour avoir
            # plus de couleurs distinctes.
            color_seq = (
                px.colors.qualitative.Alphabet
                + px.colors.qualitative.Safe
                + px.colors.qualitative.Dark24
            )

            fig = px.line(
                df_plot,
                x="n(titrant) (mol)",
                y="Value",
                color="Ratio",
                markers=True,
                title="Rapports d’intensité Raman selon [titrant]",
                color_discrete_sequence=color_seq,
            )

            # Améliorer la lisibilité : courbes un peu plus épaisses, marqueurs plus visibles,
            # légende positionnée à droite.
            fig.update_traces(line=dict(width=2), marker=dict(size=6))
            fig.update_layout(
                xaxis_title="Quantité de titrant (mol)",
                yaxis_title="Rapport d’intensité (a.u.)",
                width=1200,
                height=800,
                legend_title_text="Ratio",
                legend=dict(
                    orientation="h",
                    x=0.5,
                    y=-0.12,
                    xanchor="center",
                    yanchor="top",
                    bordercolor="black",
                    borderwidth=1,
                    bgcolor="rgba(255,255,255,0.8)",
                    font=dict(size=10),
                    title=dict(font=dict(size=10)),
                ),
                margin=dict(t=60, b=220, l=80, r=20),
            )
            # Formatage type scientifique pour l'axe X (évite les libellés
            # doublons)
            fig.update_xaxes(tickformat=".2e")
            # Verrouiller la plage X sur la courbe initiale pour éviter tout
            # changement lors des fits
            x_vals = df_plot["n(titrant) (mol)"].to_numpy(dtype=float)
            if x_vals.size and np.isfinite(x_vals).any():
                x_min = float(np.nanmin(x_vals))
                x_max = float(np.nanmax(x_vals))
                if np.isfinite(x_min) and np.isfinite(x_max) and x_min < x_max:
                    self._base_x_range = (x_min, x_max)
                    fig.update_xaxes(range=[x_min, x_max], autorange=False)
                else:
                    self._base_x_range = None
            else:
                self._base_x_range = None
            self._current_fig = fig
            self.plot_view._plotly_fig = fig
            manip_name = self._get_manip_name()
            if manip_name:
                file_base = f"{manip_name}_Rapport_Intensite"
            else:
                file_base = "Rapport_Intensite"
            set_plotly_filename(self.plot_view, file_base)
            config = {
                "toImageButtonOptions": {
                    "filename": sanitize_filename(file_base) or "Rapport_Intensite"
                }
            }
            load_plotly_html(
                self.plot_view, fig.to_html(
                    include_plotlyjs=True, config=config)
            )
        else:
            # Effacer le graphique si pas de ratios
            self.plot_view._plotly_fig = None
            set_plotly_filename(self.plot_view, None)
            self.plot_view.setHtml("<i>Aucun ratio à afficher.</i>")
            self._base_x_range = None

        # (Suppression du reset du fit et de la combo des ratios ici -- déjà fait plus haut)

        QMessageBox.information(
            self, "Succès", "Analyse terminée : intensités et ratios calculés."
        )

    # ---------- Export ----------
    def _export_results(self):
        if self._peak_intensities is None or self._peak_intensities.empty:
            QMessageBox.warning(
                self,
                "Rien à exporter",
                "Lancez d'abord l'analyse.")
            return
        import datetime as _dt

        home = os.path.expanduser("~")
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(home, f"raman_analysis_{stamp}.xlsx")
        try:
            with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
                self._peak_intensities.to_excel(
                    writer, index=False, sheet_name="intensites"
                )
                if self._ratios_long is not None:
                    self._ratios_long.to_excel(
                        writer, index=False, sheet_name="ratios")
            QMessageBox.information(
                self, "Exporté", f"Résultats enregistrés :\n{out_path}"
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Échec export", f"Impossible d'enregistrer : {e}"
            )

    # Pixels à 150 dpi pour les formats papier standard (paysage / portrait)
    _EXPORT_PRESETS: dict[str, tuple[int, int]] = {
        "A4 paysage  (297×210 mm, 150 dpi)": (1748, 1240),
        "A4 portrait (210×297 mm, 150 dpi)": (1240, 1748),
        "A3 paysage  (420×297 mm, 150 dpi)": (2480, 1748),
        "A3 portrait (297×420 mm, 150 dpi)": (1748, 2480),
        "Écran large  (1920×1080)": (1920, 1080),
        "Carré HD    (1400×1400)": (1400, 1400),
        "Personnalisé…": (0, 0),
    }

    def _save_graph(self) -> None:
        """Ouvre un dialog de configuration puis enregistre le graphique.

        PNG et SVG utilisent Plotly.toImage via JavaScript (même moteur de rendu
        que l'affichage → résultat pixel-perfect).
        PDF utilise QWebEnginePage.printToPdf (rendu Qt identique à l'écran).
        """
        if self._current_fig is None:
            return

        # ── Dialog de configuration ──────────────────────────────────────────
        dlg = QDialog(self)
        dlg.setWindowTitle("Enregistrer le graphique")
        dlg_layout = QVBoxLayout(dlg)

        # Format de fichier
        grp_fmt = QGroupBox("Format de fichier")
        fmt_layout = QHBoxLayout(grp_fmt)
        btn_grp_fmt = QButtonGroup(dlg)
        rb_png = QRadioButton("PNG (haute résolution ×2)")
        rb_svg = QRadioButton("SVG (vectoriel)")
        rb_pdf = QRadioButton("PDF")
        rb_png.setChecked(True)
        for rb in (rb_png, rb_svg, rb_pdf):
            btn_grp_fmt.addButton(rb)
            fmt_layout.addWidget(rb)
        dlg_layout.addWidget(grp_fmt)

        # Taille de sortie (PNG / SVG uniquement — PDF utilise la taille du
        # graphique affiché)
        grp_size = QGroupBox("Taille de sortie  (PNG / SVG)")
        size_layout = QVBoxLayout(grp_size)
        cmb_preset = QComboBox()
        for label in self._EXPORT_PRESETS:
            cmb_preset.addItem(label)
        size_layout.addWidget(cmb_preset)

        custom_row = QHBoxLayout()
        lbl_w = QLabel("Largeur (px) :")
        spin_w = QSpinBox()
        spin_w.setRange(400, 8000)
        spin_w.setValue(1748)
        spin_w.setSingleStep(10)
        lbl_h = QLabel("Hauteur (px) :")
        spin_h = QSpinBox()
        spin_h.setRange(400, 8000)
        spin_h.setValue(1240)
        spin_h.setSingleStep(10)
        for widget in (lbl_w, spin_w, lbl_h, spin_h):
            custom_row.addWidget(widget)
        size_layout.addLayout(custom_row)
        dlg_layout.addWidget(grp_size)

        def _on_preset_changed(idx: int) -> None:
            label = cmb_preset.itemText(idx)
            pw, ph = self._EXPORT_PRESETS[label]
            is_custom = pw == 0
            for widget in (lbl_w, spin_w, lbl_h, spin_h):
                widget.setEnabled(is_custom)
            if not is_custom:
                spin_w.setValue(pw)
                spin_h.setValue(ph)

        def _on_fmt_changed() -> None:
            grp_size.setEnabled(not rb_pdf.isChecked())

        cmb_preset.currentIndexChanged.connect(_on_preset_changed)
        rb_pdf.toggled.connect(_on_fmt_changed)
        _on_preset_changed(0)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        dlg_layout.addWidget(buttons)

        if dlg.exec() != QDialog.Accepted:
            return

        export_w = spin_w.value()
        export_h = spin_h.value()
        if rb_png.isChecked():
            fmt, ext = "png", ".png"
        elif rb_svg.isChecked():
            fmt, ext = "svg", ".svg"
        else:
            fmt, ext = "pdf", ".pdf"

        # ── Choix du fichier ────────────────────────────────────────────────
        manip_name = self._get_manip_name() or "Rapport_Intensite"
        default_name = sanitize_filename(manip_name) + "_Rapport_Intensite"
        filter_str = {"png": "PNG (*.png)", "svg": "SVG (*.svg)", "pdf": "PDF (*.pdf)"}[
            fmt
        ]
        fname, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le graphique", default_name, filter_str
        )
        if not fname:
            return
        if not fname.lower().endswith(ext):
            fname += ext

        # ── Export ──────────────────────────────────────────────────────────
        if fmt == "pdf":
            self._save_graph_pdf(fname)
        else:
            self._save_graph_js(fname, fmt, export_w, export_h)

    def _save_graph_pdf(self, fname: str) -> None:
        """Exporte en PDF via Qt (rendu identique à l'affichage)."""
        try:
            from PySide6.QtCore import QMarginsF
            from PySide6.QtGui import QPageLayout, QPageSize

            layout = QPageLayout(
                QPageSize(QPageSize.PageSizeId.A4),
                QPageLayout.Orientation.Landscape,
                QMarginsF(10, 10, 10, 10),
            )
            self.plot_view.page().printToPdf(fname, layout)
            QMessageBox.information(
                self,
                "Graphique enregistré",
                f"PDF créé :\n{fname}\n\n"
                "(Le fichier sera écrit dans quelques secondes.)",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Échec PDF", str(exc))

    def _save_graph_js(self, fname: str, fmt: str,
                       width: int, height: int) -> None:
        """Lance l'export PNG/SVG via Plotly.toImage (JavaScript).

        Le résultat est récupéré de façon asynchrone via un timer de polling.
        """
        from PySide6.QtCore import QTimer

        scale = 2 if fmt == "png" else 1
        js = f"""
        (function() {{
            window._pexReady = false;
            window._pexData  = null;
            var gd = document.querySelector('.js-plotly-plot');
            if (!gd) {{
                window._pexData  = 'ERR:no_graph';
                window._pexReady = true;
                return;
            }}
            Plotly.toImage(gd, {{
                format: '{fmt}',
                width:  {width},
                height: {height},
                scale:  {scale}
            }}).then(function(dataUrl) {{
                window._pexData  = dataUrl;
                window._pexReady = true;
            }}).catch(function(e) {{
                window._pexData  = 'ERR:' + String(e);
                window._pexReady = true;
            }});
        }})();
        """
        self._js_export_fname = fname
        self._js_export_fmt = fmt
        self.plot_view.page().runJavaScript(js)

        if hasattr(self, "_js_poll") and self._js_poll.isActive():
            self._js_poll.stop()
        self._js_poll = QTimer(self)
        self._js_poll.setInterval(300)
        self._js_poll.timeout.connect(self._poll_js_export)
        self._js_poll.start()

    def _poll_js_export(self) -> None:
        self.plot_view.page().runJavaScript("!!window._pexReady", self._check_js_ready)

    def _check_js_ready(self, ready: bool) -> None:
        if not ready:
            return
        self._js_poll.stop()
        self.plot_view.page().runJavaScript("window._pexData", self._receive_js_export)

    def _receive_js_export(self, data_url: str) -> None:
        fname = self._js_export_fname
        fmt = self._js_export_fmt

        if not data_url or str(data_url).startswith("ERR"):
            QMessageBox.critical(
                self, "Erreur d'export", f"Plotly.toImage a échoué :\n{data_url}"
            )
            return

        try:
            header, payload = data_url.split(",", 1)
            if fmt == "svg":
                import urllib.parse

                svg_text = urllib.parse.unquote(payload)
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(svg_text)
            else:  # png
                import base64

                with open(fname, "wb") as f:
                    f.write(base64.b64decode(payload))
            QMessageBox.information(
                self, "Graphique enregistré", f"Fichier créé :\n{fname}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Erreur d'écriture", str(exc))
