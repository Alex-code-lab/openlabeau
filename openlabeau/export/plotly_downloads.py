from __future__ import annotations

import copy
import json
import os
import re
import tempfile

from PySide6.QtCore import QStandardPaths, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QFileDialog, QMessageBox

_CONNECTED_PROFILE_IDS: set[int] = set()
_LAST_DOWNLOAD_DIR: str | None = None
_KNOWN_EXTS = {".png", ".pdf", ".svg"}
_LAST_PLOTLY_FILENAME: str | None = None
_LAST_PLOTLY_FIG = None  # Référence globale à la dernière figure Plotly affichée
# Tracking par page : permet de retrouver le bon nom même si page.view() échoue
_PAGE_FILENAMES: dict[int, str | None] = {}
_PAGE_FIGS: dict[int, object] = {}
_PAGE_VIEWS: dict[int, object] = (
    {}
)  # page_id → QWebEngineView (pour runJavaScript fiable)

# Script injecté dans chaque HTML Plotly : écoute l'événement plotly_relayout
# et mémorise les plages d'axes dans window._pr à chaque zoom/pan/reset.
_RANGE_TRACKER_SCRIPT = """
<script>
(function(){
  function attach(){
    var gd=document.querySelector('.plotly-graph-div');
    if(!gd||typeof gd.on!=='function'){setTimeout(attach,150);return;}
    gd.on('plotly_relayout',function(ev){
      window._pr=window._pr||{};
      if(ev['xaxis.range[0]']!==undefined)
        window._pr.xrange=[ev['xaxis.range[0]'],ev['xaxis.range[1]']];
      if(ev['xaxis.autorange']===true) delete window._pr.xrange;
      if(ev['yaxis.range[0]']!==undefined)
        window._pr.yrange=[ev['yaxis.range[0]'],ev['yaxis.range[1]']];
      if(ev['yaxis.autorange']===true) delete window._pr.yrange;
    });
  }
  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded',attach);
  } else { attach(); }
})();
</script>
"""

# JS de lecture : essaie window._pr (tracker), puis _fullLayout comme fallback
_JS_GET_RANGES = """
(function(){
  try{
    var r=window._pr||{};
    if(!r.xrange||!r.yrange){
      var gd=document.querySelector('.plotly-graph-div');
      if(gd){
        var fl=(gd._fullLayout)||{};
        var xa=fl.xaxis||{},ya=fl.yaxis||{};
        if(!r.xrange&&xa.range&&xa.range.length===2)r.xrange=[xa.range[0],xa.range[1]];
        if(!r.yrange&&ya.range&&ya.range.length===2)r.yrange=[ya.range[0],ya.range[1]];
      }
    }
    return JSON.stringify(r);
  }catch(e){return '{}';}
})()
"""


def sanitize_filename(name: str) -> str:
    if not name:
        return ""
    text = str(name).strip()
    if not text:
        return ""
    text = text.replace(" ", "_")
    # Supprime les caractères interdits dans les noms de fichiers (Windows + Unix)
    # Note : utiliser r'[...\n\r\t]' et non r"[...\\n\\r\\t]" — dans une classe de
    # caractères regex, \\n serait interprété comme '\' OU 'n', supprimant la
    # lettre n.
    text = re.sub(r'[<>:"/\\|?*\n\r\t]', "", text)
    # Supprime une extension connue résiduelle (ex: ".png" si elle n'a pas été
    # retirée avant)
    text = re.sub(r"(?i)\.(png|pdf|svg)", "", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("._")


def _strip_known_ext(name: str) -> str:
    base = str(name).strip()
    # Retire toutes les extensions connues en fin de nom (même répétées)
    while True:
        m = re.search(r"(?:\.(png|pdf|svg))\s*$", base, flags=re.IGNORECASE)
        if not m:
            return base
        base = base[: m.start()].rstrip(" ._\t\r\n")


def _get_page_from_download(download):
    for attr in ("page", "originatingPage"):
        try:
            val = getattr(download, attr, None)
            page = val() if callable(val) else val
        except Exception:
            page = None
        if page is not None:
            return page
    return None


def _get_profile_from_download(download):
    for attr in ("profile",):
        try:
            val = getattr(download, attr, None)
            prof = val() if callable(val) else val
        except Exception:
            prof = None
        if prof is not None:
            return prof
    page = _get_page_from_download(download)
    try:
        return page.profile() if page is not None else None
    except Exception:
        return None


def _desired_ext_from_filter(selected_filter: str | None) -> str | None:
    if not selected_filter:
        return None
    if "PDF" in selected_filter:
        return ".pdf"
    if "SVG" in selected_filter:
        return ".svg"
    if "PNG" in selected_filter:
        return ".png"
    return None


def _apply_extension(path: str, desired_ext: str | None) -> str:
    if not desired_ext:
        return path
    dir_name, file_name = os.path.split(path)
    base = _strip_known_ext(file_name)
    if not base:
        base = "graphique"
    return os.path.join(dir_name, base + desired_ext)


def _default_download_dir() -> str:
    dl = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
    if dl:
        return dl
    return os.path.expanduser("~")


def save_fig_with_current_zoom(
    view: "QWebEngineView | None",
    fig,
    path: str,
    fmt: str,
    parent=None,
    scale: int = 3,
) -> None:
    """Sauvegarde fig en respectant le zoom/pan courant affiché dans le navigateur.

    - PNG  : capture directe via view.grab() → pixel-perfect, zoom inclus.
    - PDF/SVG : interroge le JS (tracker + _fullLayout) pour les plages d'axes,
                les applique à une copie de la figure, puis exporte via Kaleido.
    """
    global _LAST_DOWNLOAD_DIR

    # ── PNG : capture exacte du rendu (zoom inclus) ────────────────────────
    if fmt == "png" and view is not None:
        try:
            pixmap = view.grab()
            if pixmap.save(path, "PNG"):
                _LAST_DOWNLOAD_DIR = os.path.dirname(path)
                QMessageBox.information(
                    parent, "Export réussi", f"Image enregistrée :\n{path}"
                )
            else:
                QMessageBox.critical(
                    parent, "Erreur d'export", f"Impossible d'écrire :\n{path}"
                )
        except Exception as e:
            QMessageBox.critical(parent, "Erreur d'export", str(e))
        return

    # ── PDF / SVG : kaleido avec plages d'axes récupérées depuis le JS ─────
    def _do_save_vector(js_result):
        global _LAST_DOWNLOAD_DIR
        fig_copy = copy.deepcopy(fig)
        try:
            data = json.loads(js_result or "{}")
            if "xrange" in data:
                fig_copy.update_xaxes(range=data["xrange"])
            if "yrange" in data:
                fig_copy.update_yaxes(range=data["yrange"])
        except Exception:
            pass
        try:
            fig_copy.write_image(path, format=fmt)
            _LAST_DOWNLOAD_DIR = os.path.dirname(path)
            QMessageBox.information(
                parent, "Export réussi", f"Image enregistrée :\n{path}"
            )
        except Exception as e:
            QMessageBox.critical(
                parent,
                "Erreur d'export",
                "Impossible d'exporter le graphique.\n"
                "Vérifiez que 'kaleido' est installé (pip install -U kaleido).\n\n"
                f"Détail : {e}",
            )

    if view is not None:
        try:
            view.page().runJavaScript(_JS_GET_RANGES, _do_save_vector)
            return
        except Exception:
            pass
    # Fallback : kaleido sans zoom (si pas de vue disponible)
    _do_save_vector(None)


def load_plotly_html(view: QWebEngineView, html: str) -> None:
    """Charge un HTML Plotly dans la vue via un fichier temporaire.

    QWebEngineView.setHtml() est limité à ~2 Mo ; avec include_plotlyjs=True le
    HTML fait ~3.5 Mo.  On écrit donc dans un fichier temporaire et on charge
    avec setUrl(), qui n'a pas de limite de taille.
    """
    try:
        # Injecter le tracker de plages d'axes avant </body> (ou à la fin)
        if "</body>" in html:
            html = html.replace(
                "</body>", _RANGE_TRACKER_SCRIPT + "</body>", 1)
        else:
            html = html + _RANGE_TRACKER_SCRIPT

        fd, path = tempfile.mkstemp(suffix=".html", prefix="openlabeau_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(html)
        # Supprimer l'ancien fichier temp de cette vue
        old = getattr(view, "_temp_html_path", None)
        if old and old != path:
            try:
                os.unlink(old)
            except Exception:
                pass
        view._temp_html_path = path
        view.setUrl(QUrl.fromLocalFile(path))
    except Exception:
        # Fallback : setHtml (échoue silencieusement si >2 Mo)
        view.setHtml(html)


def install_plotly_download_handler(view: QWebEngineView) -> None:
    """Installe un gestionnaire global pour les snapshots Plotly."""
    if view is None:
        return
    try:
        profile = view.page().profile()
    except Exception:
        return
    pid = id(profile)
    if pid in _CONNECTED_PROFILE_IDS:
        return
    _CONNECTED_PROFILE_IDS.add(pid)
    profile.downloadRequested.connect(_on_download_requested)


def set_plotly_filename(view: QWebEngineView | None,
                        filename: str | None) -> None:
    """Enregistre un nom de base préféré pour les exports (sans extension)."""
    global _LAST_PLOTLY_FILENAME, _LAST_PLOTLY_FIG
    name = filename or None
    if name:
        name = sanitize_filename(_strip_known_ext(name)) or None
    if view is not None:
        try:
            setattr(view, "_plotly_filename", name)
        except Exception:
            pass
        try:
            profile = view.page().profile()
            profile.setProperty("plotly_filename", name or "")
        except Exception:
            pass
        # Mémoriser par page (id stable tant que la page vit) pour lookup
        # fiable
        try:
            page_id = id(view.page())
            _PAGE_FILENAMES[page_id] = name
            _PAGE_VIEWS[page_id] = view
        except Exception:
            pass
        fig = getattr(view, "_plotly_fig", None)
        if fig is not None:
            _LAST_PLOTLY_FIG = fig
            try:
                _PAGE_FIGS[page_id] = fig
            except Exception:
                pass
    _LAST_PLOTLY_FILENAME = name


def _on_download_requested(download) -> None:
    global _LAST_DOWNLOAD_DIR
    if download is None:
        return

    # Récupérer la page en premier (pour lookup par page_id, plus fiable que
    # page.view())
    page = None
    try:
        page = _get_page_from_download(download)
    except Exception:
        pass
    page_id = id(page) if page is not None else None

    # Parent + vue (pour centrer le dialogue et exécuter le JS)
    parent = None
    view = None
    try:
        view = page.view() if page is not None else None
    except Exception:
        pass
    if view is None and page_id is not None:
        view = _PAGE_VIEWS.get(page_id)
    try:
        parent = view.window() if view is not None else None
    except Exception:
        pass

    # Figure : priorité vue directe → dict par page → global
    fig = None
    if view is not None:
        fig = getattr(view, "_plotly_fig", None)
    if fig is None and page_id is not None:
        fig = _PAGE_FIGS.get(page_id)
    if fig is None:
        fig = _LAST_PLOTLY_FIG

    try:
        fname = download.downloadFileName()
    except Exception:
        fname = ""
    if not fname:
        fname = "newplot.png"

    # Nom de fichier : priorité vue directe → dict par page → global
    base_name = None
    if view is not None:
        base_name = getattr(view, "_plotly_filename", None)
    if not base_name and page_id is not None:
        base_name = _PAGE_FILENAMES.get(page_id)
    if not base_name:
        base_name = _LAST_PLOTLY_FILENAME
    if base_name:
        base_name = os.path.basename(str(base_name))
        base_name = _strip_known_ext(base_name)
        base_name = sanitize_filename(base_name)
    if not base_name:
        base_name = sanitize_filename(_strip_known_ext(fname)) or "graphique"

    base_dir = _LAST_DOWNLOAD_DIR or _default_download_dir()
    default_ext = ".pdf" if fig is not None else ".png"
    suggested = os.path.join(base_dir, base_name + default_ext)
    path, selected_filter = QFileDialog.getSaveFileName(
        parent,
        "Enregistrer l'image",
        suggested,
        "PDF (*.pdf);;PNG (*.png);;SVG (*.svg);;Tous les fichiers (*.*)",
    )
    if not path:
        try:
            download.cancel()
        except Exception:
            pass
        return

    desired_ext = _desired_ext_from_filter(selected_filter)
    path = _apply_extension(path, desired_ext)
    _, ext = os.path.splitext(path)
    fmt = ext.lstrip(".").lower() if ext else "png"
    if fmt not in {"pdf", "png", "svg"}:
        fmt = "png"

    # Si on a accès à la figure, on exporte via Kaleido avec le zoom courant
    if fig is not None:
        try:
            download.cancel()
        except Exception:
            pass
        save_fig_with_current_zoom(view, fig, path, fmt, parent, scale=3)
        return

    # Fallback PNG via téléchargement intégré (qualité standard)
    if fmt != "png":
        try:
            download.cancel()
        except Exception:
            pass
        QMessageBox.warning(
            parent,
            "Export indisponible",
            "PDF/SVG indisponible ici. Choisissez PNG ou installez kaleido.",
        )
        return

    try:
        download.setDownloadDirectory(os.path.dirname(path))
        download.setDownloadFileName(os.path.basename(path))
        download.accept()
        _LAST_DOWNLOAD_DIR = os.path.dirname(path)
        QMessageBox.information(
            parent, "Snapshot", f"Image enregistrée :\n{path}")
    except Exception:
        try:
            download.cancel()
        except Exception:
            pass
