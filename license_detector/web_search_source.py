"""
Source de detection n(deg)4 : recherche web multi-sources (best-effort).

IMPORTANT - lire avant de modifier ce module :
Aucun moteur ne fournit d'API de recherche gratuite et stable sans cle
(l'API officielle Google Programmable Search Engine necessite une cle et un
quota payant au-dela de 100 requetes/jour ; scraper directement la page de
resultats google.com viole les conditions d'utilisation de Google et se
fait bloquer en quelques requetes). Ce module utilise donc le point d'acces
HTML public de DuckDuckGo (html.duckduckgo.com/html/), qui ne necessite pas
de cle, en injectant des directives `site:` pour cibler specifiquement les
sources listees dans le cahier des charges (Google Fonts, GitHub,
FontSquirrel, DaFont, FontSpace, Adobe Fonts, Fontesk, 1001 Fonts, Open
Foundry, The League of Moveable Type). C'est volontairement une source
"best-effort", ponderee plus faiblement que les metadonnees embarquees ou le
depot Google Fonts : la mise en page d'une page de resultats peut changer a
tout moment sans preavis, et un extrait (snippet) est une indication, pas
une preuve juridique.

Si l'utilisateur desactive `ENABLE_WEB_SEARCH` (app/config.py) ou si le
poste n'a pas de connexion internet, l'application continue de fonctionner
uniquement avec les sources locales (metadonnees embarquees + base connue).
"""
from __future__ import annotations

import asyncio
import logging
import random

import aiohttp
from bs4 import BeautifulSoup

from app.config import HTTP_MIN_DELAY_SECONDS, HTTP_RETRIES, HTTP_TIMEOUT_SECONDS, USER_AGENT
from license_detector.models import Evidence
from license_detector.patterns import match_categories

logger = logging.getLogger("fontlicense.web_search")

SOURCE_PREFIX = "Web"
BASE_WEIGHT = 0.35  # nettement plus bas que les sources locales/officielles

SEARCH_URL = "https://html.duckduckgo.com/html/"

# Sites explicitement demandes dans le cahier des charges. On les regroupe
# par requete `site:` pour limiter le nombre total d'appels HTTP.
_TARGET_SITES = [
    "fonts.google.com",
    "github.com",
    "fontsquirrel.com",
    "fontspace.com",
    "dafont.com",
    "fonts.adobe.com",
    "fontesk.com",
    "1001fonts.com",
    "openfoundry.org",
    "theleagueofmoveabletype.com",
]

# Formulations de requete demandees explicitement dans le cahier des charges.
_QUERY_TEMPLATES = [
    "{name} font license",
    "{name} font commercial use",
    "{name} OFL font",
    "{name} SIL Open Font License",
    "{name} font personal use",
]


async def _fetch(session: aiohttp.ClientSession, query: str, semaphore: asyncio.Semaphore) -> str:
    """Effectue une requete de recherche unique, avec limitation et reprises."""
    params = {"q": query}
    headers = {"User-Agent": USER_AGENT}
    timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT_SECONDS)

    async with semaphore:
        # Delai anti rate-limit (avec une petite gigue aleatoire) entre deux
        # requetes successives, meme reussies.
        await asyncio.sleep(HTTP_MIN_DELAY_SECONDS + random.uniform(0, 0.25))
        last_error: Exception | None = None
        for attempt in range(HTTP_RETRIES + 1):
            try:
                async with session.post(SEARCH_URL, data=params, headers=headers, timeout=timeout) as resp:
                    if resp.status == 200:
                        return await resp.text()
                    if resp.status == 429:
                        logger.warning("Recherche web limitee (429), pause avant reessai...")
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    return ""
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_error = exc
                await asyncio.sleep(0.5 * (attempt + 1))
        if last_error:
            logger.debug("Recherche web echouee pour '%s' : %s", query, last_error)
        return ""


def _extract_snippets(html: str, limit: int = 6) -> list[tuple[str, str]]:
    """Extrait (titre+extrait, url) des resultats d'une page HTML DuckDuckGo."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    snippets: list[tuple[str, str]] = []
    for result in soup.select(".result")[:limit]:
        title_el = result.select_one(".result__title")
        snippet_el = result.select_one(".result__snippet")
        link_el = result.select_one(".result__url")
        text = " ".join(
            el.get_text(" ", strip=True) for el in (title_el, snippet_el) if el is not None
        )
        url = ""
        if link_el is not None:
            url = "https://" + link_el.get_text(strip=True).lstrip("/")
        if text:
            snippets.append((text, url))
    return snippets


async def lookup(
    session: aiohttp.ClientSession,
    family_name: str,
    semaphore: asyncio.Semaphore,
    max_queries: int = 3,
) -> list[Evidence]:
    """
    Lance plusieurs requetes de recherche cible pour `family_name` et agrege
    les motifs de licence trouves dans les extraits de resultats.
    """
    if not family_name:
        return []

    site_filter = " OR ".join(f"site:{site}" for site in _TARGET_SITES)
    queries = [tmpl.format(name=family_name) for tmpl in _QUERY_TEMPLATES[:max_queries]]

    evidences: list[Evidence] = []
    for query in queries:
        full_query = f'"{family_name}" font ({site_filter}) {query.split(family_name, 1)[-1]}'.strip()
        html = await _fetch(session, full_query, semaphore)
        snippets = _extract_snippets(html)
        for text, url in snippets:
            hits = match_categories(text)
            for category, nb_matches in hits.items():
                confidence = min(0.85, 0.35 + 0.12 * nb_matches)
                evidences.append(
                    Evidence(
                        source=f"{SOURCE_PREFIX}: recherche cible",
                        category=category,
                        weight=BASE_WEIGHT,
                        confidence=confidence,
                        detail=f"Requete \"{query}\" -> extrait correspondant a '{category}' : "
                                f"\"{text[:140]}\"",
                        url=url,
                    )
                )
        if evidences:
            # Des qu'on a des indices exploitables, inutile de multiplier les
            # requetes (economie de quota / rapidite).
            break
    return evidences
