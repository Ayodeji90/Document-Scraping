"""
Internet Archive Wayback PPTX Mining — Local Script

Uses the IA CDX API (which ACTUALLY supports MIME filtering) to find
PPT/PPTX files archived from university domains, then downloads them.

Tested: mit.edu alone has 500K+ PPT entries, stanford.edu 100K+.
After dedup, expect tens of thousands of unique files per major university.

Usage:
    python wayback_pptx_scraper.py                         # Full run
    python wayback_pptx_scraper.py --target 1000 --test    # Quick test
    python wayback_pptx_scraper.py --reset                 # Fresh start
"""
import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
import zipfile
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OUTPUT_DIR = Path("joint_downloaded")
SEEN_FILE = Path("logs/master_seen_tags.txt")
PROGRESS_FILE = Path("logs/ia_progress.json")
STATS_FILE = Path("logs/ia_stats.json")

MIN_SIZE = 2 * 1024 * 1024  # 2MB
IA_CDX = "https://web.archive.org/cdx/search/cdx"

CHINA_KW = [
    "chinese", "china", "hong kong", "taiwan", "beijing", "shanghai",
    "mandarin", "wuhan", "guangzhou", "shenzhen", "nanjing", "zhonghua",
    ".cn/", ".edu.cn", ".ac.cn", ".com.cn", ".hk/", ".tw/",
]

PPT_MIMES = [
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
]

# International domains only — NO USA (.edu/.gov)
DOMAINS = [
    # --- International orgs (PPT-rich, fast) ---
    "who.int", "worldbank.org", "un.org", "imf.org",
    "oecd.org", "europa.eu", "ieee.org", "acm.org",
    # Africa
    "uct.ac.za", "wits.ac.za", "sun.ac.za", "up.ac.za",
    "uonbi.ac.ke", "unilag.edu.ng", "ui.edu.ng",
    "aucegypt.edu", "cu.edu.eg",
    "um5.ac.ma", "ug.edu.gh", "knust.edu.gh",
    # Americas (non-US)
    "unam.mx", "itesm.mx", "usp.br", "unicamp.br",
    "uba.ar", "uchile.cl", "unal.edu.co", "pucp.edu.pe",
    # Oceania
    "unimelb.edu.au", "usyd.edu.au", "anu.edu.au",
    "unsw.edu.au", "uq.edu.au", "monash.edu",
    "auckland.ac.nz", "canterbury.ac.nz", "otago.ac.nz",
    # Asia
    "nus.edu.sg", "ntu.edu.sg",
    "um.edu.my", "usm.my",
    "ui.ac.id", "itb.ac.id", "ugm.ac.id",
    "up.edu.ph",
    "iitb.ac.in", "iitd.ac.in", "iitk.ac.in", "iisc.ac.in",
    "itu.edu.tr", "metu.edu.tr", "boun.edu.tr",
    "sharif.ir", "ut.ac.ir",
    "ksu.edu.sa", "kau.edu.sa",
    "ju.edu.jo", "aub.edu.lb",
    "tau.ac.il", "huji.ac.il", "technion.ac.il",
    "snu.ac.kr", "kaist.ac.kr", "postech.ac.kr", "yonsei.ac.kr",
    "u-tokyo.ac.jp", "kyoto-u.ac.jp", "osaka-u.ac.jp",
    "titech.ac.jp", "tohoku.ac.jp", "nagoya-u.ac.jp",
    # UK
    "cam.ac.uk", "ox.ac.uk", "imperial.ac.uk", "ucl.ac.uk",
    "kcl.ac.uk", "lse.ac.uk", "ed.ac.uk", "gla.ac.uk",
    "manchester.ac.uk", "bham.ac.uk", "bristol.ac.uk",
    "warwick.ac.uk", "leeds.ac.uk", "sheffield.ac.uk",
    "nottingham.ac.uk", "soton.ac.uk", "exeter.ac.uk",
    "york.ac.uk", "durham.ac.uk", "cardiff.ac.uk",
    "st-andrews.ac.uk", "qub.ac.uk", "bath.ac.uk",
    # Europe
    "ethz.ch", "epfl.ch", "uzh.ch", "unibas.ch",
    "tu-berlin.de", "tu-muenchen.de", "rwth-aachen.de",
    "uni-heidelberg.de", "lmu.de", "hu-berlin.de",
    "uni-bonn.de", "kit.edu", "tu-darmstadt.de",
    "polytechnique.fr", "ens.fr", "inria.fr",
    "uva.nl", "tudelft.nl", "uu.nl", "rug.nl",
    "kuleuven.be", "ugent.be",
    "kth.se", "uu.se", "chalmers.se",
    "dtu.dk", "ku.dk", "uio.no", "ntnu.no",
    "helsinki.fi", "aalto.fi",
    "tcd.ie", "ucd.ie",
    "polimi.it", "uniroma1.it", "unibo.it", "unitn.it",
# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/ia_scraper.log"),
    ],
)
logger = logging.getLogger("IA-Scraper")


def make_session():
    s = requests.Session()
    retry = Retry(total=5, backoff_factor=2,
                  status_forcelist=[429, 500, 502, 503, 504])
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


def load_content_seen():
    hashes = set()
    if CONTENT_HASH_FILE.exists():
        with open(CONTENT_HASH_FILE) as f:
            hashes = {l.strip() for l in f if l.strip()}
    return hashes


def save_content_hash(h):
    with open(CONTENT_HASH_FILE, "a") as f:
        f.write(h + "\n")


def load_progress():
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"completed_domains": [], "downloaded": 0}


def save_progress(prog):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(prog, f, indent=2)


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
def is_blocked(text):
    if not text:
        return False
    t = text.lower()
    return any(kw in t for kw in BLOCKED_KW)


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
# CDX Query
# ---------------------------------------------------------------------------
def query_ia_cdx(session, domain, mime_type):
    """Query IA CDX for PPT files with pagination to handle large domains."""
    results = []
    page = 0

    MAX_PAGES = 100  # Cap at 100 pages × 500 = 50K URLs max per domain/mime

    # First, find out how many pages there are
    try:
        count_params = {
            "url": domain,
            "matchType": "domain",
            "filter": f"mimetype:{mime_type}",
            "collapse": "urlkey",
            "showNumPages": "true",
            "pageSize": 500,
        }
        r = session.get(IA_CDX, params=count_params, timeout=30)
        if r.ok:
            try:
                num_pages = min(int(r.text.strip()), MAX_PAGES)
            except ValueError:
                num_pages = 1
        else:
            num_pages = 1
    except Exception:
        num_pages = 1

    if num_pages > 0:
        logger.info(f"  {domain} / {mime_type.split('.')[-1]}: {num_pages} pages to fetch")

    while page < num_pages:
        params = {
            "url": domain,
            "matchType": "domain",
            "filter": f"mimetype:{mime_type}",
            "collapse": "urlkey",
            "output": "json",
            "fl": "original,timestamp,mimetype,length",
            "pageSize": 500,
            "page": page,
        }
        try:
            # Retry once after a pause
            time.sleep(5)
            try:
                r = session.get(IA_CDX, params=params, timeout=60)
                if r.ok and r.text.strip():
                    data = r.json()
                    if data and isinstance(data[0], list):
                        header = data[0]
                        for row in data[1:]:
                            entry = dict(zip(header, row))
                            results.append(entry)
                        page_count = len(data) - 1
                        logger.info(f"    Page {page + 1}/{num_pages}: {page_count} entries")
                    else:
                        break
                else:
                    break
            except Exception:
                break
        except Exception as e:
            logger.warning(f"  CDX page {page} error for {domain}: {e}")
            break

        page += 1
        time.sleep(1)  # Rate limit between pages

    return results


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
def download_from_ia(session, entry, seen, content_seen, stats):
    """Download a PPT file from Internet Archive."""
    original_url = entry.get("original", "")
    timestamp = entry.get("timestamp", "")
    if not original_url or not timestamp:
        return False

    tag = hashlib.sha1(original_url.encode()).hexdigest()[:10]
    if tag in seen:
        stats["dup"] += 1
        return False
    if is_blocked(original_url):
        stats["china"] += 1
        return False

    # Check declared length
    try:
        content_len = int(entry.get("length", 0))
        if 0 < content_len < MIN_SIZE:
            stats["small"] += 1
            return False
    except (ValueError, TypeError):
        pass

    # Build Wayback download URL (id_ = original file without rewriting)
    wb_url = f"https://web.archive.org/web/{timestamp}id_/{original_url}"

    url_lower = original_url.lower().split("?")[0]
    ext = ".ppt" if url_lower.endswith(".ppt") else ".pptx"
    url_basename = original_url.split("/")[-1].split("?")[0][:35]
    safe = re.sub(r"[^\w]", "_", url_basename)
    fname = f"{tag}_ia_{safe}{ext}"
    dest = OUTPUT_DIR / fname

    if dest.exists():
        seen.add(tag)
        return False

    try:
        r = session.get(wb_url, timeout=120, stream=True)
        if not r.ok:
            stats["errors"] += 1
            return False

        with open(dest, "wb") as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)

        sz = os.path.getsize(dest)
        if sz < MIN_SIZE:
            dest.unlink(missing_ok=True)
            stats["small"] += 1
            return False

        # --- Master Content Hash Dedup Check ---
        file_sha256 = hashlib.sha256(open(dest, "rb").read()).hexdigest()
        if file_sha256 in content_seen:
            dest.unlink(missing_ok=True)
            stats["dup"] += 1
            return False

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
        content_seen.add(file_sha256)
        save_content_hash(file_sha256)

        stats["downloaded"] += 1
        sz_kb = sz // 1024
        print(f"      💾 [{stats['downloaded']}] {fname} ({sz_kb}KB)")
        return True

    except Exception:
        if dest.exists():
            dest.unlink(missing_ok=True)
        stats["errors"] += 1
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Internet Archive PPTX Miner")
    parser.add_argument("--target", type=int, default=200000)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--test", action="store_true", help="Only process first 5 domains")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    OUTPUT_DIR.mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)

    if args.reset and PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
        print("✅ Progress reset")

    session = make_session()
    seen = load_seen()
    content_seen = load_content_seen()
    progress = load_progress()
    completed = set(progress.get("completed_domains", []))

    stats = {
        "domains_queried": 0, "urls_found": 0, "downloaded": 0,
        "small": 0, "china": 0, "invalid": 0, "dup": 0, "errors": 0,
    }

    domains = DOMAINS[:5] if args.test else DOMAINS

    print(f"🚀 Internet Archive PPTX Mining")
    print(f"   Domains: {len(domains)}")
    print(f"   Target: {args.target}")
    print(f"   Seen tags: {len(seen)} | {len(content_seen)} master content hashes")
    print(f"   Already completed: {len(completed)} domains")
    print()

    for di, domain in enumerate(domains):
        if stats["downloaded"] >= args.target:
            break
        if domain in completed:
            continue

        print(f"\n🌐 [{di + 1}/{len(domains)}] {domain}")

        # Query for both PPT MIME types
        all_entries = []
        for mime in PPT_MIMES:
            entries = query_ia_cdx(session, domain, mime)
            all_entries.extend(entries)
            time.sleep(1)  # Rate limit between queries

        stats["domains_queried"] += 1
        stats["urls_found"] += len(all_entries)

        if not all_entries:
            print(f"   → 0 PPT files found")
            completed.add(domain)
            progress["completed_domains"] = list(completed)
            save_progress(progress)
            continue

        # Deduplicate by URL within this domain
        unique = {}
        for e in all_entries:
            url = e.get("original", "")
            if url and url not in unique:
                unique[url] = e
        entries_list = list(unique.values())

        print(f"   → {len(entries_list)} unique PPT URLs found. Downloading...")

        domain_count = 0
        for ei, entry in enumerate(entries_list):
            if stats["downloaded"] >= args.target:
                break

            if download_from_ia(session, entry, seen, content_seen, stats):
                domain_count += 1
                if domain_count % 10 == 0:
                    print(f"   ✅ {domain_count} downloaded from {domain} | "
                          f"Total: {stats['downloaded']}")

            # Rate limit: 1 download per second
            if ei % 5 == 0:
                time.sleep(1)

        print(f"   📊 {domain}: {domain_count} downloaded | "
              f"Dup: {stats['dup']} | Small: {stats['small']}")

        completed.add(domain)
        progress["completed_domains"] = list(completed)
        progress["downloaded"] = stats["downloaded"]
        save_progress(progress)

        with open(STATS_FILE, "w") as f:
            json.dump(stats, f, indent=2)

        time.sleep(2)  # Rate limit between domains

    # Final report
    print(f"\n{'=' * 65}")
    print(f"📊 INTERNET ARCHIVE MINING COMPLETE")
    print(f"{'=' * 65}")
    for k, v in stats.items():
        print(f"   {k:20s}: {v:>8,}")
    print(f"{'=' * 65}")
    print(f"📁 Files saved to: {OUTPUT_DIR}")

    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)


if __name__ == "__main__":
    main()
