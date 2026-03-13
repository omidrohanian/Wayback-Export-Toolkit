from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence
from urllib.parse import urlparse

from .analysis import analyze_snapshot
from .http_client import HttpClient, UrlLibHttpClient
from .models import (
    AnalysisResult,
    AnalyzeOptions,
    CandidateFile,
    DownloadOptions,
    DownloadRecord,
    DownloadResult,
)
from .output import build_run_dir, summarize_result, write_manifest
from .selection import prompt_select_candidates


def download_candidates(
    snapshot_url: str,
    selection: Optional[Sequence[CandidateFile]] = None,
    options: Optional[DownloadOptions] = None,
    http_client: HttpClient | None = None,
    analysis: AnalysisResult | None = None,
) -> DownloadResult:
    if options is None:
        options = DownloadOptions(output_dir=Path.cwd() / "downloads")
    http_client = http_client or UrlLibHttpClient()

    if analysis is None:
        analysis = analyze_snapshot(
            snapshot_url,
            options=AnalyzeOptions(
            include_pattern=options.include_pattern,
            exclude_pattern=options.exclude_pattern,
            timeout_seconds=options.timeout_seconds,
            user_agent=options.user_agent,
            max_depth=options.max_depth,
            max_pages=options.max_pages,
            same_host_only=options.same_host_only,
        ),
        http_client=http_client,
    )

    selected = _resolve_selection(analysis.candidates, selection, options)

    target_host = urlparse(analysis.snapshot.original_url).netloc or "snapshot"
    run_dir = build_run_dir(options.output_dir, target_host, analysis.snapshot.timestamp)
    files_dir = run_dir / "files"
    manifest_path = run_dir / "manifest.json"
    files_dir.mkdir(parents=True, exist_ok=True)

    records: List[DownloadRecord] = []
    filename_counts: Dict[str, int] = {}
    for candidate in selected:
        destination = _destination_for_candidate(
            files_dir=files_dir,
            filename=candidate.estimated_filename,
            counts=filename_counts,
        )
        if options.manifest_only:
            records.append(
                DownloadRecord(
                    candidate=candidate,
                    destination_path=str(destination),
                    status="planned",
                )
            )
            continue

        if options.skip_existing and destination.exists():
            records.append(
                DownloadRecord(
                    candidate=candidate,
                    destination_path=str(destination),
                    status="skipped",
                    bytes_downloaded=destination.stat().st_size,
                )
            )
            continue

        try:
            size, checksum = http_client.download_file(
                candidate.archived_url,
                destination=destination,
                timeout=options.timeout_seconds,
                user_agent=options.user_agent,
            )
            records.append(
                DownloadRecord(
                    candidate=candidate,
                    destination_path=str(destination),
                    status="downloaded",
                    bytes_downloaded=size,
                    checksum_sha256=checksum,
                )
            )
        except Exception as exc:
            records.append(
                DownloadRecord(
                    candidate=candidate,
                    destination_path=str(destination),
                    status="failed",
                    error=str(exc),
                )
            )

    write_manifest(
        manifest_path=manifest_path,
        analysis=analysis,
        selected_count=len(selected),
        records=records,
    )
    return summarize_result(manifest_path=manifest_path, records=records)


def _resolve_selection(
    discovered: Sequence[CandidateFile],
    selection: Optional[Sequence[CandidateFile]],
    options: DownloadOptions,
) -> List[CandidateFile]:
    if selection is not None:
        return list(selection)
    if options.download_all:
        return list(discovered)
    if options.interactive:
        return prompt_select_candidates(discovered)
    return list(discovered)


def _destination_for_candidate(files_dir: Path, filename: str, counts: Dict[str, int]) -> Path:
    count = counts.get(filename, 0)
    counts[filename] = count + 1
    if count == 0:
        return files_dir / filename
    base = Path(filename)
    return files_dir / f"{base.stem}_{count}{base.suffix}"
