# PPT Document Scraper (Criteria Compliant)

This repository contains an automated scraper designed to collect high-quality academic PowerPoint presentations (`.ppt`, `.pptx`) from global open-access sources. 

The system implements a rigorous multi-stage verification pipeline to ensure compliance with strict delivery requirements (Criteria 1 & 2), including geographic exclusions, pirate site screening, content quality assessment, and metadata preservation.

## Architecture

The system uses a 10-component pipeline:
1. **Config**: Centralized settings and blocklists (`src/config.py`).
2. **Filters**: Domain, geographic, and compliance filtering (`src/filters/`).
3. **Metadata**: Full metadata capture and JSON sidecar persistence (`src/metadata.py`).
4. **Validators**: Structural integrity and slide counting via `zipfile` and `olefile` (`src/validators.py`).
5. **Quality Assessor**: Introspects PPTX XML to detect charts, tables, diagrams, and text-density for HIGH/MEDIUM/LOW classification (`src/quality.py`).
6. **Verification Pipeline**: Orchestrates 11 sequential compliance checks culminating in a DELIVER/REVIEW/REJECT decision (`src/verification.py`).
7. **Audit Logger**: Appends structured JSON records to an audit log for every processed file (`src/audit.py`).
8. **Delivery Manager**: Packages DELIVER files into sequential batches enforcing 70% HIGH / 30% MEDIUM composition (`src/delivery.py`).
9. **Scrapers**: Custom API integration for Figshare, Zenodo, HAL, Dataverse, CORE, GitHub, and Internet Archive (`src/scraper/`).
10. **Orchestrator**: The `run.py` entrypoint.

## Installation

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Usage

Run the main orchestrator:

```bash
# Default multi-source run (target 3000 files, across all sources)
python run.py

# Run one source only
python run.py --source figshare --target 500

# Skip the slow PPTX XML quality assessment (all files marked MEDIUM)
python run.py --skip-quality-check

# Dry run (download and verify, but do not package final delivery batches)
python run.py --dry-run

# Resume mode (preload seen files from downloaded_ppts/)
python run.py --resume

# Verbose logging
python run.py -v
```

## Data Outputs

- `downloaded_ppts/` — Raw files passing the initial download filters, accompanied by `.meta.json` sidecars.
- `rejected/` — Files that failed the verification pipeline (e.g. corrupted, <5 slides, low quality).
- `delivery/` — Final packaged batches (e.g. `BATCH-20260416-001/`) meeting the 70/30 quality ratio and sequential naming.
- `logs/audit_log.jsonl` — The central audit log containing a record for every file processed.

## Source Exclusion Blocklists

Exclusion criteria are configured via JSON files in the `config/` directory:
- `fortune500_blocklist.json`
- `pirate_domains_blocklist.json`
- `us_domains_blocklist.json` (includes Elite US Universities and US Research Centers)
