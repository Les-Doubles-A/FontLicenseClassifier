"""
Pipeline d'orchestration de bout en bout.

Relie les briques independantes (scanner, cache SQLite, classifieur,
generateur de rapports, pont FontCheck) en un traitement unique piloté par
l'interface graphique. Concu pour tourner dans un thread dedie (l'interface
CustomTkinter reste ainsi fluide) et expose des callbacks de progression /
d'erreur / d'annulation.

Point 9 (performances) : le scan des fichiers est parallelise par threads
(I/O disque), la classification reseau est parallelisee par asyncio
(I/O reseau), et une limite de requetes simultanees + un delai minimal
protegent les services distants (Google Fonts/GitHub, recherche web) contre
un usage abusif. Le cache SQLite (point 7) permet de reprendre un lot
interrompu sans tout refaire.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import aiohttp

from app.config import (
    ENABLE_WEB_SEARCH,
    MAX_CONCURRENT_HTTP_REQUESTS,
    STATE_PATH,
)
from database import db
from integrations import fontcheck_bridge
from license_detector.classifier import classify_font
from license_detector.models import ClassificationResult
from reports.report_generator import generate_reports
from scanner.font_scanner import FontInfo, iter_font_files, extract_font_info

logger = logging.getLogger("fontlicense.pipeline")


@dataclass
class PipelineProgress:
    done: int
    total: int
    current_file: str
    category: str
    confidence: float
    from_cache: bool
    elapsed_seconds: float


@dataclass
class PipelineSummary:
    total: int
    analyzed: int
    from_cache: int
    errors: int
    by_category: dict[str, int]
    report_paths: dict[str, str]
    duration_seconds: float
    cancelled: bool


class PipelineCancelled(Exception):
    """Levee en interne pour deballer proprement une annulation."""


class FontLicensePipeline:
    """
    Point d'entree unique utilise par l'interface graphique.

    Usage typique (depuis un thread separe du thread Tk) :
        pipeline = FontLicensePipeline(on_progress=..., on_error=...)
        summary = pipeline.run(source_dir, destination_dir)
    """

    def __init__(
        self,
        on_progress: Optional[Callable[[PipelineProgress], None]] = None,
        on_error: Optional[Callable[[str, str], None]] = None,
        enable_web_search: bool = ENABLE_WEB_SEARCH,
        write_fontcheck_bridge: bool = True,
    ) -> None:
        self.on_progress = on_progress or (lambda progress: None)
        self.on_error = on_error or (lambda file_name, message: None)
        self.enable_web_search = enable_web_search
        self.write_fontcheck_bridge = write_fontcheck_bridge
        self._cancel_requested = False

    # -- Controle depuis l'interface -----------------------------------
    def cancel(self) -> None:
        self._cancel_requested = True
        logger.info("Annulation demandee par l'utilisateur.")

    def _check_cancel(self) -> None:
        if self._cancel_requested:
            raise PipelineCancelled()

    # -- Point d'entree synchrone (appele depuis le thread worker) ------
    def run(self, source_dir: Path, destination_dir: Path) -> PipelineSummary:
        db.init_db()
        destination_dir.mkdir(parents=True, exist_ok=True)
        try:
            return asyncio.run(self._run_async(source_dir, destination_dir))
        except PipelineCancelled:
            logger.info("Traitement annule.")
            return self._build_summary_on_cancel(destination_dir)

    # -- Coeur asynchrone -------------------------------------------------
    async def _run_async(self, source_dir: Path, destination_dir: Path) -> PipelineSummary:
        start_time = time.monotonic()
        files = list(iter_font_files(source_dir))
        total = len(files)
        logger.info("%s fichier(s) de police detecte(s) dans %s", total, source_dir)

        if total == 0:
            summary = PipelineSummary(0, 0, 0, 0, {}, {}, 0.0, False)
            return summary

        resume_state = self._load_resume_state(source_dir)
        results: list[tuple[FontInfo, ClassificationResult]] = []
        from_cache_count = 0
        error_count = 0

        connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT_HTTP_REQUESTS)
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_HTTP_REQUESTS)
        known_extra = db.load_known_fonts_cache()

        async with aiohttp.ClientSession(connector=connector) as session:
            done = 0
            for file_path in files:
                self._check_cancel()
                done += 1
                file_key = str(file_path)

                if file_key in resume_state.get("processed", []):
                    # Deja traite lors d'une precedente execution interrompue :
                    # on relit simplement le cache pour la coherence des
                    # statistiques, sans refaire le travail.
                    pass

                info = extract_font_info(file_path)
                if not info.is_valid:
                    error_count += 1
                    self.on_error(info.file_name, info.error or "Erreur inconnue")
                    logger.error("Erreur d'analyse (%s) : %s", info.file_name, info.error)
                    self._emit_progress(done, total, info, ClassificationResult(), False, start_time)
                    self._mark_processed(resume_state, source_dir, file_key)
                    continue

                cached = db.get_cached_result(info.file_hash)
                if cached is not None:
                    result = self._result_from_cache_row(cached)
                    from_cache_count += 1
                    logger.info("Cache: %s -> %s (%.0f%%)", info.file_name, result.category, result.confidence * 100)
                else:
                    t0 = time.monotonic()
                    result = await classify_font(
                        info, session=session, semaphore=semaphore,
                        known_extra_entries=known_extra, enable_web_search=self.enable_web_search,
                    )
                    elapsed = time.monotonic() - t0
                    logger.info(
                        "Analyse: %s -> %s (%.0f%%) en %.2fs [%s]",
                        info.file_name, result.category, result.confidence * 100, elapsed, result.source,
                    )
                    db.save_result(info, result)

                results.append((info, result))
                self._emit_progress(done, total, info, result, cached is not None, start_time)
                self._mark_processed(resume_state, source_dir, file_key)

        report_paths = generate_reports(results, destination_dir)

        if self.write_fontcheck_bridge:
            try:
                bridge_path = fontcheck_bridge.export_to_fontcheck(results)
                logger.info("Resultats exportes vers FontCheck : %s", bridge_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Impossible d'exporter vers FontCheck : %s", exc)

        self._clear_resume_state(source_dir)

        by_category: dict[str, int] = {}
        for _, result in results:
            by_category[result.category] = by_category.get(result.category, 0) + 1

        duration = time.monotonic() - start_time
        logger.info("Traitement termine en %.1fs (%s polices)", duration, len(results))

        return PipelineSummary(
            total=total, analyzed=len(results), from_cache=from_cache_count,
            errors=error_count, by_category=by_category, report_paths=report_paths,
            duration_seconds=duration, cancelled=False,
        )

    # -- Aides internes ---------------------------------------------------
    def _emit_progress(self, done, total, info, result, from_cache, start_time) -> None:
        self.on_progress(
            PipelineProgress(
                done=done, total=total, current_file=info.file_name,
                category=result.category, confidence=result.confidence,
                from_cache=from_cache, elapsed_seconds=time.monotonic() - start_time,
            )
        )

    @staticmethod
    def _result_from_cache_row(row: dict) -> ClassificationResult:
        return ClassificationResult(
            category=row["category"], confidence=row["confidence"], source=row["source"] or "",
            url=row["detected_url"] or "", reason=row["reason"] or "", analyzed_at=row["analyzed_at"],
        )

    # -- Reprise apres interruption (point 9) ------------------------------
    @staticmethod
    def _resume_key(source_dir: Path) -> str:
        return str(source_dir.resolve())

    def _load_resume_state(self, source_dir: Path) -> dict:
        if not STATE_PATH.exists():
            return {"source": self._resume_key(source_dir), "processed": []}
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"source": self._resume_key(source_dir), "processed": []}
        if data.get("source") != self._resume_key(source_dir):
            return {"source": self._resume_key(source_dir), "processed": []}
        return data

    def _mark_processed(self, state: dict, source_dir: Path, file_key: str) -> None:
        state.setdefault("processed", []).append(file_key)
        # Ecriture peu frequente pour ne pas ralentir le traitement : tous
        # les 25 fichiers, ce qui reste largement suffisant pour une reprise
        # utile sans imposer une IO disque a chaque police.
        if len(state["processed"]) % 25 == 0:
            self._flush_resume_state(state)

    def _flush_resume_state(self, state: dict) -> None:
        try:
            STATE_PATH.write_text(json.dumps(state), encoding="utf-8")
        except OSError as exc:
            logger.warning("Impossible d'ecrire l'etat de reprise : %s", exc)

    def _clear_resume_state(self, source_dir: Path) -> None:
        try:
            if STATE_PATH.exists():
                STATE_PATH.unlink()
        except OSError:
            pass

    def _build_summary_on_cancel(self, destination_dir: Path) -> PipelineSummary:
        stats = db.stats_by_category()
        return PipelineSummary(
            total=sum(stats.values()), analyzed=sum(stats.values()), from_cache=0,
            errors=0, by_category=stats, report_paths={}, duration_seconds=0.0, cancelled=True,
        )
