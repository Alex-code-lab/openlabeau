import os

import pandas as pd
import plotly.graph_objects as go
from PySide6.QtCore import QTimer, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from data_processing import build_combined_dataframe_from_ui, load_spectrum_file
from plotly_downloads import (
    install_plotly_download_handler,
    load_plotly_html,
    sanitize_filename,
    set_plotly_filename,
)


class SpectraTab(QWidget):
    plot_status_changed = Signal(bool)

    def __init__(self, file_picker, metadata_creator, parent=None):
        super().__init__(parent)
        self.file_picker = file_picker
        self._metadata_creator = metadata_creator

        # Dernière figure Plotly affichée (pour export PNG)
        self._last_fig = None
        self._plot_done = False

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Tracer les spectres sélectionnés"))

        # Checkbox pour afficher le contrôle BRB
        self.chk_show_brb = QCheckBox("Afficher le contrôle BRB", self)
        self.chk_show_brb.setChecked(False)
        layout.addWidget(self.chk_show_brb)

        # --- Contrôle manuel des axes (optionnel) ---
        # Convention : valeur = -1 => autoscale (affiché comme "auto")
        axes = QHBoxLayout()
        axes.addWidget(QLabel("X min (cm⁻¹):"))
        self.spin_xmin = QDoubleSpinBox(self)
        self.spin_xmin.setRange(-1.0, 5000.0)
        self.spin_xmin.setDecimals(1)
        self.spin_xmin.setSingleStep(10.0)
        self.spin_xmin.setSpecialValueText("auto")
        self.spin_xmin.setValue(-1.0)
        axes.addWidget(self.spin_xmin)

        axes.addWidget(QLabel("X max (cm⁻¹):"))
        self.spin_xmax = QDoubleSpinBox(self)
        self.spin_xmax.setRange(-1.0, 5000.0)
        self.spin_xmax.setDecimals(1)
        self.spin_xmax.setSingleStep(10.0)
        self.spin_xmax.setSpecialValueText("auto")
        self.spin_xmax.setValue(-1.0)
        axes.addWidget(self.spin_xmax)

        axes.addSpacing(20)

        axes.addWidget(QLabel("Y min:"))
        self.spin_ymin = QDoubleSpinBox(self)
        self.spin_ymin.setRange(-1.0, 1e12)
        self.spin_ymin.setDecimals(2)
        self.spin_ymin.setSingleStep(100.0)
        self.spin_ymin.setSpecialValueText("auto")
        self.spin_ymin.setValue(-1.0)
        axes.addWidget(self.spin_ymin)

        axes.addWidget(QLabel("Y max:"))
        self.spin_ymax = QDoubleSpinBox(self)
        self.spin_ymax.setRange(-1.0, 1e12)
        self.spin_ymax.setDecimals(2)
        self.spin_ymax.setSingleStep(100.0)
        self.spin_ymax.setSpecialValueText("auto")
        self.spin_ymax.setValue(-1.0)
        axes.addWidget(self.spin_ymax)

        axes.addStretch(1)

        self.btn_reset_axes = QPushButton("Reset axes", self)
        self.btn_reset_axes.clicked.connect(self._reset_axes)
        axes.addWidget(self.btn_reset_axes)

        layout.addLayout(axes)

        self.btn_plot = QPushButton("Tracer les spectres")
        self.btn_plot.clicked.connect(self.plot_selected_with_baseline)
        layout.addWidget(self.btn_plot)
        self._set_plot_button_done(False)
        self.btn_export_png = QPushButton("Exporter le graphique…")
        self.btn_export_png.clicked.connect(self._export_figure)
        layout.addWidget(self.btn_export_png)

        self.plot_view = QWebEngineView(self)
        install_plotly_download_handler(self.plot_view)
        layout.addWidget(self.plot_view, 1)

    def _set_plot_button_done(self, done: bool) -> None:
        if not hasattr(self, "btn_plot"):
            return
        done = bool(done)
        if done:
            self.btn_plot.setStyleSheet(
                "background-color: #5cb85c; color: white; font-weight: 600;"
            )
            self.btn_plot.setToolTip("Spectres tracés")
        else:
            self.btn_plot.setStyleSheet(
                "background-color: #d9534f; color: white; font-weight: 600;"
            )
            self.btn_plot.setToolTip("Rouge = spectres à tracer")
        if getattr(self, "_plot_done", None) != done:
            self._plot_done = done
            self.plot_status_changed.emit(done)

    def mark_plot_stale(self) -> None:
        self._set_plot_button_done(False)

    def _apply_axis_ranges(self, fig) -> None:
        xmin = self.spin_xmin.value()
        xmax = self.spin_xmax.value()
        ymin = self.spin_ymin.value()
        ymax = self.spin_ymax.value()
        if xmin >= 0 and xmax >= 0 and xmin < xmax:
            fig.update_xaxes(range=[xmin, xmax])
        if ymin >= 0 and ymax >= 0 and ymin < ymax:
            fig.update_yaxes(range=[ymin, ymax])

    def _reset_axes(self):
        """Remet les axes en autoscale."""
        self.spin_xmin.setValue(-1.0)
        self.spin_xmax.setValue(-1.0)
        self.spin_ymin.setValue(-1.0)
        self.spin_ymax.setValue(-1.0)

    def _get_manip_name(self) -> str | None:
        md = self._metadata_creator
        if md is not None and hasattr(md, "edit_manip"):
            return md.edit_manip.text().strip() or None
        return None

    def plot_selected_with_baseline(self):
        """
        Trace les spectres sélectionnés.

        Priorité : utilise le fichier combiné construit depuis l'onglet Métadonnées.
        Fallback : lit directement les fichiers .txt sélectionnés.
        """

        self._set_plot_button_done(False)

        try:
            # 1) On tente de construire un fichier combiné à partir des
            # métadonnées créées dans l'onglet Métadonnées
            metadata_creator = self._metadata_creator
            combined_df = None
            if metadata_creator is not None and hasattr(
                metadata_creator, "build_merged_metadata"
            ):
                # Récupérer les fichiers .txt à partir du FilePicker associé à
                # cet onglet
                if hasattr(self.file_picker, "get_selected_files"):
                    txt_files = self.file_picker.get_selected_files()
                else:
                    txt_files = getattr(self.file_picker, "selected_files", [])
                if txt_files:
                    try:
                        exclude_brb = not self.chk_show_brb.isChecked()
                        combined_df = build_combined_dataframe_from_ui(
                            txt_files,
                            metadata_creator,
                            poly_order=5,
                            exclude_brb=exclude_brb,
                            apply_baseline=True,
                        )
                    except Exception as e_inner:
                        QMessageBox.warning(
                            self,
                            "Avertissement",
                            f"Impossible de construire le fichier combiné à partir des métadonnées :\n{e_inner}",
                        )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Erreur interne",
                f"Impossible de construire le fichier combiné :\n{e}",
            )
            combined_df = None

        # --- CAS 1 : Fichier combiné présent ---
        if isinstance(combined_df, pd.DataFrame) and not combined_df.empty:
            try:
                cols = set(combined_df.columns)
                if not {"Raman Shift", "Intensity_corrected"}.issubset(cols):
                    QMessageBox.critical(
                        self,
                        "Colonnes manquantes",
                        f"Le fichier combiné ne contient pas les colonnes 'Raman Shift' et 'Intensity_corrected'.\n"
                        f"Colonnes présentes : {sorted(cols)}",
                    )
                    return

                df_plot = combined_df.copy()
                df_plot = df_plot.dropna(
                    subset=[
                        "Raman Shift",
                        "Intensity_corrected"])

                if df_plot.empty:
                    QMessageBox.warning(
                        self,
                        "Avertissement",
                        "Le fichier combiné ne contient pas de données exploitables "
                        "(valeurs manquantes dans 'Raman Shift' / 'Intensity_corrected').",
                    )
                    return

                # Choix de la légende
                if "Sample description" in df_plot.columns:
                    label_col = "Sample description"
                elif "file" in df_plot.columns:
                    label_col = "file"
                else:
                    label_col = None

                traces = []

                if label_col is not None:
                    for label, g in df_plot.groupby(label_col):
                        g = g.dropna(
                            subset=["Raman Shift", "Intensity_corrected"]
                        ).sort_values("Raman Shift")
                        if g.empty:
                            continue
                        traces.append(
                            go.Scatter(
                                x=g["Raman Shift"].to_numpy(),
                                y=g["Intensity_corrected"].to_numpy(),
                                name=str(label),
                                mode="lines",
                            )
                        )
                else:
                    g = df_plot.sort_values("Raman Shift")
                    traces.append(
                        go.Scatter(
                            x=g["Raman Shift"].to_numpy(),
                            y=g["Intensity_corrected"].to_numpy(),
                            name="spectres",
                            mode="lines",
                        )
                    )

                if not traces:
                    QMessageBox.warning(
                        self, "Avertissement", "Aucun spectre à tracer après filtrage."
                    )
                    return

                # Récupérer le nom de la manip pour le titre
                manip_name = self._get_manip_name() or ""

                title = manip_name if manip_name else "Spectres Raman"
                if manip_name:
                    file_base = f"{manip_name}_Spectres"
                else:
                    file_base = "Spectres"

                fig = go.Figure(traces)
                fig.update_layout(
                    title=title,
                    xaxis_title="Raman Shift (cm⁻¹)",
                    yaxis_title="Intensité corrigée (a.u.)",
                    width=1200,
                    height=600,
                )

                self._apply_axis_ranges(fig)
                self._last_fig = fig  # Sauvegarde pour export PNG
                self.plot_view._plotly_fig = fig
                set_plotly_filename(self.plot_view, file_base)
                config = {
                    "toImageButtonOptions": {
                        "filename": sanitize_filename(file_base) or "Spectres"
                    }
                }
                load_plotly_html(
                    self.plot_view, fig.to_html(
                        include_plotlyjs=True, config=config)
                )
                self._set_plot_button_done(True)
                return

            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Erreur tracé (combined_df)",
                    f"Exception lors de l'utilisation du fichier combiné :\n{e}",
                )
                return

        # --- CAS 2 : fallback – lecture directe des .txt sélectionnés ---
        files = getattr(self.file_picker, "selected_files", [])
        if not files:
            QMessageBox.information(
                self,
                "Info",
                "Aucun fichier combiné valide et aucun fichier .txt sélectionné.\n"
                "Allez dans l’onglet Fichiers, ajoutez des .txt, puis réessayez.",
            )
            return

        traces = []
        for path in files:
            try:
                temp = load_spectrum_file(path)
                if temp is None or temp.empty:
                    continue

                # Sécurité : s'assurer que les colonnes nécessaires sont là
                if not {"Raman Shift", "Intensity_corrected"}.issubset(
                        temp.columns):
                    continue

                g = temp.dropna(
                    subset=["Raman Shift", "Intensity_corrected"]
                ).sort_values("Raman Shift")
                if g.empty:
                    continue

                traces.append(
                    go.Scatter(
                        x=g["Raman Shift"].to_numpy(),
                        y=g["Intensity_corrected"].to_numpy(),
                        name=os.path.basename(path),
                        mode="lines",
                    )
                )
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Erreur sur un fichier",
                    f"Impossible de traiter {os.path.basename(path)} :\n{e}",
                )

        if not traces:
            QMessageBox.warning(
                self,
                "Avertissement",
                "Aucun spectre valide n'a pu être chargé depuis les fichiers .txt sélectionnés.",
            )
            return

        fig = go.Figure(traces)
        fig.update_layout(
            title="Spectres Raman (lecture directe des .txt via data_processing)",
            xaxis_title="Raman Shift (cm⁻¹)",
            yaxis_title="Intensité corrigée (a.u.)",
            width=1200,
            height=600,
        )

        self._apply_axis_ranges(fig)
        self._last_fig = fig
        self.plot_view._plotly_fig = fig
        manip_name = self._get_manip_name()
        if manip_name:
            file_base = f"{manip_name}_Spectres"
        else:
            file_base = "Spectres"
        set_plotly_filename(self.plot_view, file_base)
        config = {
            "toImageButtonOptions": {
                "filename": sanitize_filename(file_base) or "Spectres"
            }
        }
        load_plotly_html(
            self.plot_view, fig.to_html(include_plotlyjs=True, config=config)
        )
        self._set_plot_button_done(True)

    # Presets de taille partagés avec l'onglet Analyse
    _EXPORT_PRESETS: dict[str, tuple[int, int]] = {
        "A4 paysage  (297×210 mm, 150 dpi)": (1748, 1240),
        "A4 portrait (210×297 mm, 150 dpi)": (1240, 1748),
        "A3 paysage  (420×297 mm, 150 dpi)": (2480, 1748),
        "A3 portrait (297×420 mm, 150 dpi)": (1748, 2480),
        "Écran large  (1920×1080)": (1920, 1080),
        "Carré HD    (1400×1400)": (1400, 1400),
        "Personnalisé…": (0, 0),
    }

    def _export_figure(self) -> None:
        """Exporte le graphique des spectres via JS (PNG/SVG) ou printToPdf (PDF)."""
        if self._last_fig is None:
            QMessageBox.information(
                self, "Aucun graphique", "Tracez d'abord les spectres."
            )
            return

        # ── Dialog de configuration ──────────────────────────────────────────
        dlg = QDialog(self)
        dlg.setWindowTitle("Exporter le graphique")
        dlg_layout = QVBoxLayout(dlg)

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

        # ── Choix du fichier ─────────────────────────────────────────────────
        manip_name = self._get_manip_name()
        base = sanitize_filename(
            f"{manip_name}_Spectres") if manip_name else "Spectres"
        filter_str = {"png": "PNG (*.png)", "svg": "SVG (*.svg)", "pdf": "PDF (*.pdf)"}[
            fmt
        ]
        fname, _ = QFileDialog.getSaveFileName(
            self, "Exporter le graphique", base, filter_str
        )
        if not fname:
            return
        if not fname.lower().endswith(ext):
            fname += ext

        # ── Export ───────────────────────────────────────────────────────────
        if fmt == "pdf":
            self._export_figure_pdf(fname)
        else:
            self._export_figure_js(fname, fmt, export_w, export_h)

    def _export_figure_pdf(self, fname: str) -> None:
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
                "Export réussi",
                f"PDF créé :\n{fname}\n\n"
                "(Le fichier sera écrit dans quelques secondes.)",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Échec PDF", str(exc))

    def _export_figure_js(self, fname: str, fmt: str,
                          width: int, height: int) -> None:
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
        self._js_poll_attempts = 0
        self.plot_view.page().runJavaScript(js)

        if hasattr(self, "_js_poll") and self._js_poll.isActive():
            self._js_poll.stop()
        self._js_poll = QTimer(self)
        self._js_poll.setInterval(300)
        self._js_poll.timeout.connect(self._poll_js_export)
        self._js_poll.start()

    _JS_POLL_MAX = 30  # 30 × 300 ms = 9 s maximum

    def _poll_js_export(self) -> None:
        self._js_poll_attempts += 1
        if self._js_poll_attempts > self._JS_POLL_MAX:
            self._js_poll.stop()
            QMessageBox.critical(
                self,
                "Délai dépassé",
                "L'export n'a pas répondu dans les 9 secondes.\n"
                "Vérifiez que le graphique est bien affiché et réessayez.",
            )
            return
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
            _, payload = data_url.split(",", 1)
            if fmt == "svg":
                import urllib.parse

                with open(fname, "w", encoding="utf-8") as f:
                    f.write(urllib.parse.unquote(payload))
            else:
                import base64

                with open(fname, "wb") as f:
                    f.write(base64.b64decode(payload))
            QMessageBox.information(
                self, "Export réussi", f"Fichier créé :\n{fname}")
        except Exception as exc:
            QMessageBox.critical(self, "Erreur d'écriture", str(exc))
