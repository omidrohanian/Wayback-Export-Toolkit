from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from .models import SnapshotInfo


WAYBACK_HOST = "web.archive.org"
SNAPSHOT_RE = re.compile(
    r"^/web/(?P<timestamp>\d{14})(?:[a-z_]{0,20})?/(?P<target>.+)$", re.IGNORECASE
)


class WaybackUrlError(ValueError):
    pass


def parse_snapshot_url(snapshot_url: str) -> SnapshotInfo:
    parsed = urlparse(snapshot_url.strip())
    if parsed.netloc.lower() != WAYBACK_HOST:
        raise WaybackUrlError(
            "Snapshot URL must point to web.archive.org (Wayback Machine)."
        )
    match = SNAPSHOT_RE.match(parsed.path)
    if not match:
        raise WaybackUrlError(
            "Invalid snapshot URL. Expected /web/<14-digit-timestamp>/<target-url>."
        )

    timestamp = match.group("timestamp")
    target = match.group("target")
    if not target.startswith(("http://", "https://")):
        target = "http://" + target

    canonical_snapshot = build_wayback_url(timestamp, target)
    return SnapshotInfo(
        snapshot_url=canonical_snapshot,
        timestamp=timestamp,
        archived_url=canonical_snapshot,
        original_url=target,
    )


def build_wayback_url(timestamp: str, target_url: str) -> str:
    return f"https://{WAYBACK_HOST}/web/{timestamp}/{target_url}"


def normalize_archived_link(snapshot: SnapshotInfo, href: str) -> str | None:
    clean = href.strip()
    if not clean or clean.startswith(("#", "javascript:", "mailto:", "tel:")):
        return None

    if clean.startswith("/web/"):
        return f"https://{WAYBACK_HOST}{clean}"

    if clean.startswith("//"):
        clean = "https:" + clean

    parsed = urlparse(clean)
    if parsed.scheme in ("http", "https"):
        if parsed.netloc.lower() == WAYBACK_HOST and parsed.path.startswith("/web/"):
            return clean
        return build_wayback_url(snapshot.timestamp, clean)

    resolved = urljoin(snapshot.original_url, clean)
    return build_wayback_url(snapshot.timestamp, resolved)


def original_url_from_archived_url(archived_url: str) -> str | None:
    parsed = urlparse(archived_url)
    if parsed.netloc.lower() != WAYBACK_HOST:
        return archived_url if parsed.scheme in {"http", "https"} else None

    match = SNAPSHOT_RE.match(parsed.path)
    if not match:
        return None
    target = match.group("target")
    if not target.startswith(("http://", "https://")):
        target = "http://" + target
    if parsed.query and "?" not in target:
        target = f"{target}?{parsed.query}"
    return target
