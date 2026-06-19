"""Onglet « Titration » (porté de Ramanalyze-simple, adapté à OpenLab'Eau).

Pour chaque spectre on a un **volume de titrant** et (optionnellement) une
**série** ; avec la **concentration** du titrant, l'abscisse devient la
**quantité de matière** (= concentration × volume). On mesure l'intensité d'un
pic (ou le ratio de deux pics) par spectre et on trace une courbe de titration
par série, avec ajustement sigmoïde optionnel (point d'équivalence).

Différences avec la version simple :
- les spectres viennent de l'onglet « Fichiers Raman » (bouton « Charger… ») ;
- le rendu Plotly passe par l'infra OpenLab'Eau (`load_plotly_html`).

Le pré-remplissage depuis la fiche et l'import/export CSV arrivent en phase 2b.
"""

import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from PySide6.QtCore import Qt
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import peak_presets
import plot_style as ps
import titrant_utils as tu
from plotly_downloads import (
    install_plotly_download_handler,
    load_plotly_html,
    sanitize_filename,
    set_plotly_filename,
)

_PALETTE = ["#0057b8", "#d9534f", "#5cb85c", "#f0ad4e", "#9b59b6",
            "#17a2b8", "#e83e8c", "#6c757d", "#20c997", "#fd7e14"]
_NO_SERIES = "(sans série)"


def _peak_intensity(x, y, peak, tol):
    """Intensité maximale dans la fenêtre [peak-tol, peak+tol], ou NaN."""
    mask = (x >= peak - tol) & (x <= peak + tol)
    if not mask.any():
        return np.nan
    return float(np.max(y[mask]))


def _baseline_corrected(x, y, poly_order=5):
    """Soustrait une ligne de base modpoly (pybaselines). y brut si échec."""
    try:
        from pybaselines import Baseline
        baseline, _ = Baseline(x).modpoly(y, poly_order=poly_order)
        return y - baseline
    except Exception as exc:  # noqa: BLE001
        print(f"[titration] Baseline impossible : {exc}")
        return y


class TitrationTab(QWidget):
    def __init__(self, file_picker, metadata_creator, store, parent=None):
        super().__init__(parent)
        self.file_picker = file_picker
        self._metadata_creator = metadata_creator
        self.store = store
        self._last_fig = None
        self._last_file_base = "titration"
        self._populating = False
        self._emitting_meta = False

        # ---------------- Panneau gauche ----------------
        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)

        left_layout.addWidget(
            QLabel("<b>Volume de titrant & série par spectre</b>", left))
        hint = QLabel(
            "Les spectres viennent de l'onglet « Fichiers Raman ». "
            "Double-cliquez les colonnes <i>Volume</i> et <i>Série</i>. "
            "L'abscisse est la quantité de matière (concentration × volume).",
            left,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888;")
        left_layout.addWidget(hint)

        self.btn_load = QPushButton(
            "↻  Charger / actualiser depuis « Fichiers Raman »", left)
        self.btn_load.setStyleSheet(
            "background-color: #0057b8; color: white; font-weight: 700;"
            " padding: 6px;")
        self.btn_load.clicked.connect(self.load_from_picker)
        left_layout.addWidget(self.btn_load)

        prefill_row = QHBoxLayout()
        self.btn_prefill = QPushButton("🧪 Pré-remplir depuis la fiche", left)
        self.btn_prefill.setToolTip(
            "Reprend les volumes de titrant (Solution B) par tube depuis la "
            "fiche terrain, via la correspondance spectres ↔ tubes.")
        self.btn_prefill.clicked.connect(self.prefill_from_fiche)
        self.btn_import_csv = QPushButton("📄 Importer un CSV…", left)
        self.btn_import_csv.setToolTip(
            "Importer un CSV (colonnes Fichier ; Volume titrant ; Série).")
        self.btn_import_csv.clicked.connect(self.import_csv)
        prefill_row.addWidget(self.btn_prefill)
        prefill_row.addWidget(self.btn_import_csv)
        left_layout.addLayout(prefill_row)

        self.table = QTableWidget(0, 3, left)
        self.table.setMinimumHeight(170)
        self.table.setHorizontalHeaderLabels(
            ["Fichier", "Volume titrant", "Série"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.itemChanged.connect(self._on_table_edited)
        left_layout.addWidget(self.table, 1)

        series_row = QHBoxLayout()
        self.edit_series = QLineEdit(left)
        self.edit_series.setPlaceholderText("Nom de série (ex. Série 1)")
        series_row.addWidget(self.edit_series, 1)
        self.btn_assign = QPushButton("Affecter à la sélection", left)
        self.btn_assign.clicked.connect(self.assign_series)
        series_row.addWidget(self.btn_assign)
        left_layout.addLayout(series_row)

        session_btns = QHBoxLayout()
        self.btn_save_session = QPushButton("💾 Enregistrer le tableau…", left)
        self.btn_save_session.clicked.connect(self.save_session)
        self.btn_load_session = QPushButton("📥 Charger un tableau…", left)
        self.btn_load_session.clicked.connect(self.load_session)
        session_btns.addWidget(self.btn_save_session)
        session_btns.addWidget(self.btn_load_session)
        left_layout.addLayout(session_btns)

        # --- Titrant : concentration + unités ---
        titrant_box = QGroupBox("Titrant", left)
        titrant_form = QFormLayout(titrant_box)
        conc_row = QHBoxLayout()
        self.spin_conc = QDoubleSpinBox(titrant_box)
        self.spin_conc.setRange(0.0, 1e9)
        self.spin_conc.setDecimals(4)
        self.spin_conc.setValue(1.0)
        conc_row.addWidget(self.spin_conc, 1)
        self.cmb_conc_unit = QComboBox(titrant_box)
        self.cmb_conc_unit.addItems(list(tu.CONC_FACTORS.keys()))
        self.cmb_conc_unit.setCurrentText("µM")
        conc_row.addWidget(self.cmb_conc_unit)
        titrant_form.addRow("Concentration :", conc_row)
        self.cmb_vol_unit = QComboBox(titrant_box)
        self.cmb_vol_unit.addItems(list(tu.VOL_FACTORS.keys()))
        self.cmb_vol_unit.setCurrentText("µL")
        titrant_form.addRow("Unité des volumes :", self.cmb_vol_unit)
        left_layout.addWidget(titrant_box)

        self.spin_conc.valueChanged.connect(self._on_titrant_changed)
        self.cmb_conc_unit.currentTextChanged.connect(self._on_titrant_changed)
        self.cmb_vol_unit.currentTextChanged.connect(self._on_titrant_changed)

        # --- Combinaisons de pics par source lumineuse ---
        src_box = QGroupBox("Combinaisons de pics (source lumineuse)", left)
        src_layout = QVBoxLayout(src_box)
        src_row = QHBoxLayout()
        src_row.addWidget(QLabel("Source :", src_box))
        self.cmb_source = QComboBox(src_box)
        self.cmb_source.addItems(peak_presets.sources())
        self.cmb_source.currentTextChanged.connect(self._refresh_pairs)
        src_row.addWidget(self.cmb_source, 1)
        src_layout.addLayout(src_row)
        src_layout.addWidget(
            QLabel("Double-cliquez une paire pour charger un ratio :", src_box))
        self.list_pairs = QListWidget(src_box)
        self.list_pairs.setMaximumHeight(120)
        self.list_pairs.itemDoubleClicked.connect(self._use_pair)
        src_layout.addWidget(self.list_pairs)
        left_layout.addWidget(src_box)

        # --- Pic(s) à mesurer ---
        params = QGroupBox("Pic à mesurer", left)
        form = QFormLayout(params)
        self.spin_peak = QDoubleSpinBox(params)
        self.spin_peak.setRange(0.0, 5000.0)
        self.spin_peak.setDecimals(1)
        self.spin_peak.setValue(1000.0)
        self.spin_peak.setSuffix(" cm⁻¹")
        form.addRow("Pic 1 :", self.spin_peak)
        self.spin_tol = QDoubleSpinBox(params)
        self.spin_tol.setRange(0.5, 200.0)
        self.spin_tol.setDecimals(1)
        self.spin_tol.setValue(5.0)
        self.spin_tol.setSuffix(" cm⁻¹")
        form.addRow("Tolérance :", self.spin_tol)
        self.chk_ratio = QCheckBox("Faire le ratio avec un 2ᵉ pic", params)
        self.chk_ratio.toggled.connect(self._on_ratio_toggled)
        form.addRow(self.chk_ratio)
        self.spin_peak2 = QDoubleSpinBox(params)
        self.spin_peak2.setRange(0.0, 5000.0)
        self.spin_peak2.setDecimals(1)
        self.spin_peak2.setValue(1500.0)
        self.spin_peak2.setSuffix(" cm⁻¹")
        self.spin_peak2.setEnabled(False)
        form.addRow("Pic 2 :", self.spin_peak2)
        self.chk_baseline = QCheckBox("Corriger la ligne de base", params)
        self.chk_baseline.setChecked(True)
        form.addRow(self.chk_baseline)
        self.chk_sigmoid = QCheckBox(
            "Ajuster une sigmoïde (point d'équivalence)", params)
        form.addRow(self.chk_sigmoid)
        self.spin_plateau = QDoubleSpinBox(params)
        self.spin_plateau.setRange(50.0, 99.9)
        self.spin_plateau.setDecimals(1)
        self.spin_plateau.setValue(95.0)
        self.spin_plateau.setSuffix(" %")
        form.addRow("Palier atteint à :", self.spin_plateau)
        left_layout.addWidget(params)

        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Titre :", left))
        self.edit_title = QLineEdit(left)
        self.edit_title.setPlaceholderText("Titre automatique (laisser vide)")
        title_row.addWidget(self.edit_title, 1)
        left_layout.addLayout(title_row)

        self.btn_plot = QPushButton("Tracer la titration", left)
        self.btn_plot.setStyleSheet(
            "background-color: #0057b8; color: white; font-weight: 700;"
            " padding: 8px;")
        self.btn_plot.clicked.connect(self.plot_titration)
        left_layout.addWidget(self.btn_plot)

        self.btn_export_csv = QPushButton(
            "⬇ Exporter les résultats (CSV)…", left)
        self.btn_export_csv.setToolTip(
            "Exporte le tableau de résultats (quantité de matière + mesure) "
            "en CSV (mêmes colonnes que l'export Excel).")
        self.btn_export_csv.clicked.connect(self.export_results_csv)
        left_layout.addWidget(self.btn_export_csv)

        self.status = QLabel("", left)
        self.status.setStyleSheet("color: #888;")
        self.status.setWordWrap(True)
        left_layout.addWidget(self.status)

        left_scroll = QScrollArea(self)
        left_scroll.setWidgetResizable(True)
        left_scroll.setWidget(left)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        left_scroll.setMinimumWidth(440)

        self.plot_view = QWebEngineView(self)
        install_plotly_download_handler(self.plot_view)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(left_scroll)
        splitter.addWidget(self.plot_view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([460, 800])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self.store.changed.connect(self._refresh_table)
        self.store.meta_changed.connect(self._on_meta_changed)
        self._sync_titrant_controls()
        self._refresh_table()
        self._refresh_pairs()

    # ------------------------------------------------------------------
    def load_from_picker(self):
        paths = []
        if self.file_picker is not None and hasattr(
                self.file_picker, "get_selected_files"):
            paths = self.file_picker.get_selected_files()
        if not paths:
            QMessageBox.information(
                self,
                "Aucun fichier",
                "Sélectionnez d'abord des fichiers .txt dans l'onglet "
                "« Fichiers Raman ».",
            )
            return
        failed = self.store.sync_paths(paths)
        n = len(self.store.paths())
        msg = f"{n} spectre(s) chargé(s)."
        if failed:
            msg += " Non lisible(s) : " + ", ".join(failed[:3]) + (
                "…" if len(failed) > 3 else "")
        self.status.setText(msg)

    # ------------------------------------------------------------------
    # Pré-remplissage depuis la fiche terrain
    # ------------------------------------------------------------------
    @staticmethod
    def _fmt_vol(value) -> str:
        try:
            f = float(value)
        except (TypeError, ValueError):
            return ""
        if not np.isfinite(f):
            return ""
        return f"{f:.4g}".replace(".", ",")

    def prefill_from_fiche(self):
        """Reprend les volumes de titrant (Solution B) par tube depuis la fiche.

        spectre → tube (correspondance) → volume Solution B (tableau de volumes).
        En mode compte-gouttes, les volumes B sont en gouttes : on les convertit
        en µL via la colonne « Pas (µL) ».
        """
        mc = self._metadata_creator
        df_comp = getattr(mc, "df_comp", None) if mc is not None else None
        df_map = getattr(mc, "df_map", None) if mc is not None else None

        def _ok(df):
            return isinstance(df, pd.DataFrame) and not df.empty

        if not _ok(df_comp) or not _ok(df_map):
            QMessageBox.information(
                self, "Fiche incomplète",
                "Renseignez d'abord le tableau de volumes et la correspondance "
                "spectres ↔ tubes dans « Ma fiche terrain ».")
            return
        if not self.store.paths():
            self.load_from_picker()
            if not self.store.paths():
                return

        # 1) spectre -> tube
        try:
            merged = mc.build_merged_metadata()
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Pré-remplissage impossible", str(exc))
            return
        name_to_tube = {}
        if {"Spectrum name", "Tube"}.issubset(merged.columns):
            for _, r in merged.iterrows():
                name_to_tube[str(r["Spectrum name"]).strip()] = str(
                    r["Tube"]).strip()

        # 2) tube -> volume Solution B (en µL)
        import metadata_model as mm
        tube_cols = mm.get_tube_columns(df_comp)
        b_mask = (
            df_comp["Réactif"].astype(str).str.strip().str.lower() == "solution b"
        )
        tube_to_vol = {}
        pas = 0.0
        if b_mask.any():
            brow = df_comp.loc[b_mask].iloc[0]
            try:
                pas = float(brow.get("Pas (µL)"))
            except (TypeError, ValueError):
                pas = 0.0
            for c in tube_cols:
                v = brow.get(c)
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    continue
                tube_to_vol[c] = v * pas if pas > 0 else v
            # concentration stock du titrant
            conc = brow.get("Concentration")
            unit = str(brow.get("Unité", "")).strip()
            try:
                if conc is not None and not pd.isna(conc):
                    self.store.titrant["conc"] = float(conc)
            except (TypeError, ValueError):
                pass
            if unit in tu.CONC_FACTORS:
                self.store.titrant["conc_unit"] = unit
            self.store.titrant["vol_unit"] = "µL"

        # 3) application par spectre
        n = 0
        for p in self.store.paths():
            base = self.store.name(p)
            stem = os.path.splitext(base)[0]
            tube = name_to_tube.get(stem) or name_to_tube.get(base)
            if not tube:
                continue
            vol = tube_to_vol.get(tube)
            if vol is None:
                vol = tube_to_vol.get(f"Tube {tube}")
            if vol is None:
                continue
            self.store.volumes[p] = self._fmt_vol(vol)
            n += 1

        self._sync_titrant_controls()
        self._refresh_table()
        self._emit_meta()
        if n:
            self.status.setText(
                f"Pré-remplissage : {n} volume(s) repris de la fiche "
                "(en µL, modifiables).")
        else:
            self.status.setText(
                "Aucun volume repris : vérifiez que les noms de fichiers "
                "correspondent aux noms de spectres de la fiche.")

    # ------------------------------------------------------------------
    # Import / export CSV
    # ------------------------------------------------------------------
    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Importer un CSV", os.path.expanduser("~"),
            "Fichiers CSV (*.csv);;Tous les fichiers (*)")
        if not path:
            return
        try:
            df = pd.read_csv(path, sep=None, engine="python")
        except Exception:
            try:
                df = pd.read_csv(path, sep=";")
            except Exception as exc:  # noqa: BLE001
                QMessageBox.critical(self, "Import impossible", str(exc))
                return

        cols = {str(c).strip().lower(): c for c in df.columns}

        def pick(*cands):
            for c in cands:
                if c in cols:
                    return cols[c]
            return None

        file_col = pick("fichier", "file", "nom du spectre", "spectrum name",
                        "nom", "spectre")
        vol_col = pick("volume titrant", "volume", "vol", "volume (µl)",
                       "v_titrant")
        ser_col = pick("série", "serie", "series", "groupe")
        if file_col is None or vol_col is None:
            QMessageBox.warning(
                self, "Colonnes manquantes",
                "Le CSV doit contenir au moins une colonne « Fichier » et une "
                "colonne « Volume titrant ».")
            return

        if not self.store.paths():
            self.load_from_picker()

        lut = {}
        for p in self.store.paths():
            base = self.store.name(p)
            lut[base.lower()] = p
            lut[os.path.splitext(base)[0].lower()] = p

        n = miss = 0
        for _, row in df.iterrows():
            key = str(row[file_col]).strip().lower()
            target = lut.get(key) or lut.get(os.path.splitext(key)[0])
            if target is None:
                miss += 1
                continue
            self.store.volumes[target] = str(row[vol_col]).strip()
            if ser_col is not None and not pd.isna(row[ser_col]):
                self.store.series[target] = str(row[ser_col]).strip()
            n += 1

        self._refresh_table()
        self._emit_meta()
        msg = f"CSV importé : {n} ligne(s) appliquée(s)."
        if miss:
            msg += f" {miss} non associée(s) (spectre non chargé)."
        self.status.setText(msg)

    def _results_dataframe(self):
        """DataFrame des résultats courants (None si aucun volume valide)."""
        peak1 = self.spin_peak.value()
        peak2 = self.spin_peak2.value()
        tol = self.spin_tol.value()
        use_ratio = self.chk_ratio.isChecked()
        do_baseline = self.chk_baseline.isChecked()
        amounts = tu.amounts_mol(
            self.store.paths(), self.store.volumes, self.store.titrant)
        if not amounts:
            return None
        unit_label, unit_factor = tu.pick_amount_unit(max(amounts.values()))
        measure_label = (
            f"I({peak1:.0f})/I({peak2:.0f})" if use_ratio
            else f"I({peak1:.0f})")
        rows = []
        for p in self.store.paths():
            if p not in amounts:
                continue
            val = self._measure(p, peak1, peak2, tol, use_ratio, do_baseline)
            rows.append({
                "Fichier": self.store.name(p),
                "Série": self._series_label(p),
                "Volume titrant": self.store.volumes.get(p, ""),
                f"Quantité ({unit_label})": amounts[p] / unit_factor,
                measure_label: val,
            })
        if not rows:
            return None
        return pd.DataFrame(rows)

    def export_results_csv(self):
        df = self._results_dataframe()
        if df is None or df.empty:
            QMessageBox.information(
                self, "Rien à exporter",
                "Renseignez la concentration du titrant et des volumes "
                "(les mêmes réglages que pour le tracé).")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter les résultats (CSV)",
            os.path.join(os.path.expanduser("~"), "resultats_titration.csv"),
            "Fichiers CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            df.to_csv(path, index=False, sep=";", decimal=",")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export impossible", str(exc))
            return
        self.status.setText(
            f"Résultats exportés : {os.path.basename(path)} "
            f"({len(df)} ligne(s)).")

    # ------------------------------------------------------------------
    def _refresh_pairs(self):
        self.list_pairs.clear()
        for a, b in peak_presets.pairs_for(self.cmb_source.currentText()):
            item = QListWidgetItem(f"{a} / {b} cm⁻¹  →  I({a}) / I({b})")
            item.setData(Qt.UserRole, (a, b))
            self.list_pairs.addItem(item)

    def _use_pair(self, item: QListWidgetItem):
        a, b = item.data(Qt.UserRole)
        self.spin_peak.setValue(float(a))
        self.spin_peak2.setValue(float(b))
        self.chk_ratio.setChecked(True)
        self.status.setText(f"Ratio chargé : I({a}) / I({b}).")

    def _on_ratio_toggled(self, checked: bool):
        self.spin_peak2.setEnabled(checked)

    # ------------------------------------------------------------------
    def save_session(self):
        if not self.store.paths():
            QMessageBox.information(
                self, "Rien à enregistrer", "Aucun spectre chargé.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer le tableau",
            os.path.join(os.path.expanduser("~"), "tableau_titration.json"),
            "Tableau de titration (*.json)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            self.store.save_session(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Enregistrement impossible", str(exc))
            return
        self.status.setText(f"Tableau enregistré : {os.path.basename(path)}")

    def load_session(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Charger un tableau", os.path.expanduser("~"),
            "Tableau de titration (*.json);;Tous les fichiers (*)",
        )
        if not path:
            return
        try:
            missing = self.store.load_session(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Chargement impossible", str(exc))
            return
        self._sync_titrant_controls()
        msg = f"Tableau chargé : {os.path.basename(path)}."
        if missing:
            msg += (f" {len(missing)} introuvable(s) — rechargez-les : "
                    + ", ".join(missing[:3])
                    + ("…" if len(missing) > 3 else ""))
        self.status.setText(msg)

    # ------------------------------------------------------------------
    def _emit_meta(self):
        self._emitting_meta = True
        self.store.meta_changed.emit()
        self._emitting_meta = False

    def _on_meta_changed(self):
        if self._emitting_meta:
            return
        self._sync_titrant_controls()
        self._refresh_table()

    def _on_titrant_changed(self, *_):
        if self._populating:
            return
        self.store.titrant["conc"] = self.spin_conc.value()
        self.store.titrant["conc_unit"] = self.cmb_conc_unit.currentText()
        self.store.titrant["vol_unit"] = self.cmb_vol_unit.currentText()
        self._emit_meta()

    def _sync_titrant_controls(self):
        self._populating = True
        t = self.store.titrant
        self.spin_conc.setValue(float(t.get("conc", 1.0)))
        self.cmb_conc_unit.setCurrentText(t.get("conc_unit", "µM"))
        self.cmb_vol_unit.setCurrentText(t.get("vol_unit", "µL"))
        self._populating = False

    def _on_table_edited(self, item):
        if self._populating:
            return
        path = item.data(Qt.UserRole)
        if path is None:
            return
        if item.column() == 1:
            self.store.volumes[path] = item.text().strip()
        elif item.column() == 2:
            self.store.series[path] = item.text().strip()
        self._emit_meta()

    def assign_series(self):
        label = self.edit_series.text().strip()
        rows = {idx.row() for idx in self.table.selectedIndexes()}
        if not rows:
            QMessageBox.information(
                self, "Aucune sélection", "Sélectionnez d'abord des lignes.")
            return
        self._populating = True
        for r in rows:
            path = self.table.item(r, 0).data(Qt.UserRole)
            self.store.series[path] = label
            self.table.item(r, 2).setText(label)
        self._populating = False
        self._emit_meta()
        self.status.setText(
            f"Série « {label or _NO_SERIES} » affectée à {len(rows)} fichier(s).")

    def _refresh_table(self):
        self._populating = True
        self.table.setRowCount(0)
        for path in self.store.paths():
            row = self.table.rowCount()
            self.table.insertRow(row)
            name_item = QTableWidgetItem(self.store.name(path))
            name_item.setData(Qt.UserRole, path)
            name_item.setToolTip(path)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, name_item)
            vol_item = QTableWidgetItem(self.store.volumes.get(path, ""))
            vol_item.setData(Qt.UserRole, path)
            self.table.setItem(row, 1, vol_item)
            ser_item = QTableWidgetItem(self.store.series.get(path, ""))
            ser_item.setData(Qt.UserRole, path)
            self.table.setItem(row, 2, ser_item)
        self._populating = False

    def _series_label(self, path):
        return self.store.series.get(path, "").strip() or _NO_SERIES

    # ------------------------------------------------------------------
    def _measure(self, path, peak1, peak2, tol, use_ratio, do_baseline):
        x, y = self.store.spectra[path]
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        yv = _baseline_corrected(x, y) if do_baseline else y
        i1 = _peak_intensity(x, yv, peak1, tol)
        if use_ratio:
            i2 = _peak_intensity(x, yv, peak2, tol)
            if i2 is None or np.isnan(i2) or i2 == 0:
                return np.nan
            return i1 / i2
        return i1

    def plot_titration(self):
        try:
            self._plot_titration_impl()
        except Exception as exc:  # noqa: BLE001
            import traceback
            QMessageBox.critical(
                self, "Erreur de tracé",
                f"Le tracé a échoué :\n{exc}\n\n{traceback.format_exc()}",
            )

    def _plot_titration_impl(self):
        if not self.store.paths():
            QMessageBox.information(
                self, "Aucun spectre",
                "Chargez d'abord des spectres (bouton « Charger… »).")
            return

        peak1 = self.spin_peak.value()
        peak2 = self.spin_peak2.value()
        tol = self.spin_tol.value()
        use_ratio = self.chk_ratio.isChecked()
        do_baseline = self.chk_baseline.isChecked()
        do_fit = self.chk_sigmoid.isChecked()

        amounts = tu.amounts_mol(
            self.store.paths(), self.store.volumes, self.store.titrant)
        if not amounts:
            QMessageBox.warning(
                self, "Volumes manquants",
                "Renseignez la concentration du titrant et au moins un volume.",
            )
            return
        unit_label, unit_factor = tu.pick_amount_unit(max(amounts.values()))

        if use_ratio:
            y_title = f"I({peak1:.0f}) / I({peak2:.0f}) (a.u.)"
            auto_title = f"Titration · ratio {peak1:.0f}/{peak2:.0f} cm⁻¹"
            self._last_file_base = f"titration_ratio_{peak1:.0f}_{peak2:.0f}"
        else:
            y_title = f"Intensité au pic {peak1:.0f} cm⁻¹ (a.u.)"
            auto_title = f"Titration · pic {peak1:.0f} cm⁻¹"
            self._last_file_base = f"titration_pic_{peak1:.0f}"
        title = self.edit_title.text().strip() or auto_title

        series_order = []
        for p in self.store.paths():
            lab = self._series_label(p)
            if lab not in series_order:
                series_order.append(lab)

        fig = go.Figure()
        multi = len(series_order) > 1
        n_pts = n_fits = 0
        eq_points = []
        for si, lab in enumerate(series_order):
            rows = []
            for p in self.store.paths():
                if self._series_label(p) != lab or p not in amounts:
                    continue
                val = self._measure(p, peak1, peak2, tol, use_ratio, do_baseline)
                if not np.isnan(val):
                    rows.append((amounts[p] / unit_factor, val, self.store.name(p)))
            if not rows:
                continue
            rows.sort(key=lambda r: r[0])
            xs = [r[0] for r in rows]
            ys = [r[1] for r in rows]
            names = [r[2] for r in rows]
            n_pts += len(rows)
            color = _PALETTE[si % len(_PALETTE)]
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines+markers",
                name=(lab if multi else "Mesures"),
                legendgroup=lab, line=dict(width=ps.LINE_WIDTH, color=color),
                marker=ps.marker(color, si),
                text=names,
                hovertemplate="%{text}<br>x=%{x:.4g}<br>val=%{y:.4g}<extra></extra>",
            ))
            if do_fit:
                popt = tu.fit_sigmoid(xs, ys)
                if popt is not None:
                    x_eq = float(popt[3])
                    bounds = tu.transition_bounds(
                        popt, self.spin_plateau.value() / 100.0)
                    x_fin = bounds[1] if bounds else None
                    cand = [min(xs), max(xs), x_eq] + (
                        [x_fin] if x_fin is not None else [])
                    xf = np.linspace(min(cand), max(cand), 320)
                    fig.add_trace(go.Scatter(
                        x=xf, y=tu.sigmoid(xf, *popt), mode="lines",
                        name=f"{lab} (sigmoïde)", legendgroup=lab,
                        showlegend=False,
                        line=dict(width=1.8, dash="dash", color=color),
                    ))
                    eq_points.append((lab, x_eq, x_fin))
                    n_fits += 1
                    if not multi:
                        y_eq = float(tu.sigmoid(x_eq, *popt))
                        fig.add_trace(go.Scatter(
                            x=[x_eq], y=[y_eq], mode="markers",
                            showlegend=False, name="point d'équivalence",
                            marker=dict(size=15, symbol="star", color=color,
                                        line=dict(width=1.4, color="#000")),
                            hovertemplate=(
                                "point d'équivalence (inflexion)"
                                f"<br>x_eq={x_eq:.4g}<extra></extra>"),
                        ))
                        fig.add_vline(
                            x=x_eq, line=dict(color=color, dash="dot", width=1.5),
                            annotation_text=f"x_eq ≈ {x_eq:.3g}",
                            annotation_position="top",
                            annotation_font=dict(size=12, color=color),
                        )

        if n_pts == 0:
            QMessageBox.warning(
                self, "Pas de points",
                "Aucun point exploitable. Vérifiez les volumes et le pic.",
            )
            return

        ps.apply(
            fig, title=title, x_title=f"Quantité de titrant ({unit_label})",
            y_title=y_title, legend_title=("Séries" if multi else None),
        )
        set_plotly_filename(self.plot_view, self._last_file_base)
        config = {"toImageButtonOptions": {
            "filename": sanitize_filename(self._last_file_base) or "titration"}}
        load_plotly_html(
            self.plot_view, fig.to_html(include_plotlyjs=True, config=config))
        self._last_fig = fig

        msg = f"{n_pts} point(s) sur {len(series_order)} série(s)."
        if do_fit:
            if n_fits:
                apercu = ", ".join(
                    f"{lab} : x_eq={xe:.4g}" for lab, xe, _ in eq_points[:3])
                msg += f" {n_fits} sigmoïde(s) — {apercu}"
            else:
                msg += " Sigmoïde : aucun ajustement convergent (≥ 4 points)."
        self.status.setText(msg)
