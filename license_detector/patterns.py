"""
Motifs de reconnaissance textuelle pour chaque categorie de licence.

Ces expressions sont utilisees a la fois pour analyser les chaines
embarquees dans les fichiers de police (champ `licenseDescription`,
`copyright`, `trademark`...) et les extraits (snippets) obtenus lors des
recherches web. Elles sont volontairement redondantes (plusieurs formulations
possibles) pour maximiser le rappel, la ponderation/le score de confiance
etant geres ensuite par le classifieur.
"""
from __future__ import annotations

import re

# Chaque entree : categorie -> liste de regex (insensibles a la casse).
# L'ordre des categories reflete la priorite en cas d'egalite de score.
CATEGORY_PATTERNS: dict[str, list[str]] = {
    "OFL": [
        r"sil open font license",
        r"\bofl\b",
        r"open font license",
        r"scripts\.sil\.org/ofl",
        r"fonts\.google\.com.*license",
    ],
    "Apache License": [
        r"apache license",
        r"apache-2\.0",
        r"licensed under the apache license",
    ],
    "GPL": [
        r"gnu general public license",
        r"\bgpl\b",
        r"gplv?[23]",
        r"gnu-fonts",
    ],
    "MIT": [
        r"\bmit license\b",
        r"permission is hereby granted, free of charge",
    ],
    "Public Domain": [
        r"public domain",
        r"creative commons zero",
        r"\bcc0\b",
        r"no rights reserved",
        r"unlicense",
    ],
    "Personal Use Only": [
        r"personal use only",
        r"free for personal use",
        r"non[- ]commercial use only",
        r"not for commercial use",
        r"personal[- ]use",
        r"usage personnel uniquement",
    ],
    "Shareware": [
        r"shareware",
        r"donationware",
        r"try before you buy",
    ],
    "Commercial Use": [
        r"commercial use permitted",
        r"commercial license",
        r"licence commerciale",
        r"purchase a license",
        r"buy a license",
        r"all rights reserved",   # faible signal seul, mais utile combine
        r"desktop license",
        r"webfont license",
    ],
}

# Compilation unique au chargement du module (performance : on scanne
# potentiellement des dizaines de milliers de chaines).
_COMPILED: dict[str, list[re.Pattern]] = {
    category: [re.compile(p, re.IGNORECASE) for p in patterns]
    for category, patterns in CATEGORY_PATTERNS.items()
}


def match_categories(text: str) -> dict[str, int]:
    """
    Retourne, pour un texte donne, le nombre de motifs distincts trouves par
    categorie. Un dictionnaire vide signifie qu'aucun motif connu n'a ete
    reconnu dans le texte.
    """
    if not text:
        return {}
    hits: dict[str, int] = {}
    for category, regexes in _COMPILED.items():
        count = sum(1 for rx in regexes if rx.search(text))
        if count:
            hits[category] = count
    return hits


def best_category(text: str) -> tuple[str, int] | None:
    """Renvoie (categorie, nb_motifs) la plus probable pour `text`, sinon None."""
    hits = match_categories(text)
    if not hits:
        return None
    category = max(hits, key=lambda c: hits[c])
    return category, hits[category]
