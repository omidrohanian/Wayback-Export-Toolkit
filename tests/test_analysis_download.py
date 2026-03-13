from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Tuple

from wayback_export.analysis import analyze_snapshot
from wayback_export.download import download_candidates
from wayback_export.models import AnalyzeOptions, DownloadOptions


class FakeHttpClient:
    def __init__(
        self, html: str, payloads: Dict[str, bytes], fail_downloads: set[str] | None = None
    ) -> None:
        self.html = html
        self.payloads = payloads
        self.fail_downloads = fail_downloads or set()

    def get_text(self, url: str, timeout: int, user_agent: str) -> str:
        return self.html

    def download_file(
        self, url: str, destination: Path, timeout: int, user_agent: str
    ) -> Tuple[int, str]:
        if url in self.fail_downloads:
            raise RuntimeError("simulated download failure")
        data = self.payloads[url]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        import hashlib

        return len(data), hashlib.sha256(data).hexdigest()


def _sample_html() -> str:
    return """
    <html><body>
      <a href="https://example.com/files/data.csv">CSV dump</a>
      <a href="https://example.com/backup.zip">Backup</a>
      <a href="https://example.com/page.html">Page</a>
    </body></html>
    """


def test_analyze_snapshot_with_fake_client() -> None:
    client = FakeHttpClient(_sample_html(), payloads={})
    result = analyze_snapshot(
        "https://web.archive.org/web/20200101010101/http://example.com/",
        options=AnalyzeOptions(),
        http_client=client,
    )
    assert len(result.candidates) == 2
    assert result.snapshot.timestamp == "20200101010101"


def test_download_candidates_manifest_and_skip_existing(tmp_path: Path) -> None:
    snapshot = "https://web.archive.org/web/20200101010101/http://example.com/"
    archived_csv = "https://web.archive.org/web/20200101010101/https://example.com/files/data.csv"
    archived_zip = "https://web.archive.org/web/20200101010101/https://example.com/backup.zip"
    client = FakeHttpClient(
        _sample_html(),
        payloads={archived_csv: b"a,b\n1,2\n", archived_zip: b"zip-bytes"},
    )

    analysis = analyze_snapshot(snapshot, options=AnalyzeOptions(), http_client=client)
    result1 = download_candidates(
        snapshot,
        selection=analysis.candidates,
        options=DownloadOptions(output_dir=tmp_path, download_all=True),
        http_client=client,
        analysis=analysis,
    )
    assert len(result1.downloaded) == 2
    manifest_path = Path(result1.manifest_path)
    assert manifest_path.exists()

    result2 = download_candidates(
        snapshot,
        selection=analysis.candidates,
        options=DownloadOptions(output_dir=tmp_path, download_all=True, skip_existing=True),
        http_client=client,
        analysis=analysis,
    )
    assert len(result2.skipped) >= 1

    body = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert body["snapshot"]["timestamp"] == "20200101010101"
    assert body["selected_count"] == 2


def test_download_candidates_partial_failure_continues(tmp_path: Path) -> None:
    snapshot = "https://web.archive.org/web/20200101010101/http://example.com/"
    archived_csv = "https://web.archive.org/web/20200101010101/https://example.com/files/data.csv"
    archived_zip = "https://web.archive.org/web/20200101010101/https://example.com/backup.zip"
    client = FakeHttpClient(
        _sample_html(),
        payloads={archived_csv: b"a,b\n1,2\n", archived_zip: b"zip-bytes"},
        fail_downloads={archived_zip},
    )
    analysis = analyze_snapshot(snapshot, options=AnalyzeOptions(), http_client=client)
    result = download_candidates(
        snapshot,
        selection=analysis.candidates,
        options=DownloadOptions(output_dir=tmp_path, download_all=True),
        http_client=client,
        analysis=analysis,
    )
    assert len(result.downloaded) == 1
    assert len(result.failed) == 1
    assert "simulated download failure" in (result.failed[0].error or "")


def test_manifest_only_marks_records_planned(tmp_path: Path) -> None:
    snapshot = "https://web.archive.org/web/20200101010101/http://example.com/"
    archived_csv = "https://web.archive.org/web/20200101010101/https://example.com/files/data.csv"
    archived_zip = "https://web.archive.org/web/20200101010101/https://example.com/backup.zip"
    client = FakeHttpClient(
        _sample_html(),
        payloads={archived_csv: b"a,b\n1,2\n", archived_zip: b"zip-bytes"},
    )
    analysis = analyze_snapshot(snapshot, options=AnalyzeOptions(), http_client=client)
    result = download_candidates(
        snapshot,
        selection=analysis.candidates,
        options=DownloadOptions(output_dir=tmp_path, download_all=True, manifest_only=True),
        http_client=client,
        analysis=analysis,
    )
    assert len(result.planned) == 2
    assert len(result.downloaded) == 0
