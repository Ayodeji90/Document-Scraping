# AGENTS.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Development commands

### Environment setup
- Install dependencies:
  - `pip install -r requirements.txt`

### Main scraper runs (`run.py`)
The orchestrator (`run.py`) now runs a full multi-stage verification pipeline and packages files into delivery batches in `delivery/`.

- Default multi-source run (target 3000):
  - `python run.py`
- Run one source only:
  - `python run.py --source figshare --target 500`
  - `python run.py --source zenodo --target 500`
- Skip quality assessment (faster, but sets all passing files to MEDIUM):
  - `python run.py --skip-quality-check`
- Dry run (download and verify, but don't package into `delivery/`):
  - `python run.py --target 10 --dry-run`
- Resume mode (preload seen files from `downloaded_ppts/`):
  - `python run.py --resume`
- Verbose logging:
  - `python run.py -v`

### Single-source smoke checks (closest equivalent to a single test)
- There is no automated test suite configured.
- Use a minimal per-source smoke run:
  - `python run.py --source figshare --target 1 --dry-run`
  - `python run.py --source zenodo --target 1 --dry-run`
  - `python run.py --source hal --target 1 --dry-run`

### Dataset utility scripts (Legacy)
- Clean duplicates/corrupt downloads:
  - `python clean_dataset.py` (Note: integrity checks are now built into the main pipeline)
- Count slides in downloaded files:
  - `python count_slides.py` (Note: slide counting is now built into the main pipeline)

## High-level architecture

### Runtime flow
- `run.py` is the orchestration entrypoint:
  1. Parse CLI flags.
  2. Initialize the DI container (Filters, Validator, QualityAssessor, VerificationPipeline, AuditLogger, MetadataStore, DeliveryManager).
  3. Instantiate and run source scrapers.
  4. Scrapers download files to `downloaded_ppts/`, run verification, and write to `logs/audit_log.jsonl`.
  5. Rejected files are moved to `rejected/`.
  6. `DeliveryManager` packages DELIVER-status files into `delivery/BATCH-ID/`.

### Verification Pipeline
- `src/verification.py` orchestrates 11 compliance checks:
  - File Integrity (ZIP/OLE check)
  - Slide Count (≥5)
  - Source & Public Verification
  - Pirate Site Screening
  - PII / COPPA / Prohibited Content Screening
  - Quality Assessment (HIGH/MEDIUM/LOW based on chart/diagram detection)

### Blocklists
- Exclusions (Fortune 500, Pirate sites, US Universities) are configured in `config/*.json`.
