"""Génère les captures d'écran du guide bénévoles OpenLab'Eau.

À relancer après une modification de l'interface, pour garder le PDF à jour.

  python "docs/Documentation pour bénévoles/captures_openlabeau/generer_captures.py"

Il faut PySide6 et kaleido installés dans l'environnement :
  python -m pip install kaleido

Les graphes (Visualiseur, Analyse) utilisent de vrais spectres .txt.
Adaptez le chemin SAMP ci-dessous à un jeu de spectres présent sur la machine.
Le graphe Analyse est illustratif : il trace la hauteur de pics réels en
fonction d'un axe de titrant d'exemple, avec sigmoïde et point d'équivalence.

La feuille de protocole n'est pas générée ici (il faut un tableau de volumes) :
faites cette capture à la main depuis le logiciel si vous la voulez.
"""

import glob
import os
import sys

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# --- Chemins -----------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))   # racine du dépôt
sys.path.insert(0, ROOT)
OUT = HERE

# Jeu de spectres .txt d'exemple (à adapter à votre machine).
SAMP = ("/Users/souchaud/Documents/Travail/CitizenSers/02_Spectroscopie/Data_Angelina/"
        "fichiers spectres AN335_and_AN341_laser_532nm_500nM_copper_variation_of_PAN_"
        "all_data_corrected_serie_11_points_spectres_txt")
SERIE = sorted(glob.glob(os.path.join(SAMP, "AN335_*.txt")))[:11]


def save(pm, name):
    ok = pm.save(os.path.join(OUT, name))
    print(f"  [{'OK' if ok else 'FAIL'}] {name}  {pm.width()}x{pm.height()}")
    return ok


# =============================================================================
# 1) Captures d'interface (Qt, hors écran)
# =============================================================================
def captures_interface():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QDate, QTime, QPoint
    import main as appmain

    app = QApplication.instance() or QApplication(sys.argv)
    appmain._apply_consistent_theme(app)

    win = appmain.MainWindow()
    win.resize(1160, 800)
    win.show()                                   # force le layout hors écran
    win.tabs.tabBar().setUsesScrollButtons(False)
    for _ in range(4):
        app.processEvents()
    mc = win.metadata_creator
    tabs = win.tabs

    def crop_tabbar(name):
        full = win.grab()
        tb = tabs.tabBar()
        vis = [i for i in range(tabs.count()) if tabs.isTabVisible(i)]
        r = tb.tabRect(max(vis))
        tl = tb.mapTo(win, QPoint(0, 0))
        w = tl.x() + r.x() + r.width() + 6
        h = tl.y() + tb.height() + 2
        save(full.copy(0, 0, int(w), int(h)), name)

    def try_set(fn):
        try:
            fn()
        except Exception as e:                   # noqa: BLE001
            print("   champ ignoré :", e)

    # Remplir quelques champs (fiche « stylée », sans titration)
    try_set(lambda: mc.edit_sampler.setText("Denis Jacquet"))
    try_set(lambda: mc.edit_sampler_association.setText("CitizenSers"))
    try_set(lambda: mc.edit_sample_date.setDate(QDate(2026, 4, 30)))
    try_set(lambda: mc.edit_sample_time.setTime(QTime(14, 0)))
    try_set(lambda: mc.edit_sample_lat.setText("46.548861"))
    try_set(lambda: mc.edit_sample_lon.setText("0.368861"))
    try_set(lambda: mc.combo_water_type.setCurrentIndex(1))      # Eau douce
    try_set(lambda: mc.spin_water_temperature.setValue(14.5))
    try_set(lambda: mc.spin_air_temperature.setValue(18.0))
    for _ in range(3):
        app.processEvents()

    tabs.setCurrentIndex(0)
    app.processEvents()
    save(win.grab(), "ov_fenetre.png")           # vue d'ensemble (Présentation)
    crop_tabbar("onglets_base.png")              # 2 onglets
    save(mc.grab(), "fiche_terrain.png")         # fiche remplie

    mc.chk_titration_done.setChecked(True)       # révèle 3 onglets
    for _ in range(3):
        app.processEvents()
    crop_tabbar("onglets_titration.png")         # 5 onglets

    win.file_picker.restore_selected_files(SERIE)
    for _ in range(3):
        app.processEvents()
    tabs.setCurrentWidget(win.file_tab)
    app.processEvents()
    save(win.file_tab.grab(), "fichiers_raman.png")


# =============================================================================
# 2) Graphes (Plotly -> PNG via kaleido)
# =============================================================================
def captures_graphes():
    import plotly.graph_objects as go
    from plotly.colors import qualitative
    from openlabeau.raman.spectrum_loader import load_spectrum
    from openlabeau.style import plot_style as ps

    spectra = []
    for p in SERIE:
        xy = load_spectrum(p)
        if xy is not None:
            spectra.append((os.path.basename(p), xy[0], xy[1]))
    if not spectra:
        print("  Aucun spectre lu : vérifiez SAMP.")
        return

    # Visualiseur : style de l'onglet (plotly_white)
    fig = go.Figure()
    for name, x, y in spectra:
        fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name=name,
                                 line=dict(width=1.6)))
    fig.update_layout(
        title="Spectres Raman", xaxis_title="Décalage Raman (cm⁻¹)",
        yaxis_title="Intensité (a.u.)", legend_title="Fichiers",
        template="plotly_white", margin=dict(l=60, r=20, t=50, b=50))
    fig.write_image(os.path.join(OUT, "visualiseur.png"),
                    width=1100, height=620, scale=2)
    print("  [OK] visualiseur.png")

    # Analyse : style de l'onglet (ps.apply / simple_white)
    def height(x, y, c, tol=6.0):
        m = np.abs(x - c) <= tol
        return float(np.max(y[m])) if m.any() else np.nan

    centers = [1364.0, 1224.0]
    x_tit = np.linspace(0.0, 2.0, len(spectra))
    fig2 = go.Figure()
    palette = qualitative.Plotly
    x_eq = None
    for i, c in enumerate(centers):
        col = palette[i % len(palette)]
        h = np.array([height(x, y, c) for _, x, y in spectra])
        fig2.add_trace(go.Scatter(x=x_tit, y=h, mode="lines+markers",
                                  name=f"pic {c:.0f} cm⁻¹",
                                  line=dict(width=1.6, color=col),
                                  marker=ps.marker(col, i)))
        if i == 0:
            try:
                from scipy.optimize import curve_fit

                def sig(xx, a, b, x0, k):
                    return a + (b - a) / (1.0 + np.exp(-k * (xx - x0)))

                popt, _ = curve_fit(
                    sig, x_tit, h,
                    p0=[np.nanmin(h), np.nanmax(h), np.median(x_tit), 3.0],
                    maxfev=20000)
                xs = np.linspace(x_tit.min(), x_tit.max(), 200)
                fig2.add_trace(go.Scatter(x=xs, y=sig(xs, *popt), mode="lines",
                                          name=f"ajustement pic {c:.0f}",
                                          line=dict(width=1.4, color=col, dash="dash")))
                a, b, x0, k = popt
                x_eq = x0 + np.log(0.95 / 0.05) / k
            except Exception as e:               # noqa: BLE001
                print("  sigmoïde non ajustée :", e)

    ps.apply(fig2, title="Suivi des pics vs quantité de titrant ajoutée",
             x_title="Quantité de titrant ajoutée (× 10⁻⁹ mol)",
             y_title="Hauteur du pic (a.u.)", legend_title="Pics suivis")
    if x_eq is not None and np.isfinite(x_eq):
        fig2.add_vline(x=float(x_eq), line=dict(color="#c0392b", width=1.6, dash="dot"))
        fig2.add_annotation(x=float(x_eq), yref="paper", y=1.0, showarrow=False,
                            text=f"équivalence ≈ {x_eq:.2f}",
                            font=dict(color="#c0392b"), xanchor="left", xshift=6)
    fig2.write_image(os.path.join(OUT, "analyse.png"),
                     width=1100, height=620, scale=2)
    print("  [OK] analyse.png")


if __name__ == "__main__":
    print("Interface…")
    captures_interface()
    print("Graphes…")
    captures_graphes()
    print("Terminé. Recompilez ensuite le PDF : latexmk -pdf guide_benevoles.tex")
