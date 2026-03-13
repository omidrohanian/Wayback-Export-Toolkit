from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .analysis import analyze_snapshot
from .download import download_candidates
from .models import AnalysisResult, AnalyzeOptions, CandidateFile, DownloadOptions


@dataclass
class GuiConfig:
    snapshot_url: str
    output_dir: Path
    include_pattern: str | None
    exclude_pattern: str | None
    timeout_seconds: int
    max_depth: int
    max_pages: int
    allow_cross_host: bool
    download_all: bool
    manifest_only: bool


HELP_TEXTS = {
    "include_pattern": "Only keep discovered candidates that match this regex.",
    "exclude_pattern": "Drop discovered candidates that match this regex.",
    "timeout_seconds": "HTTP timeout per request in seconds. Increase for slower archives.",
    "max_depth": "How many link levels to follow from the snapshot page. 0 means root page only.",
    "max_pages": "Upper limit on crawled pages to avoid runaway scraping.",
    "download_all": "If enabled, download every discovered candidate without manual selection.",
    "manifest_only": "If enabled, write only manifest/planned records and skip actual file downloads.",
    "allow_cross_host": "If enabled, traversal can follow links to hosts outside the original site.",
}


def get_help_text(key: str) -> str:
    return HELP_TEXTS[key]


def parse_int_field(raw: str, field_name: str, minimum: int) -> int:
    try:
        value = int(raw.strip())
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an integer.") from exc
    if value < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}.")
    return value


def format_candidate_row(index: int, candidate: CandidateFile) -> str:
    return (
        f"{index:>3} | {candidate.detected_type:<8} | "
        f"{candidate.confidence:>4.2f} | {candidate.estimated_filename}"
    )


def build_selection_from_indexes(
    candidates: Sequence[CandidateFile], selected_indexes: Sequence[int], all_selected: bool
) -> list[CandidateFile]:
    if all_selected:
        return list(candidates)
    out: list[CandidateFile] = []
    for idx in selected_indexes:
        if idx < 0 or idx >= len(candidates):
            raise ValueError("Candidate selection contains an invalid index.")
        out.append(candidates[idx])
    return out


def launch_gui() -> int:
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Tkinter is not available in this Python environment."
        ) from exc

    class App:
        def __init__(self, root: tk.Tk) -> None:
            self.root = root
            self.root.title("Wayback Export Toolkit")
            self.analysis: AnalysisResult | None = None
            self._build_layout()

        def _build_layout(self) -> None:
            root = self.root
            root.geometry("980x640")
            root.columnconfigure(1, weight=1)
            for row in range(8):
                root.rowconfigure(row, weight=0)
            root.rowconfigure(7, weight=1)

            self.snapshot_var = tk.StringVar()
            self.output_var = tk.StringVar(value="./downloads")
            self.include_var = tk.StringVar()
            self.exclude_var = tk.StringVar()
            self.timeout_var = tk.StringVar(value="30")
            self.depth_var = tk.StringVar(value="0")
            self.pages_var = tk.StringVar(value="100")
            self.all_var = tk.BooleanVar(value=False)
            self.manifest_only_var = tk.BooleanVar(value=False)
            self.cross_host_var = tk.BooleanVar(value=False)

            self._add_labeled_entry(0, "Snapshot URL", self.snapshot_var)
            self._add_labeled_entry(1, "Output Dir", self.output_var)
            self._add_labeled_entry(2, "Include Regex", self.include_var)
            self._add_labeled_entry(3, "Exclude Regex", self.exclude_var)
            self._add_labeled_entry(4, "Timeout (s)", self.timeout_var)
            self._add_labeled_entry(5, "Max Depth", self.depth_var)
            self._add_labeled_entry(6, "Max Pages", self.pages_var)

            options = tk.Frame(root, highlightthickness=1, highlightbackground="#d0d0d0")
            options.grid(row=0, column=2, rowspan=3, sticky="nw", padx=8, pady=6)
            tk.Label(options, text="Options", font=("TkDefaultFont", 10, "bold")).grid(
                row=0, column=0, sticky="w", padx=8, pady=(6, 2)
            )
            self._add_option_toggle(
                options,
                row=1,
                text="Download all candidates",
                variable=self.all_var,
                help_key="download_all",
            )
            self._add_option_toggle(
                options,
                row=2,
                text="Plan only (manifest only)",
                variable=self.manifest_only_var,
                help_key="manifest_only",
            )
            self._add_option_toggle(
                options,
                row=3,
                text="Allow cross-host crawl",
                variable=self.cross_host_var,
                help_key="allow_cross_host",
            )
            self.toggle_state_label = tk.Label(
                options,
                text=self._toggle_state_summary(),
                justify="left",
                fg="#404040",
                wraplength=290,
            )
            self.toggle_state_label.grid(row=4, column=0, columnspan=2, sticky="w", padx=8, pady=(6, 8))

            buttons = tk.Frame(root)
            buttons.grid(row=3, column=2, rowspan=2, sticky="nw", padx=8, pady=6)
            tk.Button(buttons, text="Analyze", width=14, command=self.on_analyze).pack(
                anchor="w", pady=3
            )
            tk.Button(
                buttons, text="Download", width=14, command=self.on_download
            ).pack(anchor="w", pady=3)

            tk.Label(root, text="Candidates").grid(
                row=7, column=0, sticky="nw", padx=6, pady=(6, 0)
            )
            self.candidate_list = tk.Listbox(root, selectmode=tk.EXTENDED, height=14)
            self.candidate_list.grid(
                row=7, column=0, columnspan=2, sticky="nsew", padx=6, pady=6
            )

            tk.Label(root, text="Log").grid(row=7, column=2, sticky="nw", padx=6, pady=(6, 0))
            self.log = tk.Text(root, wrap="word", height=14)
            self.log.grid(row=7, column=2, sticky="nsew", padx=6, pady=6)
            root.columnconfigure(2, weight=1)

        def _add_labeled_entry(self, row: int, label: str, var) -> None:
            tk.Label(self.root, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=4)
            entry = tk.Entry(self.root, textvariable=var)
            entry.grid(row=row, column=1, sticky="ew", padx=6, pady=4)
            key_map = {
                "Include Regex": "include_pattern",
                "Exclude Regex": "exclude_pattern",
                "Timeout (s)": "timeout_seconds",
                "Max Depth": "max_depth",
                "Max Pages": "max_pages",
            }
            help_key = key_map.get(label)
            if help_key:
                tk.Button(
                    self.root,
                    text="i",
                    width=2,
                    command=lambda k=help_key: messagebox.showinfo(label, get_help_text(k)),
                ).grid(row=row, column=2, sticky="w", padx=(0, 2), pady=4)

        def _add_option_toggle(self, parent, row: int, text: str, variable, help_key: str) -> None:
            check = ttk.Checkbutton(
                parent,
                text=text,
                variable=variable,
                command=self._on_toggle_change,
            )
            check.grid(row=row, column=0, sticky="w", padx=8, pady=2)
            tk.Button(
                parent,
                text="i",
                width=2,
                command=lambda k=help_key: messagebox.showinfo("Option Help", get_help_text(k)),
            ).grid(row=row, column=1, sticky="w", padx=(0, 8), pady=2)

        def _toggle_state_summary(self) -> str:
            return (
                f"Download all: {'ON' if self.all_var.get() else 'OFF'}\n"
                f"Plan only: {'ON' if self.manifest_only_var.get() else 'OFF'}\n"
                f"Cross-host crawl: {'ON' if self.cross_host_var.get() else 'OFF'}"
            )

        def _on_toggle_change(self) -> None:
            self.toggle_state_label.configure(text=self._toggle_state_summary())
            self.root.update_idletasks()
            self._append_log("Options updated.")

        def _config_from_fields(self) -> GuiConfig:
            snapshot_url = self.snapshot_var.get().strip()
            if not snapshot_url:
                raise ValueError("Snapshot URL is required.")
            return GuiConfig(
                snapshot_url=snapshot_url,
                output_dir=Path(self.output_var.get().strip() or "./downloads"),
                include_pattern=self.include_var.get().strip() or None,
                exclude_pattern=self.exclude_var.get().strip() or None,
                timeout_seconds=parse_int_field(self.timeout_var.get(), "Timeout", 1),
                max_depth=parse_int_field(self.depth_var.get(), "Max Depth", 0),
                max_pages=parse_int_field(self.pages_var.get(), "Max Pages", 1),
                allow_cross_host=self.cross_host_var.get(),
                download_all=self.all_var.get(),
                manifest_only=self.manifest_only_var.get(),
            )

        def _append_log(self, line: str) -> None:
            self.log.insert("end", line + "\n")
            self.log.see("end")

        def on_analyze(self) -> None:
            try:
                cfg = self._config_from_fields()
                self.analysis = analyze_snapshot(
                    cfg.snapshot_url,
                    AnalyzeOptions(
                        include_pattern=cfg.include_pattern,
                        exclude_pattern=cfg.exclude_pattern,
                        timeout_seconds=cfg.timeout_seconds,
                        max_depth=cfg.max_depth,
                        max_pages=cfg.max_pages,
                        same_host_only=not cfg.allow_cross_host,
                    ),
                )
            except Exception as exc:
                messagebox.showerror("Analyze failed", str(exc))
                self._append_log(f"Analyze failed: {exc}")
                return

            self.candidate_list.delete(0, "end")
            for idx, candidate in enumerate(self.analysis.candidates, start=1):
                self.candidate_list.insert("end", format_candidate_row(idx, candidate))

            self._append_log(
                f"Analyzed snapshot: found {len(self.analysis.candidates)} candidates."
            )
            for warning in self.analysis.warnings:
                self._append_log(f"Warning: {warning}")

        def on_download(self) -> None:
            try:
                self.root.update_idletasks()
                cfg = self._config_from_fields()
                if self.analysis is None or self.analysis.snapshot.snapshot_url != cfg.snapshot_url:
                    self.on_analyze()
                if self.analysis is None:
                    return

                selected_indexes = list(self.candidate_list.curselection())
                selection = build_selection_from_indexes(
                    self.analysis.candidates, selected_indexes, all_selected=cfg.download_all
                )
                if not selection and not cfg.download_all:
                    raise ValueError(
                        "No candidates selected. Select at least one item or enable Download All."
                    )

                result = download_candidates(
                    cfg.snapshot_url,
                    selection=selection,
                    options=DownloadOptions(
                        output_dir=cfg.output_dir,
                        include_pattern=cfg.include_pattern,
                        exclude_pattern=cfg.exclude_pattern,
                        timeout_seconds=cfg.timeout_seconds,
                        download_all=cfg.download_all,
                        manifest_only=cfg.manifest_only,
                        interactive=False,
                        max_depth=cfg.max_depth,
                        max_pages=cfg.max_pages,
                        same_host_only=not cfg.allow_cross_host,
                    ),
                    analysis=self.analysis,
                )
            except Exception as exc:
                messagebox.showerror("Download failed", str(exc))
                self._append_log(f"Download failed: {exc}")
                return

            self._append_log(
                f"Manifest: {result.manifest_path} | downloaded={len(result.downloaded)} "
                f"skipped={len(result.skipped)} failed={len(result.failed)} "
                f"planned={len(result.planned)}"
            )
            if result.failed:
                self._append_log("Some files failed. Check manifest for details.")

    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0
