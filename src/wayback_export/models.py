from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class SnapshotInfo:
    snapshot_url: str
    timestamp: str
    archived_url: str
    original_url: str


@dataclass(frozen=True)
class CandidateFile:
    title: str
    archived_url: str
    original_url: Optional[str]
    detected_type: str
    confidence: float
    reason: str
    estimated_filename: str


@dataclass
class AnalyzeOptions:
    include_pattern: Optional[str] = None
    exclude_pattern: Optional[str] = None
    timeout_seconds: int = 30
    user_agent: str = "wayback-export-toolkit/0.1"
    max_depth: int = 0
    max_pages: int = 100
    same_host_only: bool = True


@dataclass
class AnalysisResult:
    snapshot: SnapshotInfo
    candidates: List[CandidateFile]
    warnings: List[str] = field(default_factory=list)


@dataclass
class DownloadOptions:
    output_dir: Path
    include_pattern: Optional[str] = None
    exclude_pattern: Optional[str] = None
    timeout_seconds: int = 30
    user_agent: str = "wayback-export-toolkit/0.1"
    download_all: bool = False
    manifest_only: bool = False
    skip_existing: bool = True
    interactive: bool = True
    max_depth: int = 0
    max_pages: int = 100
    same_host_only: bool = True


@dataclass
class DownloadRecord:
    candidate: CandidateFile
    destination_path: Optional[str]
    status: str
    bytes_downloaded: int = 0
    checksum_sha256: Optional[str] = None
    error: Optional[str] = None


@dataclass
class DownloadResult:
    manifest_path: str
    downloaded: List[DownloadRecord]
    skipped: List[DownloadRecord]
    failed: List[DownloadRecord]
    planned: List[DownloadRecord]


@dataclass
class MirrorOptions:
    output_dir: Path
    timeout_seconds: int = 30
    user_agent: str = "wayback-export-toolkit/0.1"
    max_depth: int = 2
    max_pages: int = 500
    same_host_only: bool = True
    skip_existing: bool = True


@dataclass
class MirrorResult:
    manifest_path: str
    site_dir: str
    pages_saved: int
    assets_downloaded: int
    assets_skipped: int
    failed: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def dataclass_to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {
            key: dataclass_to_dict(getattr(value, key))
            for key in value.__dataclass_fields__.keys()
        }
    if isinstance(value, list):
        return [dataclass_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {k: dataclass_to_dict(v) for k, v in value.items()}
    if isinstance(value, Path):
        return str(value)
    return value


def result_to_dict(result: AnalysisResult | DownloadResult | MirrorResult) -> Dict[str, Any]:
    return dataclass_to_dict(result)
