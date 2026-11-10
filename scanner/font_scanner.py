"""
Scanner de polices.

Ce module encapsule toute l'utilisation de fontTools : decouverte des
fichiers .ttf/.otf dans une arborescence, et extraction des champs de la
table `name` (et de `head`/`OS/2` pour la version) qui nous interessent pour
la detection de licence : Family Name, Full Name, PostScript Name, Version,
Designer, Manufacturer, Copyright, Trademark, URL(s).

La lecture d'un fichier de police est une operation bloquante (I/O disque +
parsing binaire). On l'expose donc a la fois en version synchrone
(`extract_font_info`) et en version parallelisee (`scan_directory`) qui
utilise un ThreadPoolExecutor : c'est le bon outil ici puisque le cout est
majoritairement de l'I/O et que fontTools ne relache pas forcement le GIL
assez souplement pour un usage multiprocessing simple sur 10 000+ fichiers.
"""
from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Optional

from fontTools.ttLib import TTFont, TTLibError

from app.config import MAX_CONCURRENT_FONT_PARSES, SUPPORTED_EXTENSIONS

logger = logging.getLogger("fontlicense.scanner")

# Identifiants des "name IDs" du standard OpenType/TrueType qui nous
# interessent. Reference : spec OpenType, table `name`.
NAME_ID_COPYRIGHT = 0
NAME_ID_FAMILY = 1
NAME_ID_SUBFAMILY = 2
NAME_ID_UNIQUE_ID = 3
NAME_ID_FULL_NAME = 4
NAME_ID_VERSION = 5
NAME_ID_POSTSCRIPT_NAME = 6
NAME_ID_TRADEMARK = 7
NAME_ID_MANUFACTURER = 8
NAME_ID_DESIGNER = 9
NAME_ID_DESCRIPTION = 10
NAME_ID_VENDOR_URL = 11
NAME_ID_DESIGNER_URL = 12
NAME_ID_LICENSE_DESCRIPTION = 13
NAME_ID_LICENSE_URL = 14
NAME_ID_PREFERRED_FAMILY = 16
NAME_ID_WWS_FAMILY = 21


@dataclass
class FontInfo:
    """Metadonnees extraites d'un fichier de police."""

    file_path: str
    file_name: str
    file_hash: str
    family_name: str = ""
    full_name: str = ""
    postscript_name: str = ""
    subfamily: str = ""
    version: str = ""
    designer: str = ""
    designer_url: str = ""
    manufacturer: str = ""
    vendor_url: str = ""
    copyright: str = ""
    trademark: str = ""
    embedded_license_description: str = ""
    embedded_license_url: str = ""
    description: str = ""
    num_glyphs: int = 0
    error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.error is None

    @property
    def best_name(self) -> str:
        """Le nom le plus fiable disponible pour representer la police."""
        return self.family_name or self.full_name or self.postscript_name or self.file_name

    @property
    def all_urls(self) -> list[str]:
        return [u for u in (self.embedded_license_url, self.vendor_url, self.designer_url) if u]


def _file_hash(path: Path, chunk_size: int = 1 << 20) -> str:
    """Empreinte SHA-256 rapide (par blocs) utilisee comme cle de cache."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _best_name_record(name_table, name_id: int) -> str:
    """
    Recupere la meilleure valeur disponible pour un `nameID` donne.

    La table `name` d'une police stocke souvent plusieurs enregistrements
    pour le meme champ (une variante Windows/Unicode, une variante Mac
    Roman, plusieurs langues...). On privilegie l'anglais US Windows
    (le plus repandu), puis on retombe sur n'importe quel enregistrement
    disponible plutot que de renvoyer une chaine vide.
    """
    if name_table is None:
        return ""
    record = name_table.getName(name_id, 3, 1, 0x409)  # Windows, Unicode BMP, en-US
    if record is None:
        record = name_table.getName(name_id, 1, 0, 0)  # Macintosh, Roman, English
    if record is None:
        for rec in name_table.names:
            if rec.nameID == name_id:
                record = rec
                break
    if record is None:
        return ""
    try:
        return str(record).strip()
    except Exception:
        return ""


def extract_font_info(file_path: Path) -> FontInfo:
    """Ouvre une police et extrait les champs pertinents pour la classification."""
    file_hash = ""
    try:
        file_hash = _file_hash(file_path)
    except OSError as exc:
        return FontInfo(
            file_path=str(file_path), file_name=file_path.name,
            file_hash="", error=f"Lecture disque impossible : {exc}",
        )

    try:
        font = TTFont(file_path, lazy=True, fontNumber=0)
    except TTLibError as exc:
        return FontInfo(
            file_path=str(file_path), file_name=file_path.name,
            file_hash=file_hash, error=f"Fichier de police invalide : {exc}",
        )
    except Exception as exc:  # noqa: BLE001 - on veut isoler toute erreur inattendue
        return FontInfo(
            file_path=str(file_path), file_name=file_path.name,
            file_hash=file_hash, error=f"Erreur inattendue a l'ouverture : {exc}",
        )

    try:
        name_table = font["name"] if "name" in font else None

        family = (
            _best_name_record(name_table, NAME_ID_PREFERRED_FAMILY)
            or _best_name_record(name_table, NAME_ID_WWS_FAMILY)
            or _best_name_record(name_table, NAME_ID_FAMILY)
        )
        num_glyphs = 0
        try:
            num_glyphs = font["maxp"].numGlyphs if "maxp" in font else 0
        except Exception:  # noqa: BLE001
            num_glyphs = 0

        info = FontInfo(
            file_path=str(file_path),
            file_name=file_path.name,
            file_hash=file_hash,
            family_name=family,
            full_name=_best_name_record(name_table, NAME_ID_FULL_NAME),
            postscript_name=_best_name_record(name_table, NAME_ID_POSTSCRIPT_NAME),
            subfamily=_best_name_record(name_table, NAME_ID_SUBFAMILY),
            version=_best_name_record(name_table, NAME_ID_VERSION),
            designer=_best_name_record(name_table, NAME_ID_DESIGNER),
            designer_url=_best_name_record(name_table, NAME_ID_DESIGNER_URL),
            manufacturer=_best_name_record(name_table, NAME_ID_MANUFACTURER),
            vendor_url=_best_name_record(name_table, NAME_ID_VENDOR_URL),
            copyright=_best_name_record(name_table, NAME_ID_COPYRIGHT),
            trademark=_best_name_record(name_table, NAME_ID_TRADEMARK),
            embedded_license_description=_best_name_record(name_table, NAME_ID_LICENSE_DESCRIPTION),
            embedded_license_url=_best_name_record(name_table, NAME_ID_LICENSE_URL),
            description=_best_name_record(name_table, NAME_ID_DESCRIPTION),
            num_glyphs=num_glyphs,
        )
        return info
    except Exception as exc:  # noqa: BLE001
        return FontInfo(
            file_path=str(file_path), file_name=file_path.name,
            file_hash=file_hash, error=f"Erreur lors de l'extraction : {exc}",
        )
    finally:
        try:
            font.close()
        except Exception:  # noqa: BLE001
            pass


def iter_font_files(root: Path) -> Iterator[Path]:
    """Parcourt recursivement `root` et renvoie les fichiers .ttf/.otf/.ttc/.otc."""
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield path


def scan_directory(
    root: Path,
    on_progress: Optional[Callable[[int, int, FontInfo], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    max_workers: int = MAX_CONCURRENT_FONT_PARSES,
) -> list[FontInfo]:
    """
    Scanne toutes les polices d'un dossier en parallele (threads : I/O-bound).

    `on_progress(done, total, info)` est appele apres chaque fichier traite,
    `cancel_check()` permet d'interrompre proprement le scan (bouton Annuler
    de l'interface).
    """
    files = list(iter_font_files(root))
    total = len(files)
    results: list[FontInfo] = []
    if total == 0:
        return results

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(extract_font_info, path): path for path in files}
        done = 0
        for future in as_completed(futures):
            if cancel_check is not None and cancel_check():
                logger.info("Scan annule par l'utilisateur apres %s/%s fichiers", done, total)
                for f in futures:
                    f.cancel()
                break
            path = futures[future]
            try:
                info = future.result()
            except Exception as exc:  # noqa: BLE001
                info = FontInfo(file_path=str(path), file_name=path.name, file_hash="", error=str(exc))
            done += 1
            results.append(info)
            if on_progress is not None:
                on_progress(done, total, info)
    return results
