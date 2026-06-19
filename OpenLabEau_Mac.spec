# -*- mode: python ; coding: utf-8 -*-
#
# Spec PyInstaller pour OpenLab'Eau — build macOS (.app).
#
# Utilisation :
#     pip install pyinstaller
#     pyinstaller OpenLabEau_Mac.spec
#
# Résultat : dist/OpenLab'Eau.app
#
# Remarques :
#  - L'application utilise QtWebEngine (cartes + graphiques Plotly) : le hook
#    PySide6 de PyInstaller embarque QtWebEngineProcess et ses ressources dans
#    le .app. On reste donc en mode "onedir" + BUNDLE (indispensable et fiable
#    pour WebEngine sur macOS).
#  - Seuls les assets nécessaires à l'exécution sont embarqués.
#  - L'icône du .app est openlabeau.icns.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# --- Données embarquées ---
datas = [
    ("assets/modele_tableau.xlsx", "assets"),
    ("assets/Openlabeau-logo-nom.svg", "assets"),
    ("assets/Openlabeau-logo-nom.png", "assets"),
    ("assets/Openlabeau-logo-seul.png", "assets"),
    ("assets/openlabeau_icons/openlabeau.ico", "assets/openlabeau_icons"),
    ("assets/openlabeau_icons/openlabeau.icns", "assets/openlabeau_icons"),
]
datas += collect_data_files("plotly")          # données du paquet plotly

# --- Imports parfois ratés par l'analyse statique ---
hiddenimports = []
hiddenimports += collect_submodules("sklearn")
hiddenimports += collect_submodules("pybaselines")
hiddenimports += collect_submodules("odf")

# --- Gros paquets présents dans l'environnement mais NON utilisés par l'app ---
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
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,          # None = arch de la machine de build (arm64 ou x86_64)
    codesign_identity=None,
    entitlements_file=None,
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

app = BUNDLE(
    coll,
    # Nom du fichier .app sans apostrophe (plus simple sur le disque) ; le nom
    # affiché dans le Finder vient de CFBundleDisplayName ci-dessous.
    name="OpenLabEau.app",
    icon="assets/openlabeau_icons/openlabeau.icns",
    bundle_identifier="org.citizensers.openlabeau",
    info_plist={
        "CFBundleName": "OpenLab'Eau",
        "CFBundleDisplayName": "OpenLab'Eau",
        "NSHighResolutionCapable": True,
        # QtWebEngine a besoin d'un accès réseau (cartes, CDN Plotly).
        "NSAppTransportSecurity": {"NSAllowsArbitraryLoads": True},
    },
)
