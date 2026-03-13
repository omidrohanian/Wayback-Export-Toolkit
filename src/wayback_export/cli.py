from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analysis import analyze_snapshot
from .download import download_candidates
from .models import AnalyzeOptions, DownloadOptions, result_to_dict
from .selection import prompt_select_candidates
from .wayback import WaybackUrlError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wayback-export",
        description="Analyze Wayback snapshot links and download export-like artifacts.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze = subparsers.add_parser("analyze", help="Analyze snapshot and list candidates")
    analyze.add_argument("snapshot_url", help="Wayback snapshot URL")
    analyze.add_argument("--json", action="store_true", help="Print JSON output")
    analyze.add_argument("--include-pattern", help="Regex include filter", default=None)
    analyze.add_argument("--exclude-pattern", help="Regex exclude filter", default=None)
    analyze.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")
    analyze.add_argument("--max-depth", type=int, default=0, help="Traversal depth from root page")
    analyze.add_argument(
        "--max-pages", type=int, default=100, help="Maximum pages to fetch during traversal"
    )
    analyze.add_argument(
        "--allow-cross-host",
        action="store_true",
        help="Follow links outside the original host",
    )

    download = subparsers.add_parser(
        "download", help="Analyze snapshot and download selected candidates"
    )
    download.add_argument("snapshot_url", help="Wayback snapshot URL")
    download.add_argument("--output", type=Path, default=Path("./downloads"))
    download.add_argument("--all", action="store_true", help="Download all candidates")
    download.add_argument("--manifest-only", action="store_true")
    download.add_argument("--json", action="store_true", help="Print JSON output")
    download.add_argument("--include-pattern", help="Regex include filter", default=None)
    download.add_argument("--exclude-pattern", help="Regex exclude filter", default=None)
    download.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")
    download.add_argument("--max-depth", type=int, default=0, help="Traversal depth from root page")
    download.add_argument(
        "--max-pages", type=int, default=100, help="Maximum pages to fetch during traversal"
    )
    download.add_argument(
        "--allow-cross-host",
        action="store_true",
        help="Follow links outside the original host",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "analyze":
            return _cmd_analyze(args)
        if args.command == "download":
            return _cmd_download(args)
    except WaybackUrlError as exc:
        parser.error(str(exc))
    except ValueError as exc:
        parser.error(str(exc))
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    result = analyze_snapshot(
        args.snapshot_url,
        options=AnalyzeOptions(
            include_pattern=args.include_pattern,
            exclude_pattern=args.exclude_pattern,
            timeout_seconds=args.timeout,
            max_depth=args.max_depth,
            max_pages=args.max_pages,
            same_host_only=not args.allow_cross_host,
        ),
    )
    if args.json:
        print(json.dumps(result_to_dict(result), indent=2))
        return 0

    print(f"Snapshot: {result.snapshot.snapshot_url}")
    if result.warnings:
        for warning in result.warnings:
            print(f"Warning: {warning}")
    if not result.candidates:
        print("No candidates found.")
        return 0

    for idx, candidate in enumerate(result.candidates, start=1):
        print(
            f"{idx:>3}. [{candidate.detected_type}] {candidate.estimated_filename} "
            f"score={candidate.confidence:.2f}"
        )
        print(f"     {candidate.archived_url}")
    return 0


def _cmd_download(args: argparse.Namespace) -> int:
    analysis = analyze_snapshot(
        args.snapshot_url,
        options=AnalyzeOptions(
            include_pattern=args.include_pattern,
            exclude_pattern=args.exclude_pattern,
            timeout_seconds=args.timeout,
            max_depth=args.max_depth,
            max_pages=args.max_pages,
            same_host_only=not args.allow_cross_host,
        ),
    )

    selected = analysis.candidates
    if not args.all:
        selected = prompt_select_candidates(analysis.candidates)

    result = download_candidates(
        args.snapshot_url,
        selection=selected,
        options=DownloadOptions(
            output_dir=args.output,
            include_pattern=args.include_pattern,
            exclude_pattern=args.exclude_pattern,
            timeout_seconds=args.timeout,
            download_all=args.all,
            manifest_only=args.manifest_only,
            interactive=not args.all,
            max_depth=args.max_depth,
            max_pages=args.max_pages,
            same_host_only=not args.allow_cross_host,
        ),
        analysis=analysis,
    )

    if args.json:
        print(json.dumps(result_to_dict(result), indent=2))
        return 0

    print(f"Manifest: {result.manifest_path}")
    print(
        f"Downloaded={len(result.downloaded)} Skipped={len(result.skipped)} "
        f"Failed={len(result.failed)} Planned={len(result.planned)}"
    )
    return 0 if not result.failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
