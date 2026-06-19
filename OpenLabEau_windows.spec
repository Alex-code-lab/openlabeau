# -*- mode: python ; coding: utf-8 -*-
#
# Spec PyInstaller pour OpenLab'Eau — build Windows (mode dossier "onedir").
#
# Utilisation :
#     pip install pyinstaller
#     pyinstaller OpenLabEau_windows.spec
#
# Résultat : dist/OpenLabEau/OpenLabEau.exe (+ ses dépendances).
#
# Remarques :
#  - L'application utilise QtWebEngine (cartes + graphiques Plotly) : le hook
#    PySide6 de PyInstaller embarque automatiquement QtWebEngineProcess et ses
#    ressources. On reste donc en mode "onedir" (plus fiable que onefile avec
#    WebEngine).
#  - Le dossier "assets" (logos, icônes, modele_tableau.xlsx) est embarqué tel
#    quel : le code y accède via sys._MEIPASS/assets/... en mode gelé.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# --- Données embarquées ---
datas = [("assets", "assets")]
datas += collect_data_files("plotly")          # données du paquet plotly

# --- Imports parfois ratés par l'analyse statique ---
hiddenimports = []
hiddenimports += collect_submodules("sklearn")
hiddenimports += collect_submodules("pybaselines")
hiddenimports += collect_submodules("odf")

# --- Gros paquets présents dans l'environnement mais NON utilisés par l'app ---
# On les exclut pour éviter un build énorme.
excludes = [
    "tkinter", "matplotlib", "torch", "cupy", "dask", "distributed",
    "numba", "skimage", "IPython", "jupyter", "notebook", "ipykernel",
    "pytest", "sphinx", "black", "flake8", "mypy", "isort",
    "polars", "duckdb", "pyarrow", "ibis",
    "PyQt5", "PyQt6", "PySide2",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OpenLabEau",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX désactivé : il corrompt parfois les DLL Qt
    console=False,             # application fenêtrée (pas de console)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["assets/openlabeau_icons/openlabeau.ico"],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="OpenLabEau",
)
