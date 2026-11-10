"""
Cache SQLite.

Deux roles principaux, demandes par le cahier des charges :
  - Point 7 (Cache) : si une police (identifiee par son empreinte SHA-256,
    insensible au renommage/deplacement du fichier) a deja ete analysee, on
    ne refait pas les recherches internet - on relit directement le
    resultat stocke.
  - Point 9 (Performances / reprise apres interruption) : chaque resultat
    est ecrit au fil de l'eau (pas seulement a la fin du traitement), donc
    si l'application est fermee ou plante au milieu d'un lot de 10 000
    polices, relancer l'analyse sur le meme dossier saute automatiquement
    tout ce qui a deja ete traite.

La table `known_fonts` sert de cache "par famille" (independant du fichier
exact) : deux fichiers differents portant la meme famille normalisee
peuvent reutiliser un resultat a haute confiance deja obtenu, ce qui reduit
encore le nombre de requetes reseau necessaires.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from app.config import DB_PATH
from license_detector.models import ClassificationResult, Evidence

logger = logging.getLogger("fontlicense.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS font_results (
    file_hash               TEXT PRIMARY KEY,
    file_path                TEXT NOT NULL,
    file_name                TEXT NOT NULL,
    family_name               TEXT,
    full_name                 TEXT,
    postscript_name           TEXT,
    version                   TEXT,
    designer                  TEXT,
    manufacturer               TEXT,
    copyright                 TEXT,
    trademark                 TEXT,
    detected_url               TEXT,
    category                  TEXT NOT NULL,
    confidence                 REAL NOT NULL,
    source                    TEXT,
    reason                     TEXT,
    evidences_json              TEXT,
    analyzed_at                 TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS known_fonts (
    family_key   TEXT PRIMARY KEY,
    category     TEXT NOT NULL,
    confidence   REAL NOT NULL,
    url          TEXT,
    updated_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_font_results_family ON font_results(family_name);
CREATE INDEX IF NOT EXISTS idx_font_results_category ON font_results(category);
"""

_local = threading.local()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")   # tolere mieux les ecritures frequentes/concurrentes
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def get_connection() -> sqlite3.Connection:
    """Connexion SQLite par thread (sqlite3 n'aime pas le partage entre threads)."""
    if not hasattr(_local, "conn"):
        _local.conn = _connect()
    return _local.conn


_write_lock = threading.Lock()


def init_db() -> None:
    conn = get_connection()
    with _write_lock:
        conn.executescript(_SCHEMA)
        conn.commit()
    logger.info("Base SQLite initialisee : %s", DB_PATH)


@contextmanager
def _writing() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    with _write_lock:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def get_cached_result(file_hash: str) -> Optional[dict]:
    """Retourne le resultat deja stocke pour ce fichier (par empreinte), sinon None."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM font_results WHERE file_hash = ?", (file_hash,)).fetchone()
    return dict(row) if row else None


def save_result(info, result: ClassificationResult) -> None:
    """Enregistre (ou met a jour) le resultat d'une police analysee."""
    with _writing() as conn:
        conn.execute(
            """
            INSERT INTO font_results (
                file_hash, file_path, file_name, family_name, full_name, postscript_name,
                version, designer, manufacturer, copyright, trademark, detected_url,
                category, confidence, source, reason, evidences_json, analyzed_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(file_hash) DO UPDATE SET
                file_path=excluded.file_path, file_name=excluded.file_name,
                family_name=excluded.family_name, full_name=excluded.full_name,
                postscript_name=excluded.postscript_name, version=excluded.version,
                designer=excluded.designer, manufacturer=excluded.manufacturer,
                copyright=excluded.copyright, trademark=excluded.trademark,
                detected_url=excluded.detected_url, category=excluded.category,
                confidence=excluded.confidence, source=excluded.source,
                reason=excluded.reason, evidences_json=excluded.evidences_json,
                analyzed_at=excluded.analyzed_at
            """,
            (
                info.file_hash, info.file_path, info.file_name, info.family_name, info.full_name,
                info.postscript_name, info.version, info.designer, info.manufacturer,
                info.copyright, info.trademark, result.url, result.category, result.confidence,
                result.source, result.reason,
                json.dumps([asdict(e) for e in result.evidences], ensure_ascii=False),
                result.analyzed_at,
            ),
        )

    # Alimente le cache "par famille" uniquement si la confiance est haute :
    # on ne veut pas propager une hypothese fragile a d'autres fichiers.
    if result.confidence >= 0.85 and result.category != "Unknown" and info.family_name:
        from license_detector.known_fonts_db import normalize_family
        key = normalize_family(info.family_name)
        if key:
            with _writing() as conn:
                conn.execute(
                    """
                    INSERT INTO known_fonts (family_key, category, confidence, url, updated_at)
                    VALUES (?,?,?,?,?)
                    ON CONFLICT(family_key) DO UPDATE SET
                        category=excluded.category, confidence=excluded.confidence,
                        url=excluded.url, updated_at=excluded.updated_at
                    """,
                    (key, result.category, result.confidence, result.url,
                     datetime.now(timezone.utc).isoformat()),
                )


def load_known_fonts_cache() -> dict[str, dict]:
    """Charge le cache 'par famille' pour l'injecter dans known_fonts_db.lookup()."""
    conn = get_connection()
    rows = conn.execute("SELECT family_key, category, confidence, url FROM known_fonts").fetchall()
    return {
        row["family_key"]: {"category": row["category"], "url": row["url"] or "", "publisher": "cache local"}
        for row in rows
    }


def all_results() -> list[dict]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM font_results ORDER BY analyzed_at DESC").fetchall()
    return [dict(row) for row in rows]


def stats_by_category() -> dict[str, int]:
    conn = get_connection()
    rows = conn.execute("SELECT category, COUNT(*) AS n FROM font_results GROUP BY category").fetchall()
    return {row["category"]: row["n"] for row in rows}


def clear_cache() -> None:
    with _writing() as conn:
        conn.execute("DELETE FROM font_results")
        conn.execute("DELETE FROM known_fonts")
