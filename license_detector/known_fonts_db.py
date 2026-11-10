"""
Source de detection n(deg)2 : base locale de polices connues.

Une base JSON "seed" (data/known_licenses.json) recense les licences des
familles les plus courantes (fontes systeme, Google Fonts populaires,
League of Moveable Type...). Elle est completee au fil du temps par les
resultats a haute confiance trouves via les autres sources et persistes
dans la table `known_fonts` de la base SQLite (voir database/db.py), ce qui
evite de refaire une recherche web pour deux polices de la meme famille.

Une comparaison floue (SequenceMatcher) est utilisee en repli pour absorber
les variations de casse/ponctuation/suffixes de graisse ("Roboto-Bold",
"Roboto Condensed Light"...) tout en restant strict pour eviter les faux
positifs (cf. point 8 du cahier des charges).
"""
from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from app.config import KNOWN_LICENSES_JSON
from license_detector.models import Evidence

logger = logging.getLogger("fontlicense.known_db")

SOURCE_NAME = "Base connue"
BASE_WEIGHT = 0.85

_WEIGHT_SUFFIXES = re.compile(
    r"(thin|extralight|ultralight|light|regular|book|medium|semibold|demibold|"
    r"bold|extrabold|ultrabold|black|heavy|italic|oblique|condensed|expanded|"
    r"narrow|wide|display|text|caption|variable)",
    re.IGNORECASE,
)


def normalize_family(name: str) -> str:
    """Reduit un nom de famille a une forme comparable (cle du dictionnaire)."""
    if not name:
        return ""
    stripped = _WEIGHT_SUFFIXES.sub("", name)
    return re.sub(r"[^a-z0-9]", "", stripped.lower())


@lru_cache(maxsize=1)
def _load_seed_db() -> dict[str, dict]:
    if not KNOWN_LICENSES_JSON.exists():
        logger.warning("Base connue introuvable : %s", KNOWN_LICENSES_JSON)
        return {}
    try:
        raw = json.loads(KNOWN_LICENSES_JSON.read_text(encoding="utf-8"))
        return {k: v for k, v in raw.items() if not k.startswith("_")}
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Base connue illisible (%s) : %s", KNOWN_LICENSES_JSON, exc)
        return {}


def lookup(family_name: str, extra_entries: dict[str, dict] | None = None) -> list[Evidence]:
    """
    Cherche `family_name` dans la base seed + les entrees supplementaires
    (typiquement fournies par le cache SQLite `known_fonts`, alimente au fil
    des analyses precedentes a haute confiance).
    """
    key = normalize_family(family_name)
    if not key:
        return []

    db = dict(_load_seed_db())
    if extra_entries:
        db.update(extra_entries)

    # 1) correspondance exacte (apres normalisation)
    if key in db:
        entry = db[key]
        return [
            Evidence(
                source=SOURCE_NAME,
                category=entry["category"],
                weight=BASE_WEIGHT,
                confidence=0.95,
                detail=f"Famille '{family_name}' reconnue dans la base connue "
                       f"(editeur : {entry.get('publisher', 'inconnu')}).",
                url=entry.get("url", ""),
            )
        ]

    # 2) correspondance approximative (typo, variante de nom)
    best_ratio, best_key = 0.0, None
    for candidate in db:
        ratio = SequenceMatcher(None, key, candidate).ratio()
        if ratio > best_ratio:
            best_ratio, best_key = ratio, candidate
    if best_key is not None and best_ratio >= 0.90:
        entry = db[best_key]
        return [
            Evidence(
                source=SOURCE_NAME,
                category=entry["category"],
                weight=BASE_WEIGHT * 0.8,  # on baisse la confiance : ce n'est pas une correspondance exacte
                confidence=0.6,
                detail=f"Famille '{family_name}' proche de '{best_key}' "
                       f"(similarite {best_ratio:.0%}) dans la base connue.",
                url=entry.get("url", ""),
            )
        ]
    return []
