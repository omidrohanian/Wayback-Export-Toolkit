from __future__ import annotations

"""Wayback snapshot mirroring for offline static browsing."""

from collections import deque
from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
import re
import shutil
import time
from typing import Iterable, List
from urllib.parse import unquote, urlparse

from .discovery import DATA_EXTENSIONS, NON_NAV_EXTENSIONS
from .http_client import HttpClient, UrlLibHttpClient
from .models import MirrorOptions, MirrorResult, SnapshotInfo
from .output import build_run_dir
from .wayback import normalize_archived_link, original_url_from_archived_url, parse_snapshot_url

SKIP_SCHEMES = ("#", "javascript:", "mailto:", "tel:", "data:")
PAGE_LIKE_EXTENSIONS = {
    "",
    ".html",
    ".htm",
    ".xhtml",
    ".php",
    ".asp",
    ".aspx",
    ".jsp",
    ".cfm",
    ".shtml",
}


@dataclass
class CollectedResources:
    page_links: List[str]
    asset_links: List[str]


class ResourceCollector(HTMLParser):
    """Collect page and static asset references from HTML tags."""

    def __init__(self) -> None:
        super().__init__()
        self.page_links: List[str] = []
        self.asset_links: List[str] = []

    def handle_starttag(self, tag: str, attrs):
        attrs_map = dict(attrs)

        if tag == "a":
            href = attrs_map.get("href")
            if href:
                self.page_links.append(href)

        if tag in {"img", "script", "source", "video", "audio", "iframe"}:
            src = attrs_map.get("src")
            if src:
                self.asset_links.append(src)

        if tag == "link":
            href = attrs_map.get("href")
            if href:
                self.asset_links.append(href)

        srcset = attrs_map.get("srcset")
        if srcset:
            self.asset_links.extend(_parse_srcset_urls(srcset))


def mirror_snapshot(
    snapshot_url: str,
    options: MirrorOptions | None = None,
    http_client: HttpClient | None = None,
) -> MirrorResult:
    """Mirror a Wayback snapshot into a local static-site directory."""
    options = options or MirrorOptions(output_dir=Path("./downloads"))
    http_client = http_client or UrlLibHttpClient()

    if options.max_depth < 0:
        raise ValueError("max_depth must be >= 0")
    if options.max_pages < 1:
        raise ValueError("max_pages must be >= 1")

    snapshot = parse_snapshot_url(snapshot_url)
    host = urlparse(snapshot.original_url).netloc.lower()
    run_dir = build_run_dir(options.output_dir, host or "snapshot", snapshot.timestamp)
    site_dir = run_dir / "site"

    _cleanup_legacy_outputs(run_dir)
    shutil.rmtree(site_dir, ignore_errors=True)
    site_dir.mkdir(parents=True, exist_ok=True)

    queue = deque([(snapshot.snapshot_url, 0)])
    visited_pages = set()
    page_html: dict[str, str] = {}
    page_snapshot_map: dict[str, SnapshotInfo] = {}
    url_to_local_path: dict[str, Path] = {}
    asset_urls = set()
    warnings: List[str] = []
    failed: List[dict[str, str]] = []

    while queue and len(visited_pages) < options.max_pages:
        current_url, depth = queue.popleft()
        if current_url in visited_pages:
            continue
        visited_pages.add(current_url)

        fetch_url = current_url
        try:
            html = _get_text_with_retries(
                http_client,
                fetch_url,
                timeout=options.timeout_seconds,
                user_agent=options.user_agent,
            )
        except Exception as primary_exc:
            fallback_url = _alternate_archived_scheme_url(current_url)
            if fallback_url:
                try:
                    html = _get_text_with_retries(
                        http_client,
                        fallback_url,
                        timeout=options.timeout_seconds,
                        user_agent=options.user_agent,
                    )
                    fetch_url = fallback_url
                    visited_pages.add(fetch_url)
                    warnings.append(
                        f"Used scheme fallback for page: {current_url} -> {fallback_url}"
                    )
                except Exception as fallback_exc:
                    if depth == 0:
                        raise
                    failed.append(
                        {
                            "url": current_url,
                            "stage": "page_fetch",
                            "error": f"{primary_exc} | fallback_failed={fallback_exc}",
                        }
                    )
                    warnings.append(f"Failed to fetch page depth={depth}: {current_url}")
                    continue
            else:
                if depth == 0:
                    raise
                failed.append({"url": current_url, "stage": "page_fetch", "error": str(primary_exc)})
                warnings.append(f"Failed to fetch page depth={depth}: {current_url}")
                continue

        page_original_url = original_url_from_archived_url(fetch_url) or snapshot.original_url
        page_snapshot = SnapshotInfo(
            snapshot_url=fetch_url,
            timestamp=snapshot.timestamp,
            archived_url=fetch_url,
            original_url=page_original_url,
        )

        page_rel_path = _local_path_for_original_url(page_original_url)
        page_html[fetch_url] = html
        page_snapshot_map[fetch_url] = page_snapshot
        url_to_local_path[fetch_url] = page_rel_path
        if fetch_url != current_url:
            url_to_local_path[current_url] = page_rel_path

        collected = _collect_resources(html)

        for raw in collected.asset_links:
            archived_url = normalize_archived_link(page_snapshot, raw)
            if not archived_url:
                continue
            if options.same_host_only and not _same_host(archived_url, host):
                continue
            asset_urls.add(archived_url)

        if depth >= options.max_depth:
            continue

        for raw in collected.page_links:
            archived_url = normalize_archived_link(page_snapshot, raw)
            if not archived_url:
                continue
            if not _looks_like_page(archived_url):
                if options.same_host_only and not _same_host(archived_url, host):
                    continue
                asset_urls.add(archived_url)
                continue
            if options.same_host_only and not _same_host(archived_url, host):
                continue
            if archived_url not in visited_pages:
                queue.append((archived_url, depth + 1))

    if queue and len(visited_pages) >= options.max_pages:
        warnings.append(f"Stopped crawling after max_pages={options.max_pages}.")

    for asset_url in asset_urls:
        original = original_url_from_archived_url(asset_url)
        if not original:
            continue
        url_to_local_path.setdefault(asset_url, _local_path_for_original_url(original))

    assets_downloaded = 0
    assets_skipped = 0
    for asset_url in sorted(asset_urls):
        local_rel = url_to_local_path.get(asset_url)
        if local_rel is None:
            continue
        destination = site_dir / local_rel
        if options.skip_existing and destination.exists():
            assets_skipped += 1
            continue
        try:
            _download_with_retries(
                http_client,
                asset_url,
                destination=destination,
                timeout=options.timeout_seconds,
                user_agent=options.user_agent,
            )
            assets_downloaded += 1
        except Exception as primary_exc:
            fallback_url = _alternate_archived_scheme_url(asset_url)
            if not fallback_url:
                failed.append(
                    {"url": asset_url, "stage": "asset_download", "error": str(primary_exc)}
                )
                continue
            try:
                _download_with_retries(
                    http_client,
                    fallback_url,
                    destination=destination,
                    timeout=options.timeout_seconds,
                    user_agent=options.user_agent,
                )
                assets_downloaded += 1
                warnings.append(
                    f"Used scheme fallback for asset: {asset_url} -> {fallback_url}"
                )
                url_to_local_path[fallback_url] = local_rel
            except Exception as fallback_exc:
                failed.append(
                    {
                        "url": asset_url,
                        "stage": "asset_download",
                        "error": f"{primary_exc} | fallback_failed={fallback_exc}",
                    }
                )

    pages_saved = 0
    for page_url, html in page_html.items():
        page_snapshot = page_snapshot_map[page_url]
        page_rel = url_to_local_path[page_url]
        rewritten = _rewrite_html_links(
            html=html,
            page_snapshot=page_snapshot,
            current_page_path=page_rel,
            mapping=url_to_local_path,
        )
        destination = site_dir / page_rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rewritten, encoding="utf-8")
        pages_saved += 1

    manifest_path = run_dir / "mirror_manifest.json"
    manifest = {
        "snapshot_url": snapshot.snapshot_url,
        "site_dir": str(site_dir),
        "pages_saved": pages_saved,
        "assets_downloaded": assets_downloaded,
        "assets_skipped": assets_skipped,
        "warnings": warnings,
        "failed": failed,
        "saved_at": snapshot.timestamp,
        "fingerprint": hashlib.sha256(snapshot.snapshot_url.encode("utf-8")).hexdigest()[:12],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return MirrorResult(
        manifest_path=str(manifest_path),
        site_dir=str(site_dir),
        pages_saved=pages_saved,
        assets_downloaded=assets_downloaded,
        assets_skipped=assets_skipped,
        warnings=warnings,
        failed=failed,
    )


def _cleanup_legacy_outputs(run_dir: Path) -> None:
    legacy_manifest = run_dir / "manifest.json"
    legacy_files_dir = run_dir / "files"
    if legacy_manifest.exists():
        legacy_manifest.unlink()
    if legacy_files_dir.exists():
        shutil.rmtree(legacy_files_dir, ignore_errors=True)


def _alternate_archived_scheme_url(archived_url: str) -> str | None:
    if "/https://" in archived_url:
        return archived_url.replace("/https://", "/http://", 1)
    if "/http://" in archived_url:
        return archived_url.replace("/http://", "/https://", 1)
    return None


def _get_text_with_retries(
    http_client: HttpClient,
    url: str,
    timeout: int,
    user_agent: str,
    retries: int = 2,
) -> str:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return http_client.get_text(url, timeout=timeout, user_agent=user_agent)
        except Exception as exc:  # pragma: no cover - exercised by higher-level tests
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(0.25 * (attempt + 1))
    raise RuntimeError(str(last_error))


def _download_with_retries(
    http_client: HttpClient,
    url: str,
    destination: Path,
    timeout: int,
    user_agent: str,
    retries: int = 2,
) -> None:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            http_client.download_file(
                url,
                destination=destination,
                timeout=timeout,
                user_agent=user_agent,
            )
            return
        except Exception as exc:  # pragma: no cover - exercised by higher-level tests
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(0.25 * (attempt + 1))
    raise RuntimeError(str(last_error))


def _parse_srcset_urls(raw: str) -> List[str]:
    urls = []
    for chunk in raw.split(","):
        item = chunk.strip()
        if not item:
            continue
        parts = item.split()
        if parts:
            urls.append(parts[0])
    return urls


def _collect_resources(html: str) -> CollectedResources:
    parser = ResourceCollector()
    parser.feed(html)
    return CollectedResources(
        page_links=_unique(parser.page_links),
        asset_links=_unique(parser.asset_links),
    )


def _same_host(archived_url: str, root_host: str) -> bool:
    original_url = original_url_from_archived_url(archived_url)
    if not original_url:
        return False
    return urlparse(original_url).netloc.lower() == root_host


def _looks_like_page(archived_url: str) -> bool:
    original_url = original_url_from_archived_url(archived_url)
    if not original_url:
        return False
    path = urlparse(original_url).path
    ext = Path(path).suffix.lower()
    if ext in DATA_EXTENSIONS or ext in NON_NAV_EXTENSIONS:
        return False
    return ext in PAGE_LIKE_EXTENSIONS or ext == ""


def _local_path_for_original_url(original_url: str) -> Path:
    parsed = urlparse(original_url)
    path = unquote(parsed.path)
    if not path or path.endswith("/"):
        path = f"{path}index.html"
    else:
        leaf = Path(path).name
        if "." not in leaf:
            path = f"{path}.html"

    rel = Path(path.lstrip("/"))
    if parsed.query:
        digest = hashlib.sha1(parsed.query.encode("utf-8")).hexdigest()[:10]
        rel = rel.with_name(f"{rel.stem}__q_{digest}{rel.suffix}")
    return rel


def _rewrite_html_links(
    html: str,
    page_snapshot: SnapshotInfo,
    current_page_path: Path,
    mapping: dict[str, Path],
) -> str:
    attr_re = re.compile(
        r'(?P<prefix>\b(?:href|src)\s*=\s*)(?P<quote>["\'])(?P<url>.*?)(?P=quote)',
        flags=re.IGNORECASE,
    )
    srcset_re = re.compile(
        r'(?P<prefix>\bsrcset\s*=\s*)(?P<quote>["\'])(?P<url>.*?)(?P=quote)',
        flags=re.IGNORECASE | re.DOTALL,
    )

    def replace_attr(match: re.Match[str]) -> str:
        raw = match.group("url").strip()
        rewritten = _rewrite_single_url(raw, page_snapshot, current_page_path, mapping)
        return f"{match.group('prefix')}{match.group('quote')}{rewritten}{match.group('quote')}"

    def replace_srcset(match: re.Match[str]) -> str:
        raw = match.group("url")
        rebuilt: List[str] = []
        for chunk in raw.split(","):
            part = chunk.strip()
            if not part:
                continue
            parts = part.split()
            url_part = parts[0]
            descriptor = " ".join(parts[1:])
            rewritten = _rewrite_single_url(url_part, page_snapshot, current_page_path, mapping)
            rebuilt.append(f"{rewritten} {descriptor}".strip())
        final_value = ", ".join(rebuilt)
        return f"{match.group('prefix')}{match.group('quote')}{final_value}{match.group('quote')}"

    html = attr_re.sub(replace_attr, html)
    html = srcset_re.sub(replace_srcset, html)
    return html


def _rewrite_single_url(
    raw_url: str,
    page_snapshot: SnapshotInfo,
    current_page_path: Path,
    mapping: dict[str, Path],
) -> str:
    stripped = raw_url.strip()
    lowered = stripped.lower()
    if not stripped or lowered.startswith(SKIP_SCHEMES):
        return raw_url

    archived_url = normalize_archived_link(page_snapshot, stripped)
    if not archived_url:
        return raw_url

    local_target = mapping.get(archived_url)
    if local_target is None:
        alt = _alternate_archived_scheme_url(archived_url)
        if alt:
            local_target = mapping.get(alt)
    if local_target is None:
        return raw_url

    start = current_page_path.parent.as_posix() if current_page_path.parent.as_posix() else "."
    return posixpath.relpath(local_target.as_posix(), start=start)


def _unique(values: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out
