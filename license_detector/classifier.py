"""
Classifieur final : combine les indices (`Evidence`) produits par toutes les
sources de detection pour decider de la categorie de licence d'une police et
de son score de confiance.

Strategie (cf. points 3, 4 et 8 du cahier des charges) :
  1. On interroge les sources dans l'ordre de fiabilite decroissante :
     metadonnees embarquees -> base connue -> Google Fonts (GitHub) ->
     recherche web multi-sources. Les sources locales (1 et 2) ne font
     aucun appel reseau ; on ne va chercher sur internet (3 et 4) que si
     elles n'ont rien donne d'assez sur, ce qui limite enormement le nombre
     de requetes HTTP necessaires sur une bibliotheque de 10 000+ polices.
  2. Chaque `Evidence` contribue un score = poids_source x confiance a la
     categorie qu'elle propose. Les scores d'une meme categorie s'additionnent
     (plusieurs sources d'accord se renforcent mutuellement), avec un bonus
     explicite de consensus quand au moins deux sources INDEPENDANTES
     tombent d'accord.
  3. La categorie gagnante est celle au score total le plus eleve. Si ce
     score normalise reste sous `CONFIDENCE_THRESHOLD`, on retombe sur
     "Unknown" plutot que de risquer un faux positif.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

import aiohttp

from app.config import CONFIDENCE_THRESHOLD, ENABLE_WEB_SEARCH
from license_detector import embedded_detector, google_fonts_source, known_fonts_db, web_search_source
from license_detector.models import ClassificationResult, Evidence
from scanner.font_scanner import FontInfo

logger = logging.getLogger("fontlicense.classifier")

# Score (somme ponderee) au-dessus duquel on considere qu'une source locale
# est deja suffisamment concluante pour ne pas avoir a interroger internet.
LOCAL_CONFIDENCE_SHORTCUT = 0.85


def _aggregate(evidences: list[Evidence]) -> dict[str, float]:
    """Additionne les scores par categorie et ajoute un bonus de consensus."""
    per_category: dict[str, float] = {}
    sources_per_category: dict[str, set[str]] = {}

    for ev in evidences:
        per_category[ev.category] = per_category.get(ev.category, 0.0) + ev.score
        sources_per_category.setdefault(ev.category, set()).add(ev.source)

    # Bonus de consensus : si au moins deux sources DIFFERENTES s'accordent
    # sur la meme categorie, on augmente la confiance globale (independance
    # des indices = moins de risque de faux positif).
    for category, sources in sources_per_category.items():
        if len(sources) >= 2:
            per_category[category] = min(1.0, per_category[category] * 1.15)

    return per_category


def decide(evidences: list[Evidence]) -> ClassificationResult:
    """Transforme une liste d'`Evidence` en decision finale."""
    if not evidences:
        return ClassificationResult(
            category="Unknown", confidence=0.0, source="", reason="Aucun indice trouve.",
            evidences=evidences,
        )

    scores = _aggregate(evidences)
    best_category = max(scores, key=lambda c: scores[c])
    best_score = min(1.0, scores[best_category])

    if best_score < CONFIDENCE_THRESHOLD:
        return ClassificationResult(
            category="Unknown",
            confidence=round(best_score, 3),
            source="",
            reason=(
                f"Meilleure hypothese '{best_category}' avec un score de "
                f"{best_score:.0%}, sous le seuil de confiance "
                f"({CONFIDENCE_THRESHOLD:.0%}) : classee Unknown par prudence."
            ),
            evidences=evidences,
        )

    contributing = [e for e in evidences if e.category == best_category]
    contributing.sort(key=lambda e: e.score, reverse=True)
    top = contributing[0]
    sources_used = sorted({e.source for e in contributing})

    return ClassificationResult(
        category=best_category,
        confidence=round(best_score, 3),
        source=", ".join(sources_used),
        url=top.url,
        reason=top.detail,
        evidences=evidences,
    )


async def classify_font(
    info: FontInfo,
    session: Optional[aiohttp.ClientSession] = None,
    semaphore: Optional[asyncio.Semaphore] = None,
    known_extra_entries: Optional[dict[str, dict]] = None,
    enable_web_search: bool = ENABLE_WEB_SEARCH,
) -> ClassificationResult:
    """
    Pipeline complet de classification pour UNE police deja scannee.

    Retourne toujours un `ClassificationResult`, meme en cas d'echec total
    des sources reseau (on ne fait jamais planter le traitement d'un lot
    a cause d'une seule police).
    """
    if not info.is_valid:
        return ClassificationResult(
            category="Unknown", confidence=0.0, reason=f"Police illisible : {info.error}",
        )

    evidences: list[Evidence] = []

    # --- Source 1 : metadonnees embarquees (local, gratuit, tres fiable) ---
    evidences.extend(embedded_detector.detect(info))

    # --- Source 2 : base de polices connues (local) ---
    evidences.extend(known_fonts_db.lookup(info.best_name, known_extra_entries))

    # Raccourci : si les sources locales suffisent deja, on evite les appels
    # reseau (essentiel pour tenir la charge sur 10 000+ polices).
    local_scores = _aggregate(evidences)
    if local_scores and max(local_scores.values()) >= LOCAL_CONFIDENCE_SHORTCUT:
        return decide(evidences)

    # --- Source 3 : depot officiel Google Fonts (reseau, API GitHub) ---
    if session is not None:
        try:
            evidences.extend(await google_fonts_source.lookup(session, info.best_name))
        except Exception as exc:  # noqa: BLE001 - une source qui echoue ne doit jamais tout bloquer
            logger.debug("Source Google Fonts en erreur pour %s : %s", info.best_name, exc)

        local_scores = _aggregate(evidences)
        if local_scores and max(local_scores.values()) >= LOCAL_CONFIDENCE_SHORTCUT:
            return decide(evidences)

        # --- Source 4 : recherche web multi-sources (best-effort) ---
        if enable_web_search and semaphore is not None:
            try:
                evidences.extend(await web_search_source.lookup(session, info.best_name, semaphore))
            except Exception as exc:  # noqa: BLE001
                logger.debug("Source recherche web en erreur pour %s : %s", info.best_name, exc)

    return decide(evidences)
