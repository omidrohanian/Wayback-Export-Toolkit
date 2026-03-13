from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

from wayback_export.mirror import mirror_snapshot
from wayback_export.models import MirrorOptions


class FakeMirrorHttpClient:
    def __init__(self, pages: Dict[str, str], payloads: Dict[str, bytes]) -> None:
        self.pages = pages
        self.payloads = payloads
        self.page_calls: list[str] = []
        self.asset_calls: list[str] = []

    def get_text(self, url: str, timeout: int, user_agent: str) -> str:
        self.page_calls.append(url)
        return self.pages[url]

    def download_file(
        self, url: str, destination: Path, timeout: int, user_agent: str
    ) -> Tuple[int, str]:
        self.asset_calls.append(url)
        data = self.payloads[url]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return len(data), "checksum"


def test_mirror_snapshot_saves_pages_assets_and_rewrites_links(tmp_path: Path) -> None:
    root = "https://web.archive.org/web/20200101010101/http://example.com/"
    essay = "https://web.archive.org/web/20200101010101/http://example.com/essay.html"
    css = "https://web.archive.org/web/20200101010101/http://example.com/style.css"
    image = "https://web.archive.org/web/20200101010101/http://example.com/img/pic.jpg"

    client = FakeMirrorHttpClient(
        pages={
            root: (
                '<html><head><link rel="stylesheet" href="style.css"></head>'
                '<body><a href="essay.html">Essay</a>'
                '<img src="img/pic.jpg"></body></html>'
            ),
            essay: '<html><body><a href="/">Home</a><h1>Essay</h1></body></html>',
        },
        payloads={css: b"body{font-family:serif}", image: b"jpeg-bytes"},
    )

    result = mirror_snapshot(
        root,
        options=MirrorOptions(output_dir=tmp_path, max_depth=2, max_pages=20),
        http_client=client,
    )

    site_dir = Path(result.site_dir)
    assert (site_dir / "index.html").exists()
    assert (site_dir / "essay.html").exists()
    assert (site_dir / "style.css").exists()
    assert (site_dir / "img" / "pic.jpg").exists()

    root_html = (site_dir / "index.html").read_text(encoding="utf-8")
    essay_html = (site_dir / "essay.html").read_text(encoding="utf-8")

    assert 'href="essay.html"' in root_html
    assert 'href="style.css"' in root_html
    assert 'src="img/pic.jpg"' in root_html
    assert 'href="index.html"' in essay_html

    assert result.pages_saved == 2
    assert result.assets_downloaded == 2
    assert not result.failed


def test_mirror_respects_depth_limit(tmp_path: Path) -> None:
    root = "https://web.archive.org/web/20200101010101/http://example.com/"
    essay = "https://web.archive.org/web/20200101010101/http://example.com/essay.html"

    client = FakeMirrorHttpClient(
        pages={
            root: '<html><body><a href="essay.html">Essay</a></body></html>',
            essay: '<html><body><h1>Essay</h1></body></html>',
        },
        payloads={},
    )

    result = mirror_snapshot(
        root,
        options=MirrorOptions(output_dir=tmp_path, max_depth=0, max_pages=20),
        http_client=client,
    )

    site_dir = Path(result.site_dir)
    assert (site_dir / "index.html").exists()
    assert not (site_dir / "essay.html").exists()
    assert result.pages_saved == 1
