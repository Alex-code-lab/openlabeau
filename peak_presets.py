"""Combinaisons de pics par source lumineuse (porté de Ramanalyze-simple).

Pour chaque source, on fournit la liste des paires de pics (cm⁻¹) utilisées
pour calculer un rapport d'intensité I(pic A) / I(pic B).
"""

from itertools import combinations

_PEAKS_785 = [412, 444, 471, 547, 1561]

PRESETS: dict[str, list[tuple[int, int]]] = {
    "532 nm": [
        (1364, 1538),
        (1364, 1409),
        (1364, 1500),
        (1361, 1631),
        (1364, 1580),
        (1234, 1256),
    ],
    "785 nm": list(combinations(_PEAKS_785, 2)),
}


def sources() -> list[str]:
    return list(PRESETS.keys())


def pairs_for(source: str) -> list[tuple[int, int]]:
    return PRESETS.get(source, [])
