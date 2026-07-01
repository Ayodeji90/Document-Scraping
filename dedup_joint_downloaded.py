#!/usr/bin/env python3
"""
Efficient Deduplication Utility for joint_downloaded/

Identifies and separates duplicate PPT/PPTX files using a two-tier approach:
1. Fast Binary Dedup: Groups by exact file size, then computes SHA-256.
2. Deep Content Dedup: For PPTX files, extracts and hashes inner slide XMLs
   to catch files with identical slides but different zip/download timestamps.

Original/oldest files are kept in joint_downloaded/.
Duplicates are moved to quarantine_duplicates/.

Usage:
    python dedup_joint_downloaded.py
"""
import hashlib
import os
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path
from collections import defaultdict

# --- Configuration ---
SOURCE_DIR = Path("joint_downloaded")
QUARANTINE_DIR = Path("quarantine_duplicates")

def get_file_sha256(filepath: Path) -> str:
    """Compute SHA-256 hash of a file efficiently in chunks."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):  # 1MB chunks
            h.update(chunk)
    return h.hexdigest()

def get_pptx_content_hash(filepath: Path) -> str:
    """
    Compute SHA-256 hash of inner slide XML content for PPTX files.
    Catches files with identical slides but different zip timestamps/metadata.
    """
    try:
        with zipfile.ZipFile(filepath, "r") as z:
            # Filter and sort slide xml files to ensure consistent order
            slide_files = sorted(
                [n for n in z.namelist() if "slide" in n and n.endswith(".xml")]
            )
            if not slide_files:
                return ""
            
            h = hashlib.sha256()
            for name in slide_files:
                # Read content and normalize line endings/whitespace
                content = z.read(name).decode("utf-8", errors="ignore")
                # Remove timestamp/ID attributes that might vary between downloads
                content = re.sub(r' (id|val|time)="[^"]*"', '', content)
                h.update(content.encode("utf-8"))
            return h.hexdigest()
    except Exception:
        return ""

def main():
    if not SOURCE_DIR.exists():
        print(f"❌ Source directory {SOURCE_DIR} does not exist.")
        sys.exit(1)

    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print(f"🔍 STARTING EFFICIENT DEDUPLICATION")
    print(f"   Source:     {SOURCE_DIR}/")
    print(f"   Quarantine: {QUARANTINE_DIR}/")
    print("=" * 65)

    # 1. Gather all files and sort by modification time (keep oldest/original)
    all_files = list(SOURCE_DIR.glob("*.pptx")) + list(SOURCE_DIR.glob("*.ppt"))
    if not all_files:
        print("📂 No presentation files found to deduplicate.")
        sys.exit(0)

    print(f"\n📂 Scanning {len(all_files)} files...")
    all_files.sort(key=lambda f: f.stat().st_mtime)

    # --- Phase 1: Fast Size Grouping ---
    size_groups = defaultdict(list)
    for f in all_files:
        try:
            size = f.stat().st_size
            size_groups[size].append(f)
        except Exception as e:
            print(f"   ⚠️ Could not read size of {f.name}: {e}")

    unique_size_count = sum(1 for g in size_groups.values() if len(g) == 1)
    potential_dups = sum(len(g) for g in size_groups.values() if len(g) > 1)
    
    print(f"   📊 Size grouping: {unique_size_count} files have unique sizes (instant pass).")
    print(f"   📊 {potential_dups} files share exact sizes and need hashing.")

    # --- Phase 2: Exact Binary Hashing ---
    print("\n🧬 Phase 1: Hashing files with matching sizes (Exact Binary Match)...")
    binary_hashes = set()
    binary_dups = []
    passed_binary = []

    # Add unique-sized files directly to passed_binary
    for size, files in size_groups.items():
        if len(files) == 1:
            passed_binary.append(files[0])
            continue

        # For matching sizes, compute SHA-256
        for f in files:
            try:
                file_hash = get_file_sha256(f)
                if file_hash in binary_hashes:
                    binary_dups.append(f)
                else:
                    binary_hashes.add(file_hash)
                    passed_binary.append(f)
            except Exception as e:
                print(f"   ⚠️ Could not hash {f.name}: {e}")

    print(f"   🗑️ Found {len(binary_dups)} exact binary duplicates.")

    # --- Phase 3: Deep PPTX Content Hashing ---
    print("\n🔬 Phase 2: Deep Content Hashing (Checking internal slide XMLs)...")
    content_hashes = set()
    content_dups = []
    unique_kept = []

    for i, f in enumerate(passed_binary, 1):
        if i % 500 == 0:
            print(f"   Checking content {i}/{len(passed_binary)}...")

        if f.suffix.lower() == ".pptx":
            chash = get_pptx_content_hash(f)
            if chash:
                if chash in content_hashes:
                    content_dups.append(f)
                else:
                    content_hashes.add(chash)
                    unique_kept.append(f)
            else:
                # If content hash failed (or no slides found), keep it
                unique_kept.append(f)
        else:
            # Old .ppt files — rely on binary hash
            unique_kept.append(f)

    print(f"   🗑️ Found {len(content_dups)} deep content duplicates.")

    # --- Phase 4: Move Duplicates to Quarantine ---
    all_dups = binary_dups + content_dups
    total_saved_bytes = 0

    if all_dups:
        print(f"\n🚚 Moving {len(all_dups)} duplicates to {QUARANTINE_DIR}/...")
        for f in all_dups:
            try:
                total_saved_bytes += f.stat().st_size
                dest = QUARANTINE_DIR / f.name
                # If destination already exists, make filename unique
                if dest.exists():
                    dest = QUARANTINE_DIR / f"{f.stem}_{int(time.time())}{f.suffix}"
                shutil.move(str(f), str(dest))
            except Exception as e:
                print(f"   ⚠️ Could not move {f.name}: {e}")
    else:
        print("\n✨ No duplicates found! Your dataset is completely clean.")

    # --- Summary ---
    saved_mb = total_saved_bytes / (1024 * 1024)
    print("\n" + "=" * 65)
    print("📊 DEDUPLICATION SUMMARY")
    print("=" * 65)
    print(f"   Total files scanned:      {len(all_files):>8,}")
    print(f"   Exact binary duplicates:  {len(binary_dups):>8,}")
    print(f"   Deep content duplicates:  {len(content_dups):>8,}")
    print(f"   Total duplicates moved:   {len(all_dups):>8,}")
    print(f"   ✅ Clean files remaining: {len(unique_kept):>8,}")
    print(f"   💾 Disk space cleaned:    {saved_mb:>8.2f} MB")
    print("=" * 65)
    print(f"📁 Clean dataset: {SOURCE_DIR.absolute()}")
    print(f"📦 Quarantined:   {QUARANTINE_DIR.absolute()}")

if __name__ == "__main__":
    main()
