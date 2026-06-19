import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStatusBar,
    QStyle,
    QStyleOptionTab,
    QStylePainter,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# S'assurer que les imports de modules frères fonctionnent quel que soit l'endroit
# d'où on lance le script.
# En mode PyInstaller onefile, sys._MEIPASS pointe vers le dossier d'extraction
# temporaire où tous les fichiers data sont copiés.
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    APP_DIR = sys._MEIPASS
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from analysis_tab import AnalysisTab
from file_picker import FilePickerWidget
from metadata_creator import MetadataCreatorWidget
from viewer_tab import SpectraViewerTab


class WorkflowStatusTabBar(QTabBar):
    """QTabBar avec fond rouge/vert pour certains onglets de workflow."""

    _ACTIVE_EXTRA_WIDTH = 24
    _ACTIVE_EXTRA_HEIGHT = 8
    _ACTIVE_BORDER_COLOR = "#f4f4f4"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._status_colors: dict[int, str] = {}
        self.currentChanged.connect(self._refresh_active_tab)

    def tabSizeHint(self, index: int):
        size = super().tabSizeHint(index)
        if index == self.currentIndex():
            size.setWidth(size.width() + self._ACTIVE_EXTRA_WIDTH)
            size.setHeight(size.height() + self._ACTIVE_EXTRA_HEIGHT)
        return size

    def _refresh_active_tab(self, index: int) -> None:
        self.updateGeometry()
        self.update()

    def set_tab_status_color(self, index: int, color_hex: str | None) -> None:
        if color_hex:
            self._status_colors[index] = color_hex
        else:
            self._status_colors.pop(index, None)
        if 0 <= index < self.count():
            self.update(self.tabRect(index))

    def paintEvent(self, event) -> None:
        painter = QStylePainter(self)

        for index in range(self.count()):
            option = QStyleOptionTab()
            self.initStyleOption(option, index)
            color_hex = self._status_colors.get(index)
            if not color_hex:
                if option.state & QStyle.StateFlag.State_Selected:
                    self._draw_colored_tab(painter, option, QColor("#666666"))
                else:
                    painter.drawControl(
                        QStyle.ControlElement.CE_TabBarTab, option)
                continue

            color = QColor(color_hex)
            if option.state & QStyle.StateFlag.State_Selected:
                color = color.lighter(115)

            self._draw_colored_tab(painter, option, color)

    def _draw_colored_tab(
        self, painter: QStylePainter, option: QStyleOptionTab, color: QColor
    ) -> None:
        rect = option.rect.adjusted(1, 1, -1, -1)
        painter.save()
        painter.setPen(color.darker(125))
        painter.setBrush(color)
        painter.drawRoundedRect(rect, 4, 4)
        painter.restore()

        if option.state & QStyle.StateFlag.State_Selected:
            self._draw_active_frame(painter, option)

        self._draw_tab_label(
            painter,
            option,
            QColor("#ffffff"),
            bold=bool(option.state & QStyle.StateFlag.State_Selected),
        )

    def _draw_active_frame(
        self, painter: QStylePainter, option: QStyleOptionTab
    ) -> None:
        rect = option.rect.adjusted(0, 0, -1, -1)
        painter.save()
        painter.setPen(QColor(self._ACTIVE_BORDER_COLOR))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 5, 5)
        painter.restore()

    def _draw_tab_label(
        self,
        painter: QStylePainter,
        option: QStyleOptionTab,
        text_color: QColor | None = None,
        *,
        bold: bool = False,
    ) -> None:
        if text_color is not None:
            option.palette.setColor(QPalette.ColorRole.WindowText, text_color)
            option.palette.setColor(QPalette.ColorRole.ButtonText, text_color)
            option.palette.setColor(QPalette.ColorRole.Text, text_color)

        painter.save()
        if bold:
            font = painter.font()
            font.setBold(True)
            painter.setFont(font)
        painter.drawControl(QStyle.ControlElement.CE_TabBarTabLabel, option)
        painter.restore()


def _render_svg_pixmap(svg_path: str, height: int, dpr: float):
    """Rend un SVG en QPixmap net pour l'écran (gère le HiDPI/Retina).

    On dessine à la résolution physique (height × dpr) puis on fixe le
    devicePixelRatio, pour que l'image reste nette sur écran Retina sans être
    ré-agrandie par le système. Renvoie None si le SVG est invalide.
    """
    renderer = QSvgRenderer(svg_path)
    if not renderer.isValid():
        return None
    size = renderer.defaultSize()
    if size.height() <= 0:
        return None
    width = round(height * size.width() / size.height())
    image = QImage(
        round(width * dpr), round(height * dpr), QImage.Format.Format_ARGB32
    )
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OpenLab'Eau — mesure citoyenne de la qualité de l'eau")
        self.resize(1200, 800)
        # Taille de départ confortable (1200x800), mais l'utilisateur·ice peut
        # réduire la fenêtre s'il/elle le souhaite (ex. côte à côte avec une
        # autre appli). En dessous de la largeur du contenu, un défilement
        # horizontal apparaît au besoin (voir l'onglet « Ma fiche terrain »).
        self.setMinimumSize(800, 520)

        # --- Status bar ---
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Prêt")

        # --- Conteneur principal ---
        central_widget = QWidget(self)
        central_layout = QVBoxLayout(central_widget)
        self.setCentralWidget(central_widget)

        # --- Onglets ---
        tabs = QTabWidget(self)
        tabs.setTabBar(WorkflowStatusTabBar(tabs))
        self.tabs = tabs
        central_layout.addWidget(tabs)

        # Onglet Présentation (instructions d'utilisation)
        self.presentation_tab = QWidget(self)
        pres_layout = QVBoxLayout(self.presentation_tab)

        # --- Bandeau d'accueil (hero) : bandeau bleu, logo posé sur une carte
        #     blanche (le logo est bleu foncé, il ressort mieux sur blanc). ---
        header = QFrame(self.presentation_tab)
        header.setObjectName("presHeader")
        header.setStyleSheet(
            "#presHeader { background-color: #1f4e79; border-radius: 14px; }"
        )
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 18, 20, 18)
        header_layout.setSpacing(10)

        logo_card = QFrame(header)
        logo_card.setObjectName("logoCard")
        logo_card.setStyleSheet(
            "#logoCard { background-color: #ffffff; border-radius: 12px; }"
        )
        logo_card_layout = QVBoxLayout(logo_card)
        logo_card_layout.setContentsMargins(26, 14, 26, 14)

        # Logo net : rendu vectoriel (SVG) à la résolution de l'écran.
        screen = QApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 1.0
        logo_height = 120
        logo_pixmap = _render_svg_pixmap(
            os.path.join(APP_DIR, "assets", "Openlabeau-logo-nom.svg"),
            logo_height,
            dpr,
        )
        if logo_pixmap is None:
            # Repli PNG (rendu DPI-aware pour rester net sur Retina)
            png = QPixmap(
                os.path.join(APP_DIR, "assets", "Openlabeau-logo-nom.png"))
            if not png.isNull():
                png = png.scaledToHeight(
                    round(logo_height * dpr), Qt.SmoothTransformation)
                png.setDevicePixelRatio(dpr)
                logo_pixmap = png

        if logo_pixmap is not None and not logo_pixmap.isNull():
            logo_label = QLabel(logo_card)
            logo_label.setPixmap(logo_pixmap)
            logo_label.setAlignment(Qt.AlignCenter)
            logo_label.setStyleSheet("background: transparent;")
            logo_card_layout.addWidget(logo_label)
        else:
            # Repli texte si l'image est introuvable
            title_label = QLabel("OpenLab'Eau", logo_card)
            title_label.setAlignment(Qt.AlignCenter)
            title_label.setStyleSheet(
                "color: #1f4e79; font-size: 32px; font-weight: 800;"
                " background: transparent;"
            )
            logo_card_layout.addWidget(title_label)

        # Centrer la carte blanche sans l'étirer sur toute la largeur.
        logo_row = QHBoxLayout()
        logo_row.addStretch(1)
        logo_row.addWidget(logo_card)
        logo_row.addStretch(1)
        header_layout.addLayout(logo_row)

        subtitle_label = QLabel(
            "Mesurer et tracer la qualité de l'eau, ensemble.", header
        )
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setStyleSheet(
            "color: #cfe0f5; font-size: 14px; background: transparent;"
        )
        header_layout.addWidget(subtitle_label)

        pres_layout.addWidget(header)

        scroll = QScrollArea(self.presentation_tab)
        scroll.setWidgetResizable(True)
        container = QWidget()
        container_layout = QVBoxLayout(container)

        # Guide détaillé, affiché à la demande dans une fenêtre dédiée
        # (lien « Ouvrir le guide complet » en bas de la page d'accueil).
        self._full_guide_html = """
<style>
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
    color: #2b2b2b;
    max-width: 860px;
  }
  h2 { color: #1f4e79; margin-top: 6px; margin-bottom: 8px; }
  h3 { color: #2f75b5; margin-top: 22px; margin-bottom: 6px; border-bottom: 1px solid #d0d7de; padding-bottom: 3px; }
  h4 { color: #2f75b5; margin-top: 16px; margin-bottom: 4px; }
  p  { line-height: 1.6; margin-bottom: 8px; }
  ul, ol { margin-left: 20px; }
  li { margin-bottom: 5px; line-height: 1.5; }
  .key    { font-weight: 700; color: #c0392b; }
  .accent { font-weight: 600; color: #2f75b5; }
  .warn   { font-weight: 600; color: #c0392b; }
  .ok     { font-weight: 600; color: #2e7d32; }
  .mono   { font-family: Menlo, Consolas, "Courier New", monospace; font-size: 0.92em;
            background: #eef1f4; color: #1f3b57; padding: 1px 4px; border-radius: 3px; }
  .note   { border-left: 4px solid #2f75b5; background: #eaf2fb;
            padding: 8px 12px; margin: 12px 0; border-radius: 0 4px 4px 0; color: #243b53; }
  .warn-box { border-left: 4px solid #e07b00; background: #fff4e5;
              padding: 8px 12px; margin: 12px 0; border-radius: 0 4px 4px 0; color: #6b4e00; }
  table { border-collapse: collapse; margin: 8px 0; }
  td, th { border: 1px solid #d0d7de; padding: 5px 10px; font-size: 0.93em; }
  th { background: #eef1f4; color: #1f3b57; font-weight: 600; }
</style>

<h2>Guide complet — OpenLab'Eau</h2>

<p>
  <span class="key">OpenLab'Eau</span> rassemble au même endroit la traçabilité du
  prélèvement, les mesures de terrain, les analyses complémentaires et, si elle est
  réalisée, la titration du cuivre suivie par spectroscopie Raman/SERS. Ce guide
  détaille chaque onglet&nbsp;; prenez ce dont vous avez besoin, dans l'ordre qui
  vous convient.
</p>

<div class="note">
  <b style="color:#1f4e79">Guidage visuel :</b>
  les champs <span class="warn">rouges</span> sont à renseigner, les champs
  <span class="ok">verts</span> sont remplis. Les boutons rouges signalent une
  étape à préparer ou à valider ; les boutons verts indiquent une étape prête.
</div>

<h3>Parcours recommandé</h3>
<ol>
  <li><span class="key">Ma fiche terrain</span> - créez ou rechargez la fiche, puis enregistrez le fichier <span class="mono">.xlsx</span>.</li>
  <li><span class="key">Fichiers Raman</span> - ajoutez les fichiers <span class="mono">.txt</span> si une acquisition Raman/SERS a été réalisée.</li>
  <li><span class="key">Spectres</span> - contrôlez visuellement les spectres et la correction de baseline.</li>
  <li><span class="key">Analyse</span> - choisissez la longueur d'onde du spectromètre, ajustez les ratios et lancez l'ajustement mathématique de la courbe.</li>
</ol>

<h3>1 - Onglet « Ma fiche terrain »</h3>

<h4>Charger ou créer une fiche</h4>
<p>
  Le bouton <b>Charger une fiche...</b> est placé en haut pour reprendre
  une fiche existante. Sinon, remplissez les sections de haut en bas.
  Le bouton <b>Enregistrer la fiche...</b> reste en bas de page et propose
  automatiquement un nom de fichier basé sur le nom du prélèvement :
  <span class="mono">NomPrelevement_T_AnBa_TAm.xlsx</span>.
</p>
<ul>
  <li><span class="mono">_T</span> est ajouté si la titration du cuivre est cochée.</li>
  <li><span class="mono">_AnBa</span> est ajouté si les analyses bactériologiques sont cochées.</li>
  <li><span class="mono">_TAm</span> est ajouté si le test ammonium est coché.</li>
  <li><span class="mono">_Tur</span> est ajouté si la turbidité est mesurée.</li>
  <li><span class="mono">_Cond</span> est ajouté si la conductivité est mesurée.</li>
  <li><span class="mono">_pH</span> est ajouté si le pH de l'eau est mesuré.</li>
  <li><span class="mono">_Ox</span> est ajouté si l'oxygène dissous est mesuré.</li>
</ul>

<div class="note">
  <b style="color:#1f4e79">Noms générés automatiquement :</b><br>
  <ul style="margin-top:6px">
    <li>
      <span class="key">Nom du prélèvement</span> :
      <span class="mono">PRE_&lt;initiales&gt;_AAAAMMJJ_HHhMM</span><br>
      Les initiales sont celles de chaque préleveur·se (1<sup>re</sup> lettre du prénom + 1<sup>re</sup> lettre du nom, concaténées).<br>
      Exemple avec deux préleveur·ses « Denis Jacquet » et « Alice Martin » :
      <span class="mono">PRE_DJAM_20260430_14h00</span>
    </li>
    <li style="margin-top:8px">
      <span class="key">Nom de la manip de titration</span> :
      <span class="mono">&lt;initiales opérateur&gt;&lt;initiales coordinateur&gt;_AAAAMMJJ_HHhMM</span><br>
      Exemple : <span class="mono">DJAM_20260430_09h30</span>
    </li>
  </ul>
  Ces noms apparaissent dans tous les exports et dans la correspondance spectres ↔ tubes.
  <b>Assurez-vous qu'ils sont uniques avant d'enregistrer</b> — traitez-les comme le code-barres de votre session.
  Le bouton <b>Modifier</b> (titration uniquement) permet de saisir un nom manuel.
</div>

<h4>Prélèvement de l'échantillon</h4>
<ul>
  <li>Chaque préleveur·se est saisi·e au format <b>Prénom puis nom</b>, avec son association sur la même ligne.</li>
  <li>Le bouton <b>+1 préleveur·se</b> ajoute une personne et une association supplémentaires.</li>
  <li>La date et l'heure du prélèvement sont vides au départ ; elles passent au vert lorsqu'elles sont renseignées.</li>
  <li>Le <b>nom du prélèvement</b> (<span class="mono">PRE_…</span>) est généré automatiquement dès que les initiales et la date/heure sont renseignées.</li>
  <li>Latitude et longitude acceptent les degrés décimaux ou les coordonnées GPS issues d'une carte.</li>
  <li>Le bouton <b>Carte / pointer...</b> permet de placer le point sur une carte interne quand le composant web est disponible.</li>
  <li>Si Internet est disponible, département et commune sont proposés automatiquement depuis les coordonnées GPS ; ils restent modifiables à la main.</li>
</ul>

<h4>Contexte terrain</h4>
<ul>
  <li><b>Type d'eau</b> reste rouge tant qu'aucun choix n'est fait.</li>
  <li>Pour <b>eau de mer</b> ou <b>eau estuarienne</b>, le coefficient de marée et l'heure de pleine mer apparaissent.</li>
  <li>Pour <b>eau douce</b>, un champ <b>Débit (m³/s)</b> apparaît pour renseigner le débit du cours d'eau (la méthode de mesure est laissée à votre appréciation).</li>
  <li>Température de l'eau, météo, température de l'air, pluie sur 24 h et commentaire décrivent les conditions de prélèvement.</li>
</ul>

<h4>Mesures effectuées</h4>
<ul>
  <li><b>Test ammonium réalisé</b> ouvre une fenêtre pour le test grossier, le test précis, le pH et la personne qui réalise le test.</li>
  <li><b>Analyses bactériologiques</b> affiche le jour de dépôt, l'heure de dépôt, l'entreprise de mesure et les résultats E. coli / entérocoques si disponibles.</li>
  <li><b>Titration</b> est cochée uniquement si une titration est prévue ou réalisée. Elle reste en dessous des autres mesures.</li>
</ul>

<h4>Information sur la titration</h4>
<ul>
  <li>Coordinateur·ice et opérateur·ice sont saisi·es au format <b>Prénom puis nom</b>.</li>
  <li>Lieu, date et heure de titration génèrent le <b>nom de la manip de titration</b> affiché en haut de la section.</li>
  <li>Ce nom peut être modifié manuellement via le bouton <b>Modifier</b> ; cliquer <b>Auto</b> revient au nom calculé.</li>
  <li>La correspondance spectres ↔ tubes repasse rouge uniquement si une information de titration est modifiée.</li>
</ul>

<h4>Tableau de volumes et protocole</h4>
<p>
  Le modèle actuel est la titration classique compte-gouttes. Le bouton
  <b>Générer un tableau de volume...</b> reste disponible pour les usages avancés.
  La feuille de protocole devient verte quand le tableau des volumes est prêt.
</p>
<table>
  <tr><th>Solution</th><th>Rôle</th></tr>
  <tr><td><b>Solution A1</b></td><td>Tampon NH3+ concentré, volume fixe.</td></tr>
  <tr><td><b>Solution A2</b></td><td>Tampon NH3+ dilué, complémentaire à la solution B.</td></tr>
  <tr><td><b>Solution B</b></td><td>Titrant, volume variable d'un tube à l'autre.</td></tr>
  <tr><td><b>Solution C</b></td><td>Indicateur SERS.</td></tr>
  <tr><td><b>Solution D</b></td><td>PEG ou agent de crowding.</td></tr>
  <tr><td><b>Solution E</b></td><td>Nanoparticules SERS.</td></tr>
  <tr><td><b>Solution F</b></td><td>Crosslinker, à mélanger immédiatement tube par tube.</td></tr>
</table>
<p>
  Dans le protocole guidé, les cases qui ne sont pas à l'étape courante sont
  grisées. Les étapes actives passent en couleur. Des lignes de mélange sont
  prévues après les solutions B, C, D et E, puis une attention spécifique est
  affichée avant l'ajout de la solution F.
</p>

<h4>Correspondance spectres ↔ tubes</h4>
<p>
  La correspondance associe les noms de spectres aux tubes. Elle utilise le nom
  du prélèvement pour générer les noms de spectres et conserve les associations
  déjà définies lorsque les autres métadonnées terrain sont modifiées.
</p>

<h4>Fichier Excel enregistré</h4>
<p>
  L'enregistrement est possible même sans titration. Si des cases optionnelles
  sont cochées mais incomplètes, un avertissement signale les points à vérifier
  sans bloquer l'enregistrement.
</p>
<ul>
  <li><span class="mono">Mesures</span> - fiche terrain synthétique, avec une ligne par préleveur·se et les résultats de mesures.</li>
  <li><span class="mono">Index-métadonnées</span> - feuille technique masquée utilisée pour recharger les champs de façon robuste.</li>
  <li><span class="mono">Titration-volumes</span> - tableau de volumes si la titration est utilisée.</li>
  <li><span class="mono">Titration-correspondance</span> - métadonnées et correspondance spectres ↔ tubes.</li>
  <li><span class="mono">Titration-EtatProtocole</span> - état des cases du protocole si une feuille de protocole a été utilisée.</li>
</ul>

<h3>2 - Onglet Fichiers Raman</h3>
<ul>
  <li>Sélectionnez les fichiers <span class="mono">.txt</span> issus du spectromètre.</li>
  <li>Cliquez <b>Ajouter la sélection</b> pour les placer dans la liste de travail.</li>
  <li>Utilisez <b>Retirer</b> ou <b>Vider la liste</b> si nécessaire.</li>
</ul>

<h3>3 - Onglet Spectres</h3>
<ul>
  <li>Affiche les spectres corrigés et permet de contrôler rapidement les profils.</li>
  <li>La visualisation interactive permet de zoomer, comparer et exporter une figure.</li>
  <li>Un résultat incohérent doit d'abord faire vérifier la correspondance spectres ↔ tubes et la baseline.</li>
</ul>

<h3>4 - Onglet Analyse</h3>
<ul>
  <li><b>Longueur d'onde du spectromètre</b> choisit les pics adaptés au jeu spectral.</li>
  <li><b>Ajuster le ratio de longueur d'onde</b> permet de choisir le ratio utilisé pour la quantification.</li>
  <li><b>Ajustement mathématique de la courbe</b> lance le modèle d'ajustement sur les données disponibles.</li>
  <li>L'export Excel contient les intensités, ratios et résultats utiles à la comparaison.</li>
</ul>

<div class="warn-box">
  <b style="color:#8a5a00">Points à vérifier en cas d'incohérence :</b>
  nom du prélèvement, date/heure, coordonnées GPS, type d'eau, correspondance
  spectres ↔ tubes, tableau de volumes, baseline et choix de longueur d'onde.
</div>
"""

        welcome_html = """
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
         color: #2b2b2b; max-width: 820px; }
  h3 { color: #2f75b5; margin-top: 22px; margin-bottom: 6px; }
  p  { line-height: 1.6; margin-bottom: 8px; }
  ol, ul { margin-left: 20px; }
  li { margin-bottom: 8px; line-height: 1.55; }
  .key  { font-weight: 700; color: #1f4e79; }
  .ok   { font-weight: 600; color: #2e7d32; }
  .warn { font-weight: 600; color: #c0392b; }
  .note { border-left: 4px solid #2f75b5; background: #eaf2fb; padding: 10px 14px;
          margin: 14px 0; border-radius: 0 4px 4px 0; color: #243b53; }
</style>

<p>
  <b>Bienvenue&nbsp;!</b> OpenLab'Eau vous aide à noter, pas à pas, tout ce qui
  concerne un prélèvement d'eau&nbsp;: qui, où, quand, dans quelles conditions, et
  les mesures réalisées. <b>Pas besoin d'être expert·e</b> — l'application vous guide.
</p>

<div class="note">
  <b>Un code couleur tout simple&nbsp;:</b><br>
  un champ <span class="warn">rouge</span> reste à remplir, un champ
  <span class="ok">vert</span> est déjà bon. C'est pareil pour les boutons&nbsp;:
  rouge = une étape à préparer, vert = c'est prêt.
</div>

<h3>Pour commencer, en 2 étapes</h3>
<ol>
  <li>
    Ouvrez l'onglet <span class="key">Ma fiche terrain</span> et remplissez les
    sections de haut en bas. Les champs passent au vert au fur et à mesure&nbsp;;
    vous pouvez revenir corriger à tout moment.
  </li>
  <li>
    En bas de la fiche, cliquez sur <b>Enregistrer…</b>&nbsp;: l'application propose
    un nom de fichier et crée un fichier Excel (<b>.xlsx</b>) contenant tout ce que
    vous avez saisi.
  </li>
</ol>

<div class="note">
  <b>Vous réalisez aussi une titration du cuivre (mesure Raman)&nbsp;?</b><br>
  Cochez <b>Titration</b> dans la fiche terrain&nbsp;: des onglets supplémentaires
  (Fichiers Raman, Spectres, Analyse) apparaissent alors pour la suite.
  Sinon, vous n'avez pas à vous en occuper.
</div>

<p>
  Et voilà&nbsp;! Pour le détail de chaque section, ouvrez le guide complet
  ci-dessous quand vous en avez besoin.
</p>
"""

        text_label = QLabel(welcome_html, container)
        text_label.setWordWrap(True)
        text_label.setTextFormat(Qt.RichText)
        container_layout.addWidget(text_label)

        # Bouton vers le guide détaillé (fenêtre pop-up)
        guide_btn = QPushButton("📖  Ouvrir le guide complet", container)
        guide_btn.setCursor(Qt.PointingHandCursor)
        guide_btn.setStyleSheet(
            "QPushButton { background-color: #eaf2fb; color: #1f4e79;"
            " border: 1px solid #b6d3f0; border-radius: 18px;"
            " padding: 8px 18px; font-weight: 700; }"
            "QPushButton:hover { background-color: #dceafa;"
            " border-color: #0057b8; }"
        )
        guide_btn.clicked.connect(self.show_full_guide_popup)
        guide_row = QHBoxLayout()
        guide_row.addStretch(1)
        guide_row.addWidget(guide_btn)
        guide_row.addStretch(1)
        container_layout.addLayout(guide_row)

        container_layout.addStretch(1)

        scroll.setWidget(container)
        pres_layout.addWidget(scroll)

        tabs.insertTab(0, self.presentation_tab, "Présentation")
        tabs.setCurrentIndex(0)

        # Onglet Métadonnées (création directe des tableaux dans l'application)
        self.metadata_tab = QWidget(self)
        metadata_layout = QVBoxLayout(self.metadata_tab)

        meta_top_bar = QHBoxLayout()
        meta_top_bar.addStretch(1)
        self.btn_new_metadata = QPushButton("Nouvelle fiche", self)
        self.btn_new_metadata.setStyleSheet(
            "background-color: #6c757d; color: white; font-weight: 700; padding: 4px 14px;"
        )
        self.btn_new_metadata.setToolTip(
            "Vider tous les champs et repartir d'une fiche vierge."
        )
        self.btn_new_metadata.clicked.connect(self._on_new_metadata_clicked)
        meta_top_bar.addWidget(self.btn_new_metadata)
        metadata_layout.addLayout(meta_top_bar)

        metadata_scroll = QScrollArea(self.metadata_tab)
        metadata_scroll.setWidgetResizable(True)
        # Défilement horizontal au besoin : si la fenêtre est plus étroite que
        # le formulaire, on défile au lieu de couper le contenu.
        metadata_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.metadata_creator = MetadataCreatorWidget(metadata_scroll)
        metadata_scroll.setWidget(self.metadata_creator)
        metadata_layout.addWidget(metadata_scroll)
        tabs.addTab(self.metadata_tab, "Ma fiche terrain")

        # Onglet Fichiers Raman
        self.file_tab = QWidget(self)
        file_layout = QVBoxLayout(self.file_tab)
        self.file_picker = FilePickerWidget(self.file_tab)
        file_layout.addWidget(self.file_picker, 1)

        # Étape suivante : associer les spectres aux tubes. On réutilise le
        # bouton (et son libellé d'état) créé dans la fiche terrain ; l'ajouter
        # ici le reparente automatiquement, juste après le choix des fichiers,
        # sans dupliquer la logique de titration.
        map_step = QGroupBox(
            "Étape suivante — associer les spectres aux tubes", self.file_tab
        )
        map_step_layout = QVBoxLayout(map_step)
        map_step_layout.addWidget(
            QLabel(
                "Une fois vos fichiers choisis, indiquez quel spectre "
                "correspond à quel tube de titration.",
                map_step,
            )
        )
        map_step_layout.addWidget(self.metadata_creator.btn_edit_map)
        map_step_layout.addWidget(self.metadata_creator.lbl_status_map)
        file_layout.addWidget(map_step)
        tabs.addTab(self.file_tab, "Fichiers Raman")

        # Onglet Visualiseur (affichage des spectres bruts ; remplace « Spectres »)
        self.spectra_tab = SpectraViewerTab(
            self.file_picker, self.metadata_creator, self)
        tabs.addTab(self.spectra_tab, "Visualiseur")

        # Onglet Analyse
        self.analysis_tab = AnalysisTab(
            self.file_picker, self.metadata_creator, self)
        tabs.addTab(self.analysis_tab, "Analyse")

        self._copper_titration_tabs = [
            self.file_tab,
            self.spectra_tab,
            self.analysis_tab,
        ]
        self.metadata_creator.titration_visibility_changed.connect(
            self._refresh_copper_titration_tabs_visible
        )
        self.metadata_creator.metadata_saved_status_changed.connect(
            self._on_metadata_status_changed
        )
        self.metadata_creator.map_status_changed.connect(
            self._on_map_status_changed
        )
        # L'onglet « Fichiers Raman » est vert seulement si des fichiers .txt
        # sont choisis ET la correspondance spectres ↔ tubes est prête (verte).
        self._has_raman_files = False
        self._map_ready = bool(
            getattr(self.metadata_creator, "_last_map_ready", False)
        )
        self._tab_status = {
            self.metadata_tab: not self.metadata_creator.has_unsaved_metadata(),
            self.file_tab: False,
            self.spectra_tab: False,
            self.analysis_tab: False,
        }
        self.file_picker.selection_changed.connect(
            self._on_file_selection_changed)
        self.spectra_tab.plot_status_changed.connect(
            self._on_spectra_status_changed)
        self.analysis_tab.analysis_status_changed.connect(
            self._on_analysis_status_changed
        )
        self._refresh_workflow_tab_statuses()
        self._refresh_copper_titration_tabs_visible(
            self.metadata_creator.chk_titration_done.isChecked()
        )
        self._last_tab_index = tabs.currentIndex()
        tabs.currentChanged.connect(self._on_tab_changed)

        # --- Label des sources en bas ---
        self.sources_label = QLabel(
            "L'ensemble des sources sont à retrouver <a href='#'>ici</a>."
        )
        self.sources_label.setTextFormat(Qt.RichText)
        self.sources_label.setOpenExternalLinks(False)
        self.sources_label.setTextInteractionFlags(
            Qt.TextBrowserInteraction | Qt.LinksAccessibleByMouse
        )
        self.sources_label.setAlignment(Qt.AlignCenter)
        self.sources_label.linkActivated.connect(self.show_sources_popup)
        central_layout.addWidget(self.sources_label)

    def _set_workflow_tab_status(self, widget: QWidget, ready: bool) -> None:
        idx = self.tabs.indexOf(widget)
        if idx < 0:
            return
        color = "#5cb85c" if ready else "#d9534f"
        tab_bar = self.tabs.tabBar()
        if hasattr(tab_bar, "set_tab_status_color"):
            tab_bar.set_tab_status_color(idx, color)
        else:
            tab_bar.setTabTextColor(idx, QColor("#ffffff"))
        self.tabs.setTabIcon(idx, QIcon())

    def _refresh_workflow_tab_statuses(self) -> None:
        for widget, ready in getattr(self, "_tab_status", {}).items():
            self._set_workflow_tab_status(widget, ready)

    def _on_metadata_status_changed(self, saved: bool) -> None:
        self._tab_status[self.metadata_tab] = bool(saved)
        self._set_workflow_tab_status(self.metadata_tab, bool(saved))

    def _on_file_selection_changed(self, has_files: bool) -> None:
        self._has_raman_files = bool(has_files)
        self._refresh_file_tab_status()
        if hasattr(self, "spectra_tab"):
            self.spectra_tab.mark_plot_stale()
        self._on_spectra_status_changed(False)
        if hasattr(self, "analysis_tab"):
            self.analysis_tab.mark_analysis_stale()
        self._on_analysis_status_changed(False)

    def _on_map_status_changed(self, map_ready: bool) -> None:
        self._map_ready = bool(map_ready)
        self._refresh_file_tab_status()

    def _refresh_file_tab_status(self) -> None:
        """Onglet Fichiers Raman vert seulement si fichiers choisis ET
        correspondance spectres ↔ tubes prête."""
        ready = bool(
            getattr(self, "_has_raman_files", False)
            and getattr(self, "_map_ready", False)
        )
        self._tab_status[self.file_tab] = ready
        self._set_workflow_tab_status(self.file_tab, ready)

    def _on_spectra_status_changed(self, plotted: bool) -> None:
        self._tab_status[self.spectra_tab] = bool(plotted)
        self._set_workflow_tab_status(self.spectra_tab, bool(plotted))
        if not plotted and hasattr(self, "analysis_tab"):
            self.analysis_tab.mark_analysis_stale()
            self._on_analysis_status_changed(False)

    def _on_analysis_status_changed(self, analyzed: bool) -> None:
        self._tab_status[self.analysis_tab] = bool(analyzed)
        self._set_workflow_tab_status(self.analysis_tab, bool(analyzed))

    def _refresh_copper_titration_tabs_visible(self, visible: bool) -> None:
        """Affiche les onglets utiles uniquement à la titration du cuivre."""
        visible = bool(visible)
        titration_tabs = getattr(self, "_copper_titration_tabs", [])

        if not visible and self.tabs.currentWidget() in titration_tabs:
            metadata_index = self.tabs.indexOf(self.metadata_tab)
            if metadata_index >= 0:
                self.tabs.setCurrentIndex(metadata_index)

        for widget in titration_tabs:
            idx = self.tabs.indexOf(widget)
            if idx < 0:
                continue
            self.tabs.setTabVisible(idx, visible)

        self._refresh_workflow_tab_statuses()
        self._last_tab_index = self.tabs.currentIndex()

    def _on_tab_changed(self, index: int) -> None:
        previous_widget = self.tabs.widget(
            getattr(self, "_last_tab_index", index))
        if (
            previous_widget is self.metadata_tab
            and hasattr(self, "metadata_creator")
            and self.metadata_creator.has_unsaved_metadata()
        ):
            QMessageBox.warning(
                self,
                "Fiche non enregistrée",
                "La fiche terrain a été modifiée et n'est pas encore enregistrée.\n"
                "Vous pouvez continuer, mais pensez à enregistrer avant de quitter le logiciel.",
            )
        self._last_tab_index = index

    def _on_new_metadata_clicked(self) -> None:
        mc = getattr(self, "metadata_creator", None)
        if mc is None:
            return
        has_data = (
            mc.df_comp is not None
            or mc.df_map is not None
            or any(
                bool(
                    getattr(
                        mc,
                        attr,
                        None) and getattr(
                        mc,
                        attr).text().strip())
                for attr in (
                    "edit_sampler",
                    "edit_sample_location",
                    "edit_sample_lat",
                    "edit_sample_lon",
                    "edit_coordinator",
                    "edit_operator",
                )
            )
            or (
                hasattr(mc, "edit_sample_date")
                and mc.edit_sample_date.date() != mc.edit_sample_date.minimumDate()
            )
        )
        if has_data:
            reply = QMessageBox.question(
                self,
                "Nouvelle fiche",
                "Toutes les données saisies seront effacées.\n"
                "Voulez-vous vraiment repartir d'une fiche vierge ?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        mc.reset_all()
        fp = getattr(self, "file_picker", None)
        if fp is not None:
            fp.clear_selected()

    def closeEvent(self, event):
        mc = getattr(self, "metadata_creator", None)
        if mc is not None and mc.has_unsaved_metadata():
            reply = QMessageBox.question(
                self,
                "Quitter sans sauvegarder ?",
                "La fiche terrain a été modifiée et n'est pas encore enregistrée.\n"
                "Voulez-vous vraiment quitter ?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
        event.accept()

    def show_full_guide_popup(self, link_str=None):
        """Affiche le guide complet d'utilisation dans une fenêtre dédiée."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Guide complet — OpenLab'Eau")
        dialog.setModal(True)
        dialog.resize(840, 720)

        layout = QVBoxLayout(dialog)

        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        container = QWidget()
        container_layout = QVBoxLayout(container)

        label = QLabel(getattr(self, "_full_guide_html", ""), container)
        label.setWordWrap(True)
        label.setTextFormat(Qt.RichText)
        label.setOpenExternalLinks(True)
        container_layout.addWidget(label)
        container_layout.addStretch(1)

        scroll.setWidget(container)
        layout.addWidget(scroll)

        close_button = QPushButton("Fermer")
        close_button.clicked.connect(dialog.close)
        layout.addWidget(close_button)

        dialog.exec()

    def show_sources_popup(self, link_str):
        """Affiche une fenêtre contextuelle contenant les sources et références de l'application."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Sources")
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)
        sources_text = """
        <p><b>Sources et Références :</b></p>
        <ul>
            <li><b><a href="https://msc.u-paris.fr/"> Laboratoire Matière et Systèmes Complexes</a></b><br>Laboratoire de l'université de Paris.</li>
            <li><b><a href="https://www.eau-et-rivieres.org/home/"> Eau & Rivières de Bretagne</a></b><br>Association de protection de l'environnement.</li>
            <li><b><a href="https://www.campus-transition.org/fr/"> Campus de la Transition</a></b><br>Association loi 1901 de formation de l'Enseignement Superieur en vue d'une transition écologique et solidaire.</li>
            <li><b><a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a></b><br>Carte et données cartographiques utilisées pour le pointage et le géocodage.</li>
            <li><b><a href="https://nominatim.org/">Nominatim</a></b><br>Service de géocodage inverse utilisé pour proposer automatiquement département et commune.</li>
        </ul>
        """
        # <p><b>Articles Scientifiques :</b></p>
        # <ul>
        #     <li><em>Using life cycle assessments to guide reduction in the carbon footprint of single-use lab consumables</em> — Isabella Ragazzi, <a href="https://doi.org/10.1371/journal.pstr.0000080">PLOS, 2023</a></li>
        #     <li><em>The environmental impact of personal protective equipment in the UK healthcare system</em> — Reed et al., <a href="https://journals.sagepub.com/doi/epub/10.1177/01410768211001583">JRSM, 2021</a></li>
        # </ul>

        # <p><b>Crédits :</b></p>
        # <ul>
        #     <li><a href="https://www.ilfotografico.net/">Dario Danile</a> : Graphiste de l'icône de l'application.</li>
        #     <li><b>Alexandre Souchaud</b> : Codeur de l'application.</li>
        # </ul>

        label = QLabel()
        label.setTextFormat(Qt.RichText)
        label.setOpenExternalLinks(True)
        label.setText(sources_text)
        layout.addWidget(label)

        close_button = QPushButton("Fermer")
        close_button.clicked.connect(dialog.close)
        layout.addWidget(close_button)

        dialog.setLayout(layout)
        dialog.exec()


_GLOBAL_STYLESHEET = """
/* Couleur de texte de base */
QWidget { color: #243b53; }
QLabel:disabled, QCheckBox:disabled, QRadioButton:disabled { color: #aab3bf; }

/* Info-bulles sombres et lisibles */
QToolTip {
    background-color: #1f2d3d; color: #ffffff;
    border: none; padding: 5px 8px; border-radius: 4px;
}

/* Boutons par défaut. Les boutons colorés (bleu/rouge/vert) gardent leur
   fond défini en ligne ; ils héritent seulement des coins arrondis. */
QPushButton {
    background-color: #ffffff; color: #243b53;
    border: 1px solid #c9d2de; border-radius: 6px;
    padding: 6px 14px;
}
QPushButton:hover { border-color: #0057b8; }
QPushButton:pressed { background-color: #eef3fb; }
QPushButton:disabled {
    color: #aab3bf; border-color: #e4e8ee; background-color: #f4f6f9;
}

/* Champs de saisie */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit,
QPlainTextEdit, QTextEdit, QTextBrowser {
    background-color: #ffffff; border: 1px solid #c9d2de;
    border-radius: 6px; padding: 4px 8px;
    selection-background-color: #0057b8; selection-color: #ffffff;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QDateEdit:focus, QTimeEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border: 1px solid #0057b8;
}
QComboBox QAbstractItemView {
    background-color: #ffffff; border: 1px solid #c9d2de;
    selection-background-color: #0057b8; selection-color: #ffffff;
    outline: none;
}

/* Encadrés (GroupBox) en cartes blanches */
QGroupBox {
    background-color: #ffffff; border: 1px solid #dde3ec;
    border-radius: 8px; margin-top: 14px; padding: 12px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 12px; padding: 1px 6px; color: #1f4e79;
}

/* Listes / tableaux */
QListWidget, QListView, QTreeView, QTableView {
    background-color: #ffffff; border: 1px solid #dde3ec;
    border-radius: 8px; padding: 3px;
}
QListWidget::item, QListView::item { padding: 4px 6px; border-radius: 4px; }
QListWidget::item:selected, QListView::item:selected,
QTreeView::item:selected, QTableView::item:selected {
    background-color: #0057b8; color: #ffffff;
}

/* Zones défilantes : pas de bord, barres fines */
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical {
    background: #c2cad6; border-radius: 5px; min-height: 32px;
}
QScrollBar::handle:vertical:hover { background: #9aa6b6; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal {
    background: #c2cad6; border-radius: 5px; min-width: 32px;
}
QScrollBar::handle:horizontal:hover { background: #9aa6b6; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
    background: transparent;
}

/* Cases à cocher / radios */
QCheckBox, QRadioButton { spacing: 7px; }

/* Panneau des onglets */
QTabWidget::pane { border: 1px solid #dde3ec; border-radius: 8px; }

/* Barre d'état */
QStatusBar { color: #5a6b7b; }
QStatusBar::item { border: none; }
"""


def _apply_consistent_theme(app: "QApplication") -> None:
    """Force un thème clair, moderne et identique sur toutes les plateformes.

    On bascule tout le monde sur le style « Fusion » (y compris macOS) : c'est
    la seule façon d'obtenir un rendu cohérent et entièrement maîtrisé par notre
    feuille de style. Sans cela, Windows/Linux en mode sombre hériteraient d'une
    palette sombre, et chaque OS afficherait des widgets légèrement différents.
    """
    app.setStyle("Fusion")

    # Qt 6 applique la palette SOMBRE du système avant toute personnalisation
    # quand l'OS est en mode sombre. Fusion + une palette claire ne suffisent
    # alors PAS : il faut explicitement demander à Qt d'ignorer le thème sombre.
    # (API disponible depuis Qt 6.5/6.8 ; ignorée silencieusement sinon — dans
    #  ce cas l'option de plateforme "windows:darkmode=0" ci-dessous prend le
    #  relais.)
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except (AttributeError, TypeError):
        pass

    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#f5f7fa"))
    pal.setColor(QPalette.WindowText, QColor("#243b53"))
    pal.setColor(QPalette.Base, QColor("#ffffff"))
    pal.setColor(QPalette.AlternateBase, QColor("#eef2f7"))
    pal.setColor(QPalette.ToolTipBase, QColor("#ffffdc"))
    pal.setColor(QPalette.ToolTipText, QColor("#1e1e1e"))
    pal.setColor(QPalette.Text, QColor("#1e1e1e"))
    pal.setColor(QPalette.Button, QColor("#f0f0f0"))
    pal.setColor(QPalette.ButtonText, QColor("#1e1e1e"))
    pal.setColor(QPalette.BrightText, QColor("#d9534f"))
    pal.setColor(QPalette.Link, QColor("#0057b8"))
    pal.setColor(QPalette.Highlight, QColor("#0078d7"))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.PlaceholderText, QColor("#7a7a7a"))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor("#a0a0a0"))
    app.setPalette(pal)

    # Feuille de style globale (coins arrondis, champs et cartes homogènes…).
    app.setStyleSheet(_GLOBAL_STYLESHEET)


if __name__ == "__main__":
    # Doit être défini AVANT la création de QApplication : désactive l'adaptation
    # automatique de Qt au mode sombre de Windows (sinon l'appli démarre déjà
    # avec une palette sombre). Complémentaire à setColorScheme() ci-dessous, qui
    # n'existe que sur les Qt récents.
    if sys.platform == "win32":
        os.environ.setdefault("QT_QPA_PLATFORM", "windows:darkmode=0")

    app = QApplication(sys.argv)
    _apply_consistent_theme(app)

    if sys.platform == "win32":
        icon_path = os.path.join(
            APP_DIR, "assets", "openlabeau_icons", "openlabeau.ico"
        )
    else:
        icon_path = os.path.join(
            APP_DIR, "assets", "Openlabeau-logo-seul.png"
        )
    app.setWindowIcon(QIcon(icon_path))

    win = MainWindow()
    win.show()
    sys.exit(app.exec())
