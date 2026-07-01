#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Global persistence utility for managing seen file tags and URL metadata.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Set

MASTER_TAGS_FILE = Path("logs/master_seen_tags.txt")

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

def save_file_metadata(filepath: Path, source_url: str, extra: dict = None):
    """Write a .meta.json sidecar alongside a downloaded file with source URL and timestamps."""
    meta = {
        "source_url": source_url,
        "source_domain": _extract_domain(source_url),
        "download_url": source_url,
        "filename": filepath.name,
        "file_size": filepath.stat().st_size if filepath.exists() else 0,
        "file_format": filepath.suffix.lower().lstrip("."),
        "collection_timestamp": datetime.now(timezone.utc).isoformat(),
        **(extra or {}),
    }
    meta_path = filepath.with_suffix(".meta.json")
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _extract_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc
    except Exception:
        return ""
