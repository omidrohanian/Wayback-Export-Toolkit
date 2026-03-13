from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from .models import AnalysisResult, DownloadRecord, DownloadResult, result_to_dict


def build_run_dir(base: Path, snapshot_host: str, timestamp: str) -> Path:
    normalized_host = snapshot_host.replace(":", "_")
    return base / f"{normalized_host}_{timestamp}"


def ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    counter = 1
    while True:
        candidate = path.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def write_manifest(
    manifest_path: Path,
    analysis: AnalysisResult,
    selected_count: int,
    records: list[DownloadRecord],
) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "snapshot": result_to_dict(analysis.snapshot),
        "discovered_candidates": [result_to_dict(c) for c in analysis.candidates],
        "selected_count": selected_count,
        "records": [result_to_dict(r) for r in records],
    }
    manifest_path.write_text(json.dumps(body, indent=2), encoding="utf-8")


def summarize_result(manifest_path: Path, records: list[DownloadRecord]) -> DownloadResult:
    downloaded = [record for record in records if record.status == "downloaded"]
    skipped = [record for record in records if record.status == "skipped"]
    failed = [record for record in records if record.status == "failed"]
    planned = [record for record in records if record.status == "planned"]
    return DownloadResult(
        manifest_path=str(manifest_path),
        downloaded=downloaded,
        skipped=skipped,
        failed=failed,
        planned=planned,
    )


def infer_target_host(snapshot_url: str) -> str:
    parsed = urlparse(snapshot_url)
    return parsed.netloc or "snapshot"
