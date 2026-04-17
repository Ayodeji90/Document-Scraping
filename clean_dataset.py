import os
import hashlib
import zipfile
import shutil
from pathlib import Path
import logging
import olefile

# Configuration
TARGET_DIR = "downloaded_ppts"
QUARANTINE_DIR = os.path.join(TARGET_DIR, "quarantine")
MIN_SIZE_BYTES = 5120 # 5KB
LOG_FILE = "cleanup_report.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def get_file_hash(path):
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
    except Exception as e:
        logger.error(f"Error hashing {path}: {e}")
        return None
    return sha256.hexdigest()

def is_corrupted(path):
    """Check if a file is corrupted or not a valid PPT/PPTX."""
    ext = path.suffix.lower()
    
    try:
        # Check for HTML content (common false positive)
        with open(path, "rb") as f:
            head = f.read(1024).lower()
            if b"<!doctype html" in head or b"<html" in head:
                return True, "HTML content detected (likely error page)"

        if ext == ".pptx":
            if not zipfile.is_zipfile(path):
                return True, "Invalid ZIP structure (corrupted .pptx)"
            # Extra check: valid PPTX must have [Content_Types].xml
            try:
                with zipfile.ZipFile(path) as z:
                    if "[Content_Types].xml" not in z.namelist():
                        return True, "Missing PPTX content types (corrupted)"
            except Exception:
                return True, "Failed to read ZIP archive"
                
        elif ext == ".ppt":
            if not olefile.isOleFile(str(path)):
                return True, "Invalid OLE structure (corrupted .ppt)"
    except Exception as e:
        return True, f"Error during validation: {e}"
    
    return False, ""

def clean_dataset(dry_run=True):
    target_path = Path(TARGET_DIR)
    quarantine_path = Path(QUARANTINE_DIR)
    
    if not target_path.exists():
        logger.error(f"Directory {TARGET_DIR} does not exist.")
        return

    if not dry_run:
        quarantine_path.mkdir(exist_ok=True)

    # Sort files to ensure stable numerical preference (lower index kept)
    files = sorted([f for f in target_path.iterdir() if f.is_file() and f.suffix.lower() in (".ppt", ".pptx")])
    
    hashes = {} # hash -> path
    to_move = [] # (path, reason)

    logger.info(f"Scanning {len(files)} files in {TARGET_DIR}...")

    for f in files:
        # 1. Size Check
        size = f.stat().st_size
        if size < MIN_SIZE_BYTES:
            to_move.append((f, f"Below size threshold ({size} bytes)"))
            continue

        # 2. Corruption Check
        corrupted, reason = is_corrupted(f)
        if corrupted:
            to_move.append((f, reason))
            continue

        # 3. Duplicate Check
        f_hash = get_file_hash(f)
        if not f_hash:
            continue
            
        if f_hash in hashes:
            existing = hashes[f_hash]
            to_move.append((f, f"Duplicate of {existing.name}"))
        else:
            hashes[f_hash] = f
            
    # Action
    if not to_move:
        logger.info("No duplicates or corrupted files found.")
        return

    logger.info(f"{'DRY RUN: ' if dry_run else ''}Found {len(to_move)} files to quarantine.")
    
    for f, reason in to_move:
        dest = quarantine_path / f.name
        logger.info(f"[{'SKIP' if dry_run else 'MOVE'}] {f.name} -> {reason}")
        if not dry_run:
            try:
                shutil.move(str(f), str(dest))
            except Exception as e:
                logger.error(f"Failed to move {f.name}: {e}")

    if not dry_run:
        logger.info(f"Cleanup complete. Flagged files moved to {QUARANTINE_DIR}")
    else:
        logger.info("Dry run complete. No files were moved. Use --execute to proceed.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Clean dataset of duplicates and corrupted files.")
    parser.add_argument("--execute", action="store_true", help="Actually move the files")
    args = parser.parse_args()
    
    clean_dataset(dry_run=not args.execute)
