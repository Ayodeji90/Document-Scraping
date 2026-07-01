#!/usr/bin/env python3
"""
Seed Master Content Hashes Utility

Scans all existing clean presentations in joint_downloaded/ (and any other output dirs),
computes their exact SHA-256 content hashes, and saves them to logs/master_content_hashes.txt.

This creates an unbreakable baseline so no future scraper will EVER download or keep
a copy of these files, regardless of what URL or mirror site they come from.

Usage:
    python seed_master_hashes.py
"""
import hashlib
import os
import sys
from pathlib import Path

HASH_FILE = Path("logs/master_content_hashes.txt")
DIRS_TO_SCAN = [Path("joint_downloaded"), Path("hf_pptonline")]

def get_file_sha256(filepath: Path) -> str:
    """Compute SHA-256 hash of a file efficiently in chunks."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):  # 1MB chunks
            h.update(chunk)
    return h.hexdigest()

def main():
    Path("logs").mkdir(exist_ok=True)
    
    existing_hashes = set()
    if HASH_FILE.exists():
        with open(HASH_FILE, "r") as f:
            existing_hashes = {line.strip() for line in f if line.strip()}
    
    print("=" * 65)
    print(f"🌱 SEEDING MASTER CONTENT HASHES")
    print(f"   Target file: {HASH_FILE}")
    print(f"   Existing:    {len(existing_hashes)} hashes loaded")
    print("=" * 65)

    new_hashes = 0
    total_files = 0

    for directory in DIRS_TO_SCAN:
        if not directory.exists():
            continue
            
        files = list(directory.glob("*.pptx")) + list(directory.glob("*.ppt"))
        if not files:
            continue
            
        print(f"\n📂 Scanning {directory}/ ({len(files)} files)...")
        for f in files:
            total_files += 1
            try:
                file_hash = get_file_sha256(f)
                if file_hash not in existing_hashes:
                    existing_hashes.add(file_hash)
                    new_hashes += 1
                    with open(HASH_FILE, "a") as hf:
                        hf.write(file_hash + "\n")
            except Exception as e:
                print(f"   ⚠️ Could not hash {f.name}: {e}")

    print("\n" + "=" * 65)
    print("📊 SEEDING COMPLETE")
    print("=" * 65)
    print(f"   Total files scanned: {total_files:>8,}")
    print(f"   New hashes added:    {new_hashes:>8,}")
    print(f"   Total master hashes: {len(existing_hashes):>8,}")
    print("=" * 65)
    print(f"🔒 Your scrapers are now permanently locked against re-downloading these files.")

if __name__ == "__main__":
    main()
