"""Chemins de ressources pour le mode source et le mode PyInstaller."""

from __future__ import annotations

import os
import sys


def app_root() -> str:
    """Dossier racine de l'app, compatible avec PyInstaller."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def asset_path(*parts: str) -> str:
    """Chemin absolu vers un fichier dans `assets/`."""
    return os.path.join(app_root(), "assets", *parts)
