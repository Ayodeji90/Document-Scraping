#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fixes two issues in generated scrapers:
1. Strips embedded double-quotes from TOPICS lists
2. Adds strict file validation to _download to reject non-PPT files
3. Cleans up existing non-PPT junk from download folders
"""

import re
from pathlib import Path

SCRAPER_DIRS = ["africa", "asia", "europe", "north_america", "south_america", "oceania"]

def fix_file(file_path: Path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    original = content
    
    # 1. Fix TOPICS: remove embedded double quotes from list items
    # Pattern: '"lecture slides"' → 'lecture slides'
    content = re.sub(r"""'\"([^"]+)\"'""", r"'\1'", content)
    
    # 2. Fix _safe_filename: Don't blindly append .pptx
    # Replace the line that appends .pptx to non-ppt URLs
    old_safe = """if not name.lower().endswith((".pptx",".ppt")): name += ".pptx" """
    new_safe = """if not name.lower().endswith((".pptx",".ppt")): return None, None"""
    content = content.replace(old_safe.strip(), new_safe.strip())
    
    # 3. Fix _download: Add None check after _safe_filename and strict post-download validation
    # Replace the download method's first lines to handle None returns
    old_download_start = 'tag, fname = self._safe_filename(url); dest = self.out_dir / fname'
    new_download_start = '''tag, fname = self._safe_filename(url)
        if tag is None: return None
        dest = self.out_dir / fname'''
    content = content.replace(old_download_start, new_download_start)
    
    # 4. Add post-download content-type check: reject zip, html, etc.
    # Add a check after file is written - verify it's not a zip or other junk
    old_size_check = 'if dest.stat().st_size < 5120: dest.unlink(missing_ok=True); return None'
    new_size_check = '''if dest.stat().st_size < 5120: dest.unlink(missing_ok=True); return None
            # Reject non-PPT files by checking magic bytes
            with open(dest, "rb") as chk:
                header = chk.read(8)
            # PK header (PPTX/ZIP-based) or MS-CFB header (old PPT)
            if not (header[:2] == b"PK" or header[:8] == b"\\xd0\\xcf\\x11\\xe0\\xa1\\xb1\\x1a\\xe1"):
                dest.unlink(missing_ok=True); return None'''
    content = content.replace(old_size_check, new_size_check)
    
    if content != original:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ Fixed: {file_path}")
    else:
        print(f"⏭️  No changes needed: {file_path}")

def clean_junk_files():
    """Remove non-PPT files from all download folders."""
    removed = 0
    for d in Path(".").glob("downloaded_ppts_*"):
        if not d.is_dir(): continue
        for f in d.iterdir():
            if f.is_file() and not f.name.lower().endswith((".ppt", ".pptx", ".log")):
                f.unlink()
                removed += 1
    if removed:
        print(f"🗑️  Cleaned {removed} non-PPT junk files from download folders.")

def main():
    for sdir in SCRAPER_DIRS:
        d = Path(sdir)
        if not d.exists(): continue
        for f in d.glob("*_scraper.py"):
            fix_file(f)
    clean_junk_files()

if __name__ == "__main__":
    main()
