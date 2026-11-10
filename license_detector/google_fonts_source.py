"""
Source de detection n(deg)3 : depot officiel google/fonts sur GitHub.

Le depot https://github.com/google/fonts range chaque famille dans l'un de
trois dossiers selon sa licence :
    - ofl/      -> SIL Open Font License
    - apache/   -> Apache License 2.0
    - ufl/      -> Ubuntu Font Licence (classee ici comme "OFL" au sens
                   large, car c'est aussi une licence libre avec obligation
                   d'attribution similaire)

On interroge l'API GitHub "contents" (legitime, pas de scraping HTML) sur le
nom de dossier derive de la famille (minuscules, sans espace) : c'est ainsi
que Google Fonts nomme systematiquement ses dossiers. C'est une source fiable
et rapide, sans cle d'API necessaire pour un usage raisonnable (limite
publique de 60 requetes/heure sans authentification -> voir rate_limiter).
"""
from __future__ import annotations

import logging

import aiohttp

from app.config import HTTP_TIMEOUT_SECONDS, USER_AGENT
from license_detector.known_fonts_db import normalize_family
from license_detector.models import Evidence

logger = logging.getLogger("fontlicense.google_fonts")

SOURCE_NAME = "Google Fonts (GitHub)"
BASE_WEIGHT = 0.9

_LICENSE_DIRS = {
    "ofl": "OFL",
    "apache": "Apache License",
    "ufl": "OFL",
}

_API_URL = "https://api.github.com/repos/google/fonts/contents/{directory}/{family_dir}"


async def lookup(session: aiohttp.ClientSession, family_name: str) -> list[Evidence]:
    """Interroge l'API GitHub pour savoir si `family_name` existe dans google/fonts."""
    family_dir = normalize_family(family_name)
    if not family_dir:
        return []

    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)

    for directory, category in _LICENSE_DIRS.items():
        url = _API_URL.format(directory=directory, family_dir=family_dir)
        try:
            async with session.get(url, headers=headers, timeout=timeout) as resp:
                if resp.status == 200:
                    payload = await resp.json()
                    if isinstance(payload, list) and payload:
                        return [
                            Evidence(
                                source=SOURCE_NAME,
                                category=category,
                                weight=BASE_WEIGHT,
                                confidence=0.97,
                                detail=(
                                    f"Dossier '{directory}/{family_dir}' trouve dans le "
                                    f"depot officiel google/fonts sur GitHub."
                                ),
                                url=f"https://github.com/google/fonts/tree/main/{directory}/{family_dir}",
                            )
                        ]
                elif resp.status == 403:
                    logger.warning("Limite de taux GitHub atteinte, source Google Fonts ignoree pour cette police.")
                    return []
                # 404 -> ce dossier de licence ne correspond pas, on tente le suivant
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.debug("Echec requete Google Fonts (%s) pour %s : %s", directory, family_name, exc)
            continue
    return []
