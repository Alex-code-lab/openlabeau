"""Dialogue de suivi de protocole de paillasse.

Affiche le tableau des volumes avec, pour chaque tube, des cases à cocher
cliquables (Coordinateur + Opérateur).

Mode guidé : seule l'étape courante est éclairée ; tout le reste est ombré
et désactivé.  Séquence par ligne (réactif) :
  Vérif. solution → Tube 1 Coord → Tube 1 Opér → Tube 2 Coord → … → Tube N Opér
Puis passage au réactif suivant.

Un bouton "Exporter Excel" génère la feuille stylée avec l'état courant.
"""

from __future__ import annotations

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from openlabeau.export import protocol_export
from openlabeau.metadata import metadata_model as mm

# ── Couleurs actives (identique à protocol_export) ───────────────────────────
_C_TUBE = QColor("#2E75B6")
_C_COORD = QColor("#5B9BD5")
_C_OPER = QColor("#9DC3E6")
_C_REACT = QColor("#ED7D31")
_C_VERIF = QColor("#70AD47")
_C_VERIF_L = QColor("#E2EFDA")
_C_META = QColor("#D6DCE4")
_C_ROW_A = QColor("#DEEAF1")
_C_ROW_B = QColor("#FFFFFF")
_C_GRP_HDR = QColor("#1F4E79")
_C_VOL = QColor("#BDD7EE")
_C_COORD_A = QColor("#DAEEF3")
_C_COORD_B = QColor("#EBF5FB")
_C_OPER_A = QColor("#E8F4F8")
_C_OPER_B = QColor("#F5FBFD")
_C_WHITE = QColor("#FFFFFF")
_C_INSTR = QColor("#FFF2CC")
_C_WARN = QColor("#FCE4D6")
_C_INSTR_FG = QColor("#7F6000")
_C_WARN_FG = QColor("#9C0006")

# ── Couleurs ombrées ────────────────────────────────────────────────────
# Étapes inactives : grisées mais LISIBLES (thème clair). Ces couleurs sont
# posées en dur sur les cellules : elles ne dépendent ni de la palette ni du
# style, donc elles donnent le même rendu sur macOS, Windows et Linux.
_C_DIM_BG = QColor("#D3D3D3")  # fond ombré plus sombre
_C_DIM_FG = QColor("#222222")  # texte sombre, toujours lisible
_SS_DIM = "background: #D3D3D3; color: #222222;"
_SS_ACTIVE = "background: transparent;"

_FIXED_COLS = 5  # Réactif | Conc. | Unité (conc.) | Vérif. | Unité (vol.)
_SUBCOLS = 3  # Vol. | Coord. | Opér.  par tube

# Indices relatifs des sous-colonnes tube dans QTableWidget (0-based)
_SUB_VOL = 0
_SUB_COORD = 1
_SUB_OPER = 2


# ── Helpers ─────────────────────────────────────────────────────────────


def _centered_checkbox(bg: str = "transparent") -> tuple[QWidget, QCheckBox]:
    w = QWidget()
    cb = QCheckBox()
    lay = QHBoxLayout(w)
    lay.addWidget(cb)
    lay.setAlignment(Qt.AlignCenter)
    lay.setContentsMargins(0, 0, 0, 0)
    w.setStyleSheet(f"background: {bg};")
    return w, cb


def _item(
    text: str = "",
    *,
    bg: QColor | None = None,
    fg: QColor | None = None,
    bold: bool = False,
    center: bool = True,
) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    if bg:
        it.setBackground(QBrush(bg))
    if fg:
        it.setForeground(QBrush(fg))
    if bold:
        f = it.font()
        f.setBold(True)
        it.setFont(f)
    it.setTextAlignment(
        (Qt.AlignCenter if center else Qt.AlignLeft) | Qt.AlignVCenter)
    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    return it


# ── Calcul des couleurs normales ────────────────────────────────────────


def _normal_item_bg(r_idx: int, col: int, n_fixed: int,
                    n_subcols: int) -> QColor:
    """Retourne la couleur de fond normale d'une cellule (hors ombrée)."""
    if col == 0:
        return _C_REACT
    if col == 1 or col == 2:
        return _C_META
    if col == 3:
        return _C_VERIF_L  # verif
    if col == 4:
        return _C_META  # unité (vol.)
    rel = (col - n_fixed) % n_subcols
    if rel == _SUB_VOL:
        return _C_VOL
    if rel == _SUB_COORD:
        return _C_COORD_A if r_idx % 2 == 0 else _C_COORD_B
    return _C_OPER_A if r_idx % 2 == 0 else _C_OPER_B


# ── Dialogue ────────────────────────────────────────────────────────────


class ProtocolDialog(QDialog):
    """Dialogue de suivi interactif du protocole de paillasse (mode guidé)."""

    def __init__(
        self,
        df_comp: pd.DataFrame,
        meta: dict,
        initial_states: dict | None = None,
        df_map=None,
        parent=None,
    ):
        super().__init__(parent)
        self._df = df_comp.copy()
        self._df_map = df_map
        self._meta = meta
        self._initial_states = initial_states or {}
        self._tubes = mm.get_tube_columns(df_comp)
        self._n_tubes = len(self._tubes)
        self._n_rows = len(df_comp)
        self._display_rows = list(
            protocol_export._protocol_display_rows(
                self._df))

        # Registres des widgets
        self._checks: dict[tuple, QCheckBox] = {}  # clé → QCheckBox
        self._c_widgets: dict[tuple[int, int], QWidget] = (
            {}
        )  # (tr,col) → QWidget conteneur
        # ligne table → ligne df_comp
        self._r_idx_for_table_row: dict[int, int] = {}
        self._instruction_rows: dict[int, tuple[tuple, str]] = (
            {}
        )  # ligne table → (clé, type)
        self._instruction_labels: dict[tuple, str] = {}  # clé → texte affiché

        self.setWindowTitle("Suivi de protocole — Paillasse")
        parent_width = parent.width() if parent is not None else 0
        default_width = (
            parent_width if parent_width > 0 else max(
                900, 300 + self._n_tubes * 120)
        )
        self.resize(default_width, 560)
        self.setSizeGripEnabled(True)

        root = QVBoxLayout(self)
        root.setSpacing(6)

        self._build_info_bar(root, meta)
        self._build_legend(root)

        # Table
        n_cols = _FIXED_COLS + self._n_tubes * _SUBCOLS
        self._table = QTableWidget(1 + len(self._display_rows), n_cols, self)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table.setShowGrid(True)
        self._build_headers()
        self._build_data()
        root.addWidget(self._table)

        # Zone Notes
        gb_notes = QGroupBox("Notes")
        gb_layout = QVBoxLayout(gb_notes)
        gb_layout.setContentsMargins(6, 4, 6, 4)
        self._notes_edit = QPlainTextEdit()
        self._notes_edit.setPlaceholderText("Remarques sur l'expérience…")
        self._notes_edit.setMaximumHeight(90)
        gb_layout.addWidget(self._notes_edit)
        root.addWidget(gb_notes)

        self._apply_initial_states()
        self._build_buttons(root)

        # Premier affichage
        self._refresh_highlights()

    # ── Barres d'info et légende ────────────────────────────────────────────

    def _build_info_bar(self, root, meta):
        row = QHBoxLayout()
        for label, val in [
            ("Manip :", meta.get("nom_manip", "—")),
            ("Date :", meta.get("date", "—")),
            ("Lieu :", meta.get("lieu", "—")),
            ("Coordinateur :", meta.get("coordinateur", "—")),
            ("Opérateur :", meta.get("operateur", "—")),
        ]:
            lbl = QLabel(f"<b>{label}</b> {val}")
            lbl.setStyleSheet("font-size: 11px; color: #333333;")
            row.addWidget(lbl)
            row.addSpacing(12)
        row.addStretch()
        root.addLayout(row)

    def _build_legend(self, root):
        row = QHBoxLayout()
        self._lbl_step = QLabel("")
        self._lbl_step.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #46ba48; padding: 2px 6px;"
        )
        row.addWidget(self._lbl_step)
        row.addStretch()
        for color_hex, label in [
            ("#2E75B6", "Volume"),
            ("#5B9BD5", "Coordinateur"),
            ("#9DC3E6", "Opérateur"),
            ("#70AD47", "Vérif. solution"),
        ]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {color_hex}; font-size: 14px;")
            txt = QLabel(label)
            txt.setStyleSheet(
                "font-size: 11px; color: #555555; margin-right: 10px;")
            row.addWidget(dot)
            row.addWidget(txt)
        root.addLayout(row)

    # ── Construction de la table ────────────────────────────────────────────

    def _build_headers(self):
        tbl = self._table
        labels = ["Réactif", "Conc.", "Unité", "Vérif.", "Unité vol."]
        for _ in self._tubes:
            labels += ["Vol.", "Coord.", "Opér."]
        tbl.setHorizontalHeaderLabels(labels)
        tbl.horizontalHeader().setDefaultSectionSize(60)
        tbl.setColumnWidth(0, 140)
        tbl.setColumnWidth(1, 70)
        tbl.setColumnWidth(2, 60)
        tbl.setColumnWidth(3, 55)
        tbl.setColumnWidth(4, 60)  # Unité vol.
        for t in range(self._n_tubes):
            base = _FIXED_COLS + t * _SUBCOLS
            tbl.setColumnWidth(base, 65)
            tbl.setColumnWidth(base + 1, 55)
            tbl.setColumnWidth(base + 2, 55)

        # Ligne 0 : en-têtes de groupe
        tbl.setRowHeight(0, 28)
        for col, bg, label in [
            (0, _C_REACT, "Réactif"),
            (1, _C_META, ""),
            (2, _C_META, ""),
            (3, _C_VERIF, "Vérif.\nsolution"),
            (4, _C_META, "Unité"),
        ]:
            tbl.setItem(0, col, _item(label, bg=bg, fg=_C_WHITE, bold=True))
        for t_idx, tube_name in enumerate(self._tubes):
            base = _FIXED_COLS + t_idx * _SUBCOLS
            tbl.setSpan(0, base, 1, _SUBCOLS)
            tbl.setItem(
                0, base, _item(
                    tube_name, bg=_C_GRP_HDR, fg=_C_WHITE, bold=True)
            )

    def _build_data(self):
        tbl = self._table
        for display_idx, display_row in enumerate(self._display_rows):
            tr = display_idx + 1

            if display_row[0] == "instruction":
                _, key, text, kind = display_row
                bg = _C_WARN if kind == "warning" else _C_INSTR
                fg = _C_WARN_FG if kind == "warning" else _C_INSTR_FG
                self._instruction_rows[tr] = (key, kind)
                self._instruction_labels[key] = text
                tbl.setRowHeight(tr, 30 if kind == "warning" else 24)
                w, cb = _centered_checkbox(bg.name())
                self._checks[key] = cb
                self._c_widgets[(tr, 0)] = w
                cb.stateChanged.connect(self._refresh_highlights)
                tbl.setItem(tr, 0, _item("", bg=bg))
                tbl.setCellWidget(tr, 0, w)
                tbl.setSpan(tr, 1, 1, tbl.columnCount() - 1)
                tbl.setItem(
                    tr,
                    1,
                    _item(
                        text,
                        bg=bg,
                        fg=fg,
                        bold=True,
                        center=False))
                continue

            _, r_idx, row = display_row
            self._r_idx_for_table_row[tr] = r_idx
            tbl.setRowHeight(tr, 26)

            tbl.setItem(
                tr,
                0,
                _item(
                    str(row.get("Réactif", "")),
                    bg=_C_ROW_A if r_idx % 2 == 0 else _C_ROW_B,
                    center=False,
                ),
            )
            raw = row.get("Concentration", "")
            try:
                v = round(float(raw), 1)
                conc_str = str(int(v)) if v == int(v) else str(v)
            except (ValueError, TypeError):
                conc_str = str(raw) if raw not in (None, "") else ""
            rbg = _C_ROW_A if r_idx % 2 == 0 else _C_ROW_B
            tbl.setItem(tr, 1, _item(conc_str, bg=rbg))
            tbl.setItem(tr, 2, _item(str(row.get("Unité", "")), bg=rbg))

            # Vérification solution
            w, cb = _centered_checkbox(_C_VERIF_L.name())
            self._checks[("verif", r_idx)] = cb
            self._c_widgets[(tr, 3)] = w
            cb.stateChanged.connect(self._refresh_highlights)
            tbl.setCellWidget(tr, 3, w)

            # Mode compte-goutte : pas > 0 → valeurs stockées en n_gouttes
            try:
                pas = float(row.get("Pas (µL)", 0) or 0)
            except (ValueError, TypeError):
                pas = 0.0

            # Colonne Unité vol. (col 4) : "gouttes" ou "µL" une seule fois par
            # ligne
            unit_vol_str = "gouttes" if pas > 0 else "µL"
            tbl.setItem(tr, 4, _item(unit_vol_str, bg=_C_META))

            # Tubes
            for t_idx, tube_name in enumerate(self._tubes):
                base = _FIXED_COLS + t_idx * _SUBCOLS
                raw_vol = row.get(tube_name, "")
                try:
                    v = float(raw_vol)
                    if pas > 0:
                        vol_str = str(int(round(v)))
                    else:
                        vol_str = str(int(v)) if v == int(v) else str(v)
                except (ValueError, TypeError):
                    vol_str = str(raw_vol) if raw_vol not in (None, "") else ""

                tbl.setItem(tr, base, _item(vol_str, bg=_C_VOL))

                bg_c = (_C_COORD_A if r_idx % 2 == 0 else _C_COORD_B).name()
                w_c, cb_c = _centered_checkbox(bg_c)
                self._checks[("coord", r_idx, t_idx)] = cb_c
                self._c_widgets[(tr, base + 1)] = w_c
                cb_c.stateChanged.connect(self._refresh_highlights)
                tbl.setCellWidget(tr, base + 1, w_c)

                bg_o = (_C_OPER_A if r_idx % 2 == 0 else _C_OPER_B).name()
                w_o, cb_o = _centered_checkbox(bg_o)
                self._checks[("oper", r_idx, t_idx)] = cb_o
                self._c_widgets[(tr, base + 2)] = w_o
                cb_o.stateChanged.connect(self._refresh_highlights)
                tbl.setCellWidget(tr, base + 2, w_o)

    def _apply_initial_states(self):
        """Pré-coche les cases selon les états chargés depuis le fichier."""
        for key, checked in self._initial_states.items():
            cb = self._checks.get(key)
            if cb is not None and checked:
                cb.blockSignals(True)
                cb.setEnabled(True)
                cb.setChecked(True)
                cb.blockSignals(False)
        notes = self._initial_states.get("__notes__", "")
        if notes:
            self._notes_edit.setPlainText(str(notes))

    def _build_buttons(self, root):
        row = QHBoxLayout()
        btn_row = QPushButton("Cocher la ligne")
        btn_coord = QPushButton("Tout cocher — Coord.")
        btn_oper = QPushButton("Tout cocher — Opér.")
        btn_reset = QPushButton("Tout décocher")
        self._btn_export = QPushButton("Exporter Excel…")
        self._btn_close = QPushButton("Fermer")

        btn_row.setToolTip("Coche toutes les cases de la ligne sélectionnée")
        btn_row.clicked.connect(self._check_selected_row)
        btn_coord.clicked.connect(lambda: self._check_all("coord", True))
        btn_oper.clicked.connect(lambda: self._check_all("oper", True))
        btn_reset.clicked.connect(lambda: self._check_all(None, False))
        self._btn_export.clicked.connect(self._on_export)
        self._btn_close.clicked.connect(self.accept)

        for btn in (btn_row, btn_coord, btn_oper, btn_reset):
            row.addWidget(btn)
        row.addStretch()
        row.addWidget(self._btn_export)
        row.addWidget(self._btn_close)
        root.addLayout(row)

    def _check_selected_row(self):
        """Coche toutes les cases de la ligne actuellement sélectionnée."""
        indexes = self._table.selectedIndexes()
        if not indexes:
            return
        tr = indexes[0].row()
        if tr == 0:  # ligne d'en-tête de groupe (row 0 = en-têtes de tubes)
            return
        instruction = self._instruction_rows.get(tr)
        if instruction is not None:
            key, _ = instruction
            cb = self._checks.get(key)
            if cb is not None:
                cb.blockSignals(True)
                cb.setEnabled(True)
                cb.setChecked(True)
                cb.blockSignals(False)
                self._refresh_highlights()
            return
        r_idx = self._r_idx_for_table_row.get(tr)
        if r_idx is None:
            return
        for key, cb in self._checks.items():
            if key[0] in ("verif", "coord", "oper") and key[1] == r_idx:
                cb.blockSignals(True)
                cb.setEnabled(True)
                cb.setChecked(True)
                cb.blockSignals(False)
        self._refresh_highlights()

    def _check_all(self, role: str | None, state: bool):
        """Coche ou décoche toutes les cases d'un rôle (ou toutes si role=None)."""
        # Bloquer les signaux pour éviter N rafraîchissements intermédiaires
        for key, cb in self._checks.items():
            if role is None or key[0] == role:
                cb.blockSignals(True)
                cb.setEnabled(True)  # temporairement pour pouvoir cocher
                cb.setChecked(state)
                cb.blockSignals(False)
        self._refresh_highlights()

    # ── Logique de guidage ──────────────────────────────────────────────────

    def _find_active(self) -> tuple | None:
        """Retourne la prochaine étape à compléter.

        Retourne :
          ("verif", r_idx)           — vérification solution non cochée
          ("tube",  r_idx, t_idx, role) — coord ou opér non coché pour ce tube
          ("instruction", key)        — consigne non cochée
          None                       — tout est terminé
        """
        for display_row in self._display_rows:
            if display_row[0] == "instruction":
                key = display_row[1]
                if not self._checks[key].isChecked():
                    return ("instruction", key)
                continue

            _, r_idx, _ = display_row
            if not self._checks[("verif", r_idx)].isChecked():
                return ("verif", r_idx)
            for t_idx in range(self._n_tubes):
                cb_c = self._checks[("coord", r_idx, t_idx)]
                cb_o = self._checks[("oper", r_idx, t_idx)]
                if not cb_c.isChecked():
                    return ("tube", r_idx, t_idx, "coord")
                if not cb_o.isChecked():
                    return ("tube", r_idx, t_idx, "oper")
        return None

    def _active_cols(self, active: tuple) -> set[int]:
        """Colonnes éclairées (0-based) pour l'étape active."""
        if active[0] == "verif":
            return {3}  # colonne Vérif.
        if active[0] == "instruction":
            return set(range(self._table.columnCount()))
        t_idx = active[2]
        role = active[3]
        base = _FIXED_COLS + t_idx * _SUBCOLS
        active_check = base + (_SUB_COORD if role == "coord" else _SUB_OPER)
        # Volume inclus pour montrer la quantité à pipeter, puis une seule case active.
        return {base + _SUB_VOL, active_check}

    def _refresh_highlights(self):
        """Met à jour l'ombrageage de toute la table selon l'étape courante."""
        active = self._find_active()
        n_cols = self._table.columnCount()
        self._table

        if active is None:
            # Tout terminé : tout éclairé
            self._lbl_step.setText("✓ Protocole complété !")
            for tr, r_idx in self._r_idx_for_table_row.items():
                for col in range(n_cols):
                    self._set_cell(tr, col, r_idx, dim=False, enabled=True)
            for tr, (key, kind) in self._instruction_rows.items():
                self._set_instruction_row(
                    tr, key, kind, dim=False, enabled=True)
            return

        active_r_idx = active[1] if active[0] != "instruction" else None
        active_cols = self._active_cols(active)

        # Texte de guidage
        if active[0] == "verif":
            react = self._df.iloc[active_r_idx].get(
                "Réactif", f"Ligne {active_r_idx + 1}"
            )
            self._lbl_step.setText(f"→ Vérifier la solution : {react}")
        elif active[0] == "instruction":
            text = self._instruction_labels.get(active[1], "Consigne")
            self._lbl_step.setText(f"→ {text}")
        else:
            react = self._df.iloc[active_r_idx].get(
                "Réactif", f"Ligne {active_r_idx + 1}"
            )
            tube = self._tubes[active[2]]
            role = "coordinateur" if active[3] == "coord" else "opérateur"
            self._lbl_step.setText(f"→ {react}  ·  {tube}  ·  validation {role}")

        for tr, r_idx in self._r_idx_for_table_row.items():
            same_row = r_idx == active_r_idx

            for col in range(n_cols):
                same_col = col in active_cols
                # Éclairé seulement si même ligne ET même colonne active
                lit = same_row and same_col
                enabled = lit
                dim = not lit
                self._set_cell(tr, col, r_idx, dim=dim, enabled=enabled)

        for tr, (key, kind) in self._instruction_rows.items():
            lit = active[0] == "instruction" and key == active[1]
            self._set_instruction_row(tr, key, kind, dim=not lit, enabled=lit)

    def _set_cell(self, tr: int, col: int, r_idx: int,
                  dim: bool, enabled: bool):
        """Applique ou retire l'ombrageage sur une cellule."""
        tbl = self._table

        # ── Cellule item ─────────────────────────────────────────────────────
        it = tbl.item(tr, col)
        if it is not None:
            if dim:
                it.setBackground(QBrush(_C_DIM_BG))
                it.setForeground(QBrush(_C_DIM_FG))
            else:
                normal_bg = _normal_item_bg(r_idx, col, _FIXED_COLS, _SUBCOLS)
                it.setBackground(QBrush(normal_bg))
                it.setForeground(QBrush(QColor("#000000")))

        # ── Cellule widget (checkbox) ────────────────────────────────────────
        w = self._c_widgets.get((tr, col))
        if w is not None:
            if dim:
                w.setStyleSheet(_SS_DIM)
            else:
                normal_bg = _normal_item_bg(r_idx, col, _FIXED_COLS, _SUBCOLS)
                w.setStyleSheet(f"background: {normal_bg.name()};")
            # Activer / désactiver la case
            cb = w.findChild(QCheckBox)
            if cb is not None:
                cb.setEnabled(enabled or cb.isChecked())

    def _set_instruction_row(
        self, tr: int, key: tuple, kind: str, dim: bool, enabled: bool
    ):
        """Applique l'état visuel d'une ligne de consigne."""
        bg = _C_DIM_BG if dim else (_C_WARN if kind == "warning" else _C_INSTR)
        fg = _C_DIM_FG if dim else (
            _C_WARN_FG if kind == "warning" else _C_INSTR_FG)

        for col in range(self._table.columnCount()):
            it = self._table.item(tr, col)
            if it is not None:
                it.setBackground(QBrush(bg))
                it.setForeground(QBrush(fg))

        w = self._c_widgets.get((tr, 0))
        if w is not None:
            w.setStyleSheet(_SS_DIM if dim else f"background: {bg.name()};")
            cb = w.findChild(QCheckBox)
            if cb is not None:
                cb.setEnabled(enabled or cb.isChecked())

    # ── Export ──────────────────────────────────────────────────────────────

    def get_states(self) -> dict:
        states = {k: cb.isChecked() for k, cb in self._checks.items()}
        states["__notes__"] = self._notes_edit.toPlainText()
        return states

    def _on_export(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Exporter la feuille de protocole",
            "",
            "Fichier Excel (*.xlsx)",
        )
        if not path:
            return
        try:
            protocol_export.export_protocol_excel(
                self._df,
                self._meta,
                path,
                states=self.get_states(),
                df_map=self._df_map,
                notes=self._notes_edit.toPlainText(),
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Erreur d'export", f"Impossible de générer la feuille :\n{e}"
            )
            return
        QMessageBox.information(
            self, "Export réussi", f"Feuille enregistrée dans :\n{path}"
        )
