"""
Source de detection n(deg)1 : les metadonnees embarquees dans le fichier.

C'est de loin la source la plus fiable : de nombreuses fonderies inscrivent
directement la licence (ou son URL) dans la table `name` de la police -
notamment le champ dedie `licenseDescription` (nameID 13) et `licenseURL`
(nameID 14), mais aussi tres souvent dans le `copyright` (nameID 0) et le
`trademark` (nameID 7). Cette source ne fait aucun appel reseau : elle
fonctionne meme hors-ligne et doit toujours etre executee en premier.
"""
from __future__ import annotations

from license_detector.models import Evidence
from license_detector.patterns import match_categories
from scanner.font_scanner import FontInfo

# Poids de fiabilite de cette source : tres eleve, car c'est une declaration
# faite par la fonderie elle-meme, directement dans le fichier.
SOURCE_NAME = "Metadonnees embarquees"
BASE_WEIGHT = 0.95


def detect(info: FontInfo) -> list[Evidence]:
    """Analyse les champs textuels d'une police et produit des `Evidence`."""
    evidences: list[Evidence] = []

    # Le champ dedie `licenseDescription` est examine en priorite et avec un
    # poids superieur : s'il existe, c'est en general sans ambiguite.
    fields_weighted = [
        (info.embedded_license_description, 1.00, "champ licenseDescription"),
        (info.copyright, 0.75, "champ copyright"),
        (info.trademark, 0.55, "champ trademark"),
        (info.description, 0.45, "champ description"),
    ]

    for text, field_weight, label in fields_weighted:
        if not text:
            continue
        hits = match_categories(text)
        for category, nb_matches in hits.items():
            # Plus il y a de motifs distincts trouves, plus la confiance
            # monte, mais on plafonne pour ne pas depasser 1.0.
            confidence = min(1.0, 0.55 + 0.15 * nb_matches) * field_weight
            evidences.append(
                Evidence(
                    source=SOURCE_NAME,
                    category=category,
                    weight=BASE_WEIGHT,
                    confidence=confidence,
                    detail=f"Motif '{category}' trouve dans le {label} : "
                            f"\"{text[:120]}\"",
                    url=info.embedded_license_url or "",
                )
            )

    # Un `licenseURL` renseigne mais sans texte de licence explicite ailleurs
    # est tout de meme un indice utile (on peut au moins deviner la source).
    if info.embedded_license_url and not evidences:
        url = info.embedded_license_url.lower()
        guessed = None
        if "scripts.sil.org/ofl" in url or "openfontlicense" in url:
            guessed = "OFL"
        elif "apache.org/licenses" in url:
            guessed = "Apache License"
        elif "gnu.org" in url:
            guessed = "GPL"
        elif "opensource.org/licenses/mit" in url:
            guessed = "MIT"
        if guessed:
            evidences.append(
                Evidence(
                    source=SOURCE_NAME,
                    category=guessed,
                    weight=BASE_WEIGHT,
                    confidence=0.8,
                    detail=f"URL de licence embarquee reconnue : {info.embedded_license_url}",
                    url=info.embedded_license_url,
                )
            )

    return evidences
