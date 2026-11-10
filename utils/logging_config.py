"""
Journalisation complete de l'application (point 10 du cahier des charges) :
erreurs, temps d'analyse, recherches effectuees, licence trouvee, raison du
classement. Un fichier log horodate est cree a chaque lancement dans
%APPDATA%/FontLicenseClassifier/logs, et les evenements importants sont
egalement affiches dans la console pour le suivi en direct pendant le
developpement.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

from app.config import LOG_DIR


def setup_logging(level: int = logging.INFO) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"fontlicense_{datetime.now():%Y%m%d_%H%M%S}.log"

    root = logging.getLogger("fontlicense")
    root.setLevel(level)
    root.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)-24s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    root.addHandler(console_handler)

    root.info("Journalisation initialisee -> %s", log_file)
    return log_file
