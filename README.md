# OpenLab'Eau

Application de terrain et d'analyse pour les protocoles OpenLab'Eau / CitizenSers.

L'application permet notamment de :

- créer et enregistrer une fiche terrain ;
- générer le tableau de volumes de titration ;
- produire une feuille de protocole de paillasse ;
- charger et visualiser des spectres Raman ;
- suivre les pics Raman et exporter les résultats d'analyse.

## Installation développeur

Créer un environnement Python, puis installer les dépendances :

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Sous Windows :

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Lancement

```bash
python main.py
```

## Format des fiches

La fiche terrain est enregistrée en `.xlsx`. Ce format peut être ouvert et
réenregistré avec Microsoft Excel ou LibreOffice Calc.

Le CSV n'est pas utilisé pour la fiche terrain, car il ne conserve pas les
onglets, la mise en forme, les largeurs de colonnes ni les tableaux multiples.

## Packaging

Les fichiers PyInstaller sont fournis :

```bash
python -m pip install pyinstaller
pyinstaller OpenLabEau_Mac.spec
pyinstaller OpenLabEau_windows.spec
```

Le dossier `assets/` est embarqué dans l'application, notamment le modèle Excel
de feuille de protocole.
