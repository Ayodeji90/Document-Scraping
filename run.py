#!/usr/bin/env python3
"""
PPT Document Scraper — orchestration entry point.

Downloads up to 1,500 .ppt/.pptx files from academic sources
(Figshare, Zenodo, HAL, Internet Archive) and optionally uploads
them to Google Drive.

Usage:
    python run.py                        # all sources, target 1500
    python run.py -t 500 -s figshare     # single source
    python run.py --dry-run              # test without uploading
    python run.py --no-upload            # download only
    python run.py --resume               # skip already-downloaded files
    python run.py -v                     # verbose logging
"""
import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

from src.scraper.base import BaseScraper
from src.scraper.figshare import FigshareScraper
from src.scraper.hal import HALScraper
from src.scraper.internet_archive import InternetArchiveScraper
from src.scraper.zenodo import ZenodoScraper
from src.storage.gdrive import GoogleDriveUploader

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        level=level,
        stream=sys.stderr,
    )

# ---------------------------------------------------------------------------
# Google Drive helpers
# ---------------------------------------------------------------------------

def setup_gdrive() -> "GoogleDriveUploader | None":
    print("\n🔐 Authenticating with Google Drive…")
    uploader = GoogleDriveUploader()
    try:
        uploader.authenticate()
        uploader.create_folder()
        return uploader
    except FileNotFoundError as e:
        print(f"  ❌ {e}")
        print("  ⚠️  See GOOGLE_SETUP.md to create credentials.json")
        return None


def upload_batch(uploader, files, dry_run: bool):
    if dry_run:
        print(f"\n📤 [DRY RUN] Would upload {len(files)} file(s)")
        return
    if not uploader:
        print("\n⚠️  Google Drive not configured — skipping upload")
        return

    print(f"\n📤 Uploading {len(files)} file(s) to Google Drive…")
    ok, fail = 0, 0
    for fp in tqdm(files, unit="file", desc="Uploading"):
        try:
            uploader.upload_file(fp, {"scraped_date": datetime.now().isoformat()})
            ok += 1
        except Exception as e:
            tqdm.write(f"  ❌ Upload failed: {fp.name}: {e}")
            fail += 1
    print(f"  ✅ {ok} uploaded, {fail} failed")

# ---------------------------------------------------------------------------
# Scraper runners
# ---------------------------------------------------------------------------

SCRAPER_MAP = {
    "figshare": FigshareScraper,
    "zenodo": ZenodoScraper,
    "hal": HALScraper,
    "internet_archive": InternetArchiveScraper,
}

SOURCE_ORDER = ["figshare", "hal", "internet_archive", "zenodo"]


def build_scraper(name: str, delay: tuple) -> BaseScraper:
    cls = SCRAPER_MAP[name]
    return cls(
        download_dir="downloaded_ppts",
        api_delay=(delay[0] * 0.25, delay[0] * 0.75),
        download_delay=delay,
    )


def run_scrapers(sources: list, target: int, delay: tuple, verbose: bool) -> tuple:
    """
    Run scrapers in order until `target` files are collected.
    Returns (all_files, all_stats).
    """
    all_files = []
    all_stats = {}

    # Distribute target evenly; last source gets the remainder
    n = len(sources)
    base_alloc = target // n

    for i, source in enumerate(sources):
        if len(all_files) >= target:
            break

        # Give leftover slots to the last source
        alloc = target - len(all_files) if i == n - 1 else base_alloc
        alloc = max(alloc, 1)

        print(f"\n{'=' * 60}")
        print(f"🎯  SOURCE: {source.upper()}  (target: {alloc} files)")
        print(f"{'=' * 60}")

        try:
            scraper = build_scraper(source, delay)
            files = scraper.scrape(max_docs=alloc)
            all_files.extend(files)
            all_stats[source] = scraper.get_stats()
        except Exception as e:
            print(f"  ❌ Scraper error for {source}: {e}")
            if verbose:
                import traceback
                traceback.print_exc()
            all_stats[source] = {"downloaded": 0, "skipped": 0, "failed": 0}
            continue

        print(f"\n  ✅ {source}: {all_stats[source]['downloaded']} downloaded so far")
        print(f"  📦 Total collected: {len(all_files)}/{target}")

    return all_files, all_stats

# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def save_manifest(args, all_files, all_stats):
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    path = logs_dir / f"manifest_{datetime.now():%Y%m%d_%H%M%S}.json"

    total_dl = sum(s.get("downloaded", 0) for s in all_stats.values())
    total_sk = sum(s.get("skipped", 0) for s in all_stats.values())
    total_fl = sum(s.get("failed", 0) for s in all_stats.values())

    manifest = {
        "timestamp": datetime.now().isoformat(),
        "config": vars(args),
        "summary": {
            "downloaded": total_dl,
            "skipped": total_sk,
            "failed": total_fl,
            "total_files": len(all_files),
        },
        "by_source": all_stats,
        "files": [str(f) for f in all_files],
    }
    with open(path, "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"\n📝 Manifest: {path}")
    return path, manifest["summary"]

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="PPT Document Scraper — downloads .ppt/.pptx files from academic sources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-t", "--target", type=int, default=1500,
        help="Target number of PPT files (default: 1500)",
    )
    parser.add_argument(
        "-s", "--source",
        choices=["all"] + list(SCRAPER_MAP.keys()),
        default="all",
        help="Source to scrape (default: all)",
    )
    parser.add_argument(
        "--delay-min", type=float, default=1.5,
        help="Min seconds between file downloads (default: 1.5)",
    )
    parser.add_argument(
        "--delay-max", type=float, default=3.5,
        help="Max seconds between file downloads (default: 3.5)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Download files but do not upload to Google Drive",
    )
    parser.add_argument(
        "--no-upload", action="store_true",
        help="Download only, skip Google Drive upload entirely",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Skip files already present in downloaded_ppts/",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose debug logging",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    delay = (args.delay_min, args.delay_max)
    sources = SOURCE_ORDER if args.source == "all" else [args.source]

    print("\n" + "=" * 60)
    print("📊  PPT DOCUMENT SCRAPER v2.0")
    print("=" * 60)
    print(f"  Target:    {args.target} files")
    print(f"  Sources:   {', '.join(sources)}")
    print(f"  Delay:     {args.delay_min}–{args.delay_max}s (downloads)")
    print(f"  Dry run:   {args.dry_run}")
    print(f"  Resume:    {args.resume}")
    print("=" * 60)

    # Resume: pre-populate seen-files from disk
    if args.resume:
        BaseScraper.preload_seen_from_dir(Path("downloaded_ppts"))

    # Google Drive setup (unless skipping)
    uploader = None
    if not args.no_upload and not args.dry_run:
        uploader = setup_gdrive()

    # Run scrapers
    all_files, all_stats = run_scrapers(sources, args.target, delay, args.verbose)

    # Summary
    print("\n" + "=" * 60)
    print("📈  FINAL SUMMARY")
    print("=" * 60)
    for src, stats in all_stats.items():
        print(f"  {src.upper():20s}  ✓ {stats.get('downloaded', 0):4d}  "
              f"⛔ {stats.get('skipped', 0):4d}  ❌ {stats.get('failed', 0):4d}")

    _, summary = save_manifest(args, all_files, all_stats)

    print(f"\n{'=' * 60}")
    print(f"  📦 Total downloaded : {summary['downloaded']}")
    print(f"  ⛔ Total skipped    : {summary['skipped']}")
    print(f"  ❌ Total failed     : {summary['failed']}")

    if summary["downloaded"] == 0:
        print("\n  ⚠️  WARNING: Zero files downloaded.")
        print("     Check network connectivity and run with -v for details.")
    print(f"{'=' * 60}")

    # Upload
    if not args.no_upload:
        upload_batch(uploader, all_files, dry_run=args.dry_run)

    print(f"\n🏁 Done — files saved to: {Path('downloaded_ppts').absolute()}")

    # Non-zero exit if nothing was collected
    if summary["downloaded"] == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
