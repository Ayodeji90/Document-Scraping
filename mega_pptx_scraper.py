"""
Multi-Source PPTX Mega Scraper — Local Script

Combines 3 high-yield sources to fill the gap to 500K:

  Source 1: Archive.org Items API       → ~19K PPT items
  Source 2: DSpace/OAI-PMH Harvesting   → 50-100K from institutional repos
  Source 3: Direct URL Crawling         → 100K+ from known PPT-hosting pages

Usage:
    python mega_pptx_scraper.py                       # Full run
    python mega_pptx_scraper.py --source archive      # Archive.org only
    python mega_pptx_scraper.py --source oai           # OAI-PMH only
    python mega_pptx_scraper.py --source direct        # Direct URLs only
    python mega_pptx_scraper.py --target 100000 --reset
"""
import argparse
import hashlib
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OUTPUT_DIR = Path("joint_downloaded")
SEEN_FILE = Path("logs/master_seen_tags.txt")
CONTENT_HASH_FILE = Path("logs/master_content_hashes.txt")
PROGRESS_FILE = Path("logs/mega_progress.json")
STATS_FILE = Path("logs/mega_stats.json")

MIN_SIZE = 2 * 1024 * 1024  # 2MB

CHINA_KW = [
    "chinese", "china", "hong kong", "taiwan", "beijing", "shanghai",
    "mandarin", "wuhan", "guangzhou", "shenzhen", "nanjing", "zhonghua",
    ".cn/", ".edu.cn", ".ac.cn", ".com.cn", ".hk/", ".tw/",
]

USA_KW = [
    "united states", "american", "u.s.a", "washington d.c",
    "congress", "senate", "house of representatives",
    "federal government", "constitution of the united",
    "veterans", "fourth of july", "thanksgiving",
    "memorial day", "super bowl", "nfl ", "nba ",
    "us election", "us president", "american flag",
    "pledge of allegiance", "state of the union",
    ".edu/", ".gov/", ".mil/",
    "mit.edu", "stanford.edu", "berkeley.edu", "harvard.edu",
    "cmu.edu", "gatech.edu", "cornell.edu", "yale.edu",
    "princeton.edu", "columbia.edu", "umich.edu", "upenn.edu",
    "ucla.edu", "nyu.edu", "duke.edu", "caltech.edu",
    "nih.gov", "nsf.gov", "nasa.gov", "cdc.gov", "epa.gov",
    "va.gov", "veterans", "united states",
]

BLOCKED_KW = CHINA_KW + USA_KW

# --- Archive.org Search Queries ---
ARCHIVE_QUERIES = [
    "format:(PowerPoint)",
    "format:(PPTX)",
    "subject:(lecture) AND format:(PowerPoint)",
    "subject:(presentation) AND format:(PowerPoint)",
    "subject:(course) AND format:(PowerPoint)",
    "subject:(education) AND format:(PowerPoint)",
    "subject:(university) AND format:(PowerPoint)",
    "subject:(slides) AND format:(PowerPoint)",
    "subject:(tutorial) AND format:(PowerPoint)",
    "subject:(seminar) AND format:(PowerPoint)",
    "subject:(conference) AND format:(PowerPoint)",
    "subject:(workshop) AND format:(PowerPoint)",
    "subject:(academic) AND format:(PowerPoint)",
    "subject:(research) AND format:(PowerPoint)",
    "creator:(university) AND format:(PowerPoint)",
    "mediatype:(texts) AND format:(PowerPoint)",
]

# --- DSpace/OAI-PMH Repositories ---
# These are real, active DSpace institutional repositories with OAI-PMH
OAI_REPOSITORIES = [
    # Africa
    ("https://repository.uonbi.ac.ke/oai/request", "U Nairobi"),
    ("https://ir.jkuat.ac.ke/oai/request", "JKUAT Kenya"),
    ("https://repository.up.ac.za/oai/request", "U Pretoria"),
    ("https://open.uct.ac.za/oai/request", "U Cape Town"),
    ("https://wiredspace.wits.ac.za/oai/request", "Wits SA"),
    ("https://scholar.sun.ac.za/oai/request", "Stellenbosch"),
    # Asia
    ("https://repository.iiitd.edu.in/oai/request", "IIIT Delhi"),
    ("https://eprints.utm.my/oai/request", "UTM Malaysia"),
    ("https://repository.ntu.edu.sg/oai/request", "NTU Singapore"),
    ("http://dspace.bracu.ac.bd/oai/request", "BRAC Bangladesh"),
    # Europe
    ("https://spiral.imperial.ac.uk/oai/request", "Imperial College"),
    ("https://repository.lboro.ac.uk/oai/request", "Loughborough"),
    ("https://research.chalmers.se/oai/request", "Chalmers Sweden"),
    ("https://dspace.library.uu.nl/oai/request", "Utrecht NL"),
    ("https://riunet.upv.es/oai/request", "UPV Spain"),
    ("https://repositorio.uam.es/oai/request", "UAM Madrid"),
    ("https://depositonce.tu-berlin.de/oai/request", "TU Berlin"),
    ("https://publikationen.bibliothek.kit.edu/oai/request", "KIT Germany"),
    # Americas
    ("https://repositorio.unam.mx/oai/request", "UNAM Mexico"),
    ("https://repositorio.uchile.cl/oai/request", "U Chile"),
    ("https://repositorio.usp.br/oai/request", "USP Brazil"),
    # Oceania
    ("https://openresearch-repository.anu.edu.au/oai/request", "ANU Australia"),
    ("https://researchspace.auckland.ac.nz/oai/request", "U Auckland"),
    # Large aggregators
    ("https://www.opendoar.org/oai/request", "OpenDOAR"),
]

# --- Direct PPT URL patterns (non-US only) ---
DIRECT_SOURCES = [
    "https://www.cl.cam.ac.uk",
    "https://www.robots.ox.ac.uk",
    "https://www.comp.nus.edu.sg",
    "https://www.cse.iitd.ac.in",
]

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/mega_scraper.log"),
    ],
)
logger = logging.getLogger("Mega-Scraper")


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
    return {"archive_page": 0, "oai_completed": [], "downloaded": 0}


def save_progress(prog):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(prog, f, indent=2)


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
def is_blocked(text):
    """Block China and USA content."""
    if not text:
        return False
    return any(kw in text.lower() for kw in BLOCKED_KW)


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


def download_file(session, url, prefix, source_id, seen, content_seen, stats):
    """Download a PPT/PPTX file with all filters. Returns True if saved."""
    tag = hashlib.sha1(url.encode()).hexdigest()[:10]
    if tag in seen:
        stats["dup"] += 1
        return False
    if is_blocked(url):
        stats["china"] += 1
        return False

    url_lower = url.lower().split("?")[0]
    ext = ".ppt" if url_lower.endswith(".ppt") else ".pptx"
    url_basename = url.split("/")[-1].split("?")[0][:35]
    safe = re.sub(r"[^\w]", "_", url_basename)
    fname = f"{tag}_{prefix}_{safe}{ext}"
    dest = OUTPUT_DIR / fname

    if dest.exists():
        seen.add(tag)
        return False

    try:
        # HEAD check for size
        try:
            h = session.head(url, timeout=10, allow_redirects=True)
            cl = int(h.headers.get("Content-Length", 0))
            if 0 < cl < MIN_SIZE:
                stats["small"] += 1
                return False
        except Exception:
            pass

        r = session.get(url, timeout=120, stream=True)
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


# ===================================================================
# SOURCE 1: Archive.org Items API
# ===================================================================
def run_archive_org(session, target, seen, content_seen, stats, progress):
    """Search Archive.org for items containing PPT files, download them."""
    print(f"\n{'=' * 65}")
    print(f"📦 SOURCE 1: Archive.org Items API (19K+ items)")
    print(f"{'=' * 65}")

    collected_ids = set()

    for qi, query in enumerate(ARCHIVE_QUERIES):
        if stats["downloaded"] >= target:
            break

        print(f"\n  Query [{qi + 1}/{len(ARCHIVE_QUERIES)}]: {query}")
        page = 1

        while stats["downloaded"] < target:
            url = (
                f"https://archive.org/advancedsearch.php?"
                f"q={query}&fl[]=identifier&fl[]=title"
                f"&rows=100&page={page}&output=json"
                f"&sort[]=downloads+desc"
            )
            try:
                r = session.get(url, timeout=60)
                if not r.ok:
                    break
                data = r.json()
                docs = data.get("response", {}).get("docs", [])
                if not docs:
                    break

                for doc in docs:
                    if stats["downloaded"] >= target:
                        break

                    identifier = doc.get("identifier", "")
                    title = doc.get("title", "")
                    if not identifier or identifier in collected_ids:
                        continue
                    collected_ids.add(identifier)

                    if is_blocked(title):
                        stats["china"] += 1
                        continue

                    # Get item files list
                    ppt_urls = _get_archive_ppt_files(session, identifier)
                    for ppt_url in ppt_urls:
                        if stats["downloaded"] >= target:
                            break
                        download_file(session, ppt_url, "arc", identifier[:15], seen, content_seen, stats)
                        time.sleep(0.5)

                if len(docs) < 100:
                    break
                page += 1
                time.sleep(1)

            except Exception as e:
                logger.warning(f"Archive.org error: {e}")
                break

    progress["archive_done"] = True
    save_progress(progress)
    print(f"\n  ✅ Archive.org: {stats['downloaded']} total downloaded")


def _get_archive_ppt_files(session, identifier):
    """Get download URLs for PPT files in an Archive.org item."""
    ppt_urls = []
    try:
        r = session.get(
            f"https://archive.org/metadata/{identifier}/files",
            timeout=30,
        )
        if r.ok:
            files = r.json().get("result", [])
            for f in files:
                name = f.get("name", "").lower()
                if name.endswith((".ppt", ".pptx", ".pps", ".ppsx")):
                    url = f"https://archive.org/download/{identifier}/{f['name']}"
                    ppt_urls.append(url)
    except Exception:
        pass
    return ppt_urls


# ===================================================================
# SOURCE 2: OAI-PMH Institutional Repositories
# ===================================================================
def run_oai_pmh(session, target, seen, content_seen, stats, progress):
    """Harvest PPT files from DSpace/EPrints institutional repositories."""
    print(f"\n{'=' * 65}")
    print(f"🏛️  SOURCE 2: OAI-PMH Institutional Repositories ({len(OAI_REPOSITORIES)} repos)")
    print(f"{'=' * 65}")

    completed = set(progress.get("oai_completed", []))

    for ri, (oai_url, name) in enumerate(OAI_REPOSITORIES):
        if stats["downloaded"] >= target:
            break
        if oai_url in completed:
            continue

        print(f"\n  [{ri + 1}/{len(OAI_REPOSITORIES)}] {name} ({oai_url})")
        repo_count = 0

        try:
            # Use ListRecords with oai_dc to get metadata
            resumption_token = None
            page_count = 0

            while stats["downloaded"] < target:
                if resumption_token:
                    req_url = f"{oai_url}?verb=ListRecords&resumptionToken={resumption_token}"
                else:
                    req_url = f"{oai_url}?verb=ListRecords&metadataPrefix=oai_dc"

                r = session.get(req_url, timeout=60)
                if not r.ok:
                    break

                ppt_urls = _extract_ppt_from_oai(r.text, oai_url)
                page_count += 1

                for ppt_url in ppt_urls:
                    if stats["downloaded"] >= target:
                        break
                    if download_file(session, ppt_url, "oai", name[:8], seen, content_seen, stats):
                        repo_count += 1
                    time.sleep(0.5)

                # Get resumption token
                resumption_token = _get_resumption_token(r.text)
                if not resumption_token:
                    break

                if page_count > 200:  # Safety cap
                    break
                time.sleep(1)

        except Exception as e:
            logger.warning(f"OAI error for {name}: {e}")

        print(f"    → {repo_count} files from {name}")
        completed.add(oai_url)
        progress["oai_completed"] = list(completed)
        save_progress(progress)


def _extract_ppt_from_oai(xml_text, base_url):
    """Extract PPT download URLs from OAI-PMH ListRecords response."""
    ppt_urls = []
    try:
        root = ET.fromstring(xml_text)
        ns = {
            "oai": "http://www.openarchives.org/OAI/2.0/",
            "dc": "http://purl.org/dc/elements/1.1/",
        }

        for record in root.findall(".//oai:record", ns):
            # Look for identifier/URL in dc:identifier fields
            metadata = record.find(".//oai:metadata", ns)
            if metadata is None:
                continue

            for identifier in metadata.iter():
                if identifier.text and identifier.text.strip():
                    text = identifier.text.strip()
                    # Check if it's a URL pointing to a PPT file
                    if text.startswith("http") and text.lower().split("?")[0].endswith(
                        (".ppt", ".pptx", ".pps", ".ppsx")
                    ):
                        ppt_urls.append(text)
                    # Also check for repository handle URLs that might have PPT
                    elif text.startswith("http") and "/bitstream/" in text:
                        if any(ext in text.lower() for ext in [".ppt", ".pptx"]):
                            ppt_urls.append(text)
    except ET.ParseError:
        pass
    return ppt_urls


def _get_resumption_token(xml_text):
    """Extract OAI-PMH resumption token from response."""
    try:
        root = ET.fromstring(xml_text)
        ns = {"oai": "http://www.openarchives.org/OAI/2.0/"}
        token_elem = root.find(".//oai:resumptionToken", ns)
        if token_elem is not None and token_elem.text:
            return token_elem.text.strip()
    except Exception:
        pass
    return None


# ===================================================================
# SOURCE 3: Direct Courseware Crawling
# ===================================================================
def run_direct_crawl(session, target, seen, content_seen, stats, progress):
    """Crawl known university courseware sites for PPT links."""
    print(f"\n{'=' * 65}")
    print(f"🔍 SOURCE 3: Direct Courseware Crawling")
    print(f"{'=' * 65}")

    # Use Wayback Machine CDX to find PPT files on courseware sites
    IA_CDX = "https://web.archive.org/cdx/search/cdx"

    courseware_domains = [
        # Non-US universities only
        "www.cse.iitd.ac.in",
        "www.cse.iitb.ac.in",
        "www.cse.iitk.ac.in",
        "www.comp.nus.edu.sg",
        "www.cl.cam.ac.uk",
        "www.robots.ox.ac.uk",
        "www.doc.ic.ac.uk",
        "www.inf.ed.ac.uk",
        "www.cs.ox.ac.uk",
        "www.maths.cam.ac.uk",
        "course.fast.ai",
        "www.cs.toronto.edu",
        "www.cs.ubc.ca",
        "www.cs.mcgill.ca",
        "ethz.ch",
        "www.mpi-inf.mpg.de",
        "www.tudelft.nl",
        "www.lix.polytechnique.fr",
        "www.di.ens.fr",
        "www.cs.technion.ac.il",
    ]

    for di, domain in enumerate(courseware_domains):
        if stats["downloaded"] >= target:
            break

        print(f"\n  [{di + 1}/{len(courseware_domains)}] {domain}")

        for mime in [
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ]:
            if stats["downloaded"] >= target:
                break

            params = {
                "url": domain,
                "matchType": "domain",
                "filter": f"mimetype:{mime}",
                "collapse": "urlkey",
                "output": "json",
                "fl": "original,timestamp",
                "pageSize": 500,
                "page": 0,
            }

            try:
                r = session.get(IA_CDX, params=params, timeout=60)
                if r.ok and r.text.strip():
                    data = r.json()
                    if data and isinstance(data[0], list):
                        header = data[0]
                        entries = [dict(zip(header, row)) for row in data[1:]]

                        for entry in entries:
                            if stats["downloaded"] >= target:
                                break
                            url = entry.get("original", "")
                            ts = entry.get("timestamp", "")
                            if url and ts:
                                wb_url = f"https://web.archive.org/web/{ts}id_/{url}"
                                download_file(session, wb_url, "cw", domain[:10], seen, content_seen, stats)
                                time.sleep(0.5)

            except Exception as e:
                logger.warning(f"CDX error for {domain}: {e}")
            time.sleep(2)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Multi-Source PPTX Mega Scraper")
    parser.add_argument("--target", type=int, default=200000)
    parser.add_argument("--source", choices=["archive", "oai", "direct", "all"],
                        default="all")
    parser.add_argument("--reset", action="store_true")
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

    stats = {
        "downloaded": 0, "small": 0, "china": 0,
        "invalid": 0, "dup": 0, "errors": 0,
    }

    print(f"🚀 Multi-Source PPTX Mega Scraper")
    print(f"   Target: {args.target}")
    print(f"   Sources: {args.source}")
    print(f"   Seen tags: {len(seen)} | {len(content_seen)} master content hashes")

    if args.source in ("archive", "all"):
        run_archive_org(session, args.target, seen, content_seen, stats, progress)

    if args.source in ("oai", "all"):
        run_oai_pmh(session, args.target, seen, content_seen, stats, progress)

    if args.source in ("direct", "all"):
        run_direct_crawl(session, args.target, seen, content_seen, stats, progress)

    # Final report
    print(f"\n{'=' * 65}")
    print(f"📊 MEGA SCRAPER COMPLETE")
    print(f"{'=' * 65}")
    for k, v in stats.items():
        print(f"   {k:20s}: {v:>8,}")
    print(f"{'=' * 65}")
    print(f"📁 Files: {OUTPUT_DIR}")

    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)


if __name__ == "__main__":
    main()
