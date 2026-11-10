"""
Integration avec l'outil FontCheck fourni par l'utilisateur.

FontCheck (fontcheck.py) est un navigateur local de polices installees sous
Windows. Il stocke pour chaque FAMILLE de police un statut de licence choisi
manuellement par l'utilisateur, dans un fichier JSON tres simple :

    %APPDATA%/FontCheck/licenses.json
    { "Nom de famille": "personnel" | "commercial" | "libre" }
    (l'absence d'une famille dans le fichier = "inconnu")

Ce module ecrit dans ce meme fichier les resultats obtenus automatiquement
par FontLicenseClassifier, convertis vers les 4 statuts que FontCheck sait
afficher (voir `_map_category`). Ainsi, des l'ouverture de FontCheck apres
un lot d'analyse, les polices apparaissent deja classees avec leur badge
de licence (PERS / COMM / OFL), sans action supplementaire.

Regle de fusion : on ne modifie JAMAIS une famille deja renseignee
manuellement dans FontCheck (l'utilisateur a le dernier mot), et on
n'ecrit un statut automatique que si sa confiance est suffisante et que sa
categorie est "traduisible" en un des 4 statuts de FontCheck (les polices
classees "Unknown" restent simplement absentes du fichier).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.config import FREE_LICENSES, fontcheck_data_dir
from license_detector.models import ClassificationResult
from scanner.font_scanner import FontInfo

logger = logging.getLogger("fontlicense.fontcheck_bridge")

MIN_CONFIDENCE_FOR_EXPORT = 0.6


def _map_category(category: str) -> str | None:
    """Convertit une categorie FontLicenseClassifier vers un statut FontCheck."""
    if category in FREE_LICENSES:
        return "libre"
    if category == "Commercial Use":
        return "commercial"
    if category in {"Personal Use Only", "Shareware"}:
        return "personnel"
    return None  # "Unknown" ou categorie non geree -> on ne touche pas a FontCheck


def _licenses_path() -> Path:
    return fontcheck_data_dir() / "licenses.json"


def _load_existing() -> dict[str, str]:
    path = _licenses_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("licenses.json de FontCheck illisible, il ne sera pas modifie : %s", exc)
        return {}


def export_to_fontcheck(results: list[tuple[FontInfo, ClassificationResult]]) -> Path:
    """
    Fusionne les resultats d'analyse dans le fichier de statuts de FontCheck.
    Retourne le chemin du fichier mis a jour.
    """
    existing = _load_existing()
    added, skipped_manual, skipped_low_confidence = 0, 0, 0

    for info, result in results:
        family = info.family_name.strip()
        if not family:
            continue
        if family in existing:
            skipped_manual += 1
            continue
        if result.confidence < MIN_CONFIDENCE_FOR_EXPORT:
            skipped_low_confidence += 1
            continue
        mapped = _map_category(result.category)
        if mapped is None:
            continue
        existing[family] = mapped
        added += 1

    path = _licenses_path()
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "Export FontCheck : %s famille(s) ajoutee(s), %s deja definies manuellement, "
        "%s ignorees (confiance insuffisante) -> %s",
        added, skipped_manual, skipped_low_confidence, path,
    )
    return path
