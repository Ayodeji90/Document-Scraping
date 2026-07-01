#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
1. Identifies 0-byte files in joint_downloaded.
2. Removes their tags from master_seen_tags.txt so they can be re-downloaded.
3. Re-renames all valid files to 7-digit padding (e.g., 0035915).
"""

import os
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def cleanup_and_rename(start_index=35915):
    joint_dir = Path("joint_downloaded")
    master_file = Path("logs/master_seen_tags.txt")
    mapping_log = joint_dir / "rename_mapping.log"
    
    if not joint_dir.exists():
        logger.error("joint_downloaded folder not found!")
        return

    # 1. Identify 0-byte files and their tags
    bad_files = []
    tags_to_remove = set()
    
    # Load mapping to find original tags
    tag_map = {} # new_name -> original_tag
    if mapping_log.exists():
        with open(mapping_log, "r", encoding="utf-8") as ml:
            for line in ml:
                if "|" in line:
                    parts = line.split("|")
                    if len(parts) > 1:
                        new_name = parts[0].strip()
                        orig_name = parts[1].strip()
                        tag = orig_name.split("_")[0]
                        if len(tag) == 10:
                            tag_map[new_name] = tag

    logger.info("Scanning for 0-byte files...")
    for f in joint_dir.iterdir():
        if f.is_file() and f.suffix.lower() in [".ppt", ".pptx"]:
            if f.stat().st_size == 0:
                bad_files.append(f)
                if f.name in tag_map:
                    tags_to_remove.add(tag_map[f.name])

    logger.info(f"Found {len(bad_files)} empty files. Deleting and restoring tags...")
    for f in bad_files:
        f.unlink()
        
    # 2. Update master_seen_tags.txt
    if tags_to_remove and master_file.exists():
        with open(master_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        with open(master_file, "w", encoding="utf-8") as f:
            removed_count = 0
            for line in lines:
                tag = line.strip()
                if tag in tags_to_remove:
                    removed_count += 1
                    continue
                f.write(line)
        logger.info(f"Removed {removed_count} tags from master list. Scrapers will now try to re-download these.")

    # 3. Re-rename all valid files to 7-digit padding
    valid_extensions = {".ppt", ".pptx"}
    files = sorted([f for f in joint_dir.iterdir() if f.is_file() and f.suffix.lower() in valid_extensions])
    
    logger.info(f"Re-naming {len(files)} valid files to 7-digit padding starting from {start_index:07d}...")
    
    # Create a fresh mapping log for the new 7-digit session
    new_mapping_log = joint_dir / "rename_mapping_7digit.log"
    with open(new_mapping_log, "w", encoding="utf-8") as log:
        log.write(f"--- 7-Digit Rename Session starting at {start_index:07d} ---\n")
        log.write("New Name | Old Name\n")
        
        for i, file_path in enumerate(files, start=start_index):
            extension = file_path.suffix
            new_name = f"{i:07d}{extension}"
            new_path = joint_dir / new_name
            
            if file_path.name == new_name:
                continue
                
            log.write(f"{new_name} | {file_path.name}\n")
            try:
                os.rename(file_path, new_path)
            except Exception as e:
                logger.error(f"Error renaming {file_path.name}: {e}")

    logger.info(f"Done! All files are now 7-digit padded. Mapping saved to {new_mapping_log.name}")

if __name__ == "__main__":
    cleanup_and_rename()
