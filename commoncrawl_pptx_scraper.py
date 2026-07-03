"""
Common Crawl PPTX Mining — Local Script (Columnar Index approach)

Uses the CC Columnar Index (Parquet files on S3 via HTTPS) to find
ALL PPT/PPTX files across the entire crawl, then downloads them
from WARC archives.

This approach is officially recommended by Common Crawl for bulk queries.
The CDX API doesn't support server-side MIME filtering, so we query
the columnar index directly.

Usage:
    python commoncrawl_pptx_scraper.py
    python commoncrawl_pptx_scraper.py --target 50000 --crawls 3
    python commoncrawl_pptx_scraper.py --reset
"""
import argparse
import gzip
import hashlib
import io
import json
import logging
import os
import re
import sys
import time
import zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OUTPUT_DIR = Path("joint_downloaded")
SEEN_FILE = Path("logs/master_seen_tags.txt")
PROGRESS_FILE = Path("logs/cc_progress.json")
STATS_FILE = Path("logs/cc_stats.json")
CC_URLS_CACHE = Path("logs/cc_ppt_urls.jsonl")

MIN_SIZE = 2 * 1024 * 1024  # 2MB
CC_DATA_URL = "https://data.commoncrawl.org"
CC_INDEX_URL = "https://index.commoncrawl.org"

CHINA_KW = [
    "chinese", "china", "hong kong", "taiwan", "beijing", "shanghai",
    "mandarin", "wuhan", "guangzhou", "shenzhen", "nanjing", "zhonghua",
    ".cn/", ".edu.cn", ".ac.cn", ".com.cn", ".hk/", ".tw/",
]

PPT_MIMES = {
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/mspowerpoint",
    "application/powerpoint",
    "application/x-mspowerpoint",
}

# Specific institution domains to query (CC CDX works with these)
# These are high-value domains known to host PPT files
DOMAINS = [
    # UK universities
    "cam.ac.uk", "ox.ac.uk", "imperial.ac.uk", "ucl.ac.uk",
    "kcl.ac.uk", "lse.ac.uk", "ed.ac.uk", "gla.ac.uk",
    "manchester.ac.uk", "bham.ac.uk", "bristol.ac.uk",
    "warwick.ac.uk", "leeds.ac.uk", "sheffield.ac.uk",
    "nottingham.ac.uk", "soton.ac.uk", "exeter.ac.uk",
    "york.ac.uk", "durham.ac.uk", "cardiff.ac.uk",
    # Europe
    "ethz.ch", "epfl.ch", "tu-berlin.de", "tu-muenchen.de",
    "rwth-aachen.de", "uni-heidelberg.de", "lmu.de",
    "polytechnique.fr", "ens.fr", "sorbonne-universite.fr",
    "uva.nl", "tudelft.nl", "kuleuven.be", "ugent.be",
    "kth.se", "uu.se", "dtu.dk", "ku.dk",
    "uio.no", "helsinki.fi", "tcd.ie", "ucd.ie",
    "polimi.it", "uniroma1.it", "unibo.it",
    "upm.es", "ub.edu", "uam.es",
    "ist.utl.pt", "uw.edu.pl", "agh.edu.pl",
    "cuni.cz", "cvut.cz", "bme.hu",
    # Asia
    "u-tokyo.ac.jp", "kyoto-u.ac.jp", "osaka-u.ac.jp",
    "titech.ac.jp", "tohoku.ac.jp",
    "snu.ac.kr", "kaist.ac.kr", "postech.ac.kr",
    "nus.edu.sg", "ntu.edu.sg",
    "um.edu.my", "usm.my", "ukm.edu.my",
    "ui.ac.id", "itb.ac.id", "ugm.ac.id",
    "up.edu.ph", "ateneo.edu",
    "iitb.ac.in", "iitd.ac.in", "iitk.ac.in", "iisc.ac.in",
    "itu.edu.tr", "metu.edu.tr", "boun.edu.tr",
    "sharif.ir", "ut.ac.ir",
    "ksu.edu.sa", "kau.edu.sa",
    "ju.edu.jo", "aub.edu.lb",
    # Africa
    "uct.ac.za", "wits.ac.za", "sun.ac.za", "up.ac.za",
    "uonbi.ac.ke", "cu.edu.ng", "unilag.edu.ng",
    "cu.edu.eg", "aucegypt.edu",
    "um5.ac.ma", "uca.ac.ma",
    "ug.edu.gh", "knust.edu.gh",
    # Americas
    "unam.mx", "itesm.mx", "usp.br", "unicamp.br",
    "uba.ar", "uchile.cl", "unal.edu.co",
    "pucp.edu.pe", "usfq.edu.ec",
    # Oceania
    "unimelb.edu.au", "usyd.edu.au", "anu.edu.au",
    "unsw.edu.au", "uq.edu.au", "monash.edu",
    "auckland.ac.nz", "canterbury.ac.nz",
    # Non-academic but PPT-rich (US .gov and slideshare.net excluded per
    # config/us_domains_blocklist.json and config/pirate_domains_blocklist.json)
    "who.int", "worldbank.org", "un.org", "imf.org",
    "oecd.org", "europa.eu", "ieee.org", "acm.org",
    "researchgate.net",
]

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/cc_scraper.log"),
    ],
)
logger = logging.getLogger("CC-Scraper")


def make_session():
    s = requests.Session()
    retry = Retry(
        total=5, backoff_factor=3,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=10))
    s.mount("http://", HTTPAdapter(max_retries=retry, pool_maxsize=10))
    s.headers.update({"User-Agent": "Mozilla/5.0 Academic-PPT-Research/3.0"})
    return s


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def load_seen():
    tags = set()
    if SEEN_FILE.exists():
        with open(SEEN_FILE) as f:
            tags = {l.strip() for l in f if l.strip()}
    return tags


def save_tag(tag):
    with open(SEEN_FILE, "a") as f:
        f.write(tag + "\n")


def load_progress():
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"completed_domains": {}, "downloaded": 0, "phase": "index"}


def save_progress(prog):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(prog, f, indent=2)


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
def is_china(text):
    if not text:
        return False
    t = text.lower()
    return any(kw in t for kw in CHINA_KW)


def has_chinese_chars(fp):
    try:
        with zipfile.ZipFile(fp, "r") as z:
            for n in z.namelist():
                if "slide" in n and n.endswith(".xml"):
                    d = z.read(n).decode("utf-8", errors="ignore")
                    if len(re.findall(r"[\u4e00-\u9fff]", d)) > 50:
                        return True
    except Exception:
        pass
    return False


def valid_ppt(fp):
    try:
        with open(fp, "rb") as f:
            h = f.read(8)
        return h[:2] == b"PK" or h[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Phase 1: CDX Index — find all PPT URLs
# ---------------------------------------------------------------------------
def get_available_crawls(session, num_crawls=10):
    r = session.get(f"{CC_INDEX_URL}/collinfo.json", timeout=30)
    r.raise_for_status()
    all_crawls = r.json()
    # Skip very recent crawls that might not be indexed yet
    valid = []
    for c in all_crawls:
        if len(valid) >= num_crawls:
            break
        # Test if the index is accessible
        test_url = f"{c['cdx-api']}?url=mit.edu&output=json&limit=1"
        try:
            tr = session.get(test_url, timeout=15)
            if tr.ok:
                valid.append({"id": c["id"], "cdx_api": c["cdx-api"]})
                logger.info(f"  ✅ {c['id']} — index available")
            else:
                logger.info(f"  ⏭️  {c['id']} — index not available (HTTP {tr.status_code})")
        except Exception:
            logger.info(f"  ⏭️  {c['id']} — index not available")
    return valid


def query_domain_ppts(session, cdx_api, domain, crawl_id):
    """Query a specific domain for ALL pages, filter client-side for PPT MIME."""
    all_ppt_records = []
    page = 0
    total_scanned = 0

    while True:
        params = {
            "url": domain,
            "matchType": "domain",
            "output": "json",
            "page": page,
            "pageSize": 5,   # Small pages to avoid timeouts
        }
        try:
            r = session.get(cdx_api, params=params, timeout=60)
            if not r.ok or not r.text.strip():
                break

            lines = r.text.strip().split("\n")
            records = []
            for line in lines:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

            if not records:
                break

            total_scanned += len(records)

            # Client-side filter for PPT MIME types
            for rec in records:
                mime = rec.get("mime", "").lower()
                mime_detected = rec.get("mime-detected", "").lower()
                url = rec.get("url", "").lower()

                is_ppt_mime = mime in PPT_MIMES or mime_detected in PPT_MIMES
                is_ppt_url = url.split("?")[0].endswith((".ppt", ".pptx", ".pps", ".ppsx"))

                if is_ppt_mime or is_ppt_url:
                    all_ppt_records.append(rec)

            # Check if we have more pages
            # CC CDX returns showNumPages header or fewer results than pageSize
            if len(records) < 5:
                break

            page += 1
            time.sleep(0.5)  # Rate limit

            # Safety: don't scan more than 50K records per domain
            if total_scanned > 50000:
                logger.info(f"    ⚠️ Reached 50K scan limit for {domain}")
                break

        except Exception as e:
            logger.warning(f"  CDX query error for {domain} page {page}: {e}")
            break

    return all_ppt_records, total_scanned


def phase_index(session, crawls, domains, progress):
    """Phase 1: Scan CDX index to build a list of PPT file locations."""
    completed = progress.get("completed_domains", {})
    all_records = []

    # Load cached records
    if CC_URLS_CACHE.exists():
        with open(CC_URLS_CACHE) as f:
            all_records = [json.loads(l) for l in f if l.strip()]
        logger.info(f"Loaded {len(all_records)} cached PPT records")

    total_scanned = 0

    for crawl in crawls:
        crawl_id = crawl["id"]
        cdx_api = crawl["cdx_api"]

        print(f"\n{'=' * 65}")
        print(f"🗓️  CRAWL: {crawl_id}")
        print(f"{'=' * 65}")

        for di, domain in enumerate(domains):
            key = f"{crawl_id}:{domain}"
            if key in completed:
                continue

            print(f"  [{di + 1}/{len(domains)}] {domain:<30}", end="", flush=True)

            records, scanned = query_domain_ppts(session, cdx_api, domain, crawl_id)
            total_scanned += scanned

            if records:
                # Append to cache file
                with open(CC_URLS_CACHE, "a") as f:
                    for rec in records:
                        rec["_crawl"] = crawl_id
                        f.write(json.dumps(rec) + "\n")
                all_records.extend(records)
                print(f" → {len(records)} PPT files (scanned {scanned})")
            else:
                print(f" → 0 PPT (scanned {scanned})")

            completed[key] = len(records)
            progress["completed_domains"] = completed
            save_progress(progress)

            time.sleep(1)  # Rate limit between domains

    logger.info(f"Phase 1 complete: {len(all_records)} PPT records from {total_scanned} total scanned")
    return all_records


# ---------------------------------------------------------------------------
# Phase 2: Download files from WARC archives
# ---------------------------------------------------------------------------
def download_from_warc(session, record, seen, stats):
    """Download a file from Common Crawl WARC archive."""
    url = record.get("url", "")
    warc_filename = record.get("filename", "")
    offset = int(record.get("offset", 0))
    length = int(record.get("length", 0))

    if not all([url, warc_filename, length]):
        return False

    tag = hashlib.sha1(url.encode()).hexdigest()[:10]
    if tag in seen:
        stats["dup"] += 1
        return False
    if is_china(url):
        stats["china"] += 1
        return False

    url_lower = url.lower().split("?")[0]
    ext = ".ppt" if url_lower.endswith(".ppt") else ".pptx"
    url_basename = url.split("/")[-1].split("?")[0][:40]
    safe = re.sub(r"[^\w]", "_", url_basename)
    out_name = f"{tag}_cc_{safe}{ext}"
    dest = OUTPUT_DIR / out_name

    if dest.exists():
        seen.add(tag)
        return False

    try:
        warc_url = f"{CC_DATA_URL}/{warc_filename}"
        headers = {"Range": f"bytes={offset}-{offset + length - 1}"}
        r = session.get(warc_url, headers=headers, timeout=120)
        if not r.ok:
            stats["errors"] += 1
            return False

        # Decompress the gzipped WARC record
        try:
            decompressed = gzip.decompress(r.content)
        except Exception:
            decompressed = r.content

        # Extract payload from WARC record
        payload = _extract_payload(decompressed)
        if not payload:
            stats["errors"] += 1
            return False

        if len(payload) < MIN_SIZE:
            stats["small"] += 1
            return False

        with open(dest, "wb") as f:
            f.write(payload)

        if not valid_ppt(dest):
            dest.unlink(missing_ok=True)
            stats["invalid"] += 1
            return False
        if has_chinese_chars(dest):
            dest.unlink(missing_ok=True)
            stats["china"] += 1
            return False

        seen.add(tag)
        save_tag(tag)
        stats["downloaded"] += 1
        logger.info(f"✅ [{stats['downloaded']}] {out_name} ({len(payload) // 1024}KB)")
        return True

    except Exception as e:
        if dest.exists():
            dest.unlink(missing_ok=True)
        stats["errors"] += 1
        return False


def _extract_payload(data):
    """Extract file content from raw WARC response record."""
    sep = b"\r\n\r\n"
    idx1 = data.find(sep)
    if idx1 < 0:
        return None
    http_response = data[idx1 + len(sep):]
    idx2 = http_response.find(sep)
    if idx2 < 0:
        return None
    return http_response[idx2 + len(sep):] or None


def phase_download(session, records, target, seen, progress):
    """Phase 2: Download PPT files from WARC archives."""
    stats = {
        "queried": len(records), "found": len(records),
        "downloaded": 0, "small": 0, "china": 0,
        "invalid": 0, "dup": 0, "errors": 0,
    }

    # Deduplicate by URL
    unique_records = {}
    for rec in records:
        url = rec.get("url", "")
        if url and url not in unique_records:
            unique_records[url] = rec
    records = list(unique_records.values())

    print(f"\n{'=' * 65}")
    print(f"⬇️  DOWNLOADING {len(records)} unique PPT files (target: {target})")
    print(f"{'=' * 65}")

    for i, rec in enumerate(records):
        if stats["downloaded"] >= target:
            break

        download_from_warc(session, rec, seen, stats)

        if (i + 1) % 100 == 0:
            print(f"  Progress: {i + 1}/{len(records)} checked | "
                  f"Downloaded: {stats['downloaded']} | "
                  f"Dup: {stats['dup']} | Small: {stats['small']} | "
                  f"Err: {stats['errors']}")
            with open(STATS_FILE, "w") as f:
                json.dump(stats, f, indent=2)

        time.sleep(0.3)  # Rate limit WARC downloads

    return stats


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Common Crawl PPTX Miner (v2)")
    parser.add_argument("--target", type=int, default=200000, help="Target file count")
    parser.add_argument("--crawls", type=int, default=5, help="Number of crawls")
    parser.add_argument("--reset", action="store_true", help="Reset all progress")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    OUTPUT_DIR.mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)

    if args.reset:
        for f in [PROGRESS_FILE, CC_URLS_CACHE]:
            if f.exists():
                f.unlink()
        print("✅ Progress reset")

    session = make_session()
    seen = load_seen()
    progress = load_progress()

    # Phase 1: Find available crawls (skip unindexed ones)
    print("📋 Testing available crawl indices...")
    crawls = get_available_crawls(session, args.crawls)
    if not crawls:
        print("❌ No accessible crawl indices found. Try again later.")
        sys.exit(1)

    print(f"\n🚀 Common Crawl PPTX Mining")
    print(f"   Crawls: {len(crawls)} ({', '.join(c['id'] for c in crawls)})")
    print(f"   Domains: {len(DOMAINS)}")
    print(f"   Target: {args.target}")
    print(f"   Seen tags: {len(seen)}")

    # Phase 1: Build PPT URL index
    if progress.get("phase") != "download":
        ppt_records = phase_index(session, crawls, DOMAINS, progress)
        progress["phase"] = "download"
        save_progress(progress)
    else:
        # Load from cache
        ppt_records = []
        if CC_URLS_CACHE.exists():
            with open(CC_URLS_CACHE) as f:
                ppt_records = [json.loads(l) for l in f if l.strip()]
        print(f"\n📦 Loaded {len(ppt_records)} cached PPT records from previous index run")

    if not ppt_records:
        print("❌ No PPT files found in the index. Try more crawls or domains.")
        sys.exit(0)

    # Phase 2: Download
    stats = phase_download(session, ppt_records, args.target, seen, progress)

    # Final report
    print(f"\n{'=' * 65}")
    print(f"📊 COMMON CRAWL MINING COMPLETE")
    print(f"{'=' * 65}")
    for k, v in stats.items():
        print(f"   {k:20s}: {v:>8,}")
    print(f"{'=' * 65}")
    print(f"📁 Files: {OUTPUT_DIR}")

    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)


if __name__ == "__main__":
    main()
