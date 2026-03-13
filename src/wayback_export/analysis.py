from __future__ import annotations

"""Snapshot analysis orchestration.

This module coordinates bounded crawling of Wayback snapshot pages and turns
raw HTML responses into filtered candidate export artifacts.
"""

from collections import deque

from .discovery import (
    dedupe_candidates,
    discover_candidates,
    discover_follow_links,
    filter_candidates,
)
from .http_client import HttpClient, UrlLibHttpClient
from .models import AnalysisResult, AnalyzeOptions, SnapshotInfo
from .wayback import original_url_from_archived_url, parse_snapshot_url


def analyze_snapshot(
    snapshot_url: str,
    options: AnalyzeOptions | None = None,
    http_client: HttpClient | None = None,
) -> AnalysisResult:
    """Analyze a snapshot URL and return likely export/data candidates.

    Crawling is breadth-first and bounded by `max_depth` and `max_pages`.
    Root-page fetch errors are raised; child-page fetch errors are recorded as
    warnings so a partial analysis can still succeed.
    """
    options = options or AnalyzeOptions()
    http_client = http_client or UrlLibHttpClient()
    if options.max_depth < 0:
        raise ValueError("max_depth must be >= 0")
    if options.max_pages < 1:
        raise ValueError("max_pages must be >= 1")

    snapshot = parse_snapshot_url(snapshot_url)
    queue = deque([(snapshot.snapshot_url, 0)])
    visited = set()
    discovered_all = []
    warnings = []
    pages_crawled = 0

    while queue and len(visited) < options.max_pages:
        current_url, depth = queue.popleft()
        if current_url in visited:
            continue
        visited.add(current_url)
        try:
            html = http_client.get_text(
                current_url,
                timeout=options.timeout_seconds,
                user_agent=options.user_agent,
            )
            pages_crawled += 1
        except Exception as exc:
            # Root page failure is a hard error; child failures are soft warnings.
            if depth == 0:
                raise
            warnings.append(f"Failed to fetch depth {depth} page: {current_url} ({exc})")
            continue

        page_original_url = original_url_from_archived_url(current_url) or snapshot.original_url
        page_snapshot = SnapshotInfo(
            snapshot_url=current_url,
            timestamp=snapshot.timestamp,
            archived_url=current_url,
            original_url=page_original_url,
        )

        discovered_all.extend(discover_candidates(page_snapshot, html))
        if depth >= options.max_depth:
            continue

        follow_links = discover_follow_links(
            page_snapshot,
            html,
            same_host_only=options.same_host_only,
        )
        for next_url in follow_links:
            if next_url not in visited:
                queue.append((next_url, depth + 1))

    if queue and len(visited) >= options.max_pages:
        warnings.append(f"Stopped crawling after reaching max_pages={options.max_pages}.")

    discovered = dedupe_candidates(discovered_all)
    filtered = filter_candidates(
        discovered,
        include_pattern=options.include_pattern,
        exclude_pattern=options.exclude_pattern,
    )

    if not filtered:
        warnings.append("No likely export/data links were found after crawling and filtering.")
    if pages_crawled > 1:
        warnings.append(f"Crawled {pages_crawled} page(s) with max_depth={options.max_depth}.")

    return AnalysisResult(snapshot=snapshot, candidates=filtered, warnings=warnings)
