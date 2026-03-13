from __future__ import annotations

import os
import re
from html.parser import HTMLParser
from typing import Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from .models import CandidateFile
from .wayback import normalize_archived_link, original_url_from_archived_url


DATA_EXTENSIONS = {
    ".zip": "zip",
    ".csv": "csv",
    ".sql": "sql",
    ".json": "json",
    ".xml": "xml",
    ".xlsx": "xlsx",
    ".xls": "xls",
    ".parquet": "parquet",
    ".gz": "gzip",
    ".bz2": "bzip2",
    ".7z": "7z",
    ".tar": "tar",
}

KEYWORDS = (
    "dump",
    "backup",
    "archive",
    "dataset",
    "export",
    "download",
    "data",
    "db",
)

NON_NAV_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".css",
    ".js",
    ".pdf",
    ".mp3",
    ".mp4",
    ".avi",
    ".mov",
    ".woff",
    ".woff2",
    ".ttf",
}


class LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._stack: List[str] = []
        self._active_anchor_href: Optional[str] = None
        self.links: List[Tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        attrs_map = dict(attrs)
        href = attrs_map.get("href")
        self._stack.append(tag)
        if tag == "a" and href:
            self._active_anchor_href = href
            self.links.append((href, ""))
            return
        if href and tag == "link":
            self.links.append((href, ""))

    def handle_data(self, data: str) -> None:
        if not self._stack or not self._active_anchor_href:
            return
        current_href, current_text = self.links[-1]
        if current_href == self._active_anchor_href:
            text = (current_text + " " + data).strip()
            self.links[-1] = (current_href, text)

    def handle_endtag(self, tag: str) -> None:
        if self._stack:
            self._stack.pop()
        if tag == "a":
            self._active_anchor_href = None


def extract_links(html: str) -> List[Tuple[str, str]]:
    parser = LinkCollector()
    parser.feed(html)
    deduped = []
    seen = set()
    for href, text in parser.links:
        key = (href.strip(), text.strip())
        if key not in seen:
            seen.add(key)
            deduped.append((href.strip(), text.strip()))
    return deduped


def classify_candidate(archived_url: str, label_text: str = "") -> Tuple[float, str, str]:
    parsed = urlparse(archived_url)
    path = parsed.path.lower()
    lowered_text = label_text.lower()
    reasons = []
    score = 0.0
    detected_type = "unknown"

    ext = os.path.splitext(path)[1]
    if ext in DATA_EXTENSIONS:
        detected_type = DATA_EXTENSIONS[ext]
        score += 0.7
        reasons.append(f"extension:{ext}")

    for keyword in KEYWORDS:
        if keyword in path or keyword in lowered_text:
            score += 0.08
            reasons.append(f"keyword:{keyword}")

    qs = parse_qs(parsed.query)
    for key in ("format", "type", "file"):
        values = qs.get(key, [])
        for value in values:
            value_lower = value.lower()
            for ext_name in ("csv", "json", "xml", "sql", "zip", "xlsx", "parquet"):
                if ext_name in value_lower:
                    score += 0.15
                    reasons.append(f"query:{key}={ext_name}")
                    if detected_type == "unknown":
                        detected_type = ext_name
                    break

    score = min(score, 0.99)
    reason = ",".join(reasons) if reasons else "weak-signal"
    return score, reason, detected_type


def estimate_filename(archived_url: str, fallback_index: int) -> str:
    parsed = urlparse(archived_url)
    name = os.path.basename(parsed.path)
    if name and "." in name:
        return sanitize_filename(name)

    qs = parse_qs(parsed.query)
    for key in ("file", "filename", "download"):
        values = qs.get(key, [])
        if values:
            return sanitize_filename(values[0])
    return f"candidate_{fallback_index}.bin"


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    cleaned = cleaned.strip("._")
    return cleaned or "download.bin"


def discover_candidates(snapshot, html: str) -> List[CandidateFile]:
    links = extract_links(html)
    candidates: List[CandidateFile] = []
    for idx, (href, text) in enumerate(links, start=1):
        archived_url = normalize_archived_link(snapshot, href)
        if not archived_url:
            continue
        confidence, reason, detected_type = classify_candidate(archived_url, text)
        if confidence < 0.5:
            continue

        candidates.append(
            CandidateFile(
                title=text or estimate_filename(archived_url, idx),
                archived_url=archived_url,
                original_url=None,
                detected_type=detected_type,
                confidence=round(confidence, 3),
                reason=reason,
                estimated_filename=estimate_filename(archived_url, idx),
            )
        )

    return dedupe_candidates(candidates)


def filter_candidates(
    candidates: Iterable[CandidateFile],
    include_pattern: Optional[str],
    exclude_pattern: Optional[str],
) -> List[CandidateFile]:
    include_re = re.compile(include_pattern) if include_pattern else None
    exclude_re = re.compile(exclude_pattern) if exclude_pattern else None
    filtered: List[CandidateFile] = []
    for candidate in candidates:
        haystack = f"{candidate.archived_url} {candidate.title} {candidate.estimated_filename}"
        if include_re and not include_re.search(haystack):
            continue
        if exclude_re and exclude_re.search(haystack):
            continue
        filtered.append(candidate)
    return filtered


def discover_follow_links(snapshot, html: str, same_host_only: bool = True) -> List[str]:
    links = extract_links(html)
    follow: List[str] = []
    snapshot_host = urlparse(snapshot.original_url).netloc.lower()
    for href, text in links:
        archived_url = normalize_archived_link(snapshot, href)
        if not archived_url:
            continue
        if not _is_likely_navigational(archived_url):
            continue
        if same_host_only:
            original_url = original_url_from_archived_url(archived_url)
            if not original_url:
                continue
            original_host = urlparse(original_url).netloc.lower()
            if original_host and original_host != snapshot_host:
                continue
        # Skip links that are likely direct data artifacts, not crawl pages.
        score, _, _ = classify_candidate(archived_url, text)
        if score >= 0.5:
            continue
        follow.append(archived_url)
    return _unique_urls(follow)


def dedupe_candidates(candidates: Iterable[CandidateFile]) -> List[CandidateFile]:
    deduped: List[CandidateFile] = []
    seen = set()
    for candidate in candidates:
        if candidate.archived_url in seen:
            continue
        seen.add(candidate.archived_url)
        deduped.append(candidate)
    return deduped


def _is_likely_navigational(url: str) -> bool:
    parsed = urlparse(url)
    ext = os.path.splitext(parsed.path.lower())[1]
    if ext in DATA_EXTENSIONS:
        return False
    if ext in NON_NAV_EXTENSIONS:
        return False
    return True


def _unique_urls(urls: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out
