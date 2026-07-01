#!/usr/bin/env python3
"""
Deduplicate PPT files across all downloaded_ppt* folders.
Creates a duplicates folder and logs all duplicates.
"""
import os
import sys
import json
import hashlib
import shutil
from pathlib import Path
from datetime import datetime
from collections import defaultdict


def get_file_hash(filepath: Path, chunk_size: int = 8192) -> str:
    """Calculate MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"  ⚠ Error hashing {filepath}: {e}")
        return None


def find_all_ppt_folders(base_dir: Path) -> list:
    """Find all downloaded_ppt* folders."""
    folders = []
    for item in base_dir.iterdir():
        if item.is_dir() and item.name.startswith("downloaded_ppt"):
            folders.append(item)
    return sorted(folders)


def collect_all_files(folders: list) -> list:
    """Collect all PPT/PPTX files from folders."""
    all_files = []
    for folder in folders:
        for ext in ["*.ppt", "*.pptx"]:
            for file_path in folder.glob(ext):
                all_files.append(file_path)
    return all_files


def find_duplicates(files: list) -> dict:
    """Find duplicate files based on hash."""
    hash_to_files = defaultdict(list)
    
    print(f"\n📊 Analyzing {len(files)} files...")
    
    for i, file_path in enumerate(files, 1):
        if i % 50 == 0:
            print(f"  Processed {i}/{len(files)} files...")
        
        file_hash = get_file_hash(file_path)
        if file_hash:
            hash_to_files[file_hash].append(file_path)
    
    # Filter to only duplicates
    duplicates = {h: paths for h, paths in hash_to_files.items() if len(paths) > 1}
    return duplicates


def move_duplicates(duplicates: dict, duplicates_folder: Path) -> dict:
    """Move duplicate files to duplicates folder, keeping first in original location."""
    log = {
        "timestamp": datetime.now().isoformat(),
        "total_duplicate_groups": len(duplicates),
        "total_duplicate_files": 0,
        "duplicates": []
    }
    
    duplicates_folder.mkdir(exist_ok=True)
    
    for file_hash, paths in duplicates.items():
        # Keep the first file in its original location, move the rest
        original = paths[0]
        duplicates_list = paths[1:]
        
        group_info = {
            "hash": file_hash,
            "original_kept": str(original),
            "duplicates_moved": []
        }
        
        for dup_path in duplicates_list:
            # Create unique name for duplicate
            unique_name = f"{dup_path.parent.name}_{dup_path.name}"
            dest_path = duplicates_folder / unique_name
            
            # Handle name collision
            counter = 1
            while dest_path.exists():
                stem = dup_path.stem
                suffix = dup_path.suffix
                dest_path = duplicates_folder / f"{dup_path.parent.name}_{stem}_{counter}{suffix}"
                counter += 1
            
            try:
                shutil.move(str(dup_path), str(dest_path))
                group_info["duplicates_moved"].append({
                    "from": str(dup_path),
                    "to": str(dest_path)
                })
                print(f"  ✓ Moved: {dup_path.name} -> duplicates/{dest_path.name}")
            except Exception as e:
                print(f"  ❌ Failed to move {dup_path}: {e}")
                group_info["duplicates_moved"].append({
                    "from": str(dup_path),
                    "error": str(e)
                })
        
        log["duplicates"].append(group_info)
        log["total_duplicate_files"] += len(duplicates_list)
    
    return log


def main():
    base_dir = Path(__file__).parent
    
    print("=" * 60)
    print("🔍 PPT DEDUPLICATION TOOL")
    print("=" * 60)
    
    # Find all downloaded_ppt folders
    folders = find_all_ppt_folders(base_dir)
    print(f"\n📁 Found {len(folders)} downloaded_ppt* folders:")
    for f in folders:
        count = len(list(f.glob("*.ppt"))) + len(list(f.glob("*.pptx")))
        print(f"   {f.name}: {count} files")
    
    if not folders:
        print("\n❌ No downloaded_ppt folders found!")
        return
    
    # Collect all files
    all_files = collect_all_files(folders)
    print(f"\n📄 Total PPT/PPTX files found: {len(all_files)}")
    
    if len(all_files) < 2:
        print("\n⚠ Not enough files to check for duplicates")
        return
    
    # Find duplicates
    duplicates = find_duplicates(all_files)
    
    if not duplicates:
        print("\n✅ No duplicates found!")
        return
    
    print(f"\n🎯 Found {len(duplicates)} duplicate groups")
    total_dups = sum(len(paths) - 1 for paths in duplicates.values())
    print(f"   Total duplicate files to move: {total_dups}")
    
    # Create duplicates folder
    duplicates_folder = base_dir / "duplicates"
    print(f"\n📂 Duplicates folder: {duplicates_folder}")
    
    # Move duplicates
    print("\n🚚 Moving duplicates...")
    log = move_duplicates(duplicates, duplicates_folder)
    
    # Save log
    log_path = base_dir / "duplicates_log.json"
    with open(log_path, 'w') as f:
        json.dump(log, f, indent=2)
    
    print(f"\n📝 Log saved: {log_path}")
    print(f"\n📊 Summary:")
    print(f"   - Duplicate groups: {log['total_duplicate_groups']}")
    print(f"   - Files moved: {log['total_duplicate_files']}")
    print(f"   - Originals kept: {log['total_duplicate_groups']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
