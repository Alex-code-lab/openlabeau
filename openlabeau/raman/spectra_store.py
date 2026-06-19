"""Magasin partagé des spectres Raman chargés.

Dans OpenLab'Eau, les spectres viennent de l'onglet « Fichiers Raman ». Le store
ne conserve donc que la liste synchronisée des fichiers et les tableaux x/y
chargés, puis prévient les onglets dépendants via `changed`.
"""

import os

from PySide6.QtCore import QObject, Signal

from openlabeau.raman.spectrum_loader import load_spectrum


class SpectraStore(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.spectra: dict[str, tuple] = {}

    def paths(self) -> list[str]:
        return list(self.spectra.keys())

    @staticmethod
    def name(path: str) -> str:
        return os.path.basename(path)

    # ------------------------------------------------------------------
    def sync_paths(self, paths: list[str]) -> list[str]:
        """Aligne l'ensemble des spectres sur `paths` (depuis « Fichiers Raman »).

        Charge les nouveaux, retire ceux qui ne sont plus sélectionnés, et
        renvoie la liste des fichiers non lisibles.
        """
        wanted = list(dict.fromkeys(paths))
        failed: list[str] = []

        ordered: dict[str, tuple] = {}
        for p in wanted:
            data = self.spectra.get(p)
            if data is None:
                data = load_spectrum(p)
                if data is None:
                    failed.append(self.name(p))
                    continue
            ordered[p] = data
        self.spectra = ordered
        self.changed.emit()
        return failed
