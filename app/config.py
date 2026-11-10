"""
Configuration centrale de FontLicenseClassifier.

Toutes les constantes "de reglage" de l'application vivent ici : chemins de
travail, categories de licence reconnues, poids utilises par le moteur de
score de confiance, limites reseau, etc. Regrouper ces valeurs a un seul
endroit permet de les ajuster sans avoir a fouiller dans la logique metier.
"""
from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- 
# Emplacements sur disque
# ---------------------------------------------------------------------------
APP_NAME = "FontLicenseClassifier"

# Dossier de configuration persistant (a cote de celui deja utilise par
# FontCheck : %APPDATA%/FontCheck sous Windows, ~/.config ailleurs).
def app_data_dir() -> Path:
    base = Path(os.environ.get("APPDATA", str(Path.home() / ".config")))
    directory = base / APP_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def fontcheck_data_dir() -> Path:
    """Dossier de donnees de l'outil FontCheck fourni par l'utilisateur."""
    base = Path(os.environ.get("APPDATA", str(Path.home())))
    directory = base / "FontCheck"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


DB_PATH = app_data_dir() / "cache.sqlite3"
LOG_DIR = app_data_dir() / "logs"
STATE_PATH = app_data_dir() / "resume_state.json"

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
KNOWN_LICENSES_JSON = DATA_DIR / "known_licenses.json"

# --------------------------------------------------------------------------- 
# Categories de licence
# ---------------------------------------------------------------------------
LICENSE_CATEGORIES = [
    "Commercial Use",
    "Personal Use Only",
    "OFL",
    "Apache License",
    "GPL",
    "MIT",
    "Public Domain",
    "Shareware",
    "Unknown",
]

# Categories considerees comme "libres" au sens large (utilisees pour le
# pont avec FontCheck, qui n'a que 4 statuts : inconnu / personnel /
# commercial / libre).
FREE_LICENSES = {"OFL", "Apache License", "GPL", "MIT", "Public Domain"}

# En dessous de ce score [0-1], on refuse de trancher et on retombe sur
# "Unknown" plutot que de risquer un faux positif (cf. point 8 du cahier
# des charges : ne jamais attribuer de licence si la confiance est faible).
CONFIDENCE_THRESHOLD = 0.55

# --------------------------------------------------------------------------- 
# Reseau / performance
# ---------------------------------------------------------------------------
MAX_CONCURRENT_FONT_PARSES = 8       # threads pour la lecture des fichiers
MAX_CONCURRENT_HTTP_REQUESTS = 5     # requetes HTTP simultanees (asyncio)
HTTP_TIMEOUT_SECONDS = 12
HTTP_MIN_DELAY_SECONDS = 0.35        # anti rate-limit entre deux requetes
HTTP_RETRIES = 2
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) FontLicenseClassifier/1.0"
)

# Active ou desactive la recherche web (Etape 3 du cahier des charges).
# Peut etre coupee depuis l'interface si l'utilisateur n'a pas de connexion
# ou veut un classement 100% local (metadonnees embarquees + base connue).
ENABLE_WEB_SEARCH = True

SUPPORTED_EXTENSIONS = {".ttf", ".otf"}
