#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Patches all regional scrapers to use the global persistence log.
Also adds a path fix to ensure 'src' is always findable.
"""

import os
import sys
from pathlib import Path
import re

SCRAPER_DIRS = ["africa", "asia", "europe", "north_america", "south_america", "oceania"]

# This block ensures 'src' is findable regardless of where the script is run from
PATH_FIX = """
import sys
import os
# Add project root to sys.path
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)
"""

IMPORT_LINE = "from src.utils.persistence import load_master_tags, save_new_tag\n"

NEW_PRELOAD = """
    def _preload_seen_from_disk(self):
        # Load from global persistence log
        master_tags = load_master_tags()
        self._seen_tags.update(master_tags)
        
        # Also check local disk for current session continuity
        if self.out_dir.exists():
            for p in self.out_dir.glob("*_*"):
                tag = p.name.split("_")[0]
                if len(tag) == 10:
                    self._seen_tags.add(tag)
        
        if len(self._seen_tags) > 0:
            logger.info("Resuming: Loaded %d seen tags (Global + Local).", len(self._seen_tags))
"""

def patch_file(file_path: Path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Add Path Fix (only once)
    if "import sys" not in content[:500] or "os.path.join" not in content[:1000]:
        content = content.replace("import argparse", PATH_FIX + "\nimport argparse", 1)

    # 2. Ensure Persistence Imports
    if "from src.utils.persistence" not in content:
        content = re.sub(r"(import requests)", IMPORT_LINE + r"\1", content)

    # 3. Replace the _preload_seen_from_disk method block
    pattern = r"\n\s+def _preload_seen_from_disk\(self\):.*?(?=\n\s+def _build_session)"
    content = re.sub(pattern, NEW_PRELOAD, content, flags=re.DOTALL)

    # 4. Ensure save_new_tag is called in _download
    save_marker = 'logger.info("  Downloaded: %s (%d KB)", dest.name, dest.stat.st_size // 1024)'
    if "save_new_tag(tag)" not in content:
        content = content.replace(save_marker, f"save_new_tag(tag)\n                {save_marker}")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✅ Patched: {file_path}")

def run_patch():
    for sdir in SCRAPER_DIRS:
        d = Path(sdir)
        if not d.exists(): continue
        for f in d.glob("*_scraper.py"):
            patch_file(f)

if __name__ == "__main__":
    run_patch()
