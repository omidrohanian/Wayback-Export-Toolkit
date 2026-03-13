from pathlib import Path

from wayback_export.discovery import (
    classify_candidate,
    discover_candidates,
    discover_follow_links,
    filter_candidates,
    sanitize_filename,
)
from wayback_export.wayback import parse_snapshot_url


def _fixture_html() -> str:
    fixture = Path(__file__).parent / "fixtures" / "sample_snapshot.html"
    return fixture.read_text(encoding="utf-8")


def test_classify_candidate_high_confidence_for_csv() -> None:
    confidence, reason, detected_type = classify_candidate(
        "https://web.archive.org/web/20200101010101/http://example.com/files/data.csv",
        "Download data",
    )
    assert confidence >= 0.7
    assert "extension:.csv" in reason
    assert detected_type == "csv"


def test_discover_candidates_filters_non_data_links() -> None:
    snapshot = parse_snapshot_url(
        "https://web.archive.org/web/20200101010101/http://example.com/"
    )
    candidates = discover_candidates(snapshot, _fixture_html())
    urls = [c.archived_url for c in candidates]
    assert any("cities.csv" in url for url in urls)
    assert any("backup-2020.zip" in url for url in urls)
    assert all("reports.html" not in url for url in urls)


def test_filter_candidates_include_exclude_patterns() -> None:
    snapshot = parse_snapshot_url(
        "https://web.archive.org/web/20200101010101/http://example.com/"
    )
    candidates = discover_candidates(snapshot, _fixture_html())
    filtered = filter_candidates(candidates, include_pattern="zip|json", exclude_pattern="json")
    assert len(filtered) == 1
    assert filtered[0].estimated_filename.endswith(".zip")


def test_sanitize_filename() -> None:
    assert sanitize_filename(" weird file (final).csv ") == "weird_file_final_.csv"


def test_discover_follow_links_same_host_only() -> None:
    snapshot = parse_snapshot_url(
        "https://web.archive.org/web/20200101010101/http://example.com/"
    )
    html = """
    <html><body>
      <a href="/blog/post.html">post</a>
      <a href="https://other.example.com/page.html">offsite page</a>
      <a href="/download/data.csv">csv</a>
    </body></html>
    """
    urls = discover_follow_links(snapshot, html, same_host_only=True)
    assert urls == ["https://web.archive.org/web/20200101010101/http://example.com/blog/post.html"]


def test_discover_candidates_collects_nested_anchor_text() -> None:
    snapshot = parse_snapshot_url(
        "https://web.archive.org/web/20200101010101/http://example.com/"
    )
    html = """
    <html><body>
      <a href="/api/report">
        <span>Export</span><span>data</span><span>backup</span><span>archive</span>
        <span>dataset</span><span>download</span><span>dump</span>
      </a>
    </body></html>
    """
    candidates = discover_candidates(snapshot, html)
    assert len(candidates) == 1
    assert candidates[0].archived_url.endswith("/api/report")
