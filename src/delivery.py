"""
Delivery packaging module — enforces delivery composition, assigns batch IDs,
and packages DELIVER-status files into final delivery batches.

Implements criteria1 §6 delivery targets:
  - 70%+ High Quality
  - 20-30% Medium Quality
  - 0% Low Quality
"""
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List

from src.config import get_config
from src.metadata import FileMetadata, MetadataStore

logger = logging.getLogger(__name__)


class DeliveryManager:
    """Manages the creation of delivery batches."""

    def __init__(self, delivery_dir: Path, metadata_store: MetadataStore):
        self.delivery_dir = delivery_dir
        self.metadata_store = metadata_store
        self.delivery_dir.mkdir(parents=True, exist_ok=True)
        self.config = get_config()

    def generate_batch_id(self) -> str:
        """Generate a unique batch identifier (e.g., BATCH-20260416-001)."""
        date_str = datetime.utcnow().strftime("%Y%m%d")
        # Find next batch number
        existing_batches = [
            d for d in self.delivery_dir.iterdir()
            if d.is_dir() and d.name.startswith(f"BATCH-{date_str}-")
        ]
        next_num = len(existing_batches) + 1
        return f"BATCH-{date_str}-{next_num:03d}"

    def package_delivery(self, source_dir: Path, dry_run: bool = False) -> str:
        """
        Scan a source directory for DELIVER files, enforce quality composition,
        and package them into a new batch directory.
        """
        logger.info(f"Scanning {source_dir} for deliverable files...")
        
        # 1. Gather all deliverable candidates
        candidates_high = []
        candidates_medium = []
        
        for p in source_dir.glob("*"):
            if not p.is_file() or p.suffix.lower() not in (".ppt", ".pptx"):
                continue
                
            meta = self.metadata_store.load(p)
            if not meta or meta.delivery_status != "DELIVER":
                continue
                
            if meta.quality_classification == "HIGH":
                candidates_high.append((p, meta))
            elif meta.quality_classification == "MEDIUM":
                candidates_medium.append((p, meta))
            # LOW is automatically rejected by the verification pipeline

        total_candidates = len(candidates_high) + len(candidates_medium)
        if total_candidates == 0:
            logger.info("No deliverable files found.")
            return ""

        # 2. Enforce composition rules (70%+ HIGH, 20-30% MEDIUM)
        # Determine how many HIGH files we have. We can include MEDIUM files up to
        # (HIGH_COUNT / 0.70) * 0.30 to maintain the 70/30 ratio.
        max_medium = int((len(candidates_high) / self.config.delivery_high_pct) * self.config.delivery_medium_pct)
        
        # Select files for delivery
        selected_high = candidates_high
        selected_medium = candidates_medium[:max_medium]
        delivery_files = selected_high + selected_medium
        
        # We can chunk them into batch sizes (e.g. 500) if needed, but for now we'll
        # just create one batch with up to config.batch_size files.
        batch_files = delivery_files[:self.config.batch_size]
        if not batch_files:
            logger.warning("No files selected for delivery after applying constraints.")
            return ""

        # 3. Create batch directory and package files
        batch_id = self.generate_batch_id()
        batch_dir = self.delivery_dir / batch_id
        
        if dry_run:
            logger.info(f"[DRY RUN] Would create batch {batch_id} with {len(batch_files)} files")
            return batch_id

        batch_dir.mkdir()
        logger.info(f"Packaging {len(batch_files)} files into batch {batch_id}...")

        # 4. Copy files and metadata, update batch ID
        manifest_records = []
        for i, (fp, meta) in enumerate(batch_files, 1):
            # Standardized sequential naming within the batch
            ext = fp.suffix
            new_name = f"{batch_id}_FILE{i:05d}{ext}"
            new_path = batch_dir / new_name
            
            # Copy file
            shutil.copy2(fp, new_path)
            
            # Update metadata
            meta.batch_id = batch_id
            
            # Save metadata sidecar in batch directory
            new_sidecar = batch_dir / (new_name + self.config.metadata_sidecar_ext)
            with open(new_sidecar, "w", encoding="utf-8") as f:
                json.dump(meta.to_dict(), f, indent=2, ensure_ascii=False)
                
            manifest_records.append(meta.to_dict())

        # 5. Generate Batch Manifest
        manifest = {
            "batch_id": batch_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "total_files": len(batch_files),
            "composition": {
                "high_quality": len(selected_high),
                "medium_quality": len(selected_medium),
                "high_pct": round(len(selected_high) / len(batch_files) * 100, 1),
                "medium_pct": round(len(selected_medium) / len(batch_files) * 100, 1)
            },
            "files": manifest_records
        }
        
        manifest_path = batch_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
            
        logger.info(f"Batch {batch_id} complete. High: {manifest['composition']['high_pct']}%, Medium: {manifest['composition']['medium_pct']}%")
        return batch_id
