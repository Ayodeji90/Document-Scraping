#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Global persistence utility for managing seen file tags and BATCH_02 metadata.
"""

import fcntl
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Set

MASTER_TAGS_FILE   = Path("logs/master_seen_tags.txt")


def load_master_tags() -> Set[str]:
    if not MASTER_TAGS_FILE.exists():
        MASTER_TAGS_FILE.parent.mkdir(exist_ok=True)
        return set()
    with open(MASTER_TAGS_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}


def save_new_tag(tag: str):
    MASTER_TAGS_FILE.parent.mkdir(exist_ok=True)
    with open(MASTER_TAGS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{tag}\n")


def get_next_batch_number(batch_id: str) -> int:
    """Atomically increment and return the next sequence number for a given
    batch_id (e.g. "BATCH_02", "BATCH_03"). Each batch_id gets its own
    independent counter file, so separate batches don't share numbering.
    Safe for concurrent use across multiple scraper processes."""
    # "batch02" (no underscore) to exactly match the pre-existing BATCH_02
    # counter file path — changing it would silently reset production numbering.
    slug = batch_id.lower().replace("_", "")
    counter_file = Path(f"logs/{slug}_counter.txt")
    lock_file = Path(f"logs/{slug}_counter.lock")
    lock_file.parent.mkdir(exist_ok=True)
    with open(lock_file, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            current = int(counter_file.read_text().strip()) if counter_file.exists() else 0
            next_num = current + 1
            counter_file.write_text(str(next_num))
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)
    return next_num


def get_next_batch02_number() -> int:
    """Atomically increment and return the next BATCH_02 sequence number.
    Safe for concurrent use across multiple scraper processes."""
    return get_next_batch_number("BATCH_02")


def save_file_metadata(filepath: Path, source_url: str, extra: dict = None) -> Path:
    """Rename downloaded file to BATCH_02_XXXXXX format, write per-file .meta.json sidecar.
    Returns the new file path."""
    num = get_next_batch02_number()
    ext = filepath.suffix.lower() or ".pptx"
    new_name = f"BATCH_02_names_{num:06d}{ext}"
    new_path = filepath.parent / new_name

    try:
        filepath.rename(new_path)
    except Exception:
        new_path = filepath  # fallback: keep original name

    meta = {
        "batch_id": "BATCH_02",
        "sequence_number": num,
        "filename": new_name,
        "original_filename": filepath.name,
        "source_url": source_url,
        "source_domain": _extract_domain(source_url),
        "download_url": source_url,
        "collection_timestamp": datetime.now(timezone.utc).isoformat(),
        "file_size": new_path.stat().st_size if new_path.exists() else 0,
        "file_format": ext.lstrip("."),
        **(extra or {}),
    }

    meta_path = new_path.with_suffix(".meta.json")
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return new_path


def _extract_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc
    except Exception:
        return ""
