#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Aggregates all country-specific PPTX downloads into a single 'joint_downloaded' folder.
Original files are preserved in their source folders.
"""

import os
import shutil
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def aggregate():
    base_dir = Path(".")
    joint_dir = base_dir / "joint_downloaded"
    joint_dir.mkdir(exist_ok=True)
    
    # Find all directories that look like downloaded_ppts*
    source_dirs = [d for d in base_dir.iterdir() if d.is_dir() and (d.name.startswith("downloaded_ppts") or d.name == "downloaded_ppts")]
    
    total_copied = 0
    total_skipped = 0
    
    logger.info(f"Found {len(source_dirs)} source directories.")
    
    for sdir in source_dirs:
        if sdir.name == "joint_downloaded":
            continue
            
        logger.info(f"Processing (Moving): {sdir.name}...")
        files = [f for f in sdir.iterdir() if f.is_file()]
        
        for f in files:
            dest_file = joint_dir / f.name
            
            # If it already exists in joint, it's a duplicate. 
            # Delete from source to free space.
            if dest_file.exists():
                try:
                    f.unlink()
                    total_skipped += 1
                except Exception as e:
                    logger.error(f"Error deleting duplicate {f.name}: {e}")
                continue
            
            try:
                # Move instead of copy
                shutil.move(str(f), str(dest_file))
                total_copied += 1
            except Exception as e:
                logger.error(f"Error moving {f.name}: {e}")
                
    logger.info("--- Aggregation (Move) Complete ---")
    logger.info(f"Total files moved to 'joint_downloaded': {total_copied}")
    logger.info(f"Total duplicates removed from source: {total_skipped}")
    logger.info(f"Current total in 'joint_downloaded': {len(list(joint_dir.iterdir()))}")

if __name__ == "__main__":
    aggregate()
