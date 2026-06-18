"""
generate_doc_pca.py
Genere le document PDF d'explication de l'onglet PCA.
Usage : python generate_doc_pca.py
"""

from fpdf import FPDF, XPos, YPos
import os
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)


OUTPUT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "Documentation_PCA_Raman.pdf"
)

MARGIN = 18
TW = 174
LINE_H = 6
BLUE = (26, 79, 160)
DARK = (30, 30, 30)
GREY = (90, 90, 90)
LIGHT_BG = (240, 244, 250)
ACCENT = (220, 235, 255)
WHITE = (255, 255, 255)


class PDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(MARGIN, MARGIN, MARGIN)

    # ------------------------------------------------------------------
    def titre_doc(self, text):
        self.set_font("Helvetica", "B", 22)
        self.set_text_color(*BLUE)
        self.multi_cell(TW, 11, text, align="C")
        self.ln(3)

    def sous_titre(self, text):
        self.set_font("Helvetica", "I", 12)
        self.set_text_color(*GREY)
        self.multi_cell(TW, 7, text, align="C")
        self.ln(8)

    def h1(self, num, text):
        self.ln(5)
        self.set_fill_color(*BLUE)
        self.set_text_color(*WHITE)
        self.set_font("Helvetica", "B", 13)
        self.cell(
            TW, 9, f"  {num}. {text}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True
        )
        self.set_text_color(*DARK)
        self.ln(3)

    def h2(self, text):
        self.ln(3)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*BLUE)
        self.cell(TW, 7, f">  {text}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*DARK)

    def body(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*DARK)
        self.multi_cell(TW, LINE_H, text)
        self.ln(1)

    def bullet(self, text, indent=5):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*DARK)
        self.set_x(MARGIN + indent)
        self.multi_cell(TW - indent, LINE_H, f"- {text}")
        self.set_x(MARGIN)

    def math_box(self, formula, comment=""):
        self.ln(2)
        self.set_fill_color(*ACCENT)
        self.set_font("Courier", "B", 9)
        self.set_text_color(*BLUE)
        self.multi_cell(TW, 5.5, formula, fill=True)
        if comment:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(*GREY)
            self.multi_cell(TW, 4.5, comment)
        self.set_text_color(*DARK)
        self.ln(2)

    def info_box(self, text):
        self.ln(2)
        self.set_fill_color(*LIGHT_BG)
        self.set_font("Helvetica", "I", 9)
        self.set_text_color(*GREY)
        self.set_draw_color(*BLUE)
        self.set_line_width(0.3)
        self.multi_cell(TW, 5, f"  (i)  {text}", border="L", fill=True)
        self.set_text_color(*DARK)
        self.set_draw_color(0, 0, 0)
        self.set_line_width(0.2)
        self.ln(2)

    def separator(self):
        self.ln(3)
        self.set_draw_color(*BLUE)
        self.set_line_width(0.3)
        self.line(MARGIN, self.get_y(), MARGIN + TW, self.get_y())
        self.ln(4)
        self.set_draw_color(0, 0, 0)
        self.set_line_width(0.2)

    def header(self):
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*GREY)
        self.cell(
            0,
            5,
            "Documentation Onglet PCA - Analyse Raman/SERS",
            align="L")
        self.cell(
            0,
            5,
            f"Page {self.page_no()}",
            align="R",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        self.set_text_color(*DARK)
        self.line(MARGIN, self.get_y(), MARGIN + TW, self.get_y())
        self.ln(3)

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*GREY)
        self.cell(0, 6, f"Page {self.page_no()}", align="C")


# ======================================================================
pdf = PDF()
pdf.add_page()

# ── Page de titre ──────────────────────────────────────────────────────
pdf.set_y(35)
pdf.titre_doc("Onglet PCA")
pdf.sous_titre(
    "Analyse en Composantes Principales\n"
    "appliquee aux spectres Raman/SERS de titration\n\n"
    "Documentation technique et guide d'interpretation"
)
pdf.set_draw_color(*BLUE)
pdf.set_line_width(0.5)
pdf.line(MARGIN, pdf.get_y(), MARGIN + TW, pdf.get_y())
pdf.ln(10)
pdf.set_font("Helvetica", "", 9)
pdf.set_text_color(*GREY)
pdf.multi_cell(
    TW,
    5,
    "Ce document explique en detail le fonctionnement de l'onglet PCA du logiciel\n"
    "de traitement de donnees spectroscopie Raman/SERS - CitizenSers.\n"
    "Il couvre : les algorithmes utilises, les options disponibles,\n"
    "les graphiques produits et leur interpretation pratique.",
    align="C",
)

# ── Sommaire ──────────────────────────────────────────────────────────
pdf.add_page()
pdf.set_font("Helvetica", "B", 14)
pdf.set_text_color(*BLUE)
pdf.cell(TW, 10, "Sommaire", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
pdf.set_text_color(*DARK)
sections = [
    ("0", "Preambule : qu'est-ce que la PCA ?"),
    ("1", "Pourquoi utiliser la PCA sur des spectres Raman ?"),
    ("2", "Preparation des donnees : du fichier .txt a la matrice"),
    ("3", "Construction de la matrice spectrale (pivot)"),
    ("4", "Options de normalisation"),
    ("5", "L'algorithme PCA : fonctionnement mathematique"),
    ("6", "Les scores - nuage de points PC1 vs PC2"),
    ("7", "Les loadings - quelles longueurs d'onde comptent ?"),
    ("8", "La variance expliquee"),
    ("9", "La reconstruction de spectre"),
    ("10", "Guide pratique d'utilisation pas a pas"),
    ("11", "Interpretation dans le contexte SERS/titration"),
    ("12", "Limites et precautions"),
    ("13", "Onglet Selection pics : correlation, paires et PCA correlee"),
]
for num, title in sections:
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(12, 7, f"{num}.", align="R")
    pdf.cell(TW - 12, 7, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

# ======================================================================
# Preambule
# ======================================================================
pdf.add_page()
pdf.h1("0", "Preambule : qu'est-ce que la PCA ?")

pdf.h2("0.1 - Definition")
pdf.body(
    "La PCA (Principal Component Analysis), ou Analyse en Composantes Principales (ACP) "
    "en francais, est une methode statistique multivariee. "
    "Son objectif est de transformer un jeu de donnees contenant de nombreuses variables "
    "correlees en un nombre reduit de nouvelles variables independantes, "
    "appelees composantes principales (PC), qui condensent l'essentiel de l'information."
)
pdf.body(
    "Dans le contexte de la spectroscopie Raman, un spectre est un objet de haute dimension : "
    "chaque spectre est decrit par plusieurs centaines a plusieurs milliers de valeurs "
    "d'intensite (une par longueur d'onde). La PCA permet de reduire cet espace enorme "
    "a 2 ou 3 dimensions lisibles par l'oeil humain, sans perdre les tendances essentielles."
)
pdf.info_box(
    "Exemple concret : 15 spectres x 800 longueurs d'onde = un espace de dimension 800. "
    "La PCA reduit cela a un nuage de 15 points dans un plan 2D (PC1, PC2), "
    "qui capture souvent 80 a 95% de toute la variabilite des spectres."
)

pdf.h2("0.2 - A quoi ca sert ?")
pdf.body(
    "La PCA repond a plusieurs questions concretes en spectroscopie de titration :"
)
pdf.bullet(
    "Mes spectres montrent-ils une evolution avec la concentration de titrant ? "
    "-> Si oui, ils s'organisent en gradient dans le nuage de scores."
)
pdf.bullet(
    "Quelles longueurs d'onde varient le plus entre conditions ? "
    "-> Les loadings l'indiquent sans hypothese prealable."
)
pdf.bullet(
    "Y a-t-il des spectres aberrants (hotspot anormal, fluorescence, contamination) ? "
    "-> Un point isole dans le nuage de scores signale un spectre atypique."
)
pdf.bullet(
    "La variabilite entre spectres est-elle d'origine chimique ou instrumentale ? "
    "-> Si la variance est corrigee par la normalisation L2, c'etait de l'intensite SERS ; "
    "si elle persiste, c'est une vraie variation chimique."
)
pdf.bullet(
    "Quels pics Raman dois-je analyser pour mon ratio d'intensite ? "
    "-> Les loadings de la composante correlee a la titration donnent directement les candidats."
)

pdf.h2("0.3 - Comment ca marche ? (principe mathematique simplifie)")
pdf.body(
    "La PCA cherche les 'directions' dans l'espace des donnees qui capturent "
    "le maximum de variance. Voici le principe en 5 etapes :"
)

steps_preamble = [
    (
        "Etape 1 - Construction de la matrice",
        "On assemble tous les spectres dans une matrice X de taille "
        "(n_spectres x n_wavenumbers). Chaque ligne est un spectre, chaque colonne "
        "est une longueur d'onde.",
    ),
    (
        "Etape 2 - Centrage",
        "On soustrait la moyenne de chaque colonne (wavenumber). "
        "Chaque colonne a maintenant une moyenne de zero. "
        "Cela place l'origine au 'spectre moyen'.",
    ),
    (
        "Etape 3 - Recherche de la premiere composante (PC1)",
        "On cherche la direction (vecteur dans l'espace des longueurs d'onde) "
        "le long de laquelle les projections des spectres ont la variance maximale. "
        "Cette direction est PC1. Le vecteur qui la definit s'appelle le 'loading' de PC1.",
    ),
    (
        "Etape 4 - Composantes suivantes (PC2, PC3, ...)",
        "On cherche ensuite la direction orthogonale a PC1 qui maximise la variance restante -> PC2. "
        "Puis la direction orthogonale a PC1 et PC2 -> PC3. Et ainsi de suite. "
        "L'orthogonalite garantit que chaque composante apporte une information nouvelle, "
        "independante des precedentes.",
    ),
    (
        "Etape 5 - Projection (calcul des scores)",
        "Chaque spectre est projete sur les composantes retenues. "
        "Sa coordonnee sur PC1 s'appelle 'score PC1', sur PC2 'score PC2', etc. "
        "Ces scores sont les coordonnees du spectre dans le nouvel espace reduit.",
    ),
]
for title, desc in steps_preamble:
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*BLUE)
    pdf.cell(TW, 6, f"  > {title}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*DARK)
    pdf.set_x(MARGIN + 8)
    pdf.multi_cell(TW - 8, LINE_H, desc)
    pdf.ln(1)

pdf.math_box(
    "    Mathematiquement : X_centree  =  U x S x V^T   (SVD)\n\n"
    "    Scores   =  U x S   (coordonnees des spectres, taille n_spectres x n_comp)\n"
    "    Loadings =  V       (directions des composantes, taille n_comp x n_wavenumbers)\n"
    "    Variance expliqueee par PCk = S_k^2 / somme(S^2)",
    "U, S, V : matrices issues de la decomposition en valeurs singulieres (SVD)\n"
    "Cette formulation est celle implementee par scikit-learn (Python).",
)

pdf.h2("0.4 - Comment s'en servir en pratique ?")
pdf.body("L'utilisation de la PCA suit toujours le meme enchaînement logique :")
usage_steps = [
    "Charger les spectres corriges et les metadonnees de l'experience "
    "(tubes, concentrations, volumes).",
    "Choisir la normalisation adaptee : L2 pour SERS (supprime la variabilite d'intensite), "
    "Z-score pour equaliser tous les pics, ou aucune si les intensites sont homogenes.",
    "Lancer la PCA et lire la variance expliquee : PC1 capte quelle fraction de la variabilite ?",
    "Visualiser le nuage de scores (PC1 vs PC2) en colorant par la concentration de titrant. "
    "Un gradient de couleur = la PCA a trouve l'axe chimique.",
    "Lire les loadings de la composante correllee au titrant : les pics avec les plus grands "
    "|loadings| sont les candidats au ratio d'intensite.",
    "Verifier les spectres atypiques avec la reconstruction : residu = ce que la PCA n'explique pas.",
    "Passer a l'onglet 'Selection pics' pour un classement automatique des meilleures paires de pics.",
]
for i, step in enumerate(usage_steps, 1):
    pdf.bullet(f"{i}. {step}")

pdf.info_box(
    "La PCA n'est pas une fin en soi : c'est un outil exploratoire. "
    "Elle oriente l'analyse vers les bons pics et signale les spectres problematiques. "
    "La conclusion quantitative (valeur de l'equivalence, courbe de titration) "
    "vient ensuite avec l'onglet 'Analyse'."
)

pdf.separator()

# ======================================================================
# Section 1
# ======================================================================
pdf.add_page()
pdf.h1("1", "Pourquoi utiliser la PCA sur des spectres Raman ?")

pdf.body(
    "Un spectre Raman contient typiquement plusieurs centaines a plusieurs milliers de points "
    "(un nombre d'intensite par longueur d'onde mesuree). Dans une experience de titration SERS, "
    "on acquiert un spectre par tube (condition de concentration differente), ce qui peut "
    "representer 8 a 30 spectres selon le plan experimental."
)
pdf.body(
    "Analyser chaque pic a la main prend du temps et suppose que l'on sait a l'avance "
    "quels pics regarder. La PCA permet de :"
)
pdf.bullet(
    "Resumer l'ensemble des spectres en quelques 'axes' (PC1, PC2, ...) qui capturent "
    "l'essentiel des variations sans hypothese prealable."
)
pdf.bullet(
    "Visualiser d'un seul coup d'oeil si les spectres forment des groupes, si des spectres "
    "aberrants existent (hot spots SERS tres intenses), ou si une tendance claire existe "
    "en fonction de la concentration de titrant."
)
pdf.bullet(
    "Identifier les longueurs d'onde (Raman Shifts) qui changent le plus entre conditions "
    "via les loadings, sans avoir a les choisir a priori."
)
pdf.bullet(
    "Detecter des spectres parasites (fluorescence forte, bruit excessif) avant de les "
    "exclure de l'analyse des pics individuels."
)
pdf.bullet(
    "Valider que la variation observee est bien liee a la chimie (titration) et non a "
    "un artefact instrumental ou a la variabilite SERS."
)

pdf.info_box(
    "La PCA ne remplace pas l'analyse des pics - elle la prepare. "
    "Elle indique 'regardez ces regions spectrales' sans vous forcer a les choisir a priori. "
    "Le logiciel propose ensuite l'onglet 'Selection pics' pour exploiter cela."
)

# ======================================================================
# Section 2
# ======================================================================
pdf.h1("2", "Preparation des donnees : du fichier .txt a la matrice")

pdf.h2("2.1 - Lecture des fichiers spectres")
pdf.body(
    "Chaque fichier .txt contient un spectre brut : deux colonnes separees par des tabulations "
    "ou espaces (Raman Shift en cm^-1 et intensite brute 'Dark Subtracted #1'). "
    "L'application lit ces fichiers et applique un pretraitement en deux etapes :"
)
pdf.bullet(
    "Correction de ligne de base (baseline) par polynome d'ordre 5, methode asymetrique. "
    "Cette correction retire la fluorescence de fond et la derive lente du spectre. "
    "L'intensite corrigee est stockee dans la colonne 'Intensity_corrected'. "
    "C'est cette valeur (et non l'intensite brute) que la PCA utilise."
)
pdf.bullet(
    "Les spectres 'Tube BRB' (blanc de reference tampon) sont exclus par defaut, "
    "car ils ne contiennent pas l'information de titration."
)

pdf.h2("2.2 - Fusion avec les metadonnees")
pdf.body(
    "Chaque spectre est associe a un tube (condition experimentale) via le tableau de "
    "correspondance cree dans l'onglet Metadonnees. Ce tableau relie :"
)
pdf.bullet(
    "'Nom du spectre' (nom du fichier sans .txt) -> 'Tube' (ex: Tube 1, Tube 2, Controle)"
)
pdf.bullet("'Tube' -> volumes des solutions A, B, C injectees dans la cuvette")
pdf.bullet(
    "La quantite de titrant n(titrant) en mol est calculee : "
    "n = C(Solution B) x V_cuvette (en litres)."
)
pdf.body(
    "Le resultat est un DataFrame combine contenant, pour chaque ligne spectre x wavenumber : "
    "l'intensite corrigee + toutes les metadonnees du tube correspondant."
)

pdf.info_box(
    "Si les metadonnees sont absentes ou mal renseignees, la PCA fonctionnera quand meme "
    "(elle ne necessite que les intensites), mais les couleurs de points et la correlation "
    "avec la concentration de titrant ne seront pas disponibles."
)

# ======================================================================
# Section 3
# ======================================================================
pdf.add_page()
pdf.h1("3", "Construction de la matrice spectrale (pivot)")

pdf.body(
    "La PCA requiert une matrice rectangulaire unique. Le DataFrame combine "
    "(long format : une ligne par couple spectre x wavenumber) est transforme en "
    "format large (wide) par une operation de pivot :"
)
pdf.math_box(
    "    X  =  matrice  (n_spectres  x  n_wavenumbers)",
    "n_spectres    = nombre de tubes/fichiers (ex: 12)\n"
    "n_wavenumbers = nombre de Raman Shifts dans la plage choisie (ex: 800)",
)
pdf.body("Construction :")
pdf.bullet(
    "Chaque ligne = un spectre, identifie par son 'Spectrum name' ou 'file'.")
pdf.bullet("Chaque colonne = une valeur de Raman Shift (cm^-1).")
pdf.bullet(
    "La valeur dans la cellule = intensite corrigee a ce shift pour ce spectre.")
pdf.bullet(
    "Si plusieurs mesures existent pour le meme couple (spectre, shift), "
    "on prend la moyenne (aggfunc='mean')."
)
pdf.bullet("Les colonnes entierement vides sont supprimees.")
pdf.bullet(
    "Les cases manquantes (NaN) sont remplacees par la moyenne de la colonne correspondante "
    "(imputation par la moyenne des autres spectres au meme wavenumber)."
)

pdf.h2("Filtrage par plage Raman")
pdf.body(
    "Les spinboxes 'Raman min' et 'Raman max' de l'interface permettent de restreindre "
    "la plage de longueurs d'onde incluses dans la matrice. "
    "Ce filtrage a lieu AVANT le pivot. Effets :"
)
pdf.bullet(
    "Exclure les regions non informatives (ex : bord de spectre avec fluorescence residuelle "
    "ou bruit eleve) ameliore la qualite des composantes principales."
)
pdf.bullet(
    "Reduire la plage reduit n_wavenumbers, accelere le calcul et rend les loadings "
    "plus lisibles."
)
pdf.bullet(
    "La plage par defaut est remplie automatiquement depuis les donnees reelles "
    "au moment du chargement."
)

pdf.info_box(
    "Conseil : commencer avec la plage complete. Regarder les loadings. "
    "Identifier les regions 'plates' (loading proche de 0 partout). "
    "Restreindre la plage a la zone active et relancer."
)

# ======================================================================
# Section 4
# ======================================================================
pdf.h1("4", "Options de normalisation")

pdf.body(
    "Avant de lancer la PCA, la matrice X peut etre normalisee. "
    "Ce choix est crucial car il determine ce que la PCA va 'voir' comme source de variation."
)

pdf.h2("Option 1 : Aucune normalisation (centrage seulement)")
pdf.body(
    "La matrice X est utilisee telle quelle. La PCA (implementation scikit-learn) "
    "centrera automatiquement chaque colonne (wavenumber) en soustrayant sa moyenne. "
    "Consequences :"
)
pdf.bullet("PC1 sera domine par la variance absolue d'intensite.")
pdf.bullet(
    "En SERS, si certains spectres sont globalement plus intenses (hotspot brillant vs. faible), "
    "PC1 reflete simplement cette intensite globale, sans lien avec la chimie de titration."
)
pdf.bullet(
    "A utiliser quand tous les spectres ont des intensites comparables "
    "(experience bien controlee, peu de fluctuation SERS)."
)

pdf.h2("Option 2 : Normalisation L2 (recommandee pour SERS)")
pdf.math_box(
    "    x'_i  =  x_i  /  ||x_i||_2    pour chaque spectre i",
    "||x_i||_2 = racine(somme des carres de toutes les intensites du spectre i)\n"
    "Apres normalisation : ||x'_i||_2 = 1 pour tous les spectres.",
)
pdf.body(
    "Chaque spectre est ramene a une norme egale a 1. Les variations d'intensite globale "
    "(dues aux fluctuations SERS de hotspot a hotspot) sont supprimees. "
    "La PCA voit uniquement la forme du spectre, pas son intensite absolue."
)
pdf.bullet("Recommandee en SERS ou l'intensite fluctue fortement entre hotspots.")
pdf.bullet("Les differences de ratio de pics (I_A/I_B) deviennent plus visibles.")
pdf.bullet(
    "Si deux spectres ont exactement la meme forme mais des intensites tres differentes, "
    "ils seront superposes apres L2."
)

pdf.h2("Option 3 : Standardisation Z-score (par longueur d'onde)")
pdf.math_box(
    "    x'_ij  =  (x_ij - moyenne_j)  /  ecart_type_j",
    "Pour chaque wavenumber j : centrage par la moyenne + division par l'ecart-type.\n"
    "Resultat : chaque wavenumber a variance = 1 et moyenne = 0.",
)
pdf.body(
    "Toutes les longueurs d'onde contribuent egalement a la PCA, "
    "independamment de leur intensite absolue. "
    "Un pic a 1 000 coups et un pic a 10 coups auront le meme poids."
)
pdf.bullet(
    "Utile si l'information est dans de petits pics souvent eclipses par les grands."
)
pdf.bullet(
    "Attention : amplifie aussi le bruit dans les regions peu intenses. "
    "A utiliser avec prudence si le rapport signal/bruit est heterogene."
)

pdf.info_box(
    "Recommandation pour SERS/titration : commencer par L2. "
    "Si PC1 explique encore >70% de variance avec L2, c'est qu'une autre source domine ; "
    "essayer Z-score. Si les resultats sont incoherents avec Z-score, revenir a L2."
)

# ======================================================================
# Section 5
# ======================================================================
pdf.add_page()
pdf.h1("5", "L'algorithme PCA : fonctionnement mathematique")

pdf.body(
    "La PCA cherche les directions dans l'espace des longueurs d'onde qui maximisent "
    "la variance des donnees projetees. L'implementation utilisee est celle de "
    "scikit-learn (PCA), basee sur la decomposition en valeurs singulieres (SVD)."
)

pdf.h2("5.1 - Centrage automatique")
pdf.body(
    "Quelle que soit la normalisation choisie, la PCA (scikit-learn) centre "
    "automatiquement la matrice en soustrayant la moyenne de chaque colonne "
    "(c'est-a-dire la moyenne de chaque wavenumber sur tous les spectres) :"
)
pdf.math_box(
    "    X_centree  =  X  -  moyenne(X, axe=spectres)\n\n"
    "    pca.mean_  =  vecteur de dimension n_wavenumbers contenant ces moyennes"
)

pdf.h2("5.2 - Decomposition SVD")
pdf.math_box(
    "    X_centree  =  U  x  S  x  V^T",
    "U : matrice (n_spectres x n_comp) - vecteurs propres des spectres\n"
    "S : vecteur des valeurs singulieres (racine des valeurs propres)\n"
    "V : matrice (n_comp x n_wavenumbers) - vecteurs propres des wavenumbers\n"
    "   -> stockee dans pca.components_ (lignes = composantes principales)",
)

pdf.h2("5.3 - Calcul des scores")
pdf.body("Les scores sont les coordonnees des spectres dans l'espace reduit :")
pdf.math_box(
    "    scores  =  X_centree  x  V^T  =  U  x  S",
    "scores[i, k] = coordonnee du spectre i sur la composante principale k\n"
    "Dimension : (n_spectres x n_composantes_retenues)",
)
pdf.body(
    "Deux spectres proches dans l'espace des scores (distance euclidienne faible) "
    "ont des profils Raman similaires (apres normalisation)."
)

pdf.h2("5.4 - Calcul des loadings")
pdf.math_box(
    "    loadings  =  V   (lignes de pca.components_)\n\n"
    "    loadings[k, j] = contribution du wavenumber j a la composante k",
    "Dimension : (n_composantes x n_wavenumbers)",
)
pdf.body(
    "Les loadings decrivent 'quelle combinaison de longueurs d'onde' definit chaque "
    "composante principale. Un loading fortement positif a 1231 cm^-1 sur PC1 signifie "
    "que PC1 augmente quand l'intensite a 1231 cm^-1 est elevee."
)

pdf.h2("5.5 - Variance expliquee")
pdf.math_box(
    "    var_k  =  S_k^2  /  somme_totale(S^2)    (en fraction)\n"
    "    var_k (%)  =  var_k  x  100",
    "Stocke dans pca.explained_variance_ratio_",
)
pdf.body(
    "Exprimee en pourcentage, elle indique l'importance de chaque composante. "
    "PC1 explique toujours la fraction la plus grande, PC2 la seconde, etc. "
    "La somme des variances de toutes les composantes = 100%."
)

pdf.h2("5.6 - Nombre de composantes")
pdf.body(
    "Le parametre 'Nombre de composantes' (defaut : 5) determine combien de PC sont calculees. "
    "Ce nombre est limite par :"
)
pdf.math_box(
    "    n_comp  <=  min(n_spectres - 1, n_wavenumbers)",
    "Exemple : 12 spectres, 800 wavenumbers -> n_comp <= 11",
)
pdf.body(
    "Retenir trop peu de composantes = perdre de l'information. "
    "Retenir trop = inclure du bruit. "
    "La regle pratique : s'arreter quand la variance cumulee depasse 85-90%."
)

# ======================================================================
# Section 6
# ======================================================================
pdf.add_page()
pdf.h1("6", "Les scores - nuage de points PC1 vs PC2")

pdf.body(
    "Le graphique des scores est la visualisation centrale de la PCA. "
    "Il projette chaque spectre comme un point dans le plan forme par "
    "les deux premieres composantes principales."
)

pdf.h2("6.1 - Lecture du nuage")
pdf.bullet("Deux spectres proches (petite distance) = profils Raman similaires.")
pdf.bullet("Deux spectres eloignes = profils Raman differents.")
pdf.bullet("Un groupe de points = classe de spectres avec un comportement commun.")
pdf.bullet(
    "Un point isole = spectre atypique : hotspot tres brillant, bruit eleve, "
    "fluorescence non corrigee, contamination."
)
pdf.bullet(
    "Les axes PC1 et PC2 sont orthogonaux par construction "
    "(independants mathematiquement)."
)

pdf.h2("6.2 - Coloration par variable")
pdf.body(
    "La combo 'Colorer par' permet de superposer une variable experimentale sur le nuage :"
)
pdf.bullet(
    "Colorer par '[titrant] (M)' ou 'n(titrant) (mol)' : si les spectres s'organisent "
    "en gradient de couleur le long de PC1 (ou PC2), cela prouve que cette composante "
    "capture l'evolution chimique de la titration. C'est le resultat ideal."
)
pdf.bullet(
    "Colorer par 'Tube' : verifie si les replicats d'un meme tube sont proches.")
pdf.bullet(
    "Colorer par 'Sample description' : repere les classes d'echantillons "
    "(ex : avant/apres ajout, different pH)."
)

pdf.h2("6.3 - Que faire si PC1 ne correleles pas avec la chimie ?")
pdf.body(
    "En SERS, il est frequent que PC1 capture 'l'intensite globale' plutot que "
    "la chimie. Plusieurs strategies :"
)
pdf.bullet(
    "Appliquer la normalisation L2 et relancer la PCA. "
    "Cela divise chaque spectre par sa norme et supprime la variance d'intensite absolue."
)
pdf.bullet(
    "Regarder PC2 et PC3 plutot que PC1. En colorant par concentration, "
    "si PC2 montre un gradient clair -> PC2 porte la chimie."
)
pdf.bullet(
    "Utiliser l'onglet 'Selection pics' qui calcule explicitement la correlation "
    "de chaque composante avec n(titrant)."
)

pdf.info_box(
    "Astuce : si les points forment une ligne diagonale de bas-gauche a haut-droit "
    "dans le plan PC1-PC2, c'est souvent le signe que PC1 = intensite globale et "
    "PC2 = forme du spectre. La normalisation L2 corrige generalement cela."
)

pdf.h2("6.4 - Comprendre concretement PC1 et PC2")
pdf.body(
    "PC1 et PC2 ne sont pas des spectres reels. Ce sont des directions abstraites "
    "dans l'espace de variation des spectres. Voici une analogie :"
)
pdf.body(
    "Imaginez que vos spectres varient principalement selon deux effets independants : "
    "(A) l'intensite globale SERS change d'un hotspot a l'autre, et "
    "(B) le ratio de deux pics change avec la concentration de titrant. "
    "La PCA va automatiquement construire PC1 = direction de A (car c'est la plus grande source "
    "de variance) et PC2 = direction de B (orthogonale a A)."
)
pdf.bullet(
    "La coordonnee d'un spectre sur PC1 (son 'score PC1') dit 'a quel point ce spectre "
    "est extremement intense (ou peu intense)'. Ce n'est pas une concentration."
)
pdf.bullet(
    "La coordonnee sur PC2 (son 'score PC2') dit 'a quel point ce spectre a subi "
    "l'effet chimique de la titration' - si PC2 porte la chimie."
)
pdf.bullet(
    "Dans le nuage PC1 vs PC2, un point en haut a droite n'est pas 'meilleur' qu'un point "
    "en bas a gauche. Les axes n'ont pas de valeur absolue physique - c'est leur POSITION "
    "RELATIVE par rapport aux autres points qui compte."
)
pdf.body(
    "Ce qui peut etre troublant : si PC1 ne porte pas la chimie de titration, "
    "les points ne montrent pas de gradient par concentration sur l'axe horizontal. "
    "Il faut alors regarder PC2 (axe vertical) ou meme PC3 (en changeant les axes affiches). "
    "La composante qui porte la chimie est celle dont les scores montrent un gradient de couleur "
    "quand on colore par n(titrant). L'onglet 'Selection pics' calcule automatiquement "
    "|rho(PCk, n(titrant))| pour toutes les composantes et identifie la bonne."
)
pdf.math_box(
    "    Exemple concret (3 spectres, 4 wavenumbers) :\n\n"
    "    Spectre 1 (tube sans titrant)  : [100, 200, 150, 80]\n"
    "    Spectre 2 (tube avec titrant)  : [110, 180, 170, 90]\n"
    "    Spectre 3 (tube titrant x2)    : [105, 160, 200, 85]\n\n"
    "    Score PC1 spectre 1 = -0.8  (peu concerne par l'effet dominant)\n"
    "    Score PC1 spectre 2 =  0.1  (effet moyen)\n"
    "    Score PC1 spectre 3 =  0.7  (tres concerne par l'effet dominant)\n\n"
    "    Si PC1 correlele avec la concentration -> PC1 porte la chimie.",
    "Les valeurs exactes dependent de la normalisation et de la distribution des spectres.",
)

# ======================================================================
# Section 7
# ======================================================================
pdf.h1("7", "Les loadings - quelles longueurs d'onde comptent ?")

pdf.body(
    "Les loadings sont des 'spectres virtuels' qui decrivent la direction de chaque "
    "composante principale dans l'espace des longueurs d'onde."
)

pdf.h2("7.1 - Lecture d'un loading")
pdf.body("Pour la composante PCk, le loading est une courbe Loading(shift). ")
pdf.bullet(
    "Loading fortement positif au shift X : quand PCk est eleve, "
    "l'intensite a X est elevee. Le pic a X est caracteristique des spectres "
    "avec un score PCk fort."
)
pdf.bullet(
    "Loading fortement negatif au shift X : quand PCk est eleve, "
    "l'intensite a X est faible. Ce pic contribue 'en sens inverse' a PCk."
)
pdf.bullet(
    "Loading proche de 0 au shift X : ce shift ne contribue pas "
    "significativement a PCk."
)

pdf.h2("7.2 - Signature d'une reaction chimique")
pdf.body(
    "Une signature typique de reaction chimique (changement de conformation, de liaison, "
    "de protonation) dans les loadings est un profil 'bipolaire' :"
)
pdf.bullet(
    "Loading positif sur un pic (ex : 1231 cm^-1) + loading negatif sur un autre "
    "(ex : 1256 cm^-1) sur la meme composante."
)
pdf.bullet(
    "Cela signifie que, quand le spectre se deplace le long de PCk, le pic a 1231 cm^-1 "
    "augmente PENDANT que le pic a 1256 cm^-1 diminue."
)
pdf.bullet(
    "Ce type d'echange est exactement ce que capture le ratio I_1231/I_1256 "
    "dans l'onglet Analyse."
)

pdf.h2("7.3 - Identifier les candidats pour le ratio")
pdf.body("Pour trouver les meilleurs candidats a analyser par ratio de pics :")
pdf.bullet(
    "Identifier la composante PCk la plus correlee avec n(titrant) "
    "(via coloration dans les scores ou l'onglet 'Selection pics')."
)
pdf.bullet(
    "Sur les loadings de PCk, noter les 2-3 positions avec les plus grands "
    "|loading| positifs et les 2-3 positions avec les plus grands |loading| negatifs."
)
pdf.bullet(
    "Former des paires (pic positif, pic negatif) et les tester dans l'onglet Analyse."
)

pdf.h2("7.4 - Affichage PC1 & PC2 simultane")
pdf.body(
    "L'option 'PC1 & PC2' trace les deux loadings sur le meme graphe. "
    "Cela permet d'identifier :"
)
pdf.bullet("Les pics presents dans les deux composantes (forte variance globale).")
pdf.bullet(
    "Les pics presents dans l'une mais pas l'autre "
    "(specifiques a une source de variation)."
)
pdf.bullet(
    "Les regions ou les deux loadings se croisent ou divergent "
    "sont particulierement interessantes."
)

pdf.h2(
    "7.5 - Pourquoi les 'regions influentes' ne correspondent pas a la meilleure paire ?"
)
pdf.body(
    "C'est une question fondamentale. Les loadings et la meilleure paire de l'onglet "
    "'Selection pics' sont deux choses differentes, calculees par deux methodes distinctes."
)
pdf.body(
    "Les loadings repondent a : 'Quelles longueurs d'onde varient le plus le long de PCk ?'"
)
pdf.body(
    "La meilleure paire repond a : 'Quel rapport I_A/I_B correlele le mieux avec n(titrant) ?'"
)
pdf.body(
    "Ces deux questions ne donnent pas forcement la meme reponse. Voici pourquoi :"
)
pdf.bullet(
    "Un loading fort = ce wavenumber varie beaucoup dans la direction de PCk. "
    "Mais PCk maximise la VARIANCE totale, pas la correlation avec n(titrant). "
    "Un pic peut tres bien varier beaucoup (fort loading) sans etre correle au titrant "
    "(ex : un pic qui fluctue aleatoirement a cause du bruit SERS aura une forte variance "
    "sans etre informatif pour la chimie)."
)
pdf.bullet(
    "La meilleure paire utilise le rapport I_A/I_B, pas les intensites individuelles. "
    "Deux pics qui varient INDEPENDAMMENT peuvent avoir des loadings moyens, "
    "mais leur RAPPORT peut exploser en correlation si l'un monte quand l'autre descend. "
    "Le ratio amplifie les effets differentiels que les loadings individuels cachent."
)
pdf.bullet(
    "La 'meilleure PC' (la plus correlee avec n(titrant)) n'est pas toujours PC1. "
    "Si vous regardez les loadings de PC1 alors que c'est PC3 qui porte la chimie, "
    "vous ne verrez pas les bons pics. Utilisez les loadings de la PC la plus correlee "
    "avec n(titrant) (identifiee dans l'onglet 'Selection pics')."
)
pdf.info_box(
    "Regle pratique : pour trouver la meilleure paire a partir des loadings, "
    "prenez la composante la plus correlee avec n(titrant). "
    "Identifiez le pic avec le plus grand loading POSITIF (pic A) "
    "et le pic avec le plus grand loading NEGATIF (pic B). "
    "Testez le ratio I_A/I_B. C'est exactement ce que l'algorithme 'Selection pics' fait "
    "de facon automatique et exhaustive sur toutes les combinaisons de candidats."
)
pdf.math_box(
    "    Exemple : loading PC2 a 1231 cm^-1 = +0.45 (positif, monte avec PC2)\n"
    "              loading PC2 a 1256 cm^-1 = -0.38 (negatif, descend avec PC2)\n\n"
    "    Si PC2 correlele avec n(titrant) :\n"
    "      -> quand titrant augmente, I_1231 augmente ET I_1256 diminue\n"
    "      -> le ratio I_1231/I_1256 varie DOUBLEMENT avec le titrant\n"
    "      -> c'est ce ratio que l'algorithme trouvera comme meilleure paire",
    "C'est l'opposition de signe des loadings qui cree les meilleures paires.",
)

# ======================================================================
# Section 8
# ======================================================================
pdf.add_page()
pdf.h1("8", "La variance expliquee")

pdf.body(
    "Affichee sous la forme 'PC1: 45.2% | PC2: 18.7% | PC3: 11.1% | ...', "
    "la variance expliquee renseigne sur la distribution de l'information dans les donnees."
)

pdf.h2("8.1 - Interpretation des valeurs")
pdf.bullet(
    "PC1 = 70-90% : un seul facteur dominant. En SERS sans normalisation, "
    "c'est souvent l'intensite globale. Appliquer L2 avant de relancer."
)
pdf.bullet(
    "PC1 = 40-60% + PC2 = 20-30% : deux sources de variation importantes. "
    "L'une peut etre chimique (titration), l'autre instrumentale (hotspot, bruit)."
)
pdf.bullet(
    "PC1 = 20-30% + beaucoup de petites PCs : variance tres distribuee. "
    "Donnees potentiellement bruyantes ou tres homogenes."
)
pdf.bullet(
    "Variance cumulee PC1+PC2 > 80% : le plan PC1-PC2 est une bonne representation. "
    "Ce que vous voyez dans le nuage de scores capture bien les donnees."
)

pdf.h2("8.2 - Nombre de composantes a retenir")
pdf.body(
    "Il n'y a pas de regle universelle. En pratique pour la spectroscopie SERS de titration :"
)
pdf.bullet("Retenir les composantes dont la variance individuelle depasse 5%.")
pdf.bullet("S'arreter quand la variance cumulee depasse 85-90%.")
pdf.bullet(
    "Verifier que les loadings des composantes retenues ont des pics "
    "nets et reconnaissables (et non un profil chaotique = bruit)."
)
pdf.bullet(
    "Un loading ressemblant a du bruit blanc (aucun pic net) indique "
    "que cette composante ne capte que du bruit de mesure."
)

pdf.info_box(
    "Regle pratique : pour 10-20 spectres de titration SERS, 3 a 5 composantes "
    "suffisent generalement. Au-dela, on capture du bruit. "
    "L'important est d'avoir la composante qui correlele avec n(titrant)."
)

# ======================================================================
# Section 9
# ======================================================================
pdf.h1("9", "La reconstruction de spectre")

pdf.body(
    "La reconstruction permet de verifier la fidelite du modele PCA pour un spectre donne. "
    "Elle compare le spectre original (apres normalisation) au spectre que la PCA "
    "reconstituerait a partir des n composantes retenues."
)

pdf.h2("9.1 - Calcul de la reconstruction")
pdf.body("Pour un spectre x_orig (dans l'espace normalise) :")
pdf.math_box(
    "    x_centre  =  x_orig  -  pca.mean_\n\n"
    "    scores_single  =  x_centre  x  pca.components_^T\n"
    "                   (projection du spectre sur les composantes)\n\n"
    "    x_reconstruit  =  scores_single  x  pca.components_  +  pca.mean_\n"
    "                   (reconstruction dans l'espace original)",
    "pca.components_ : matrice des loadings (n_comp x n_wavenumbers)\n"
    "pca.mean_       : vecteur de centrage (n_wavenumbers)",
)

pdf.h2("9.2 - Interpretation")
pdf.bullet(
    "Reconstruction parfaite (courbes superposees) : le modele PCA capture "
    "toute l'information de ce spectre. Le residu est nul."
)
pdf.bullet(
    "Reconstruction imparfaite : le residu = x_orig - x_reconstruit "
    "represente ce que la PCA n'a pas capture avec n composantes."
)
pdf.bullet(
    "Residu avec des pics nets : information non capturee par les n premieres PCs. "
    "Peut indiquer une structure spectrale unique a ce spectre."
)
pdf.bullet(
    "Residu plat et bruite : la PCA capture l'essentiel, le residu est du bruit "
    "de mesure. C'est la situation ideale."
)

pdf.h2("9.3 - Usage pratique")
pdf.body(
    "Cas d'usage typique : selectionner un spectre atypique dans le nuage des scores "
    "(point isole) et regarder sa reconstruction. Le residu peut reveler :"
)
pdf.bullet(
    "Un artefact de fluorescence : pic large et lent -> baseline mal corrigee "
    "pour ce spectre specifique."
)
pdf.bullet(
    "Un pic de contamination : pic fin et tres intense a un shift inhabituel "
    "(ex : vibration d'une molecule etrangere)."
)
pdf.bullet(
    "Un vrai signal chimique unique : hotspot tres specifique qui a "
    "amplifie preferentiellement une conformation moleculaire particuliere."
)
pdf.bullet(
    "Dans les deux premiers cas, le spectre devrait etre exclu de l'analyse "
    "et reacquis si possible."
)

# ======================================================================
# Section 10
# ======================================================================
pdf.add_page()
pdf.h1("10", "Guide pratique d'utilisation pas a pas")

steps = [
    (
        "Etape 1 - Prerequis",
        "S'assurer que les onglets 'Fichiers' et 'Metadonnees' sont complets : "
        "fichiers .txt selectionnes, tableaux de composition et de correspondance "
        "tubes<->spectres definis et sauvegardes.",
    ),
    (
        "Etape 2 - Charger les donnees",
        "Cliquer sur 'Recharger le fichier combine depuis Metadonnees'. "
        "Le bouton passe au vert si le chargement reussit. "
        "Le nombre de spectres charges s'affiche dans le label de statut.",
    ),
    (
        "Etape 3 - Plage Raman",
        "Choisir la plage de Raman Shift. Conseil : commencer avec la plage complete "
        "(valeur remplie automatiquement). On affinera apres avoir vu les loadings.",
    ),
    (
        "Etape 4 - Normalisation",
        "Choisir 'Norme L2' en premier essai. C'est le choix recommande pour SERS. "
        "Si PC1 explique >80% de variance meme avec L2, essayer le Z-score.",
    ),
    (
        "Etape 5 - Nombre de composantes",
        "Laisser 5 en premier essai. Ajuster apres lecture de la variance expliquee "
        "(objectif : couvrir 85-90% de variance).",
    ),
    (
        "Etape 6 - Lancer la PCA",
        "Cliquer 'Lancer la PCA'. Un message confirme la fin du calcul. "
        "Le label 'Variance expliquee' se met a jour. Les boutons de graphiques "
        "sont maintenant actifs.",
    ),
    (
        "Etape 7 - Lire la variance",
        "Combien de % pour PC1 ? Si PC1 > 70% avec L2, quelque chose domine. "
        "Regarder le loading PC1 : ressemble-t-il au spectre moyen ? Si oui, "
        "c'est l'intensite globale. Tenter Z-score.",
    ),
    (
        "Etape 8 - Scores PC1 vs PC2",
        "Ouvrir la fenetre des scores. Colorer par '[titrant] (M)' ou Tube. "
        "Y a-t-il un gradient de couleur dans une direction du nuage ? "
        "Si oui, cette direction porte la chimie de titration.",
    ),
    (
        "Etape 9 - Loadings",
        "Afficher les loadings. Identifier les pics Raman avec les plus grands "
        "|loading| sur la PC correlee au titrant. Ce sont les candidats a analyser "
        "dans l'onglet 'Analyse' par ratio I_A/I_B.",
    ),
    (
        "Etape 10 - Reconstruction",
        "Selectionner un spectre atypique (point eloigne dans le nuage des scores). "
        "Verifier sa reconstruction. Si le residu montre des pics nets, "
        "investiguer si ce spectre doit etre exclu.",
    ),
    (
        "Etape 11 - Iterer",
        "Affiner la plage Raman pour exclure les regions non informatives. "
        "Relancer la PCA. Repeter jusqu'a obtenir une image claire de la chimie.",
    ),
    (
        "Etape 12 - Passer a 'Selection pics'",
        "Utiliser l'onglet 'Selection pics' pour obtenir automatiquement : "
        "le spectre de correlation de Spearman, le classement des paires de pics, "
        "et la correlation de chaque PC avec n(titrant).",
    ),
]

for title, desc in steps:
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*BLUE)
    pdf.cell(TW, 6, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*DARK)
    pdf.set_x(MARGIN + 5)
    pdf.multi_cell(TW - 5, LINE_H, desc)
    pdf.ln(1)

# ======================================================================
# Section 11
# ======================================================================
pdf.add_page()
pdf.h1("11", "Interpretation dans le contexte SERS/titration")

pdf.h2("11.1 - Pattern typique d'une titration reussie")
pdf.body(
    "Dans une experience de titration SERS bien conduite, on observe typiquement :"
)
pdf.bullet(
    "Les points dans le nuage de scores s'organisent selon une trajectoire ordonnee "
    "par concentration croissante de titrant (arc, ligne ou courbe sigmoide le long de PC1 ou PC2)."
)
pdf.bullet(
    "Apres normalisation L2, PC1 ou PC2 correlele fortement avec n(titrant). "
    "Les loadings de cette composante montrent des pics en opposition de phase."
)
pdf.bullet(
    "Le point d'equivalence (r ~ 1) correspond souvent a un 'coude' ou un point d'inflexion "
    "dans la trajectoire du nuage de scores."
)

pdf.h2("11.2 - Impact des hotspots SERS")
pdf.body(
    "En SERS, l'intensite varie fortement selon l'etat d'agregation des nanoparticules. "
    "On reconnait leur impact :"
)
pdf.bullet(
    "Sans normalisation : PC1 explique 80-95% de variance et ses loadings ressemblent "
    "au spectre moyen -> PC1 = intensite globale."
)
pdf.bullet(
    "Apres L2 : PC1 chute a 30-50% et de nouvelles composantes avec des loadings "
    "structures apparaissent -> la chimie emerge."
)
pdf.bullet(
    "Un ou deux points tres eloignes des autres dans le nuage = hotspot unique ou spectre "
    "contamine. Verifier avec la reconstruction et decider de l'exclure ou non."
)

pdf.h2("11.3 - Equivalence chimique dans la PCA")
pdf.body(
    "L'equivalence peut parfois se visualiser directement dans le nuage des scores : "
    "les points r < 1 (avant equivalence) sont d'un cote de la trajectoire et "
    "les points r > 1 de l'autre cote. La frontiere correspond a l'equivalence. "
    "Cependant, la PCA ne donne pas de valeur precise de l'equivalence. "
    "Pour une valeur quantitative, utiliser l'onglet 'Analyse' avec le fit sigmoide."
)

pdf.h2("11.4 - PCA multi-runs")
pdf.body(
    "Si plusieurs manipulations (runs) sont chargees simultanement dans le logiciel :"
)
pdf.bullet(
    "Les spectres du meme run formeront souvent un cluster distinct dans le nuage "
    "-> variabilite run-to-run visible."
)
pdf.bullet(
    "Si les clusters de runs differents sont alignes le long du meme axe que la concentration, "
    "la PCA est robuste et reproductible entre runs."
)
pdf.bullet(
    "Si les clusters sont orthogonaux a la concentration, il y a une variation "
    "systematique entre runs (ex : derive instrumentale, conditions de mesure differentes) "
    "qui devra etre corrigee avant l'analyse quantitative."
)

# ======================================================================
# Section 12
# ======================================================================
pdf.h1("12", "Limites et precautions")

pdf.bullet(
    "La PCA est lineaire. Elle ne capturera pas bien des transitions non-lineaires abruptes. "
    "Les scores formeront une courbe plutot qu'une ligne dans le plan PC1-PC2, "
    "ce qui n'est pas un probleme mais rend l'interpretation moins directe."
)
pdf.bullet(
    "La PCA est non supervisee : elle maximise la variance, pas l'information chimique. "
    "Une source de variance non chimique (bruit, fluorescence residuelle) peut dominer "
    "et masquer le signal de titration."
)
pdf.bullet(
    "Le nombre de composantes retenues influence la reconstruction. "
    "Plus on en retient, plus la reconstruction est fidele, mais plus on inclut du bruit. "
    "Il n'y a pas de nombre optimal universel."
)
pdf.bullet(
    "Le choix de la normalisation change radicalement les resultats. "
    "Il est recommande d'essayer les trois options et de comparer les nuages de scores."
)
pdf.bullet(
    "La PCA ne fonctionne pas bien avec tres peu de spectres (< 5). "
    "Avec seulement 4 spectres, toute la variance est expliquee par 3 composantes "
    "sans portee statistique reelle."
)
pdf.bullet(
    "Les outliers (valeurs aberrantes) ont un fort impact sur la PCA. "
    "Un seul spectre de tres haute intensite peut 'tirer' PC1 vers lui "
    "et fausser l'interpretation. Identifier et traiter les outliers avant la PCA."
)
pdf.bullet(
    "La correction de baseline doit etre bonne avant la PCA. Une baseline mal corrigee "
    "pour certains spectres peut introduire une source de variance artificielle "
    "qui domine les premieres composantes."
)
pdf.bullet(
    "Les loadings doivent etre interpretes dans l'espace normalise. "
    "Avec la normalisation L2, un loading positif ne signifie pas 'ce pic est intense' "
    "mais 'ce pic est intense relativement aux autres pics dans ce spectre'."
)

# ======================================================================
# Section 13
# ======================================================================
pdf.add_page()
pdf.h1("13", "Onglet Selection pics : correlation, paires et PCA correlee")

pdf.body(
    "L'onglet 'Selection pics' est un workflow automatise qui identifie, sans hypothese prealable, "
    "quels pics Raman portent l'information de titration et quelle paire de pics "
    "I_A/I_B est la plus pertinente pour la detection de l'equivalence. "
    "Il repose sur la correlation de Spearman, une mesure statistique non parametrique "
    "expliquee en detail ci-dessous."
)

pdf.h2("13.1 - La correlation de Spearman (rho) : definition et calcul")
pdf.body(
    "Le rho de Spearman (note rho ou rs) est un coefficient de correlation non parametrique "
    "qui mesure si deux variables ont une relation MONOTONE, c'est-a-dire si quand l'une augmente, "
    "l'autre augmente (ou diminue) de facon coherente, sans exiger une relation lineaire parfaite."
)
pdf.body("Distinction importante avec la correlation de Pearson :")
pdf.bullet(
    "Pearson mesure les relations LINEAIRES uniquement (droite y = ax + b). "
    "Sensible aux valeurs aberrantes. Suppose une distribution normale."
)
pdf.bullet(
    "Spearman mesure les relations MONOTONES (croissant ou decroissant). "
    "Insensible aux valeurs aberrantes. Capture les courbes sigmoïdes, exponentielles, "
    "les seuils. Pas d'hypothese de distribution. "
    "Ideal pour des relations chimiques non lineaires comme une titration."
)

pdf.h2("13.1.1 - Comment calculer rho de Spearman")
pdf.body("Le calcul se fait en 3 etapes :")
pdf.body("Etape 1 : Remplacer chaque valeur par son rang.")
pdf.math_box(
    "    Variables d'origine :\n"
    "    I_j = [800, 200, 1200, 500, 900]   (intensite au wavenumber j)\n"
    "    n   = [0.0, 0.5, 1.0, 0.8, 1.5]   (quantite de titrant en mol)\n\n"
    "    Rangs de I_j : [3, 1, 5, 2, 4]     (200 -> rang 1, 500 -> rang 2, ...)\n"
    "    Rangs de n   : [1, 2, 4, 3, 5]     (0.0 -> rang 1, 0.5 -> rang 2, ...)",
    "Les rangs sont calcules independamment pour chaque variable.",
)
pdf.body("Etape 2 : Calculer les differences de rangs d_i = rang(I_j)_i - rang(n)_i.")
pdf.math_box(
    "    d = [3-1, 1-2, 5-4, 2-3, 4-5] = [2, -1, 1, -1, -1]\n"
    "    d^2 = [4, 1, 1, 1, 1]   ->  somme(d^2) = 8"
)
pdf.body("Etape 3 : Appliquer la formule.")
pdf.math_box(
    "    rho = 1 - (6 x somme(d_i^2)) / (n x (n^2 - 1))\n\n"
    "    rho = 1 - (6 x 8) / (5 x (25 - 1))\n"
    "        = 1 - 48 / 120\n"
    "        = 1 - 0.40\n"
    "        = 0.60",
    "n = nombre de paires (ici 5 spectres). "
    "Cette formule exacte suppose des rangs sans ex-aequo. "
    "En pratique, scipy.stats.spearmanr gere les ex-aequo automatiquement.",
)
pdf.body(
    "Dans le logiciel, ce calcul est repete pour CHAQUE wavenumber j, en calculant "
    "rho(I_j, n(titrant)) sur tous les spectres. Le resultat est un 'spectre de correlation' : "
    "une valeur rho pour chaque longueur d'onde."
)

pdf.h2("13.1.1.b - Pourquoi cette formule mesure-t-elle la correlation ?")
pdf.body(
    "La cle est dans les RANGS. Tout s'explique en regardant les deux cas extremes :"
)

# Cas 1 : corrélation parfaite
pdf.set_font("Helvetica", "B", 9)
pdf.set_text_color(*BLUE)
pdf.set_x(MARGIN)
pdf.cell(
    TW,
    5,
    "  Cas 1 : correlation parfaite (l'intensite suit exactement n(titrant))",
    new_x=XPos.LMARGIN,
    new_y=YPos.NEXT,
)
pdf.set_text_color(*DARK)
pdf.math_box(
    "    Tube  Rang_n   Rang_I   d = Rg_n - Rg_I   d^2\n"
    "      1     1        1            0              0\n"
    "      2     2        2            0              0\n"
    "      3     3        3            0              0\n"
    "      4     4        4            0              0\n"
    "      5     5        5            0              0\n\n"
    "    somme(d^2) = 0\n"
    "    rho = 1 - (6 x 0) / (5 x 24) = 1 - 0 = 1.0  <- correlation parfaite",
    "Les rangs sont identiques : chaque d_i = 0. "
    "La somme est nulle, donc rho = 1. "
    "L'intensite monte EXACTEMENT comme n(titrant).",
)

# Cas 2 : anti-corrélation parfaite
pdf.set_font("Helvetica", "B", 9)
pdf.set_text_color(*BLUE)
pdf.set_x(MARGIN)
pdf.cell(
    TW,
    5,
    "  Cas 2 : anti-correlation parfaite (l'intensite fait exactement l'inverse)",
    new_x=XPos.LMARGIN,
    new_y=YPos.NEXT,
)
pdf.set_text_color(*DARK)
pdf.math_box(
    "    Tube  Rang_n   Rang_I   d = Rg_n - Rg_I   d^2\n"
    "      1     1        5           -4             16\n"
    "      2     2        4           -2              4\n"
    "      3     3        3            0              0\n"
    "      4     4        2            2              4\n"
    "      5     5        1            4             16\n\n"
    "    somme(d^2) = 40\n"
    "    rho = 1 - (6 x 40) / (5 x 24) = 1 - 240/120 = 1 - 2 = -1.0  <- anti-correlation parfaite",
    "Les rangs sont exactement inverses. "
    "La somme est maximale, d'ou rho = -1. "
    "L'intensite DESCEND exactement quand n(titrant) monte.",
)

# Cas 3 : aucune corrélation
pdf.set_font("Helvetica", "B", 9)
pdf.set_text_color(*BLUE)
pdf.set_x(MARGIN)
pdf.cell(
    TW,
    5,
    "  Cas 3 : aucune correlation (rangs melanges aleatoirement)",
    new_x=XPos.LMARGIN,
    new_y=YPos.NEXT,
)
pdf.set_text_color(*DARK)
pdf.math_box(
    "    Tube  Rang_n   Rang_I   d    d^2\n"
    "      1     1        3     -2     4\n"
    "      2     2        1      1     1\n"
    "      3     3        5     -2     4\n"
    "      4     4        2      2     4\n"
    "      5     5        4      1     1\n\n"
    "    somme(d^2) = 14\n"
    "    rho = 1 - (6 x 14) / (5 x 24) = 1 - 84/120 = 1 - 0.70 = 0.30",
    "Les rangs n'ont aucun lien. Les d se compensent partiellement "
    "et rho tend vers 0. Plus le melange est 'parfaitement aleatoire', "
    "plus rho se rapproche de 0.",
)
pdf.info_box(
    "RESUME : rho mesure a quel point les classements (rangs) de deux variables "
    "se ressemblent. Rangs identiques -> rho = +1. "
    "Rangs inverses -> rho = -1. "
    "Rangs sans lien -> rho = 0. "
    "Pas besoin de relation lineaire : seul l'ORDRE compte."
)

pdf.h2("13.1.2 - Interpretation des valeurs de rho")
pdf.body("Les valeurs de rho vont toujours de -1 a +1 :")
corr_table = [
    (
        "rho = +1.0",
        "Relation parfaitement croissante. Quand n augmente, I augmente exactement.",
    ),
    (
        "rho = +0.7 a +1.0",
        "Forte correlation positive. Ce pic augmente de facon fiable avec le titrant.",
    ),
    (
        "rho = +0.4 a +0.7",
        "Correlation moderee positive. Tendance visible mais avec dispersion.",
    ),
    ("|rho| < 0.4", "Correlation faible. Ce pic ne suit pas bien le titrant."),
    (
        "rho = -0.4 a -0.7",
        "Correlation moderee negative. Ce pic diminue avec le titrant.",
    ),
    (
        "rho = -0.7 a -1.0",
        "Forte correlation negative. Ce pic diminue de facon fiable.",
    ),
    ("rho = -1.0", "Relation parfaitement decroissante."),
]
for val, interp in corr_table:
    pdf.set_font("Courier", "B", 9)
    pdf.set_text_color(*BLUE)
    pdf.set_x(MARGIN + 3)
    pdf.cell(45, 5.5, val)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*DARK)
    pdf.multi_cell(TW - 48, 5.5, interp)

pdf.ln(2)
pdf.h2("13.1.3 - Signe de rho et couleur des barres (rouge / bleu)")
pdf.body(
    "Dans le graphique 'Paires candidates', les barres sont colorees selon le signe de rho "
    "calcule pour le rapport I_A/I_B :"
)
pdf.bullet(
    "ROUGE : rho > 0. Quand on ajoute du titrant, le rapport I_A/I_B AUGMENTE. "
    "Le pic A monte relativement au pic B (ou le pic B descend). "
    "Chimiquement : A est la forme produite par la reaction, B est la forme consommee."
)
pdf.bullet(
    "BLEU : rho < 0. Quand on ajoute du titrant, le rapport I_A/I_B DIMINUE. "
    "Le pic A descend relativement au pic B. "
    "Chimiquement : A est la forme consommee, B est la forme produite."
)
pdf.body(
    "IMPORTANT : le signe ne change pas la QUALITE analytique de la paire. "
    "Une paire bleue avec |rho| = 0.90 est aussi bonne qu'une paire rouge avec |rho| = 0.90. "
    "La courbe de titration sera juste decroissante plutot que croissante. "
    "Dans l'onglet Analyse, le fit sigmoïde fonctionne dans les deux cas."
)
pdf.body(
    "Astuce : si vous preferez une paire rouge plutot que bleue, "
    "il suffit d'inverser le rapport (utiliser I_B/I_A au lieu de I_A/I_B). "
    "Cela change le signe de rho sans changer |rho|."
)

pdf.add_page()
pdf.h2("13.1.4 - Application concrete : comment rho est calcule sur un spectre Raman")
pdf.body(
    "Voici pas-a-pas comment le logiciel calcule rho pour UN wavenumber particulier. "
    "Ce calcul est repete pour chaque wavenumber du spectre (typiquement 1000 a 3000 points)."
)
pdf.info_box(
    "Contexte : vous avez mesure N tubes, chacun avec une concentration differente de titrant. "
    "Pour chaque tube, vous avez un spectre Raman complet. "
    "Le logiciel veut savoir : 'a 1364 cm^-1, l'intensite augmente-t-elle quand on ajoute du titrant ?'"
)

pdf.body("Etape 0 : les donnees de depart (exemple avec 6 tubes)")
# Table header
col_widths = [28, 38, 38, 20, 20, 28, 16]
headers = [
    "Spectre",
    "n(titrant) (mol)",
    "I a 1364 cm-1",
    "Rang n",
    "Rang I",
    "d = Rg_n - Rg_I",
    "d^2",
]
pdf.set_font("Helvetica", "B", 8)
pdf.set_fill_color(220, 230, 245)
pdf.set_x(MARGIN)
for i, (h, w) in enumerate(zip(headers, col_widths)):
    pdf.cell(w, 6, h, border=1, fill=True, align="C")
pdf.ln()
rows_example = [
    ("Tube 1", "0.00e-9", "120", "1", "4", "1-4 = -3", "9"),
    ("Tube 2", "0.50e-9", "85", "2", "2", "2-2 =  0", "0"),
    ("Tube 3", "1.00e-9", "60", "3", "1", "3-1 =  2", "4"),
    ("Tube 4", "2.00e-9", "140", "4", "5", "4-5 = -1", "1"),
    ("Tube 5", "4.00e-9", "190", "5", "6", "5-6 = -1", "1"),
    ("Tube 6", "8.00e-9", "110", "6", "3", "6-3 =  3", "9"),
]
pdf.set_font("Courier", "", 8)
for i, row in enumerate(rows_example):
    fill = i % 2 == 0
    pdf.set_fill_color(245, 248, 255)
    pdf.set_x(MARGIN)
    for val, w in zip(row, col_widths):
        pdf.cell(w, 5.5, val, border=1, fill=fill, align="C")
    pdf.ln()

pdf.ln(2)
pdf.set_font("Helvetica", "", 9)
pdf.set_text_color(*DARK)
pdf.body(
    "Note : les rangs sont attribues de 1 (valeur la plus petite) a N (valeur la plus grande), "
    "independamment pour n et pour I."
)
pdf.body("Etape 1 : calculer la somme des d^2.")
pdf.math_box(
    "    somme(d^2) = 9 + 0 + 4 + 1 + 1 + 9 = 24\n" "    N = 6 (nombre de spectres)"
)
pdf.body("Etape 2 : appliquer la formule de Spearman.")
pdf.math_box(
    "    rho = 1 - (6 x somme(d^2)) / (N x (N^2 - 1))\n\n"
    "        = 1 - (6 x 24) / (6 x (36 - 1))\n"
    "        = 1 - 144 / 210\n"
    "        = 1 - 0.686\n"
    "        = 0.314",
    "rho = 0.31 : correlation FAIBLE a ce wavenumber. L'intensite a 1364 cm^-1 "
    "ne suit pas bien n(titrant) dans cet exemple.",
)
pdf.body(
    "Si l'on refait le meme calcul a un autre wavenumber, par exemple 1409 cm^-1, "
    "et que les intensites suivent parfaitement l'ordre croissant de n(titrant), "
    "on obtiendrait rho = 1.0 (correlation parfaite)."
)
pdf.ln(2)

pdf.h2("13.1.5 - Pourquoi la courbe brute (rho point-a-point) est-elle si bruitee ?")
pdf.body(
    "Le logiciel calcule rho pour CHAQUE colonne de pixels du spectre, soit un calcul "
    "independant par wavenumber. Cela pose un probleme pratique :"
)
pdf.bullet(
    "Les spectres Raman sont continus : le wavenumber 1363 cm^-1 et 1365 cm^-1 portent "
    "une information quasiment identique. Leurs rho individuels devraient donc etre proches."
)
pdf.bullet(
    "Mais chaque mesure de rho est basee sur seulement N spectres (souvent 8 a 15). "
    "Avec si peu de points, la variabilite statistique est grande : un seul spectre 'anormal' "
    "peut faire passer rho de 0.9 a 0.4 pour un seul wavenumber."
)
pdf.bullet(
    "Resultat : la courbe rho brute 'tremble' vite d'un wavenumber au suivant, "
    "rendant difficile l'identification des vrais pics (maxima stables) "
    "par rapport au bruit statistique."
)
pdf.info_box(
    "Solution : on calcule |rho| puis on lisse par une moyenne glissante (fenetre de quelques cm^-1). "
    "Les vrais pics Raman (larges de 5 a 30 cm^-1) ressortent comme des bosses stables, "
    "tandis que les fluctuations aleatoires point-a-point sont moyennees. "
    "C'est la 'Courbe 2 : |rho| lisse' visible dans l'onglet 'Selection pics'."
)

pdf.add_page()
pdf.h2("13.2 - Le graphique 'Correlation spectrale' : detail de chaque element")
pdf.body(
    "Ce graphique est le coeur de l'analyse. Il montre, pour chaque longueur d'onde, "
    "a quel point l'intensite a cette position est correlee avec la quantite de titrant. "
    "Il contient 3 courbes superposees et des indicateurs visuels."
)
pdf.info_box(
    "Intuition generale : imaginez que pour chaque colonne de pixels du spectre "
    "(chaque wavenumber), on pose la question 'est-ce que l'intensite ici monte ou descend "
    "de facon coherente quand j'ajoute du titrant ?'. Les trois courbes repondent a cette "
    "question avec des niveaux de detail croissants."
)

pdf.set_font("Helvetica", "B", 10)
pdf.set_text_color(*BLUE)
pdf.cell(
    TW,
    6,
    "  Courbe 1 : rho de Spearman brut (bleu clair semi-transparent)",
    new_x=XPos.LMARGIN,
    new_y=YPos.NEXT,
)
pdf.set_text_color(*DARK)
pdf.set_font("Helvetica", "", 10)
pdf.set_x(MARGIN + 5)
pdf.multi_cell(
    TW - 5,
    LINE_H,
    "Pour chaque wavenumber j, valeur brute de rho(I_j, n(titrant)) calculee sur tous les spectres. "
    "C'est la mesure directe, point par point. "
    "Le signe indique le sens de la correlation :\n"
    "  rho = +1 : l'intensite monte exactement quand n(titrant) augmente\n"
    "  rho = -1 : l'intensite descend exactement quand n(titrant) augmente\n"
    "  rho =  0 : pas de relation monotone entre ce wavenumber et le titrant\n\n"
    "PROBLEME de cette courbe brute : elle est tres bruitee car calculee point par point. "
    "Un wavenumber a des voisins presque identiques (les spectres sont continus), "
    "donc rho oscille rapidement et il est difficile de distinguer les vrais pics des artefacts. "
    "C'est pour cela qu'on lui prefere la courbe 2 (lissee) pour l'identification des candidats.",
)
pdf.ln(2)

pdf.set_font("Helvetica", "B", 10)
pdf.set_text_color(*BLUE)
pdf.cell(
    TW,
    6,
    "  Courbe 2 : |rho| lisse (bleu fonce, trait epais) -- LA COURBE PRINCIPALE",
    new_x=XPos.LMARGIN,
    new_y=YPos.NEXT,
)
pdf.set_text_color(*DARK)
pdf.set_font("Helvetica", "", 10)
pdf.set_x(MARGIN + 5)
pdf.multi_cell(
    TW - 5,
    LINE_H,
    "On prend la valeur absolue du rho brut -- on 'oublie' le signe pour s'interesser uniquement "
    "a l'INTENSITE de la correlation (montante ou descendante, peu importe) -- puis on lisse "
    "par une moyenne glissante (parametre 'Fenetre de lissage' en cm^-1). "
    "Ce lissage supprime le bruit point-a-point et fait ressortir les regions spectrales coherentes.\n\n"
    "|rho| va de 0 a 1 : 0 = aucune correlation, 1 = correlation parfaite (dans un sens ou l'autre). "
    "C'est la COURBE PRINCIPALE pour reperer les regions qui varient avec la chimie. "
    "Les maxima locaux de cette courbe sont les CANDIDATS PICS : "
    "les positions Raman qui bougent de facon consistante avec le titrant.",
)
pdf.ln(2)

pdf.set_font("Helvetica", "B", 10)
pdf.set_text_color(*BLUE)
pdf.cell(
    TW,
    6,
    "  Courbe 3 : Dynamique normalisee (rouge tiretee, axe droit)",
    new_x=XPos.LMARGIN,
    new_y=YPos.NEXT,
)
pdf.set_text_color(*DARK)
pdf.set_font("Helvetica", "", 10)
pdf.set_x(MARGIN + 5)
pdf.multi_cell(
    TW - 5,
    LINE_H,
    "IMPORTANT : ce n'est PAS une correlation. C'est une mesure de combien l'intensite "
    "VARIE en valeur absolue entre tous les spectres, independamment de toute relation avec le titrant.\n\n"
    "Formule : (max(I_j) - min(I_j)) / moyenne(|I_j|), normalise entre 0 et 1 sur toute la plage.\n\n"
    "Pourquoi cette courbe ? Un wavenumber peut avoir un bon rho mais une variation minuscule "
    "(quelques unites sur des milliers, soit du bruit numerique). En multipliant |rho| x dynamique, "
    "on s'assure de ne retenir que les pics qui sont a la fois CORRELES au titrant ET "
    "REELLEMENT VISIBLES dans le spectre. "
    "Un pic intense qui varie beaucoup a une forte dynamique. "
    "Une region plate (bruit, ligne de base) a une faible dynamique.",
)
pdf.ln(2)

pdf.set_font("Helvetica", "B", 10)
pdf.set_text_color(*BLUE)
pdf.cell(
    TW,
    6,
    "  Score combine (non affiche directement)",
    new_x=XPos.LMARGIN,
    new_y=YPos.NEXT,
)
pdf.set_text_color(*DARK)
pdf.set_font("Helvetica", "", 10)
pdf.set_x(MARGIN + 5)
pdf.multi_cell(
    TW - 5,
    LINE_H,
    "Score combine = |rho| lisse x dynamique normalisee. "
    "C'est ce score qui determine quels wavenumbers deviennent candidats. "
    "Un bon candidat doit avoir A LA FOIS une forte correlation avec n(titrant) "
    "ET une forte amplitude de variation. Ce double critere elimine :",
)
pdf.set_x(MARGIN + 10)
pdf.multi_cell(
    TW - 10,
    LINE_H,
    "- Les regions bruitees a correlation artificielle (forte rho mais amplitude nulle)\n"
    "- Les pics intenses qui ne varient pas avec le titrant (forte dynamique mais rho = 0)",
)
pdf.ln(2)

pdf.set_font("Helvetica", "B", 10)
pdf.set_text_color(*BLUE)
pdf.cell(
    TW,
    6,
    "  Lignes vertes verticales : les candidats retenus",
    new_x=XPos.LMARGIN,
    new_y=YPos.NEXT,
)
pdf.set_text_color(*DARK)
pdf.set_font("Helvetica", "", 10)
pdf.set_x(MARGIN + 5)
pdf.multi_cell(
    TW - 5,
    LINE_H,
    "Maxima locaux du score combine qui depassent 5% du maximum global (seuil de bruit). "
    "Le nombre de candidats est controle par le parametre 'Nombre de candidats' (defaut : 15). "
    "Une separation minimale de 20 cm^-1 est imposee entre candidats pour eviter "
    "de selectionner plusieurs fois le meme pic (flancs d'un meme pic Raman large).",
)
pdf.ln(2)

pdf.set_font("Helvetica", "B", 10)
pdf.set_text_color(*BLUE)
pdf.cell(
    TW, 6, "  Ligne horizontale grise : rho = 0", new_x=XPos.LMARGIN, new_y=YPos.NEXT
)
pdf.set_text_color(*DARK)
pdf.set_font("Helvetica", "", 10)
pdf.set_x(MARGIN + 5)
pdf.multi_cell(
    TW - 5,
    LINE_H,
    "Reference visuelle. Les wavenumbers dont rho brut est au-dessus = correlation positive "
    "avec titrant. En dessous = correlation negative. Permet de voir rapidement "
    "quelles regions montent et lesquelles descendent avec le titrant.",
)

pdf.h2("13.3 - Comment lire le graphique 'Correlation spectrale' en pratique")
pdf.body("Etapes de lecture recommandees :")
pdf.bullet(
    "1. Reperer les maxima de la courbe bleu fonce (|rho| lisse). "
    "Ces positions sont les wavenumbers les plus informatifs pour la titration."
)
pdf.bullet(
    "2. Verifier que ces maxima coincident avec de vrais pics Raman visibles "
    "dans l'onglet Spectres. Un maximum en |rho| dans une region plate du spectre "
    "est suspect (artefact numerique)."
)
pdf.bullet(
    "3. Regarder le signe du rho brut (courbe bleue claire) aux positions candidates : "
    "positif = pic qui monte avec titrant, negatif = pic qui descend."
)
pdf.bullet(
    "4. Identifier des paires naturelles : un maximum positif + un maximum negatif "
    "forment la meilleure paire candidate. Leur rapport exploite l'opposition de phase."
)
pdf.bullet(
    "5. Les zones ou le rho lisse et la dynamique sont tous deux eleves "
    "(courbes bleue et rouge se rejoignent) sont les zones les plus prometteuses."
)

pdf.info_box(
    "Si aucun maximum clair n'emerge (|rho| lisse plat partout), "
    "cela signifie soit que les spectres ne changent pas avec le titrant, "
    "soit que la normalisation choisie masque le signal. "
    "Essayer une autre normalisation ou verifier les metadonnees de concentration."
)

pdf.h2("13.4 - Vue d'ensemble : relation entre PCA (loadings) et Selection pics (rho)")
pdf.body(
    "Ces deux analyses mesurent des choses complementaires mais differentes. "
    "Voici le tableau comparatif :"
)
compare_rows = [
    (
        "Ce qui est calcule",
        "Direction de variance maximale",
        "Correlation monotone avec n(titrant)",
    ),
    ("Methode", "SVD (algebre lineaire)", "Rang de Spearman (statistique)"),
    (
        "Question posee",
        "Quelles longueurs d'onde varient ensemble ?",
        "Quelles longueurs d'onde covarient avec la chimie ?",
    ),
    (
        "Resultat pic fort",
        "Ce wavenumber contribue a PCk",
        "Ce wavenumber suit le titrant",
    ),
    (
        "Meilleure paire",
        "Loading + fort + loading - fort sur PCk correlee",
        "Ratio I_A/I_B avec |rho| maximal",
    ),
    (
        "Insensible a",
        "La correlation avec une variable specifique",
        "Les variations non liees a n(titrant)",
    ),
]

# Header
pdf.set_fill_color(*BLUE)
pdf.set_font("Helvetica", "B", 8)
pdf.set_text_color(*WHITE)
col_w = [40, 67, 67]
pdf.cell(col_w[0], 6, "Critere", border=1, fill=True)
pdf.cell(col_w[1], 6, "Loadings PCA", border=1, fill=True)
pdf.cell(
    col_w[2],
    6,
    "rho de Spearman (Selection pics)",
    border=1,
    fill=True,
    new_x=XPos.LMARGIN,
    new_y=YPos.NEXT,
)
pdf.set_text_color(*DARK)
for i, (crit, pca_val, rho_val) in enumerate(compare_rows):
    fill = i % 2 == 0
    pdf.set_fill_color(
        245,
        247,
        252) if fill else pdf.set_fill_color(
        255,
        255,
        255)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(col_w[0], 6, crit, border=1, fill=fill)
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(col_w[1], 6, pca_val, border=1, fill=fill)
    pdf.cell(
        col_w[2], 6, rho_val, border=1, fill=fill, new_x=XPos.LMARGIN, new_y=YPos.NEXT
    )

pdf.ln(3)
pdf.info_box(
    "Strategie optimale : utiliser les deux de facon complementaire. "
    "La PCA identifie la composante la plus correlee avec n(titrant) et ses loadings "
    "suggerent des regions candidates. L'onglet 'Selection pics' confirme et classe "
    "les paires par force de correlation brute. Les deux outils convergent en general "
    "vers les memes pics - si ce n'est pas le cas, investiguer pourquoi."
)

pdf.add_page()
pdf.h2("13.5 - Comment sont calculees les meilleures paires de pics ?")
pdf.body(
    "Une fois le spectre de correlation calcule, le logiciel identifie les meilleures paires "
    "de pics en deux etapes enchainees."
)

pdf.h2("13.5.1 - Etape 1 : identifier les pics candidats (wavenumbers individuels)")
pdf.body("Le logiciel calcule le score combine pour chaque wavenumber j :")
pdf.math_box(
    "    Score(j) = |rho(I_j, n)| lisse  x  dynamique normalisee(j)",
    "Ce score est eleve uniquement si le wavenumber est A LA FOIS "
    "bien correle avec n(titrant) ET visible dans le spectre (amplitude suffisante).",
)
pdf.body(
    "Les MAXIMA LOCAUX de ce score deviennent les 'pics candidats'. "
    "Par exemple : 1234, 1364, 1409, 1500, 1538, 1580, 1631 cm^-1."
)
pdf.body(
    "Un parametre 'Nb de candidats' controle combien de maxima sont retenus. "
    "Trop peu -> on rate de bonnes paires. Trop -> on teste des combinaisons peu pertinentes."
)

pdf.h2("13.5.2 - Etape 2 : tester toutes les paires de candidats")
pdf.body("Pour CHAQUE combinaison (pic A, pic B) parmi les candidats, le logiciel :")
pdf.bullet(
    "Calcule le rapport I_A / I_B pour chaque spectre (un seul nombre par tube)")
pdf.bullet("Calcule rho(I_A/I_B, n(titrant)) sur tous les spectres")
pdf.bullet("Retient |rho| comme score de la paire")
pdf.body("Toutes les paires sont ensuite triees par |rho| decroissant.")

pdf.h2("13.5.3 - Pourquoi un rapport I_A/I_B plutot qu'un pic seul ?")
pdf.body("Exemple concret avec 4 tubes :")
# Table
col_widths_p = [22, 30, 28, 28, 38]
headers_p = ["Tube", "n(titrant)", "I(1364)", "I(1538)", "I1364 / I1538"]
pdf.set_font("Helvetica", "B", 8)
pdf.set_fill_color(220, 230, 245)
pdf.set_x(MARGIN + 10)
for h, w in zip(headers_p, col_widths_p):
    pdf.cell(w, 6, h, border=1, fill=True, align="C")
pdf.ln()
rows_p = [
    ("Tube 1", "0 mol", "200", "800", "0.25"),
    ("Tube 2", "20e-9 mol", "300", "600", "0.50"),
    ("Tube 3", "40e-9 mol", "400", "400", "1.00"),
    ("Tube 4", "60e-9 mol", "500", "200", "2.50"),
]
pdf.set_font("Courier", "", 8)
for i, row in enumerate(rows_p):
    fill = i % 2 == 0
    pdf.set_fill_color(245, 248, 255)
    pdf.set_x(MARGIN + 10)
    for val, w in zip(row, col_widths_p):
        pdf.cell(w, 5.5, val, border=1, fill=fill, align="C")
    pdf.ln()

pdf.ln(2)
pdf.set_font("Helvetica", "", 9)
pdf.set_text_color(*DARK)
pdf.body("Dans cet exemple :")
pdf.bullet(
    "rho(I_1364, n) est bon, mais peut etre perturbe si le laser fluctue : "
    "si la puissance monte de 10%, I_1364 monte aussi... sans lien avec la chimie."
)
pdf.bullet(
    "rho(I_1364/I_1538, n) est ENCORE MEILLEUR : si le laser monte de 10%, "
    "I_1364 et I_1538 montent tous les deux de 10%, et le ratio reste constant. "
    "Seule la variation CHIMIQUE (reaction) modifie le rapport. "
    "Le rapport divise le bruit laser commun."
)
pdf.info_box(
    "Resume du pipeline complet :\n\n"
    "Spectres bruts\n"
    "  -> rho(I_j, n) pour chaque wavenumber j\n"
    "  -> Spectre de correlation (courbe brute, section 13.2)\n"
    "  -> |rho| lisse x dynamique = Score combine\n"
    "  -> Maxima du score = pics candidats\n"
    "  -> Pour chaque paire (A, B) de candidats : rho(I_A/I_B, n)\n"
    "  -> Tri par |rho| decroissant\n"
    "  -> Tableau 'Paires candidates' (onglet Selection pics)"
)

pdf.separator()
pdf.set_font("Helvetica", "I", 8)
pdf.set_text_color(*GREY)
pdf.multi_cell(
    TW,
    5,
    "Ce document a ete genere automatiquement par generate_doc_pca.py "
    "a partir du code source de l'onglet PCA (pca.py) "
    "de l'application CitizenSers - Spectroscopie Raman.",
)

# ── Export ─────────────────────────────────────────────────────────────
pdf.output(OUTPUT)
print(f"PDF genere : {OUTPUT}")
