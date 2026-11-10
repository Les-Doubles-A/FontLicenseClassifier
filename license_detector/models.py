"""Structures de donnees partagees par les differentes sources de detection."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Evidence:
    """
    Un indice unique en faveur d'une categorie de licence, produit par l'une
    des sources (metadonnees embarquees, base connue, Google Fonts, recherche
    web...). Le classifieur (`classifier.py`) agrege plusieurs `Evidence`
    pour prendre une decision finale et calculer un score de confiance.
    """

    source: str            # ex: "Metadonnees embarquees", "Base connue", "Google Fonts", "Web: Bing"
    category: str          # une des LICENSE_CATEGORIES
    weight: float          # poids de fiabilite de la source elle-meme [0-1]
    confidence: float      # confiance de la source sur CE resultat precis [0-1]
    detail: str = ""       # explication humaine, tracee dans le rapport/log
    url: str = ""          # URL source, si disponible

    @property
    def score(self) -> float:
        return max(0.0, min(1.0, self.weight * self.confidence))


@dataclass
class ClassificationResult:
    """Resultat final de la classification d'une police."""

    category: str = "Unknown"
    confidence: float = 0.0
    source: str = ""
    url: str = ""
    reason: str = ""
    evidences: list[Evidence] = field(default_factory=list)
    analyzed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
