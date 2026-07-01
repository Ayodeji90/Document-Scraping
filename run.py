#!/usr/bin/env python3
"""
PPT Document Scraper — orchestration entry point.

Complies with Criteria1 & Criteria2 requirements for delivery, quality,
metadata preservation, and multi-stage verification.

Usage:
    python run.py                        # all sources, target 3000
    python run.py -t 500 -s figshare     # single source
    python run.py --dry-run              # test without packaging
    python run.py --skip-quality-check   # disable slow quality assessment
    python run.py -v                     # verbose logging
"""
import argparse
import logging
import sys
from pathlib import Path

from src.config import get_config, set_config
from src.metadata import MetadataStore
from src.audit import AuditLogger
from src.delivery import DeliveryManager
from src.validators import FileValidator
from src.quality import QualityAssessor
from src.filters import DomainFilter, GeoFilter, ComplianceFilter
from src.verification import VerificationPipeline

from src.scraper.figshare import FigshareScraper
from src.scraper.hal import HALScraper
from src.scraper.internet_archive import InternetArchiveScraper
from src.scraper.zenodo import ZenodoScraper
from src.scraper.dataverse import DataverseScraper
from src.scraper.core import CoreScraper
from src.scraper.github import GitHubScraper

from src.scraper.base import BaseScraper


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=level,
        stream=sys.stderr,
    )


SCRAPER_MAP = {
    "figshare": FigshareScraper,
    "zenodo": ZenodoScraper,
    "hal": HALScraper,
    "internet_archive": InternetArchiveScraper,
    "dataverse": DataverseScraper,
    "core": CoreScraper,
    "github": GitHubScraper,
}
SOURCE_ORDER = ["figshare", "zenodo", "hal", "core", "github", "dataverse", "internet_archive"]


def run_scrapers(sources: list, target: int, deps: dict, verbose: bool) -> dict:
    """Run scrapers in order until `target` files are collected."""
    all_stats = {}
    total_downloaded = 0

    n = len(sources)
    base_alloc = target // n

    for i, source in enumerate(sources):
        if total_downloaded >= target:
            break

        alloc = target - total_downloaded if i == n - 1 else base_alloc
        alloc = max(alloc, 1)

        print(f"\n{'=' * 60}")
        print(f"🎯  SOURCE: {source.upper()}  (target: {alloc} files)")
        print(f"{'=' * 60}")

        try:
            cls = SCRAPER_MAP[source]
            scraper = cls(
                metadata_store=deps["metadata_store"],
                verification_pipeline=deps["verification_pipeline"],
                audit_logger=deps["audit_logger"],
            )
            scraper.scrape(max_docs=alloc)
            stats = scraper.get_stats()
            all_stats[source] = stats
            total_downloaded += stats["downloaded"]
        except Exception as e:
            print(f"  ❌ Scraper error for {source}: {e}")
            if verbose:
                import traceback
                traceback.print_exc()
            all_stats[source] = {"downloaded": 0, "delivered": 0, "rejected": 0, "skipped": 0, "failed": 0}
            continue

        print(f"\n  ✅ {source}: {stats['downloaded']} downloaded, {stats['delivered']} deliverable")
        print(f"  📦 Total downloaded so far: {total_downloaded}/{target}")

    return all_stats


def main():
    parser = argparse.ArgumentParser(
        description="PPT Document Scraper — Criteria-Compliant Version",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-t", "--target", type=int, default=3000, help="Target number of PPT files (default: 3000)")
    parser.add_argument("-s", "--source", choices=["all"] + list(SCRAPER_MAP.keys()), default="all", help="Source to scrape")
    parser.add_argument("--batch-size", type=int, default=500, help="Max files per delivery batch (default: 500)")
    parser.add_argument("--skip-quality-check", action="store_true", help="Skip the slow PPTX XML quality assessment")
    parser.add_argument("--dry-run", action="store_true", help="Download and verify, but don't package final delivery batches")
    parser.add_argument("--resume", action="store_true", help="Skip files already present in downloaded_ppts/")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging")
    args = parser.parse_args()

    setup_logging(args.verbose)

    # 1. Configuration
    config = get_config()
    config.target = args.target
    config.batch_size = args.batch_size
    config.skip_quality_check = args.skip_quality_check
    config.dry_run = args.dry_run
    config.resume = args.resume
    config.verbose = args.verbose
    config.ensure_dirs()

    # 2. Dependency Injection
    domain_filter = DomainFilter()
    geo_filter = GeoFilter()
    compliance_filter = ComplianceFilter(domain_filter, geo_filter)
    validator = FileValidator(
        min_size_bytes=config.min_file_size_bytes,
        min_slides=config.min_slide_count,
        max_slides=config.max_slide_count,
    )
    quality_assessor = QualityAssessor()
    verification_pipeline = VerificationPipeline(
        validator=validator,
        compliance_filter=compliance_filter,
        quality_assessor=quality_assessor,
        skip_quality=config.skip_quality_check,
    )
    metadata_store = MetadataStore(sidecar_ext=config.metadata_sidecar_ext)
    audit_logger = AuditLogger(config.audit_log_path)
    delivery_manager = DeliveryManager(config.delivery_dir, metadata_store)

    deps = {
        "metadata_store": metadata_store,
        "verification_pipeline": verification_pipeline,
        "audit_logger": audit_logger,
        "delivery_manager": delivery_manager,
    }

    sources = SOURCE_ORDER if args.source == "all" else [args.source]

    print("\n" + "=" * 60)
    print("📊  PPT DOCUMENT SCRAPER v3.0 (CRITERIA COMPLIANT)")
    print("=" * 60)
    print(f"  Target:    {args.target} files")
    print(f"  Sources:   {', '.join(sources)}")
    print(f"  Quality:   {'SKIPPED' if args.skip_quality_check else 'ENABLED'}")
    print(f"  Dry run:   {args.dry_run}")
    print("=" * 60)

    # Resume pre-loading
    if args.resume:
        BaseScraper.preload_seen_from_dir(config.download_dir)

    # 3. Scraping Phase
    all_stats = run_scrapers(sources, args.target, deps, args.verbose)

    # 4. Packaging Phase
    print("\n" + "=" * 60)
    print("📦  PACKAGING DELIVERY BATCHES")
    print("=" * 60)
    
    # Run delivery manager to package all DELIVER status files
    batch_id = delivery_manager.package_delivery(config.download_dir, dry_run=args.dry_run)
    if batch_id:
        print(f"  ✅ Packaged delivery batch: {batch_id}")
    else:
        print("  ⚠️ No files were eligible for delivery packaging.")

    # 5. Summary
    print("\n" + "=" * 60)
    print("📈  FINAL PIPELINE SUMMARY")
    print("=" * 60)
    
    total_dl = sum(s.get("downloaded", 0) for s in all_stats.values())
    total_del = sum(s.get("delivered", 0) for s in all_stats.values())
    total_rej = sum(s.get("rejected", 0) for s in all_stats.values())
    total_rev = sum(s.get("review", 0) for s in all_stats.values())
    
    for src, stats in all_stats.items():
        print(f"  {src.upper():20s}  ✓ DL: {stats.get('downloaded', 0):4d}  "
              f"📦 DELIVER: {stats.get('delivered', 0):4d}  "
              f"❌ REJECT: {stats.get('rejected', 0):4d}")

    print(f"\n{'=' * 60}")
    print(f"  📥 Total Downloaded : {total_dl}")
    print(f"  ✅ Total Deliverable: {total_del}")
    print(f"  ⚠️ Total Review     : {total_rev}")
    print(f"  ❌ Total Rejected   : {total_rej}")
    print(f"  📝 Audit Log        : {config.audit_log_path.absolute()}")
    print(f"{'=' * 60}")

    if total_dl == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
