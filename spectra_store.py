"""Magasin partagé des spectres chargés (porté de Ramanalyze-simple, adapté).

Les onglets d'analyse (Titration, Suivi de pic) lisent et écrivent ici, et se
synchronisent via deux signaux :
- `changed`      : l'ensemble des spectres a changé (ajout / retrait) ;
- `meta_changed` : les métadonnées (volume, série, réglages titrant) ont changé.

Dans OpenLab'Eau, l'ensemble des spectres est alimenté depuis l'onglet
« Fichiers Raman » via `sync_paths()`. Le tableau (volumes / séries / titrant)
peut aussi être enregistré et rechargé (JSON).
"""

import json
import os

from PySide6.QtCore import QObject, Signal

from spectrum_loader import load_spectrum


class SpectraStore(QObject):
    changed = Signal()       # ensemble des spectres modifié
    meta_changed = Signal()  # volumes / séries / réglages titrant modifiés

    def __init__(self):
        super().__init__()
        self.spectra: dict[str, tuple] = {}   # path -> (x, y)
        self.volumes: dict[str, str] = {}     # path -> volume de titrant (texte)
        self.series: dict[str, str] = {}      # path -> étiquette de série
        self.titrant: dict = {"conc": 1.0, "conc_unit": "µM", "vol_unit": "µL"}
        # métadonnées d'un tableau chargé dont le fichier était introuvable,
        # appliquées par NOM quand l'utilisateur rechargera le .txt
        self._pending_meta: dict[str, tuple] = {}

    # ------------------------------------------------------------------
    def add(self, path: str, data: tuple) -> None:
        is_new = path not in self.spectra
        self.spectra[path] = data
        if is_new:
            self.volumes.setdefault(path, "")
            self.series.setdefault(path, "")
            meta = self._pending_meta.pop(self.name(path), None)
            if meta is not None:
                self.volumes[path] = meta[0]
                self.series[path] = meta[1]
        self.changed.emit()

    def remove(self, path: str) -> None:
        self.spectra.pop(path, None)
        self.volumes.pop(path, None)
        self.series.pop(path, None)
        self.changed.emit()

    def clear(self) -> None:
        self.spectra.clear()
        self.volumes.clear()
        self.series.clear()
        self._pending_meta.clear()
        self.changed.emit()

    def paths(self) -> list[str]:
        return list(self.spectra.keys())

    @staticmethod
    def name(path: str) -> str:
        return os.path.basename(path)

    # ------------------------------------------------------------------
    def sync_paths(self, paths: list[str]) -> list[str]:
        """Aligne l'ensemble des spectres sur `paths` (depuis « Fichiers Raman »).

        Charge les nouveaux, retire ceux qui ne sont plus sélectionnés, et
        conserve volumes/séries des fichiers gardés. Renvoie la liste des
        fichiers non lisibles.
        """
        wanted = list(dict.fromkeys(paths))  # dédoublonne en gardant l'ordre
        failed: list[str] = []

        # Retirer ceux qui ne sont plus voulus
        for p in self.paths():
            if p not in wanted:
                self.spectra.pop(p, None)
                self.volumes.pop(p, None)
                self.series.pop(p, None)

        # Ajouter / garder, dans l'ordre voulu
        ordered: dict[str, tuple] = {}
        for p in wanted:
            data = self.spectra.get(p)
            if data is None:
                data = load_spectrum(p)
                if data is None:
                    failed.append(self.name(p))
                    continue
            ordered[p] = data
            self.volumes.setdefault(p, "")
            self.series.setdefault(p, "")
            meta = self._pending_meta.pop(self.name(p), None)
            if meta is not None:
                self.volumes[p] = meta[0]
                self.series[p] = meta[1]
        self.spectra = ordered
        self.changed.emit()
        return failed

    # ------------------------------------------------------------------
    def save_session(self, path: str) -> None:
        data = {
            "titrant": self.titrant,
            "rows": [
                {
                    "path": p,
                    "name": self.name(p),
                    "volume": self.volumes.get(p, ""),
                    "serie": self.series.get(p, ""),
                }
                for p in self.paths()
            ],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_session(self, path: str) -> list[str]:
        """Recharge un tableau enregistré. Réimporte les spectres si les fichiers
        existent encore. Renvoie la liste des fichiers introuvables."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "rows" not in data:
            raise ValueError(
                "Fichier JSON non reconnu : ce n'est pas un tableau de titration."
            )
        if isinstance(data.get("titrant"), dict):
            self.titrant.update(data["titrant"])

        by_name = {}
        for q in self.spectra:
            by_name.setdefault(self.name(q), q)

        missing = []
        for row in data.get("rows", []):
            if not isinstance(row, dict):
                continue
            p = row.get("path", "")
            if not p:
                continue
            name = row.get("name") or os.path.basename(p)
            volume = row.get("volume", "")
            serie = row.get("serie", "")

            if p in self.spectra:
                target = p
            elif os.path.exists(p):
                spec = load_spectrum(p)
                if spec is None:
                    self._pending_meta[name] = (volume, serie)
                    missing.append(name)
                    continue
                self.spectra[p] = spec
                target = p
            elif name in by_name:
                target = by_name[name]
            else:
                self._pending_meta[name] = (volume, serie)
                missing.append(name)
                continue

            self.volumes[target] = volume
            self.series[target] = serie
        self.changed.emit()
        return missing
