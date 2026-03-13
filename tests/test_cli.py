from wayback_export import cli
from wayback_export.models import (
    AnalysisResult,
    CandidateFile,
    DownloadResult,
    SnapshotInfo,
)
import pytest


def _analysis_result() -> AnalysisResult:
    snapshot = SnapshotInfo(
        snapshot_url="https://web.archive.org/web/20200101010101/http://example.com/",
        timestamp="20200101010101",
        archived_url="https://web.archive.org/web/20200101010101/http://example.com/",
        original_url="http://example.com/",
    )
    candidate = CandidateFile(
        title="cities",
        archived_url="https://web.archive.org/web/20200101010101/http://example.com/cities.csv",
        original_url="http://example.com/cities.csv",
        detected_type="csv",
        confidence=0.9,
        reason="extension:.csv",
        estimated_filename="cities.csv",
    )
    return AnalysisResult(snapshot=snapshot, candidates=[candidate], warnings=[])


def _download_result() -> DownloadResult:
    return DownloadResult(
        manifest_path="/tmp/manifest.json",
        downloaded=[],
        skipped=[],
        failed=[],
        planned=[],
    )


def test_cli_analyze_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "analyze_snapshot", lambda *args, **kwargs: _analysis_result())
    rc = cli.main(
        ["analyze", "https://web.archive.org/web/20200101010101/http://example.com/", "--json"]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert '"timestamp": "20200101010101"' in out


def test_cli_download_all_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "analyze_snapshot", lambda *args, **kwargs: _analysis_result())
    monkeypatch.setattr(cli, "download_candidates", lambda *args, **kwargs: _download_result())
    rc = cli.main(
        [
            "download",
            "https://web.archive.org/web/20200101010101/http://example.com/",
            "--all",
            "--json",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "manifest.json" in out


def test_cli_passes_depth_and_host_flags(monkeypatch) -> None:
    captured = {}

    def fake_analyze(snapshot_url, options):
        captured["snapshot_url"] = snapshot_url
        captured["options"] = options
        return _analysis_result()

    monkeypatch.setattr(cli, "analyze_snapshot", fake_analyze)
    cli.main(
        [
            "analyze",
            "https://web.archive.org/web/20200101010101/http://example.com/",
            "--max-depth",
            "3",
            "--max-pages",
            "25",
            "--allow-cross-host",
        ]
    )
    assert captured["options"].max_depth == 3
    assert captured["options"].max_pages == 25
    assert captured["options"].same_host_only is False


def test_cli_gui_command(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_cmd_gui", lambda: 0)
    rc = cli.main(["gui"])
    assert rc == 0


def test_cli_download_requires_tty_for_interactive_mode(monkeypatch) -> None:
    class _NoTty:
        @staticmethod
        def isatty() -> bool:
            return False

    monkeypatch.setattr(cli, "analyze_snapshot", lambda *args, **kwargs: _analysis_result())
    monkeypatch.setattr(cli.sys, "stdin", _NoTty())
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["download", "https://web.archive.org/web/20200101010101/http://example.com/"])
    assert exc_info.value.code == 2
