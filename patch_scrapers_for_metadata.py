#!/usr/bin/env python3
"""
Patches all regional scrapers to save a .meta.json sidecar (with source URL)
alongside every downloaded file. Run once after updating persistence.py.
"""

import re
from pathlib import Path

SCRAPER_DIRS = ["africa", "asia", "europe", "north_america", "south_america", "oceania"]

OLD_IMPORT = "from src.utils.persistence import load_master_tags, save_new_tag"
NEW_IMPORT = "from src.utils.persistence import load_master_tags, save_new_tag, save_file_metadata"

# Insert save_file_metadata(dest, url) right before "return dest" inside _download
# The marker is the logger.info("  Downloaded: ...") line which always precedes the return
DOWNLOAD_LOGGER_RE = re.compile(
    r'(logger\.info\("  Downloaded: %s \(%d KB\)", dest\.name, dest\.stat\(\)\.st_size // 1024\))',
)
REPLACEMENT = r'\1\n                save_file_metadata(dest, url)'

patched = 0
skipped = 0

for sdir in SCRAPER_DIRS:
    d = Path(sdir)
    if not d.exists():
        continue
    for f in sorted(d.glob("*_scraper.py")):
        content = f.read_text(encoding="utf-8")

        if "save_file_metadata(dest, url)" in content:
            skipped += 1
            continue

        # Update import line
        content = content.replace(OLD_IMPORT, NEW_IMPORT)

        # Insert metadata save call after the Downloaded logger line
        new_content = DOWNLOAD_LOGGER_RE.sub(REPLACEMENT, content)

        if new_content == content:
            print(f"  WARN: no download logger found in {f} — skipping")
            skipped += 1
            continue

        f.write_text(new_content, encoding="utf-8")
        print(f"  Patched: {f}")
        patched += 1

print(f"\nDone — {patched} patched, {skipped} skipped.")
