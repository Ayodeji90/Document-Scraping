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
BATCH02_COUNTER    = Path("logs/batch02_counter.txt")
BATCH02_LOCK       = Path("logs/batch02_counter.lock")


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


def get_next_batch02_number() -> int:
    """Atomically increment and return the next BATCH_02 sequence number.
    Safe for concurrent use across multiple scraper processes."""
    BATCH02_LOCK.parent.mkdir(exist_ok=True)
    with open(BATCH02_LOCK, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            current = int(BATCH02_COUNTER.read_text().strip()) if BATCH02_COUNTER.exists() else 0
            next_num = current + 1
            BATCH02_COUNTER.write_text(str(next_num))
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)
    return next_num


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
