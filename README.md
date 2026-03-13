# Wayback Export Toolkit

A Python package and CLI for mirroring Wayback snapshots into offline-browsable static websites, with optional export-artifact analysis/downloading.

## What it does

- Mirrors a Wayback snapshot into local HTML pages + static assets (CSS/JS/images)
- Rewrites internal links so mirrored pages can be opened locally
- Supports bounded crawling with `--max-depth` and `--max-pages`
- Writes a `mirror_manifest.json` with counts, warnings, and failed URLs
- Also supports export-file discovery/download mode (`analyze` / `download`)

## Project structure

```text
src/wayback_export/
  cli.py         # CLI entry points and argument parsing
  gui.py         # Tkinter desktop GUI
  mirror.py      # Full static-site mirror pipeline
  analysis.py    # Export-candidate crawl orchestration
  discovery.py   # Link extraction and confidence scoring
  download.py    # Export artifact download + manifest generation
  http_client.py # HTTP transport abstraction
  wayback.py     # Wayback URL parsing/normalization helpers
  output.py      # Output pathing helpers
tests/           # Unit and behavior tests
```

## Install

```bash
python -m pip install -e .[dev]
```

Optional rich prompt/table output:

```bash
python -m pip install -e .[ui]
```

## Main usage: mirror a site

```bash
wayback-export mirror "https://web.archive.org/web/20140208014753/https://www.paulgraham.com/" \
  --output ./downloads \
  --max-depth 3 \
  --max-pages 1000
```

JSON output:

```bash
wayback-export mirror "https://web.archive.org/web/20140208014753/https://www.paulgraham.com/" --json
```

## Output layout for mirror mode

`<output>/<host>_<timestamp>/`

- `mirror_manifest.json`
- `site/` (offline-browsable mirrored pages + assets)

Open `site/index.html` to browse the mirrored snapshot locally.

## Export-artifact mode (optional)

Analyze likely data/export files:

```bash
wayback-export analyze "https://web.archive.org/web/20200101010101/http://example.com/"
```

Download export-like files:

```bash
wayback-export download "https://web.archive.org/web/20200101010101/http://example.com/" --all --output ./downloads
```

## Development quickstart

```bash
python -m pip install -e .[dev]
pytest -q
```

## Scope notes

- Mirroring is best-effort and depends on what Wayback captured for the snapshot timestamp.
- Dynamic server-driven features and external third-party dependencies may not render offline.
- Traversal is bounded by `--max-depth` and `--max-pages`.
