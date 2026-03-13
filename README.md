# Wayback Export Toolkit

A Python package and CLI that accepts a specific Wayback Machine snapshot URL, discovers likely export/data files from that archived page, and downloads either selected files or all candidates to your local machine.

## What v1 does

- Accepts a single Wayback snapshot URL (`web.archive.org/web/<timestamp>/...`)
- Analyzes the archived page for likely export/data links (`.zip`, `.csv`, `.sql`, `.json`, `.xml`, `.xlsx`, dumps/backups/archives)
- Lets you choose interactively what to download (or use `--all` for automation)
- Saves original files and writes a structured `manifest.json`
- Skips files that already exist by default

## Install

```bash
python -m pip install -e .[dev]
```

Optional rich prompt/table output:

```bash
python -m pip install -e .[ui]
```

## CLI Usage

Analyze only:

```bash
wayback-export analyze "https://web.archive.org/web/20200101010101/http://example.com/"
```

Download with interactive selection:

```bash
wayback-export download "https://web.archive.org/web/20200101010101/http://example.com/" --output ./downloads
```

Download all without prompts:

```bash
wayback-export download "https://web.archive.org/web/20200101010101/http://example.com/" --all --output ./downloads
```

Depth-controlled traversal (follow connected pages up to depth 2):

```bash
wayback-export analyze "https://web.archive.org/web/20200101010101/http://example.com/" --max-depth 2 --max-pages 200
```

JSON output:

```bash
wayback-export analyze "https://web.archive.org/web/20200101010101/http://example.com/" --json
```

Launch the desktop GUI:

```bash
wayback-export gui
```

## Output layout

For each snapshot, files are stored under:

`<output>/<host>_<timestamp>/`

- `manifest.json`
- `files/` (downloaded artifacts)

The manifest includes snapshot metadata, discovered candidates, selected candidates, and per-file statuses (`downloaded`, `skipped`, `failed`, or `planned`).

## Python API

```python
from pathlib import Path
from wayback_export import analyze_snapshot, download_candidates, AnalyzeOptions, DownloadOptions

snapshot = "https://web.archive.org/web/20200101010101/http://example.com/"
analysis = analyze_snapshot(snapshot, AnalyzeOptions())

result = download_candidates(
    snapshot,
    selection=analysis.candidates,
    options=DownloadOptions(output_dir=Path("./downloads"), download_all=True),
    analysis=analysis,
)
```

## Scope notes

- v1 does not do a full recursive site reconstruction.
- Traversal is bounded by `--max-depth` and `--max-pages` (defaults: `0`, `100`).
- v1 expects a direct snapshot URL (not an original URL that needs snapshot discovery).
- Files are preserved in original format; no cross-format normalization is attempted.
