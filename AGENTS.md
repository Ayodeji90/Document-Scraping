# AGENTS.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Development commands

### Environment setup
- Install dependencies:
  - `pip install -r requirements.txt`

### Main scraper runs (`run.py`)
- Default multi-source run:
  - `python run.py`
- Run one source only:
  - `python run.py --source figshare --target 500`
  - `python run.py --source zenodo --target 500`
- Dry run (download without Drive upload):
  - `python run.py --target 10 --dry-run`
- Download-only mode (skip Drive auth/upload path):
  - `python run.py --target 100 --no-upload`
- Resume mode (preload seen files from `downloaded_ppts/`):
  - `python run.py --resume`
- Verbose logging:
  - `python run.py -v`

### Single-source smoke checks (closest equivalent to a single test)
- There is no automated test suite configured (`tests/`, `pytest`, `tox`, and lint configs are absent).
- Use a minimal per-source smoke run:
  - `python run.py --source figshare --target 1 --dry-run --no-upload`
  - `python run.py --source zenodo --target 1 --dry-run --no-upload`
  - `python run.py --source hal --target 1 --dry-run --no-upload`

### Dataset utility scripts
- Clean duplicates/corrupt downloads (dry-run by default):
  - `python clean_dataset.py`
- Execute cleanup (moves files into `downloaded_ppts/quarantine/`):
  - `python clean_dataset.py --execute`
- Rename downloads sequentially:
  - `python rename_files.py --start 577 --dir downloaded_ppts`
- Count slides in downloaded files:
  - `python count_slides.py`

## High-level architecture

### Runtime flow
- `run.py` is the orchestration entrypoint:
  1. Parse CLI flags (`--target`, `--source`, `--resume`, delays, upload flags).
  2. Optionally preload dedupe state from `downloaded_ppts/` via `BaseScraper.preload_seen_from_dir`.
  3. Instantiate and run source scrapers in `SOURCE_ORDER`.
  4. Aggregate per-source stats and write `logs/manifest_*.json`.
  5. Rename downloaded files to sequential numeric filenames using `--start-index`.

### Scraper framework
- `src/scraper/base.py` defines shared behavior for all sources:
  - HTTP session + retry policy
  - request/download pacing
  - cross-instance URL and filename dedup (`_seen_urls`, `_seen_files`)
  - domain-level filtering (`src/filters/domain_filter.py`)
  - metadata/language filtering (`src/filters/geo_filter.py`)
  - streamed file download + basic content-type/empty-file checks
- Source scrapers in `src/scraper/*.py` implement source-specific search/extract logic and call `_download_file(...)`:
  - `figshare.py`, `zenodo.py`, `hal.py`, `internet_archive.py`, `dataverse.py`, `core.py`, `github.py`
- Query breadth is centralized in `src/scraper/keywords.py` for discipline-driven discovery.

### Storage integration
- `src/storage/gdrive.py` manages OAuth + Drive folder creation + upload.
- `GOOGLE_SETUP.md` is the canonical setup reference for `credentials.json` and token bootstrap.

## Repository-specific caveats to know before editing
- README drift exists:
  - README still mentions SlideShare/Selenium and a different default target, but `run.py` currently uses API-based sources (`figshare`, `zenodo`, `hal`, `core`, `github`, `dataverse`, `internet_archive`) and defaults to `--target 3000`.
- Upload path in `run.py`:
  - `setup_gdrive()` is invoked when uploads are enabled, but `upload_batch(...)` is defined and currently not called in `main()`. Do not assume files are uploaded unless this is explicitly wired back in.
- `BaseScraper._fetch_json` / `_post_json` currently accept `(url, params|payload, bypass_filter)`; keep call signatures aligned when editing source scrapers.
