"""Style graphique commun, d'allure « publication » (porté de Ramanalyze-simple).

Tous les onglets d'analyse passent leur figure dans `apply()` pour un rendu
homogène (axes encadrés, croix, polices).
"""

_FONT = dict(family="Arial, Helvetica, sans-serif", size=14, color="#222222")

MARKER_SYMBOL = "cross"
LINE_WIDTH = 1.6
MARKER_SIZE = 7
MARKER_LINE = 0.6


def marker(color, series_index=0, size=MARKER_SIZE):
    """Croix pleine « + » aux couleurs de la courbe."""
    return dict(
        size=size,
        color=color,
        symbol=MARKER_SYMBOL,
        line=dict(width=MARKER_LINE, color=color),
    )


def _axis(title=None):
    ax = dict(
        showline=True, linewidth=1.4, linecolor="#222222", mirror=True,
        ticks="outside", tickwidth=1.4, ticklen=6, tickcolor="#222222",
        showgrid=True, gridcolor="#ededed", gridwidth=1, zeroline=False,
        title_font=dict(size=15, color="#222222"),
        tickfont=dict(size=12, color="#333333"),
    )
    if title is not None:
        ax["title_text"] = title
    return ax


def apply(fig, title=None, x_title=None, y_title=None, legend_title=None,
          groupclick=None):
    """Applique le style pro à une figure Plotly (axes, polices, fond, légende)."""
    legend = dict(
        bgcolor="rgba(255,255,255,0.88)", bordercolor="#cccccc", borderwidth=1,
        font=dict(size=12),
    )
    if legend_title:
        legend["title"] = dict(text=legend_title, font=dict(size=13))
    if groupclick:
        legend["groupclick"] = groupclick

    fig.update_layout(
        template="simple_white",
        font=_FONT,
        plot_bgcolor="white",
        paper_bgcolor="white",
        title=(
            dict(text=title, font=dict(size=18, color="#111111"),
                 x=0.02, xanchor="left")
            if title else None
        ),
        margin=dict(l=85, r=35, t=70, b=75),
        legend=legend,
    )
    fig.update_xaxes(**_axis(x_title))
    fig.update_yaxes(**_axis(y_title))
    return fig
