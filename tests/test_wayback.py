from wayback_export.wayback import WaybackUrlError, normalize_archived_link, parse_snapshot_url


def test_parse_snapshot_url_valid() -> None:
    snapshot = parse_snapshot_url(
        "https://web.archive.org/web/20200101010101/http://example.com/index.html"
    )
    assert snapshot.timestamp == "20200101010101"
    assert snapshot.original_url == "http://example.com/index.html"


def test_parse_snapshot_url_invalid_domain() -> None:
    try:
        parse_snapshot_url("https://example.com/web/20200101010101/http://example.com/")
    except WaybackUrlError as exc:
        assert "web.archive.org" in str(exc)
        return
    assert False, "Expected WaybackUrlError"


def test_normalize_archived_link_relative() -> None:
    snapshot = parse_snapshot_url(
        "https://web.archive.org/web/20200101010101/http://example.com/root/"
    )
    archived = normalize_archived_link(snapshot, "files/data.csv")
    assert archived == "https://web.archive.org/web/20200101010101/http://example.com/root/files/data.csv"
