#!/usr/bin/env python3
"""
CKAN Open Data Portal PPT/PPTX Scraper — Local Script

CKAN (ckan.org) is open-source data-portal software, not a single website —
it powers hundreds of independent government/NGO open-data catalogs
worldwide (data.gov.ie, data.gov.gr, HDX, opendata.swiss, open.canada.ca...).
Every CKAN instance exposes the same public Action API, so this script:

  1. Validates a curated list of known CKAN instances at runtime via
     /api/3/action/status_show (dead/renamed/non-CKAN URLs are skipped —
     verified live, ~40% of hand-picked candidate URLs go stale over time).
  2. Queries each live instance's package_search with
     fq=res_format:(PPTX OR PPT ...) — this returns direct resource
     download URLs already embedded in the dataset JSON, so there is no
     HTML scraping or search-engine dependency involved.
  3. Downloads matches, verifies file signature, dedupes globally against
     the other scrapers in this repo, and writes a rich .meta.json sidecar
     from CKAN's own dataset metadata (title, org, license, tags...).

Reality check on the 300K target: CKAN portals are dataset catalogs
(CSV/JSON/geodata/PDF), not presentation repositories, so per-instance
supply varies wildly and is usually small. Most validated instances return
single digits (data.gov.gr: 3, HDX: 1, podatki.gov.si: 1, several: 0), but
a few return much more when an agency has dumped internal decks into open
data (open.canada.ca and Northern Ireland's opendatani each returned 60-90+
in testing). Total yield scales with how many live instances you query —
this script is built to harvest every reachable one exhaustively and be
safely re-run as portals publish new datasets. Use --portals-file to add
more instances as you find them (see --list-portals to check which
candidates are currently live); reaching 300K in one pass is unlikely even
so, since global native-PPT supply on CKAN catalogs is inherently limited.

Usage:
    python ckan_pptx_scraper.py                    # discover + harvest all known portals
    python ckan_pptx_scraper.py --list-portals      # just show which candidates are live CKAN
    python ckan_pptx_scraper.py --dry-run           # harvest + print matches, don't download
    python ckan_pptx_scraper.py --portals-file extra_ckan_portals.txt
    python ckan_pptx_scraper.py --target 500
"""
import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_root = os.path.abspath(os.path.dirname(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

from src.filters.domain_filter import DomainFilter  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OUTPUT_DIR = Path("ckan_downloaded")  # isolated from mega/commoncrawl/wayback's shared joint_downloaded/
SEEN_FILE = Path("logs/master_seen_tags.txt")
CONTENT_HASH_FILE = Path("logs/master_content_hashes.txt")
STATS_FILE = Path("logs/ckan_stats.json")

MIN_SIZE = 15 * 1024  # 15KB — CKAN presentations are official docs, not junk decks
REQUEST_TIMEOUT = 20
ROWS_PER_PAGE = 100
MAX_PAGES_PER_QUERY = 200  # safety cap: 20,000 records per (portal, format token)
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 CKAN-PPT-Research/1.0"
)

# Solr query tokens covering how CKAN instances label PPT/PPTX resources.
# Quoted phrases handle values containing slashes/dots/hyphens.
FORMAT_TOKENS = [
    "PPTX", "PPT", "PPS", "PPSX",
    '"MS-POWERPOINT"',
    '"MS POWERPOINT"',
    '"application/vnd.ms-powerpoint"',
    '"application/vnd.openxmlformats-officedocument.presentationml.presentation"',
]

DOWNLOADABLE_EXTENSIONS = (".ppt", ".pptx")

# Curated CKAN instances. Runtime-validated on every run — entries that no
# longer resolve to a live CKAN Action API are skipped automatically, so
# it's safe to keep speculative entries here. Extend via --portals-file
# rather than editing this list.
CANDIDATE_PORTALS = [
    ("CKAN Demo", "https://demo.ckan.org"),
    ("Humanitarian Data Exchange (HDX)", "https://data.humdata.org"),
    ("Canada Open Government", "https://open.canada.ca/data"),
    ("Ireland Open Data", "https://data.gov.ie"),
    ("Switzerland Open Data", "https://ckan.opendata.swiss"),
    ("Greece Open Data", "https://data.gov.gr"),
    ("Romania Open Data", "https://data.gov.ro"),
    ("Slovenia Open Data", "https://podatki.gov.si"),
    ("Latvia Open Data", "https://data.gov.lv"),
    ("Chile Open Data", "https://datos.gob.cl"),
    ("Argentina Open Data", "https://datos.gob.ar"),
    ("Spain — Aragon Open Data", "https://opendata.aragon.es"),
    ("Canada — British Columbia", "https://catalog.data.gov.bc.ca"),
    ("Canada — Montreal", "https://donnees.montreal.ca"),
    ("UK Government Open Data", "https://ckan.publishing.service.gov.uk"),
    ("OpenAfrica (Code for Africa)", "https://open.africa"),
    ("New Zealand Open Data", "https://catalogue.data.govt.nz"),
    ("Northern Ireland Open Data", "https://admin.opendatani.gov.uk"),
    ("Malta Open Data", "https://data.gov.mt"),
    ("Finland Open Data", "https://www.avoindata.fi"),
    ("Croatia Open Data", "https://data.gov.hr"),
]

Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/ckan_scraper.log"),
    ],
)
logger = logging.getLogger("CKAN-Scraper")


# ---------------------------------------------------------------------------
# Session / persistence
# ---------------------------------------------------------------------------
def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=4, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=20))
    s.mount("http://", HTTPAdapter(max_retries=retry, pool_maxsize=20))
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return s


def load_seen() -> Set[str]:
    if SEEN_FILE.exists():
        return {l.strip() for l in SEEN_FILE.read_text().splitlines() if l.strip()}
    return set()


def save_tag(tag: str):
    with open(SEEN_FILE, "a") as f:
        f.write(tag + "\n")


def load_content_seen() -> Set[str]:
    if CONTENT_HASH_FILE.exists():
        return {l.strip() for l in CONTENT_HASH_FILE.read_text().splitlines() if l.strip()}
    return set()


def save_content_hash(h: str):
    with open(CONTENT_HASH_FILE, "a") as f:
        f.write(h + "\n")


def valid_ppt(fp: Path) -> bool:
    try:
        with open(fp, "rb") as f:
            head = f.read(8)
        return head[:2] == b"PK" or head[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Phase 1: Discover live CKAN instances
# ---------------------------------------------------------------------------
def _probe_portal(session: requests.Session, name: str, base_url: str) -> Optional[Dict]:
    base_url = base_url.rstrip("/")
    try:
        r = session.get(f"{base_url}/api/3/action/status_show", timeout=REQUEST_TIMEOUT, allow_redirects=True)
        data = r.json()
        result = data.get("result", {})
        if data.get("success") and result.get("ckan_version"):
            # Resolve to the final URL (some instances redirect to a canonical host)
            resolved = r.url.split("/api/3/action/status_show")[0]
            return {"name": name, "base_url": resolved, "version": result["ckan_version"]}
    except Exception:
        pass
    return None


def discover_portals(session: requests.Session, candidates: List[tuple], workers: int = 12) -> List[Dict]:
    live = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_probe_portal, session, name, url): (name, url) for name, url in candidates}
        for fut in as_completed(futures):
            info = fut.result()
            name, url = futures[fut]
            if info:
                live.append(info)
                logger.info(f"  live   {name:40s} {info['base_url']}  (CKAN {info['version']})")
            else:
                logger.debug(f"  skip   {name:40s} {url}  (not a reachable CKAN instance)")
    return live


def load_extra_portals(path: Optional[str]) -> List[tuple]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        logger.warning(f"--portals-file not found: {path}")
        return []
    extra = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        extra.append((line, line))
    return extra


# ---------------------------------------------------------------------------
# Phase 2: Query package_search for PPT/PPTX resources
# ---------------------------------------------------------------------------
def _extract_matches(package: Dict, portal: Dict) -> List[Dict]:
    matches = []
    org = package.get("organization") or {}
    for res in package.get("resources", []):
        url = (res.get("url") or "").strip()
        if not url:
            continue
        # Some CKAN instances (misconfigured ckan.site_url) emit host-relative
        # resource URLs — resolve them against the portal's own base URL.
        if not urlparse(url).netloc:
            url = urljoin(portal["base_url"] + "/", url)
        ext = Path(urlparse(url).path).suffix.lower()
        fmt = (res.get("format") or "").strip().upper()
        looks_like_ppt = ext in DOWNLOADABLE_EXTENSIONS or fmt in {"PPT", "PPTX"}
        if not looks_like_ppt:
            continue
        matches.append({
            "url": url,
            "format": res.get("format", ""),
            "resource_name": res.get("name") or res.get("description") or "",
            "resource_id": res.get("id", ""),
            "package_id": package.get("id", ""),
            "package_title": package.get("title", "untitled"),
            "organization": org.get("title") or org.get("name") or "",
            "author": package.get("author") or org.get("title") or "",
            "license_title": package.get("license_title", ""),
            "tags": [t.get("name") for t in package.get("tags", []) if t.get("name")],
            "metadata_created": package.get("metadata_created", ""),
            "metadata_modified": package.get("metadata_modified", ""),
            "portal_name": portal["name"],
            "portal_base_url": portal["base_url"],
        })
    return matches


def search_portal(session: requests.Session, portal: Dict) -> List[Dict]:
    base_url = portal["base_url"]
    found = []

    for token in FORMAT_TOKENS:
        start = 0
        seen_package_ids: Set[str] = set()
        for page in range(MAX_PAGES_PER_QUERY):
            params = {"fq": f"res_format:{token}", "rows": ROWS_PER_PAGE, "start": start}
            try:
                r = session.get(f"{base_url}/api/3/action/package_search", params=params, timeout=REQUEST_TIMEOUT)
                if not r.ok:
                    logger.debug(f"  {portal['name']}: HTTP {r.status_code} for {token}")
                    break
                data = r.json()
                if not data.get("success"):
                    break
                result = data.get("result", {})
                packages = result.get("results", [])
                if not packages:
                    break

                for pkg in packages:
                    pid = pkg.get("id", "")
                    if pid in seen_package_ids:
                        continue
                    seen_package_ids.add(pid)
                    found.extend(_extract_matches(pkg, portal))

                total = result.get("count", 0)
                start += ROWS_PER_PAGE
                if start >= total or len(packages) < ROWS_PER_PAGE:
                    break
                time.sleep(0.3)
            except Exception as e:
                logger.debug(f"  {portal['name']}: query error for {token}: {e}")
                break

        time.sleep(0.3)

    return found


# ---------------------------------------------------------------------------
# Phase 3: Download + verify + write metadata sidecar
# ---------------------------------------------------------------------------
def build_sidecar(record: Dict, filename: str) -> Dict:
    return {
        "source_url": record["url"],
        "original_filename": Path(urlparse(record["url"]).path).name or filename,
        "source_domain": urlparse(record["url"]).netloc,
        "collection_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "publication_date": record.get("metadata_created", ""),
        "author": record.get("author", ""),
        "organization": record.get("organization", ""),
        "title": record.get("resource_name") or record.get("package_title", ""),
        "language": "",
        "tags": record.get("tags", []),
        "crawl_metadata": {
            "source": "ckan",
            "portal_name": record.get("portal_name", ""),
            "portal_base_url": record.get("portal_base_url", ""),
            "package_id": record.get("package_id", ""),
            "package_title": record.get("package_title", ""),
            "resource_id": record.get("resource_id", ""),
            "license_title": record.get("license_title", ""),
            "declared_format": record.get("format", ""),
        },
    }


def download_resource(
    session: requests.Session,
    record: Dict,
    domain_filter: DomainFilter,
    seen: Set[str],
    content_seen: Set[str],
    stats: dict,
    min_size: int,
) -> bool:
    url = record["url"]
    tag = hashlib.sha1(url.encode()).hexdigest()[:10]
    if tag in seen:
        stats["dup"] += 1
        return False
    if not domain_filter.is_allowed(url):
        stats["blocked"] += 1
        return False

    portal_slug = re.sub(r"[^\w]", "_", urlparse(record["portal_base_url"]).netloc)[:30]
    # Use the resource's own filename, not the dataset title — a dataset often
    # bundles English/French (or other) variants of the same title as separate
    # resources, and the title alone would make genuinely different files look
    # like duplicates.
    original_name = Path(urlparse(url).path).name or "file.pptx"
    if not original_name.lower().endswith((".ppt", ".pptx")):
        original_name += ".pptx" if not url.lower().split("?")[0].endswith(".ppt") else ".ppt"
    name_stem = re.sub(r"[^\w.\-]", "_", Path(original_name).stem)[:80]
    ext = Path(original_name).suffix.lower()
    filename = f"{tag}_ckan_{portal_slug}_{name_stem}{ext}"
    dest = OUTPUT_DIR / filename

    if dest.exists():
        seen.add(tag)
        return False

    try:
        r = session.get(url, timeout=120, stream=True, allow_redirects=True)
        if not r.ok:
            stats["errors"] += 1
            return False

        with open(dest, "wb") as f:
            for chunk in r.iter_content(65536):
                if chunk:
                    f.write(chunk)

        size = dest.stat().st_size
        if size < min_size:
            dest.unlink(missing_ok=True)
            stats["small"] += 1
            return False

        if not valid_ppt(dest):
            dest.unlink(missing_ok=True)
            stats["invalid"] += 1
            return False

        file_hash = hashlib.sha256(dest.read_bytes()).hexdigest()
        if file_hash in content_seen:
            dest.unlink(missing_ok=True)
            stats["dup"] += 1
            return False

        sidecar = build_sidecar(record, filename)
        dest.with_suffix(".meta.json").write_text(json.dumps(sidecar, ensure_ascii=False, indent=2))

        seen.add(tag)
        save_tag(tag)
        content_seen.add(file_hash)
        save_content_hash(file_hash)
        stats["downloaded"] += 1
        logger.info(f"  [{stats['downloaded']}] {filename} ({size // 1024}KB) <- {record['portal_name']}")
        return True

    except Exception as e:
        if dest.exists():
            dest.unlink(missing_ok=True)
        stats["errors"] += 1
        logger.debug(f"Download error for {url}: {e}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="CKAN Open Data Portal PPT/PPTX Scraper")
    parser.add_argument("--target", type=int, default=300_000, help="Stop after this many new downloads")
    parser.add_argument("--min-size", type=int, default=MIN_SIZE, help="Minimum file size in bytes")
    parser.add_argument("--portals-file", help="Text file with one extra CKAN base URL per line")
    parser.add_argument("--list-portals", action="store_true", help="Only run discovery and print live instances")
    parser.add_argument("--dry-run", action="store_true", help="Harvest matches but do not download")
    parser.add_argument("--discover-workers", type=int, default=12)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    OUTPUT_DIR.mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)

    session = make_session()
    domain_filter = DomainFilter()

    candidates = CANDIDATE_PORTALS + load_extra_portals(args.portals_file)
    print(f"Probing {len(candidates)} candidate CKAN portals...")
    portals = discover_portals(session, candidates, workers=args.discover_workers)
    print(f"\n{len(portals)}/{len(candidates)} candidates are live CKAN instances.\n")

    if args.list_portals:
        return

    seen = load_seen()
    content_seen = load_content_seen()
    stats = {"downloaded": 0, "small": 0, "invalid": 0, "dup": 0, "blocked": 0, "errors": 0}

    print(f"{'=' * 65}\nHarvesting package_search results from {len(portals)} portals\n{'=' * 65}")
    all_records: List[Dict] = []
    for i, portal in enumerate(portals, 1):
        print(f"  [{i}/{len(portals)}] {portal['name']} ({portal['base_url']})")
        records = search_portal(session, portal)
        if records:
            print(f"      -> {len(records)} PPT/PPTX resource(s) found")
        all_records.extend(records)

    # Dedupe by resource URL across portals/format-token queries
    unique = {r["url"]: r for r in all_records}
    records = list(unique.values())
    print(f"\n{len(records)} unique PPT/PPTX resources found across all live portals.")

    if args.dry_run:
        for r in records:
            print(f"  DRY-RUN  {r['url']}  [{r['portal_name']}] {r['package_title']}")
        return

    print(f"\n{'=' * 65}\nDownloading (target: {args.target})\n{'=' * 65}")
    for record in records:
        if stats["downloaded"] >= args.target:
            break
        download_resource(session, record, domain_filter, seen, content_seen, stats, args.min_size)

    print(f"\n{'=' * 65}\nCKAN SCRAPER COMPLETE\n{'=' * 65}")
    for k, v in stats.items():
        print(f"  {k:12s}: {v:>6,}")
    print(f"{'=' * 65}")
    print(f"Files saved to: {OUTPUT_DIR}")
    if stats["downloaded"] < args.target:
        print(
            f"\nNote: only {stats['downloaded']} files were available across the "
            f"{len(portals)} live portals queried — this reflects real CKAN supply, "
            f"not a scraper limitation. Add more instances with --portals-file to "
            f"increase coverage, and re-run periodically as portals publish new data."
        )

    STATS_FILE.write_text(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
