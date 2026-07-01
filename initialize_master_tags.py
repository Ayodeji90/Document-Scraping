#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Initializes the master_seen_tags.txt file by extracting tags from joint_downloaded.
"""

import os
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def initialize():
    joint_dir = Path("joint_downloaded")
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    master_file = log_dir / "master_seen_tags.txt"
    
    if not joint_dir.exists():
        logger.error("joint_downloaded folder not found!")
        return

    tags = set()
    logger.info("Harvesting tags from joint_downloaded...")
    
    for f in joint_dir.glob("*_*"):
        tag = f.name.split("_")[0]
        if len(tag) == 10:
            tags.add(tag)
            
    # Also check rename_mapping.log if it exists for extra safety
    mapping_log = joint_dir / "rename_mapping.log"
    if mapping_log.exists():
        logger.info("Checking rename_mapping.log for additional tags...")
        with open(mapping_log, "r", encoding="utf-8") as ml:
            for line in ml:
                if "|" in line:
                    parts = line.split("|")
                    if len(parts) > 1:
                        orig_name = parts[1].strip()
                        tag = orig_name.split("_")[0]
                        if len(tag) == 10:
                            tags.add(tag)

    logger.info(f"Total unique tags found: {len(tags)}")
    
    with open(master_file, "w", encoding="utf-8") as f:
        for tag in sorted(list(tags)):
            f.write(f"{tag}\n")
            
    logger.info(f"Master tag list initialized at: {master_file}")

if __name__ == "__main__":
    initialize()
