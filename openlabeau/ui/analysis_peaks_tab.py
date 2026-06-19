"""Onglet d'analyse « Suivi des pics » — piloté par la fiche.

Démarche (comme Ramanalyze de base, mais propre et automatique) :
1. Les spectres viennent de « Fichiers Raman ».
2. L'abscisse est la **quantité de titrant ajoutée** dans chaque tube,
   lue automatiquement dans la fiche (correspondance spectres ↔ tubes +
   tableau de volumes). Aucune saisie manuelle.
3. On détecte les pics (scipy.find_peaks) dans une fenêtre, on les apparie d'un
   spectre à l'autre, et on garde ceux présents dans ≥ X % des spectres.
4. Pour chaque pic gardé, on suit sa **hauteur** en fonction de la quantité de
   titrant ajoutée.
5. La courbe est plateau → droite → plateau ; on ajuste une sigmoïde et on marque
   la **fin de la droite = équivalence** (seuil de palier réglable).
"""

import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from PySide6.QtCore import Qt, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from openlabeau.export.plotly_downloads import (
    install_plotly_download_handler,
    load_plotly_html,
    sanitize_filename,
    set_plotly_filename,
)
from openlabeau.raman import titrant_utils as tu
from openlabeau.style import plot_style as ps

_PALETTE = ["#0057b8", "#d9534f", "#5cb85c", "#f0ad4e", "#9b59b6",
            "#17a2b8", "#e83e8c", "#6c757d", "#20c997", "#fd7e14"]
_AMOUNT_UNITS = [("mol", 1.0), ("mmol", 1e-3), ("µmol", 1e-6),
                 ("nmol", 1e-9), ("pmol", 1e-12), ("fmol", 1e-15)]


def _pick_amount_unit(max_mol):
    """Unité de quantité lisible pour la valeur max (en mol)."""
    if not np.isfinite(max_mol) or max_mol <= 0:
        return "mol", 1.0
    for label, factor in _AMOUNT_UNITS:
        if max_mol / factor >= 1.0:
            return label, factor
    return _AMOUNT_UNITS[-1]


def _baseline_corrected(x, y, poly_order=5):
    try:
        from pybaselines import Baseline
        baseline, _ = Baseline(x).modpoly(y, poly_order=poly_order)
        return y - baseline
    except Exception as exc:  # noqa: BLE001
        print(f"[analyse] Baseline impossible : {exc}")
        return y


def _detect_peaks(x, y, wmin, wmax, prominence_frac):
    """Positions des pics détectés dans [wmin, wmax] (liste de cm⁻¹)."""
    mask = (x >= wmin) & (x <= wmax)
    if not mask.any():
        return []
    xb, yb = x[mask], y[mask]
    try:
        from scipy.signal import find_peaks
        span = float(np.ptp(yb)) or 1.0
        idx, _ = find_peaks(yb, prominence=prominence_frac * span)
        return [float(xb[i]) for i in idx]
    except Exception:  # noqa: BLE001
        return [float(xb[int(np.argmax(yb))])]


def _cluster(detections, tol):
    """Regroupe des pics proches. detections : liste de (position, indice_spectre).
    Renvoie [(centre, support)] où support = nb de spectres contenant le pic."""
    if not detections:
        return []
    pts = sorted(detections, key=lambda d: d[0])
    clusters, cur = [], [pts[0]]
    for pos, si in pts[1:]:
        if pos - cur[-1][0] > tol:
            clusters.append(cur)
            cur = []
        cur.append((pos, si))
    clusters.append(cur)
    out = []
    for cl in clusters:
        center = float(np.mean([p for p, _ in cl]))
        support = len({si for _, si in cl})
        out.append((center, support))
    return out


def _measure_at(x, y, center, tol):
    """Hauteur (max) dans [center-tol, center+tol], ou NaN."""
    mask = (x >= center - tol) & (x <= center + tol)
    if not mask.any():
        return np.nan
    return float(np.max(y[mask]))


class PeakAnalysisTab(QWidget):
    # Émis quand un tracé est produit (True) ou devient obsolète (False) :
    # utilisé par MainWindow pour la couleur de l'onglet « Analyse ».
    analysis_status_changed = Signal(bool)

    def __init__(self, file_picker, metadata_creator, store, parent=None):
        super().__init__(parent)
        self.file_picker = file_picker
        self._metadata_creator = metadata_creator
        self.store = store
        self._corr = {}
        self._centers = []
        self._last_fig = None
        self._last_file_base = "suivi_pics"
        self._populating = False
        self._analyzed = False
        self._peaks_detected = False

        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.addWidget(
            QLabel("<b>Suivi des pics vs quantité de titrant ajoutée</b>", left)
        )
        hint = QLabel(
            "Les spectres viennent de « Fichiers Raman ». L'abscisse (quantité "
            "de titrant ajoutée = volume de Solution B × concentration stock) "
            "est lue automatiquement dans la fiche via la correspondance "
            "spectres ↔ tubes.", left)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888;")
        left_layout.addWidget(hint)

        self.lbl_files = QLabel("Aucun spectre Raman sélectionné.", left)
        self.lbl_files.setWordWrap(True)
        self.lbl_files.setStyleSheet("color: #555;")
        left_layout.addWidget(self.lbl_files)

        # --- Fenêtre & détection ---
        params = QGroupBox("Fenêtre & détection", left)
        form = QFormLayout(params)
        self.spin_min = self._spin(params, 0, 5000, 1200, " cm⁻¹", 0, 10)
        form.addRow("Borne min :", self.spin_min)
        self.spin_max = self._spin(params, 0, 5000, 1500, " cm⁻¹", 0, 10)
        form.addRow("Borne max :", self.spin_max)
        self.spin_prom = self._spin(params, 0.1, 100, 5.0, " %", 1, 1.0)
        self.spin_prom.setToolTip("Proéminence minimale d'un pic (% de l'amplitude).")
        form.addRow("Proéminence :", self.spin_prom)
        self.spin_tol = self._spin(params, 1, 200, 10, " cm⁻¹", 0, 1.0)
        self.spin_tol.setToolTip("Tolérance d'appariement / fenêtre de mesure.")
        form.addRow("Tolérance :", self.spin_tol)
        self.spin_presence = QSpinBox(params)
        self.spin_presence.setRange(1, 100)
        self.spin_presence.setValue(90)
        self.spin_presence.setSuffix(" %")
        self.spin_presence.setToolTip(
            "On ne garde que les pics présents dans au moins ce % de spectres.")
        form.addRow("Présence min :", self.spin_presence)
        self.chk_baseline = QCheckBox("Corriger la ligne de base", params)
        self.chk_baseline.setChecked(True)
        form.addRow(self.chk_baseline)
        for control in (
            self.spin_min,
            self.spin_max,
            self.spin_prom,
            self.spin_tol,
            self.spin_presence,
        ):
            control.valueChanged.connect(self._mark_detection_stale)
        self.chk_baseline.toggled.connect(self._mark_detection_stale)
        left_layout.addWidget(params)

        self.btn_detect = QPushButton("1) Détecter les pics", left)
        self.btn_detect.clicked.connect(self.detect_peaks)
        left_layout.addWidget(self.btn_detect)

        peaks_box = QGroupBox("Pics détectés (cochez ceux à suivre)", left)
        peaks_layout = QVBoxLayout(peaks_box)
        self.list_peaks = QListWidget(peaks_box)
        self.list_peaks.setMaximumHeight(170)
        self.list_peaks.itemChanged.connect(self._on_peak_check_changed)
        peaks_layout.addWidget(self.list_peaks)
        check_row = QHBoxLayout()
        btn_all = QPushButton("Tout cocher", peaks_box)
        btn_all.clicked.connect(lambda: self._set_all_checked(True))
        btn_none = QPushButton("Tout décocher", peaks_box)
        btn_none.clicked.connect(lambda: self._set_all_checked(False))
        check_row.addWidget(btn_all)
        check_row.addWidget(btn_none)
        peaks_layout.addLayout(check_row)
        left_layout.addWidget(peaks_box)

        # --- Équivalence ---
        eq_box = QGroupBox("Équivalence (fin de la droite)", left)
        eq_form = QFormLayout(eq_box)
        self.chk_sigmoid = QCheckBox(
            "Ajuster (plateau → droite → plateau) et marquer l'équivalence", eq_box)
        self.chk_sigmoid.setChecked(True)
        eq_form.addRow(self.chk_sigmoid)
        self.combo_fit_peak = QComboBox(eq_box)
        self.combo_fit_peak.setToolTip(
            "Choisissez le pic sur lequel appliquer l'ajustement. "
            "Cela évite de superposer toutes les équivalences sur le graphique."
        )
        eq_form.addRow("Ajuster :", self.combo_fit_peak)
        self.spin_plateau = self._spin(eq_box, 50, 99.9, 95.0, " %", 1, 1.0)
        self.spin_plateau.setToolTip(
            "Seuil « nouveau plateau atteint » : l'équivalence est l'abscisse où "
            "le signal a parcouru ce % de son changement (fin de la droite).")
        eq_form.addRow("Palier atteint à :", self.spin_plateau)
        left_layout.addWidget(eq_box)

        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Titre :", left))
        self.edit_title = QLineEdit(left)
        self.edit_title.setPlaceholderText("Titre automatique (laisser vide)")
        title_row.addWidget(self.edit_title, 1)
        left_layout.addLayout(title_row)

        self.btn_plot = QPushButton("2) Tracer la hauteur des pics", left)
        self.btn_plot.setStyleSheet(
            "background-color: #0057b8; color: white; font-weight: 700;"
            " padding: 8px;")
        self.btn_plot.clicked.connect(self.plot_evolution)
        left_layout.addWidget(self.btn_plot)

        export_row = QHBoxLayout()
        self.btn_export_csv = QPushButton("⬇ Exporter les résultats (CSV)…", left)
        self.btn_export_csv.clicked.connect(self.export_results_csv)
        self.btn_export_csv.setEnabled(False)
        export_row.addWidget(self.btn_export_csv)
        self.btn_export_xlsx = QPushButton("⬇ Exporter les résultats (XLSX)…", left)
        self.btn_export_xlsx.clicked.connect(self.export_results_xlsx)
        self.btn_export_xlsx.setEnabled(False)
        export_row.addWidget(self.btn_export_xlsx)
        left_layout.addLayout(export_row)

        self.status = QLabel("", left)
        self.status.setStyleSheet("color: #888;")
        self.status.setWordWrap(True)
        left_layout.addWidget(self.status)

        left_scroll = QScrollArea(self)
        left_scroll.setWidgetResizable(True)
        left_scroll.setWidget(left)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        left_scroll.setMinimumWidth(420)

        self.plot_view = QWebEngineView(self)
        install_plotly_download_handler(self.plot_view)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(left_scroll)
        splitter.addWidget(self.plot_view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([440, 820])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self.store.changed.connect(self._on_store_changed)
        if self.file_picker is not None and hasattr(self.file_picker, "selection_changed"):
            self.file_picker.selection_changed.connect(self._sync_from_picker)
        self._on_store_changed()
        self._sync_from_picker(silent=True)

    @staticmethod
    def _spin(parent, lo, hi, val, suffix, decimals, step):
        s = QDoubleSpinBox(parent)
        s.setRange(lo, hi)
        s.setDecimals(decimals)
        s.setSingleStep(step)
        s.setValue(val)
        s.setSuffix(suffix)
        return s

    # ------------------------------------------------------------------
    def _style_step_button(self, button: QPushButton, done: bool) -> None:
        color = "#5cb85c" if done else "#d9534f"
        button.setStyleSheet(
            f"background-color: {color}; color: white; font-weight: 700; padding: 8px;"
        )

    def _set_peaks_detected(self, done: bool) -> None:
        self._peaks_detected = bool(done)
        self._style_step_button(self.btn_detect, self._peaks_detected)

    def _mark_detection_stale(self, *_args) -> None:
        if not getattr(self, "_peaks_detected", False) and not self._centers:
            return
        self._corr = {}
        self._centers = []
        self.list_peaks.clear()
        self._refresh_fit_combo()
        self._set_peaks_detected(False)
        self._set_analyzed(False)
        self.btn_export_csv.setEnabled(False)
        self.btn_export_xlsx.setEnabled(False)
        self.status.setText("Paramètres modifiés : redétectez les pics.")

    def _sync_from_picker(self, *_args, silent: bool = False):
        paths = []
        if self.file_picker is not None and hasattr(
                self.file_picker, "get_selected_files"):
            paths = self.file_picker.get_selected_files()
        if not paths:
            self.store.sync_paths([])
            self.status.setText(
                "" if silent else "Aucun fichier Raman sélectionné."
            )
            return
        failed = self.store.sync_paths(paths)
        msg = f"{len(self.store.paths())} spectre(s) Raman synchronisé(s)."
        if failed:
            msg += " Non lisible(s) : " + ", ".join(failed[:3])
        if not silent:
            self.status.setText(msg)

    def _on_store_changed(self):
        self._corr = {}
        self._centers = []
        self.list_peaks.clear()
        self._refresh_fit_combo()
        n = len(self.store.paths())
        self.lbl_files.setText(
            "Aucun spectre Raman sélectionné." if n == 0
            else f"{n} spectre(s) Raman prêt(s). Détectez les pics, puis tracez.")
        self._set_peaks_detected(False)
        self.btn_export_csv.setEnabled(False)
        self.btn_export_xlsx.setEnabled(False)
        self._set_analyzed(False)

    # -- contrat de statut d'onglet (compatible avec l'ancien onglet Analyse) --
    def _set_analyzed(self, done: bool) -> None:
        done = bool(done)
        self._style_step_button(self.btn_plot, done)
        if self._analyzed != done:
            self._analyzed = done
            self.analysis_status_changed.emit(done)

    def mark_analysis_stale(self) -> None:
        self._set_analyzed(False)

    def session_state(self) -> dict:
        """État léger de l'onglet Analyse à sauvegarder avec la fiche."""
        return {
            "window_min": self.spin_min.value(),
            "window_max": self.spin_max.value(),
            "prominence_percent": self.spin_prom.value(),
            "tolerance_cm": self.spin_tol.value(),
            "presence_percent": self.spin_presence.value(),
            "baseline": self.chk_baseline.isChecked(),
            "sigmoid": self.chk_sigmoid.isChecked(),
            "plateau_percent": self.spin_plateau.value(),
            "title": self.edit_title.text(),
            "centers": [
                {"center": float(center), "support": int(support)}
                for center, support in self._centers
            ],
            "checked_centers": [float(c) for c in self._checked_centers()],
            "fit_choice": self.combo_fit_peak.currentData(),
            "analyzed": self._analyzed,
        }

    def restore_session_state(self, state: dict | None) -> None:
        """Restaure les réglages d'analyse sauvegardés avec la fiche."""
        if not isinstance(state, dict):
            return
        self.spin_min.setValue(float(state.get("window_min", self.spin_min.value())))
        self.spin_max.setValue(float(state.get("window_max", self.spin_max.value())))
        self.spin_prom.setValue(
            float(state.get("prominence_percent", self.spin_prom.value()))
        )
        self.spin_tol.setValue(float(state.get("tolerance_cm", self.spin_tol.value())))
        self.spin_presence.setValue(
            int(state.get("presence_percent", self.spin_presence.value()))
        )
        self.chk_baseline.setChecked(bool(state.get("baseline", True)))
        self.chk_sigmoid.setChecked(bool(state.get("sigmoid", True)))
        self.spin_plateau.setValue(
            float(state.get("plateau_percent", self.spin_plateau.value()))
        )
        self.edit_title.setText(str(state.get("title", "")))

        centers = []
        for item in state.get("centers", []):
            if not isinstance(item, dict):
                continue
            try:
                centers.append((float(item["center"]), int(item.get("support", 0))))
            except (KeyError, TypeError, ValueError):
                continue
        if centers:
            self._centers = centers
            self._populate_peak_list()
            checked = {
                round(float(c), 6)
                for c in state.get("checked_centers", [])
                if c is not None
            }
            if checked:
                self._populating = True
                for i in range(self.list_peaks.count()):
                    item = self.list_peaks.item(i)
                    center = round(float(item.data(Qt.UserRole)), 6)
                    item.setCheckState(
                        Qt.Checked if center in checked else Qt.Unchecked
                    )
                self._populating = False
                self._refresh_fit_combo()
            fit_choice = state.get("fit_choice")
            for i in range(self.combo_fit_peak.count()):
                data = self.combo_fit_peak.itemData(i)
                if data == fit_choice:
                    self.combo_fit_peak.setCurrentIndex(i)
                    break
                try:
                    if np.isclose(float(data), float(fit_choice)):
                        self.combo_fit_peak.setCurrentIndex(i)
                        break
                except (TypeError, ValueError):
                    pass
            self._set_peaks_detected(True)
            self._set_analyzed(False)
            self.status.setText(
                "Réglages d'analyse restaurés depuis la fiche. "
                "Cliquez sur « Tracer la hauteur des pics » pour recalculer."
            )

    # ------------------------------------------------------------------
    def _titrant_amount_by_path(self):
        """{path: quantité de titrant ajoutée (mol)} via la fiche."""
        mc = self._metadata_creator
        if mc is None:
            return {}
        try:
            merged = mc.build_merged_metadata()
        except Exception:  # noqa: BLE001
            return {}
        col = (
            "[titrant ajouté] (mol)"
            if "[titrant ajouté] (mol)" in merged.columns
            else None
        )
        if col is None or "Spectrum name" not in merged.columns:
            return {}
        name_to_amount = {}
        for _, r in merged.iterrows():
            try:
                name_to_amount[str(r["Spectrum name"]).strip()] = float(r[col])
            except (TypeError, ValueError):
                continue
        out = {}
        for p in self.store.paths():
            stem = os.path.splitext(self.store.name(p))[0]
            amount = name_to_amount.get(stem)
            if amount is None:
                amount = name_to_amount.get(self.store.name(p))
            if amount is not None and np.isfinite(amount):
                out[p] = amount
        return out

    def _tube_by_path(self):
        mc = self._metadata_creator
        if mc is None:
            return {}
        try:
            merged = mc.build_merged_metadata()
        except Exception:  # noqa: BLE001
            return {}
        if "Spectrum name" not in merged.columns or "Tube" not in merged.columns:
            return {}
        n2t = {str(r["Spectrum name"]).strip(): str(r["Tube"]).strip()
               for _, r in merged.iterrows()}
        out = {}
        for p in self.store.paths():
            stem = os.path.splitext(self.store.name(p))[0]
            out[p] = n2t.get(stem) or n2t.get(self.store.name(p)) or ""
        return out

    # ------------------------------------------------------------------
    def _corrected_spectra(self):
        do_baseline = self.chk_baseline.isChecked()
        corr = {}
        for path in self.store.paths():
            x, y = self.store.spectra[path]
            x = np.asarray(x, dtype=float)
            y = np.asarray(y, dtype=float)
            corr[path] = (x, _baseline_corrected(x, y) if do_baseline else y)
        return corr

    def detect_peaks(self):
        if not self.store.paths():
            QMessageBox.information(
                self, "Aucun spectre",
                "Sélectionnez d'abord des fichiers .txt dans « Fichiers Raman ».")
            return
        wmin, wmax = self.spin_min.value(), self.spin_max.value()
        if wmax <= wmin:
            QMessageBox.warning(
                self, "Fenêtre invalide", "La borne max doit dépasser la min.")
            return
        self._corr = self._corrected_spectra()
        prom = self.spin_prom.value() / 100.0
        tol = self.spin_tol.value()
        detections = []
        for si, path in enumerate(self.store.paths()):
            x, y = self._corr[path]
            for pos in _detect_peaks(x, y, wmin, wmax, prom):
                detections.append((pos, si))
        n_spec = len(self.store.paths())
        min_support = max(1, int(np.ceil(self.spin_presence.value() / 100.0 * n_spec)))
        centers = [(c, s) for c, s in _cluster(detections, tol) if s >= min_support]
        self._centers = centers
        self._populate_peak_list()
        if not centers:
            self._set_peaks_detected(False)
            self.status.setText(
                "Aucun pic retenu. Baissez la proéminence ou la présence min.")
        else:
            self._set_peaks_detected(True)
            self._set_analyzed(False)
            self.status.setText(
                f"{len(centers)} pic(s) présent(s) dans ≥ "
                f"{self.spin_presence.value()} % des spectres. Cochez puis tracez.")

    def _populate_peak_list(self):
        self._populating = True
        self.list_peaks.clear()
        n_spec = len(self.store.paths())
        for center, support in self._centers:
            item = QListWidgetItem(
                f"{center:.0f} cm⁻¹   (présent dans {support}/{n_spec})")
            item.setData(Qt.UserRole, center)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.list_peaks.addItem(item)
        self._populating = False
        self._refresh_fit_combo()

    def _set_all_checked(self, checked: bool):
        self._populating = True
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self.list_peaks.count()):
            self.list_peaks.item(i).setCheckState(state)
        self._populating = False
        self._refresh_fit_combo()

    def _on_peak_check_changed(self, _item=None):
        if self._populating:
            return
        self._refresh_fit_combo()
        self._set_analyzed(False)

    def _checked_centers(self):
        out = []
        for i in range(self.list_peaks.count()):
            it = self.list_peaks.item(i)
            if it.checkState() == Qt.Checked:
                out.append(float(it.data(Qt.UserRole)))
        return out

    def _refresh_fit_combo(self):
        if not hasattr(self, "combo_fit_peak"):
            return
        previous = self.combo_fit_peak.currentData()
        centers = sorted(self._checked_centers())
        self.combo_fit_peak.blockSignals(True)
        self.combo_fit_peak.clear()
        self.combo_fit_peak.addItem("Aucun ajustement", "__none__")
        for center in centers:
            self.combo_fit_peak.addItem(f"{center:.0f} cm⁻¹", center)
        if len(centers) > 1:
            self.combo_fit_peak.addItem("Tous les pics cochés", "__all__")

        selected = 0
        for i in range(self.combo_fit_peak.count()):
            if self.combo_fit_peak.itemData(i) == previous:
                selected = i
                break
        else:
            selected = 1 if centers else 0
        self.combo_fit_peak.setCurrentIndex(selected)
        self.combo_fit_peak.setEnabled(bool(centers))
        self.combo_fit_peak.blockSignals(False)

    def _fit_centers(self, centers):
        if not self.chk_sigmoid.isChecked():
            return set()
        choice = self.combo_fit_peak.currentData()
        if choice == "__none__" or choice is None:
            return set()
        if choice == "__all__":
            return set(centers)
        try:
            selected = float(choice)
        except (TypeError, ValueError):
            return set()
        return {c for c in centers if np.isclose(c, selected)}

    # ------------------------------------------------------------------
    def plot_evolution(self):
        try:
            self._plot_impl()
        except Exception as exc:  # noqa: BLE001
            import traceback
            QMessageBox.critical(
                self, "Erreur de tracé",
                f"Le tracé a échoué :\n{exc}\n\n{traceback.format_exc()}")

    def _plot_impl(self):
        centers = sorted(self._checked_centers())
        if not centers:
            QMessageBox.information(
                self, "Aucun pic coché",
                "Détectez les pics puis cochez au moins un pic à suivre.")
            return
        if not self._corr:
            self._corr = self._corrected_spectra()

        amount = self._titrant_amount_by_path()
        if not amount:
            QMessageBox.warning(
                self, "Quantité de titrant indisponible",
                "Impossible de lire la quantité de titrant ajoutée depuis la fiche.\n"
                "Vérifiez le tableau de volumes, la concentration stock de la "
                "Solution B et la correspondance spectres ↔ tubes.")
            return
        unit_label, factor = _pick_amount_unit(max(amount.values()))
        x_title = f"Quantité de titrant ajoutée ({unit_label})"
        tol = self.spin_tol.value()

        grp = [p for p in self.store.paths() if p in amount]
        grp.sort(key=lambda p: amount[p])
        xs = [amount[p] / factor for p in grp]
        names = [self.store.name(p) for p in grp]

        inten = {}
        for p in grp:
            x, y = self._corr[p]
            inten[p] = {c: _measure_at(x, y, c, tol) for c in centers}

        fit_centers = self._fit_centers(centers)
        title = (self.edit_title.text().strip()
                 or f"Hauteur des pics vs quantité de titrant ajoutée · "
                 f"{self.spin_min.value():.0f}–{self.spin_max.value():.0f} cm⁻¹")
        self._last_file_base = "suivi_pics"

        fig = go.Figure()
        n_fits = 0
        eq_points = []
        for ci, center in enumerate(centers):
            color = _PALETTE[ci % len(_PALETTE)]
            ys = [None if np.isnan(inten[p][center]) else inten[p][center]
                  for p in grp]
            fig.add_trace(go.Scatter(
                x=xs, y=ys, mode="lines+markers", name=f"{center:.0f} cm⁻¹",
                connectgaps=False, line=dict(width=ps.LINE_WIDTH, color=color),
                marker=ps.marker(color, ci), text=names,
                hovertemplate=(f"pic {center:.0f} cm⁻¹<br>%{{text}}<br>"
                               f"titrant ajouté=%{{x:.4g}} {unit_label}<br>"
                               f"I=%{{y:.4g}}<extra></extra>"),
            ))
            if center in fit_centers:
                x_eq = self._add_fit(fig, xs, ys, color, f"{center:.0f} cm⁻¹")
                if x_eq is not None:
                    n_fits += 1
                    eq_points.append((center, x_eq))

        ps.apply(fig, title=title, x_title=x_title,
                 y_title="Hauteur du pic (a.u.)", legend_title="Pics suivis",
                 groupclick="toggleitem")
        set_plotly_filename(self.plot_view, self._last_file_base)
        config = {"toImageButtonOptions": {
            "filename": sanitize_filename(self._last_file_base) or "suivi_pics"}}
        load_plotly_html(self.plot_view, fig.to_html(
            include_plotlyjs=True, config=config))
        self._last_fig = fig
        self._inten = inten
        self._grp = grp
        self._centers_plotted = centers
        self._amount = amount
        self._unit = (unit_label, factor)
        self.btn_export_csv.setEnabled(True)
        self.btn_export_xlsx.setEnabled(True)
        self._set_analyzed(True)

        msg = f"{len(centers)} pic(s) sur {len(grp)} spectre(s)."
        if fit_centers:
            seuil = self.spin_plateau.value()
            if n_fits:
                apercu = ", ".join(
                    f"{c:.0f} cm⁻¹ : éq={xe:.4g} {unit_label}"
                    for c, xe in eq_points[:3])
                msg += (f" Équivalence (fin de droite, {seuil:.0f} %) — {apercu}"
                        + ("…" if len(eq_points) > 3 else ""))
            else:
                msg += " Ajustement : aucun convergent (≥ 4 points requis)."
        self.status.setText(msg)

    def _add_fit(self, fig, xs, ys, color, label):
        """Sigmoïde (plateau→droite→plateau). Marque l'équivalence = fin de droite.
        Renvoie l'abscisse d'équivalence ou None."""
        popt = tu.fit_sigmoid(xs, ys)
        if popt is None:
            return None
        seuil = self.spin_plateau.value()
        bounds = tu.transition_bounds(popt, seuil / 100.0)
        if bounds is None:
            return None
        x_eq = bounds[1]                       # fin de la droite = équivalence
        xa = np.array([x for x, y in zip(xs, ys) if y is not None], dtype=float)
        b99 = tu.transition_bounds(popt, 0.99) or bounds
        lo = min(float(np.min(xa)), b99[0])
        hi = max(float(np.max(xa)), b99[1])
        xf = np.linspace(lo, hi, 320)
        fig.add_trace(go.Scatter(
            x=xf, y=tu.sigmoid(xf, *popt), mode="lines",
            name=f"{label} (ajustement)", showlegend=False,
            line=dict(width=1.6, dash="dash", color=color), opacity=0.9))
        y_eq = float(tu.sigmoid(x_eq, *popt))
        fig.add_trace(go.Scatter(
            x=[x_eq], y=[y_eq], mode="markers", showlegend=False,
            marker=dict(size=14, symbol="star", color=color,
                        line=dict(width=1.4, color="#000")),
            hovertemplate=f"équivalence ({label})<br>x={x_eq:.4g}<extra></extra>"))
        fig.add_vline(x=x_eq, line=dict(color=color, dash="dot", width=1.4),
                      annotation_text=f"éq ≈ {x_eq:.3g}",
                      annotation_position="top",
                      annotation_font=dict(size=11, color=color))
        return x_eq

    # ------------------------------------------------------------------
    def _results_dataframe(self):
        if self._last_fig is None or not getattr(self, "_grp", None):
            QMessageBox.information(
                self, "Rien à exporter", "Tracez d'abord la hauteur des pics.")
            return None
        unit_label, factor = self._unit
        tubes = self._tube_by_path()
        rows = []
        for p in self._grp:
            row = {
                "Fichier": self.store.name(p),
                "Tube": tubes.get(p, ""),
                f"titrant ajouté ({unit_label})": self._amount[p] / factor,
            }
            for c in self._centers_plotted:
                v = self._inten[p][c]
                row[f"pic {c:.0f} cm⁻¹"] = None if np.isnan(v) else v
            rows.append(row)
        return pd.DataFrame(rows)

    def export_results_csv(self):
        df = self._results_dataframe()
        if df is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter les résultats (CSV)",
            os.path.join(os.path.expanduser("~"), "suivi_pics.csv"),
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
            f"Résultats exportés : {os.path.basename(path)} ({len(df)} ligne(s)).")

    def export_results_xlsx(self):
        df = self._results_dataframe()
        if df is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exporter les résultats (XLSX)",
            os.path.join(os.path.expanduser("~"), "suivi_pics.xlsx"),
            "Fichiers Excel (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            from openpyxl.utils import get_column_letter

            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Suivi pics")
                worksheet = writer.sheets["Suivi pics"]
                for idx, column in enumerate(df.columns, start=1):
                    width = max(len(str(column)) + 2, 14)
                    worksheet.column_dimensions[get_column_letter(idx)].width = min(
                        width, 40
                    )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export impossible", str(exc))
            return
        self.status.setText(
            f"Résultats exportés : {os.path.basename(path)} ({len(df)} ligne(s)).")
