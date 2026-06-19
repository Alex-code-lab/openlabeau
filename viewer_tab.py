"""Onglet « Visualiseur » : affiche les spectres .txt sélectionnés.

Approche reprise de Ramanalyze-simple : affichage *brut* (sans correction de
baseline), légende = nom de fichier, cases pour afficher/masquer chaque spectre.
Les fichiers viennent de l'onglet « Fichiers Raman » (file_picker partagé).

Cet onglet remplace l'ancien onglet « Spectres » et en respecte le contrat
(`plot_status_changed`, `mark_plot_stale`) pour la signalétique d'onglets.
"""

import os

import plotly.graph_objects as go
from PySide6.QtCore import Qt, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from plotly_downloads import (
    install_plotly_download_handler,
    load_plotly_html,
    sanitize_filename,
    set_plotly_filename,
)
from spectrum_loader import load_spectrum


class SpectraViewerTab(QWidget):
    """Visualiseur de spectres bruts (légende = nom de fichier)."""

    plot_status_changed = Signal(bool)

    def __init__(self, file_picker, metadata_creator=None, parent=None):
        super().__init__(parent)
        self.file_picker = file_picker
        self._metadata_creator = metadata_creator
        self._spectra: dict[str, tuple] = {}   # path -> (x, y)
        self._checked: dict[str, bool] = {}     # path -> affiché ?
        self._plot_done = False

        # --- Panneau gauche : actions + liste des spectres ---
        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.addWidget(QLabel("<b>Spectres</b>", left))

        self.btn_plot = QPushButton("Tracer les spectres", left)
        self.btn_plot.clicked.connect(self.plot_selected)
        left_layout.addWidget(self.btn_plot)

        hint = QLabel(
            "Les spectres viennent de l'onglet « Fichiers Raman ». "
            "Cochez / décochez un spectre pour l'afficher ou le masquer.",
            left,
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888;")
        left_layout.addWidget(hint)

        axes_box = QGroupBox("Axes", left)
        axes_layout = QFormLayout(axes_box)
        self.spin_x_min = self._axis_spin(1150.0, " cm⁻¹", axes_box)
        self.spin_x_max = self._axis_spin(1500.0, " cm⁻¹", axes_box)
        self.spin_y_min = self._axis_spin(None, "", axes_box)
        self.spin_y_max = self._axis_spin(None, "", axes_box)
        axes_layout.addRow("X min :", self.spin_x_min)
        axes_layout.addRow("X max :", self.spin_x_max)
        axes_layout.addRow("Y min :", self.spin_y_min)
        axes_layout.addRow("Y max :", self.spin_y_max)
        axes_buttons = QHBoxLayout()
        self.btn_apply_axes = QPushButton("Appliquer les axes", axes_box)
        self.btn_apply_axes.clicked.connect(self.refresh_plot)
        axes_buttons.addWidget(self.btn_apply_axes)
        self.btn_reset_y = QPushButton("Y auto", axes_box)
        self.btn_reset_y.clicked.connect(self._reset_y_axis)
        axes_buttons.addWidget(self.btn_reset_y)
        axes_layout.addRow(axes_buttons)
        left_layout.addWidget(axes_box)

        self.file_list = QListWidget(left)
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_list.itemChanged.connect(self._on_item_changed)
        left_layout.addWidget(self.file_list, 1)

        self.status = QLabel("Aucun spectre", left)
        self.status.setStyleSheet("color: #888;")
        self.status.setWordWrap(True)
        left_layout.addWidget(self.status)

        left_scroll = QScrollArea(self)
        left_scroll.setWidgetResizable(True)
        left_scroll.setWidget(left)
        left_scroll.setMinimumWidth(300)

        # --- Vue Plotly (téléchargement PNG via la modebar) ---
        self.plot_view = QWebEngineView(self)
        install_plotly_download_handler(self.plot_view)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(left_scroll)
        splitter.addWidget(self.plot_view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 900])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self._set_plot_done(False)

    @staticmethod
    def _axis_spin(value: float | None, suffix: str, parent) -> QDoubleSpinBox:
        spin = QDoubleSpinBox(parent)
        spin.setRange(-1_000_000, 1_000_000)
        spin.setDecimals(2)
        spin.setSingleStep(10.0 if suffix else 100.0)
        spin.setSpecialValueText("Auto")
        spin.setSuffix(suffix)
        spin.setValue(-1_000_000 if value is None else value)
        return spin

    # ------------------------------------------------------------------
    # Contrat workflow (compatible avec l'ancien onglet « Spectres »)
    # ------------------------------------------------------------------
    def _set_plot_done(self, done: bool) -> None:
        done = bool(done)
        if done:
            self.btn_plot.setStyleSheet(
                "background-color: #5cb85c; color: white; font-weight: 600;")
            self.btn_plot.setToolTip("Spectres tracés")
        else:
            self.btn_plot.setStyleSheet(
                "background-color: #d9534f; color: white; font-weight: 600;")
            self.btn_plot.setToolTip("Rouge = spectres à tracer")
        if self._plot_done != done:
            self._plot_done = done
            self.plot_status_changed.emit(done)

    def mark_plot_stale(self) -> None:
        self._set_plot_done(False)

    # ------------------------------------------------------------------
    def _selected_files(self) -> list[str]:
        fp = self.file_picker
        if fp is not None and hasattr(fp, "get_selected_files"):
            return fp.get_selected_files()
        return []

    def plot_selected(self) -> None:
        paths = self._selected_files()
        if not paths:
            QMessageBox.information(
                self,
                "Aucun fichier",
                "Sélectionnez d'abord des fichiers .txt dans l'onglet "
                "« Fichiers Raman ».",
            )
            return

        self.file_list.blockSignals(True)
        self.file_list.clear()
        spectra: dict[str, tuple] = {}
        failed: list[str] = []
        for path in paths:
            data = self._spectra.get(path) or load_spectrum(path)
            if data is None:
                failed.append(os.path.basename(path))
                continue
            spectra[path] = data
            self._checked.setdefault(path, True)
            self._add_item(path)
        self._spectra = spectra
        self.file_list.blockSignals(False)

        self.refresh_plot()
        self._set_plot_done(bool(self._spectra))
        if failed:
            self.status.setText(
                f"{len(failed)} fichier(s) non lisible(s) : "
                + ", ".join(failed[:3]) + ("…" if len(failed) > 3 else "")
            )

    def _add_item(self, path: str) -> None:
        item = QListWidgetItem(os.path.basename(path))
        item.setToolTip(path)
        item.setData(Qt.UserRole, path)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(
            Qt.Checked if self._checked.get(path, True) else Qt.Unchecked)
        self.file_list.addItem(item)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.UserRole)
        self._checked[path] = item.checkState() == Qt.Checked
        self.refresh_plot()

    def _checked_paths(self) -> list[str]:
        return [p for p in self._spectra if self._checked.get(p, True)]

    def _axis_range(self, min_spin: QDoubleSpinBox, max_spin: QDoubleSpinBox):
        auto = min_spin.minimum()
        lo = None if min_spin.value() == auto else min_spin.value()
        hi = None if max_spin.value() == auto else max_spin.value()
        if lo is None or hi is None:
            return None
        if hi <= lo:
            return None
        return [lo, hi]

    def _reset_y_axis(self) -> None:
        auto = self.spin_y_min.minimum()
        self.spin_y_min.setValue(auto)
        self.spin_y_max.setValue(auto)
        self.refresh_plot()

    def refresh_plot(self) -> None:
        paths = self._checked_paths()
        fig = go.Figure()
        for path in paths:
            x, y = self._spectra[path]
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=y,
                    mode="lines",
                    name=os.path.basename(path),
                    line=dict(width=1.6),
                )
            )
        x_range = self._axis_range(self.spin_x_min, self.spin_x_max)
        y_range = self._axis_range(self.spin_y_min, self.spin_y_max)
        fig.update_layout(
            title=(
                "Spectres Raman" if paths
                else "Cliquez sur « Tracer les spectres »"
            ),
            xaxis_title="Décalage Raman (cm⁻¹)",
            yaxis_title="Intensité (a.u.)",
            legend_title="Fichiers",
            template="plotly_white",
            margin=dict(l=60, r=20, t=50, b=50),
        )
        if x_range is not None:
            fig.update_xaxes(range=x_range)
        if y_range is not None:
            fig.update_yaxes(range=y_range)
        set_plotly_filename(self.plot_view, "spectres")
        config = {
            "toImageButtonOptions": {
                "filename": sanitize_filename("spectres") or "spectres"
            }
        }
        load_plotly_html(
            self.plot_view, fig.to_html(include_plotlyjs=True, config=config)
        )

        n = len(self._spectra)
        self.status.setText(
            "Aucun spectre" if n == 0 else f"{len(paths)} affiché(s) / {n} chargé(s)"
        )
