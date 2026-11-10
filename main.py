"""
Point d'entree de FontLicenseClassifier.

Lancement :
    python main.py

Prerequis : `pip install -r requirements.txt` (voir README.md pour le
detail des dependances et de l'architecture du projet).
"""
from __future__ import annotations

import logging
import sys

from utils.logging_config import setup_logging


def main() -> int:
    setup_logging(level=logging.INFO)
    logger = logging.getLogger("fontlicense.main")
    logger.info("Demarrage de FontLicenseClassifier")

    try:
        from database import db
        db.init_db()
    except Exception:
        logger.exception("Impossible d'initialiser la base de cache SQLite")
        return 1

    try:
        from gui.main_window import launch
        launch()
    except Exception:
        logger.exception("Erreur fatale au demarrage de l'interface")
        return 1

    logger.info("Fermeture de FontLicenseClassifier")
    return 0


if __name__ == "__main__":
    sys.exit(main())
