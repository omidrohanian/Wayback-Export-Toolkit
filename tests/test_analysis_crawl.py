from __future__ import annotations

from pathlib import Path
from typing import Dict, Set, Tuple

import pytest

from wayback_export.analysis import analyze_snapshot
from wayback_export.models import AnalyzeOptions


class CrawlHttpClient:
    def __init__(
        self, pages: Dict[str, str], payloads: Dict[str, bytes] | None = None, fail_urls: Set[str] | None = None
    ) -> None:
        self.pages = pages
        self.payloads = payloads or {}
        self.fail_urls = fail_urls or set()
        self.calls: list[str] = []

    def get_text(self, url: str, timeout: int, user_agent: str) -> str:
        self.calls.append(url)
        if url in self.fail_urls:
            raise RuntimeError(f"cannot fetch {url}")
        return self.pages[url]

    def download_file(
        self, url: str, destination: Path, timeout: int, user_agent: str
    ) -> Tuple[int, str]:
        raise NotImplementedError


ROOT = "https://web.archive.org/web/20200101010101/http://example.com/"
PAGE_1 = "https://web.archive.org/web/20200101010101/http://example.com/page1.html"
PAGE_2 = "https://web.archive.org/web/20200101010101/http://example.com/deep/page2.html"


def _crawl_pages() -> Dict[str, str]:
    return {
        ROOT: """
        <html><body>
          <a href="root.csv">root csv</a>
          <a href="page1.html">page1</a>
        </body></html>
        """,
        PAGE_1: """
        <html><body>
          <a href="backup.zip">backup zip</a>
          <a href="deep/page2.html">page2</a>
        </body></html>
        """,
        PAGE_2: """
        <html><body>
          <a href="grand.json">grand json export</a>
        </body></html>
        """,
    }


def test_depth_zero_only_root_candidates() -> None:
    client = CrawlHttpClient(_crawl_pages())
    result = analyze_snapshot(ROOT, AnalyzeOptions(max_depth=0), http_client=client)
    urls = {candidate.archived_url for candidate in result.candidates}
    assert urls == {"https://web.archive.org/web/20200101010101/http://example.com/root.csv"}
    assert PAGE_1 not in client.calls


def test_depth_one_includes_child_candidates() -> None:
    client = CrawlHttpClient(_crawl_pages())
    result = analyze_snapshot(ROOT, AnalyzeOptions(max_depth=1), http_client=client)
    urls = {candidate.archived_url for candidate in result.candidates}
    assert "https://web.archive.org/web/20200101010101/http://example.com/root.csv" in urls
    assert "https://web.archive.org/web/20200101010101/http://example.com/backup.zip" in urls
    assert "https://web.archive.org/web/20200101010101/http://example.com/deep/grand.json" not in urls


def test_depth_two_includes_grandchild_candidates() -> None:
    client = CrawlHttpClient(_crawl_pages())
    result = analyze_snapshot(ROOT, AnalyzeOptions(max_depth=2), http_client=client)
    urls = {candidate.archived_url for candidate in result.candidates}
    assert "https://web.archive.org/web/20200101010101/http://example.com/deep/grand.json" in urls


def test_child_fetch_failure_becomes_warning_not_crash() -> None:
    client = CrawlHttpClient(_crawl_pages(), fail_urls={PAGE_1})
    result = analyze_snapshot(ROOT, AnalyzeOptions(max_depth=2), http_client=client)
    assert any("Failed to fetch depth 1 page" in warning for warning in result.warnings)
    urls = {candidate.archived_url for candidate in result.candidates}
    assert "https://web.archive.org/web/20200101010101/http://example.com/root.csv" in urls


def test_max_pages_stops_crawl() -> None:
    client = CrawlHttpClient(_crawl_pages())
    result = analyze_snapshot(
        ROOT, AnalyzeOptions(max_depth=3, max_pages=1), http_client=client
    )
    assert any("max_pages=1" in warning for warning in result.warnings)
    assert len(client.calls) == 1


def test_invalid_depth_and_page_limits_raise() -> None:
    client = CrawlHttpClient(_crawl_pages())
    with pytest.raises(ValueError, match="max_depth"):
        analyze_snapshot(ROOT, AnalyzeOptions(max_depth=-1), http_client=client)
    with pytest.raises(ValueError, match="max_pages"):
        analyze_snapshot(ROOT, AnalyzeOptions(max_pages=0), http_client=client)


def test_root_fetch_failure_raises() -> None:
    client = CrawlHttpClient(_crawl_pages(), fail_urls={ROOT})
    with pytest.raises(RuntimeError, match="cannot fetch"):
        analyze_snapshot(ROOT, AnalyzeOptions(max_depth=2), http_client=client)
