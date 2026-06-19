import os

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_SETTINGS_KEY = "file_picker/last_dir"


def _default_dir() -> str:
    settings = QSettings("Ramanalyze", "Ramanalyze")
    saved = settings.value(_SETTINGS_KEY, "")
    if saved and os.path.isdir(saved):
        return saved
    return os.path.expanduser("~")


class FilePickerWidget(QWidget):
    selection_changed = Signal(bool)

    """Sélection des fichiers .txt de spectres Raman.

    On s'appuie sur la fenêtre de fichiers du système d'exploitation (la même
    que partout ailleurs sur l'ordinateur) : un seul bouton « Choisir des
    fichiers… ». Les fichiers retenus sont listés à l'écran et accessibles via
    `self.selected_files` ou `get_selected_files()`.
    """

    def __init__(self, parent=None, start_dir: str | None = None):
        super().__init__(parent)
        self.selected_files: list[str] = []
        self._start_dir = start_dir or _default_dir()

        # ---------- Instruction ----------
        instructions = QLabel(
            "<b>Vos fichiers de spectres Raman (.txt)</b><br>"
            "Cliquez sur le bouton ci-dessous pour les choisir dans votre "
            "ordinateur. Vous pouvez en sélectionner plusieurs à la fois.",
            self,
        )
        instructions.setWordWrap(True)

        # ---------- Bouton principal : fenêtre de fichiers du système ----------
        self.btn_browse = QPushButton(
            "📂  Choisir des fichiers Raman (.txt)…", self)
        self.btn_browse.setStyleSheet(
            "background-color: #0057b8; color: white; font-weight: 700;"
            " padding: 8px 16px;"
        )
        self.btn_browse.setToolTip(
            "Ouvre la fenêtre de fichiers de votre ordinateur."
        )
        self.btn_browse.clicked.connect(self._browse_native)

        # ---------- Liste des fichiers retenus ----------
        self.selected_list_widget = QListWidget(self)
        self.selected_list_widget.setSelectionMode(
            QAbstractItemView.ExtendedSelection)

        self.btn_remove = QPushButton("Retirer la sélection", self)
        self.btn_remove.clicked.connect(self._remove_selected_from_list)
        self.btn_clear = QPushButton("Vider la liste", self)
        self.btn_clear.clicked.connect(self.clear_selected)
        list_btns = QHBoxLayout()
        list_btns.addWidget(self.btn_remove)
        list_btns.addWidget(self.btn_clear)
        list_btns.addStretch(1)

        # ---------- Info ----------
        self.info = QLabel("0 fichier sélectionné", self)

        # ---------- Layout principal ----------
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(instructions)
        main_layout.addWidget(self.btn_browse)
        main_layout.addWidget(QLabel("Fichiers sélectionnés :", self))
        main_layout.addWidget(self.selected_list_widget, 1)
        main_layout.addLayout(list_btns)
        main_layout.addWidget(self.info)

    # ---------- Sélection ----------
    def _browse_native(self):
        """Ouvre la fenêtre de fichiers du système pour choisir des .txt."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Choisir des fichiers de spectres (.txt)",
            self._start_dir,
            "Spectres Raman (*.txt)",
        )
        if not files:
            return
        # Mémorise le dossier pour la prochaine ouverture.
        folder = os.path.dirname(files[0])
        if os.path.isdir(folder):
            self._start_dir = folder
            QSettings("Ramanalyze", "Ramanalyze").setValue(_SETTINGS_KEY, folder)
        self._add_paths(files)

    def _add_paths(self, paths: list[str]) -> None:
        """Ajoute des fichiers .txt à la liste interne (dédoublonnés)."""
        added = False
        for path in paths:
            if (
                os.path.isfile(path)
                and path.lower().endswith(".txt")
                and path not in self.selected_files
            ):
                self.selected_files.append(path)
                added = True
        if added:
            self._notify_count()
            self._refresh_selected_list()

    def _notify_count(self):
        n = len(self.selected_files)
        if n == 0:
            self.info.setText("0 fichier sélectionné")
        else:
            self.info.setText(f"{n} fichier(s) prêt(s) à tracer")
        self.selection_changed.emit(n > 0)

    def clear_selected(self):
        self.selected_files.clear()
        self._notify_count()
        self.selected_list_widget.clear()

    def _refresh_selected_list(self):
        self.selected_list_widget.clear()
        for file_path in self.selected_files:
            item = QListWidgetItem(os.path.basename(file_path))
            item.setToolTip(file_path)
            item.setData(Qt.UserRole, file_path)
            self.selected_list_widget.addItem(item)

    def _remove_selected_from_list(self):
        for item in self.selected_list_widget.selectedItems():
            file_path = item.data(Qt.UserRole) or item.text()
            if file_path in self.selected_files:
                self.selected_files.remove(file_path)
            self.selected_list_widget.takeItem(
                self.selected_list_widget.row(item))
        self._notify_count()

    # Accès externe optionnel
    def get_selected_files(self) -> list[str]:
        return list(self.selected_files)
