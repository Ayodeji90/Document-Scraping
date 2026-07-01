#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Global persistence utility for managing seen file tags.
Ensures we don't redownload files even after local copies are deleted.
"""

import os
from pathlib import Path
from typing import Set

MASTER_TAGS_FILE = Path("logs/master_seen_tags.txt")

def load_master_tags() -> Set[str]:
    """Load all seen tags from the master log file."""
    if not MASTER_TAGS_FILE.exists():
        MASTER_TAGS_FILE.parent.mkdir(exist_ok=True)
        return set()
    
    with open(MASTER_TAGS_FILE, "r", encoding="utf-8") as f:
        return {line.strip() for line in f if line.strip()}

def save_new_tag(tag: str):
    """Append a single new tag to the master log file."""
    MASTER_TAGS_FILE.parent.mkdir(exist_ok=True)
    with open(MASTER_TAGS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{tag}\n")
