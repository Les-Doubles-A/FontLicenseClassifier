"""
Interface graphique principale (point 1 du cahier des charges).

Construite avec CustomTkinter pour un rendu moderne tout en restant sur la
base de Tkinter (aucune dependance lourde, coherent avec l'outil FontCheck
deja fourni par l'utilisateur, egalement base sur Tkinter). Le traitement
long (scan + classification) tourne dans un thread separe pour ne jamais
geler l'interface ; la communication vers le thread Tk se fait via une
`queue.Queue`, seule methode sure pour mettre a jour des widgets Tk depuis
un autre thread.
"""
from __future__ import annotations

import logging
import queue
import threading
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app.config import ENABLE_WEB_SEARCH
from app.pipeline import FontLicensePipeline, PipelineProgress, PipelineSummary

logger = logging.getLogger("fontlicense.gui")

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("dark-blue")

BG = "#f4efe6"
INK = "#20201e"
ACCENT = "#e95c43"
MUTED = "#75716b"

_CATEGORY_BADGE_COLOR = {
    "Commercial Use": "#2f8f57",
    "Personal Use Only": "#c9463a",
    "OFL": "#3a6fc9",
    "Apache License": "#3a6fc9",
    "GPL": "#3a6fc9",
    "MIT": "#3a6fc9",
    "Public Domain": "#3a6fc9",
    "Shareware": "#c98a3a",
    "Unknown": "#75716b",
}


class _QueueEvent:
    """Petits messages types echanges entre le thread pipeline et le thread Tk."""

    def __init__(self, kind: str, payload) -> None:
        self.kind = kind  # "progress" | "error" | "done" | "log"
        self.payload = payload


class FontLicenseApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("FontLicenseClassifier - Classement automatique de licences de polices")
        self.geometry("980x720")
        self.minsize(820, 600)
        self.configure(fg_color=BG)

        self._queue: queue.Queue[_QueueEvent] = queue.Queue()
        self._pipeline: FontLicensePipeline | None = None
        self._worker: threading.Thread | None = None
        self._running = False

        self.source_dir = ctk.StringVar(value="")
        self.destination_dir = ctk.StringVar(value="")
        self.web_search_enabled = ctk.BooleanVar(value=ENABLE_WEB_SEARCH)

        self._build_layout()
        self.after(120, self._poll_queue)

    # ------------------------------------------------------------------
    # Construction de l'interface
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        header = ctk.CTkFrame(self, fg_color=INK, corner_radius=0, height=90)
        header.pack(side="top", fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text="FontLicenseClassifier",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"), text_color="white",
        ).pack(anchor="w", padx=30, pady=(18, 0))
        ctk.CTkLabel(
            header, text="Classement automatique de milliers de polices selon leur licence",
            font=ctk.CTkFont(family="Segoe UI", size=12), text_color="#c9c3ba",
        ).pack(anchor="w", padx=30, pady=(0, 14))

        body = ctk.CTkFrame(self, fg_color=BG)
        body.pack(side="top", fill="both", expand=True, padx=28, pady=22)

        self._build_folder_section(body)
        self._build_options_section(body)
        self._build_progress_section(body)
        self._build_log_section(body)
        self._build_action_bar(body)

    def _build_folder_section(self, parent) -> None:
        frame = ctk.CTkFrame(parent, fg_color="white", corner_radius=10)
        frame.pack(fill="x", pady=(0, 14))

        self._folder_row(frame, "Dossier des polices (.ttf / .otf)", self.source_dir, self._pick_source, 0)
        self._folder_row(frame, "Dossier de destination (rapports)", self.destination_dir, self._pick_destination, 1)

    def _folder_row(self, parent, label, variable, command, row) -> None:
        ctk.CTkLabel(
            parent, text=label, font=ctk.CTkFont(size=12, weight="bold"), text_color=INK,
        ).grid(row=row * 2, column=0, sticky="w", padx=18, pady=(14 if row == 0 else 4, 2), columnspan=2)
        entry = ctk.CTkEntry(parent, textvariable=variable, width=650, placeholder_text="Aucun dossier selectionne")
        entry.grid(row=row * 2 + 1, column=0, sticky="ew", padx=(18, 8), pady=(0, 14))
        ctk.CTkButton(
            parent, text="Parcourir...", width=120, fg_color=INK, hover_color=ACCENT, command=command,
        ).grid(row=row * 2 + 1, column=1, sticky="e", padx=(0, 18), pady=(0, 14))
        parent.grid_columnconfigure(0, weight=1)

    def _build_options_section(self, parent) -> None:
        frame = ctk.CTkFrame(parent, fg_color="white", corner_radius=10)
        frame.pack(fill="x", pady=(0, 14))
        ctk.CTkSwitch(
            frame, text="Activer la recherche de licence sur internet (Google Fonts, GitHub, sites specialises...)",
            variable=self.web_search_enabled, progress_color=ACCENT,
        ).pack(anchor="w", padx=18, pady=12)
        ctk.CTkLabel(
            frame,
            text="Desactivez cette option pour un classement 100% local (metadonnees embarquees "
                 "et base de polices connues uniquement), plus rapide et fonctionnant hors-ligne.",
            font=ctk.CTkFont(size=11), text_color=MUTED, wraplength=880, justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 14))

    def _build_progress_section(self, parent) -> None:
        frame = ctk.CTkFrame(parent, fg_color="white", corner_radius=10)
        frame.pack(fill="x", pady=(0, 14))

        stats_row = ctk.CTkFrame(frame, fg_color="white")
        stats_row.pack(fill="x", padx=18, pady=(16, 6))
        self.progress_label = ctk.CTkLabel(
            stats_row, text="Pret. Selectionnez un dossier de polices pour commencer.",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=INK,
        )
        self.progress_label.pack(side="left")
        self.counter_label = ctk.CTkLabel(stats_row, text="", font=ctk.CTkFont(size=12), text_color=MUTED)
        self.counter_label.pack(side="right")

        self.progress_bar = ctk.CTkProgressBar(frame, progress_color=ACCENT)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=18, pady=(0, 8))

        self.current_file_label = ctk.CTkLabel(
            frame, text="", font=ctk.CTkFont(size=11), text_color=MUTED, anchor="w",
        )
        self.current_file_label.pack(fill="x", padx=18, pady=(0, 16))

    def _build_log_section(self, parent) -> None:
        frame = ctk.CTkFrame(parent, fg_color="white", corner_radius=10)
        frame.pack(fill="both", expand=True, pady=(0, 14))
        ctk.CTkLabel(
            frame, text="JOURNAL D'ANALYSE ET ERREURS", font=ctk.CTkFont(size=11, weight="bold"), text_color=MUTED,
        ).pack(anchor="w", padx=18, pady=(14, 4))
        self.log_box = ctk.CTkTextbox(frame, fg_color="#faf8f4", text_color=INK, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_box.pack(fill="both", expand=True, padx=18, pady=(0, 16))
        self.log_box.configure(state="disabled")

    def _build_action_bar(self, parent) -> None:
        frame = ctk.CTkFrame(parent, fg_color=BG)
        frame.pack(fill="x")
        self.start_button = ctk.CTkButton(
            frame, text="Lancer l'analyse", fg_color=ACCENT, hover_color="#c94a35",
            font=ctk.CTkFont(size=13, weight="bold"), height=42, width=180, command=self._start,
        )
        self.start_button.pack(side="left")
        self.cancel_button = ctk.CTkButton(
            frame, text="Annuler", fg_color=INK, hover_color="#3a3a37",
            height=42, width=140, command=self._cancel, state="disabled",
        )
        self.cancel_button.pack(side="left", padx=10)
        self.open_report_button = ctk.CTkButton(
            frame, text="Ouvrir le rapport HTML", fg_color="white", text_color=INK,
            border_width=1, border_color=MUTED, hover_color="#eee8dd",
            height=42, width=200, command=self._open_report, state="disabled",
        )
        self.open_report_button.pack(side="right")
        self._last_report_path: str | None = None

    # ------------------------------------------------------------------
    # Selection des dossiers
    # ------------------------------------------------------------------
    def _pick_source(self) -> None:
        path = filedialog.askdirectory(title="Choisir le dossier contenant les polices")
        if path:
            self.source_dir.set(path)

    def _pick_destination(self) -> None:
        path = filedialog.askdirectory(title="Choisir le dossier de destination des rapports")
        if path:
            self.destination_dir.set(path)

    # ------------------------------------------------------------------
    # Lancement / annulation du traitement
    # ------------------------------------------------------------------
    def _start(self) -> None:
        if self._running:
            return
        source = self.source_dir.get().strip()
        destination = self.destination_dir.get().strip()
        if not source or not Path(source).is_dir():
            messagebox.showwarning("Dossier manquant", "Choisissez d'abord un dossier de polices valide.")
            return
        if not destination:
            messagebox.showwarning("Dossier manquant", "Choisissez un dossier de destination pour les rapports.")
            return

        self._running = True
        self._set_running_state(True)
        self._append_log(f"Demarrage de l'analyse : {source}")
        self._clear_log(keep_first=True)

        self._pipeline = FontLicensePipeline(
            on_progress=self._on_progress_threadsafe,
            on_error=self._on_error_threadsafe,
            enable_web_search=self.web_search_enabled.get(),
        )
        self._worker = threading.Thread(
            target=self._run_pipeline_worker,
            args=(Path(source), Path(destination)),
            daemon=True,
        )
        self._worker.start()

    def _cancel(self) -> None:
        if self._pipeline is not None:
            self._pipeline.cancel()
            self.cancel_button.configure(state="disabled", text="Annulation...")

    def _run_pipeline_worker(self, source: Path, destination: Path) -> None:
        try:
            summary = self._pipeline.run(source, destination)
            self._queue.put(_QueueEvent("done", summary))
        except Exception as exc:  # noqa: BLE001 - on ne veut jamais perdre l'erreur silencieusement
            logger.exception("Erreur fatale dans le pipeline")
            self._queue.put(_QueueEvent("fatal_error", str(exc)))

    # -- Callbacks appeles depuis le thread pipeline (jamais toucher Tk ici) --
    def _on_progress_threadsafe(self, progress: PipelineProgress) -> None:
        self._queue.put(_QueueEvent("progress", progress))

    def _on_error_threadsafe(self, file_name: str, message: str) -> None:
        self._queue.put(_QueueEvent("error", (file_name, message)))

    # -- Boucle de sondage cote thread Tk (seul endroit ou l'on touche les widgets) --
    def _poll_queue(self) -> None:
        try:
            while True:
                event = self._queue.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        self.after(120, self._poll_queue)

    def _handle_event(self, event: _QueueEvent) -> None:
        if event.kind == "progress":
            self._render_progress(event.payload)
        elif event.kind == "error":
            file_name, message = event.payload
            self._append_log(f"[ERREUR] {file_name} : {message}")
        elif event.kind == "done":
            self._render_summary(event.payload)
        elif event.kind == "fatal_error":
            self._set_running_state(False)
            self._append_log(f"[ERREUR FATALE] {event.payload}")
            messagebox.showerror("Erreur", f"Le traitement s'est arrete de facon inattendue :\n{event.payload}")

    def _render_progress(self, progress: PipelineProgress) -> None:
        ratio = progress.done / progress.total if progress.total else 0
        self.progress_bar.set(ratio)
        self.progress_label.configure(text=f"Analyse en cours... ({ratio:.0%})")
        self.counter_label.configure(text=f"{progress.done} / {progress.total} polices analysees")
        badge = "[cache]" if progress.from_cache else ""
        self.current_file_label.configure(
            text=f"{progress.current_file}  ->  {progress.category} "
                 f"(confiance {progress.confidence:.0%}) {badge}"
        )
        if progress.done % 5 == 0 or progress.done == progress.total:
            self._append_log(
                f"{progress.current_file} -> {progress.category} ({progress.confidence:.0%}) {badge}"
            )

    def _render_summary(self, summary: PipelineSummary) -> None:
        self._set_running_state(False)
        if summary.cancelled:
            self.progress_label.configure(text="Analyse annulee par l'utilisateur.")
            self._append_log("Analyse annulee. Les resultats deja obtenus sont conserves dans le cache.")
            return

        self.progress_bar.set(1.0)
        self.progress_label.configure(text=f"Termine : {summary.analyzed} police(s) analysee(s) en {summary.duration_seconds:.1f}s")
        self.counter_label.configure(
            text=f"{summary.from_cache} depuis le cache | {summary.errors} erreur(s)"
        )
        self._append_log("--- Resume ---")
        for category, count in sorted(summary.by_category.items(), key=lambda item: -item[1]):
            self._append_log(f"  {category} : {count}")
        if summary.report_paths:
            self._append_log(f"Rapports generes : {summary.report_paths}")
            self._last_report_path = summary.report_paths.get("html")
            self.open_report_button.configure(state="normal")

    def _set_running_state(self, running: bool) -> None:
        self._running = running
        self.start_button.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(state="normal" if running else "disabled", text="Annuler")

    def _open_report(self) -> None:
        if self._last_report_path:
            webbrowser.open(f"file://{self._last_report_path}")

    # -- Journal texte ------------------------------------------------------
    def _append_log(self, text: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _clear_log(self, keep_first: bool = False) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")


def launch() -> None:
    app = FontLicenseApp()
    app.mainloop()
