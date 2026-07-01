"""
PPTOnline Local Downloader — 1.4M presentations from ppt-online.org

Streams metadata from the HuggingFace nyuuzyou/pptonline dataset (15 parquet
files, 1,418,349 entries), discovers the working download URL pattern, then
bulk-downloads PPT files with full filtering.

Output:  hf_pptonline/           (its own dedicated folder)
Dedup:   logs/master_seen_tags.txt  (shared with all other scrapers)

Usage:
    python pptonline_scraper.py                    # Full run (target 500K)
    python pptonline_scraper.py --target 1000      # Small test
    python pptonline_scraper.py --reset            # Fresh start
    python pptonline_scraper.py --skip-discovery   # Reuse cached URL pattern
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
OUTPUT_DIR = Path("hf_pptonline")
SEEN_FILE = Path("logs/master_seen_tags.txt")
CONTENT_HASH_FILE = Path("logs/master_content_hashes.txt")
PROGRESS_FILE = Path("logs/pptonline_progress.json")
STATS_FILE = Path("logs/pptonline_stats.json")

MIN_SIZE = 2 * 1024 * 1024  # 2MB

# HuggingFace dataset — 15 parquet shards
HF_DATASET = "nyuuzyou/pptonline"
HF_PARQUET_BASE = (
    "https://huggingface.co/api/datasets/nyuuzyou/pptonline/parquet/default/train"
)

# URL patterns to try for downloading (discovered at runtime)
URL_PATTERNS = [
    "https://ppt-online.org/download/{id}",
    "https://ppt-online.org/{id}/download",
    "https://en.ppt-online.org/download/{id}",
    "https://ppt-online.org/{id}",
    "https://en.ppt-online.org/{id}",
]

# --- Geo-filtering: China + USA ---
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
]

BLOCKED_KW = CHINA_KW + USA_KW

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/pptonline_scraper.log"),
    ],
)
logger = logging.getLogger("PPTOnline")


def make_session():
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    s = requests.Session()
    s.verify = False
    retry = Retry(
        total=5, backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=10))
    s.mount("http://", HTTPAdapter(max_retries=retry, pool_maxsize=10))
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
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
    return {"shard_idx": 0, "row_idx": 0, "downloaded": 0, "url_pattern": None}


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
    """Check if PPTX contains significant Chinese characters."""
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


def has_us_content(fp):
    """Check if PPTX slide content is heavily US-focused."""
    us_terms = [
        "united states", "american", "u.s.a", "washington d.c",
        "congress", "senate", "house of representatives",
        "federal government", "constitution of the united",
    ]
    try:
        with zipfile.ZipFile(fp, "r") as z:
            text = ""
            for name in z.namelist():
                if "slide" in name and name.endswith(".xml"):
                    text += z.read(name).decode("utf-8", errors="ignore").lower()
                    if len(text) > 50000:
                        break
            hits = sum(1 for term in us_terms if term in text)
            return hits >= 3
    except Exception:
        pass
    return False


def valid_ppt(fp):
    """Check magic bytes: PK (PPTX/ZIP) or D0CF (old PPT)."""
    try:
        with open(fp, "rb") as f:
            h = f.read(8)
        return h[:2] == b"PK" or h[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Parquet streaming (no `datasets` library needed)
# ---------------------------------------------------------------------------
def get_parquet_urls(session):
    """Get list of parquet file URLs from HuggingFace API."""
    try:
        r = session.get(HF_PARQUET_BASE, timeout=30)
        if r.ok:
            urls = r.json()
            if isinstance(urls, list):
                logger.info(f"Found {len(urls)} parquet shards")
                return urls
    except Exception as e:
        logger.warning(f"Failed to get parquet URLs from API: {e}")

    # Fallback: construct URLs manually (15 shards)
    urls = []
    for i in range(15):
        url = (
            f"https://huggingface.co/datasets/nyuuzyou/pptonline/resolve/main/"
            f"data/train-{i:05d}-of-00015.parquet"
        )
        urls.append(url)
    logger.info(f"Using {len(urls)} fallback parquet URLs")
    return urls


def stream_parquet_rows(session, parquet_url):
    """Download a parquet file and yield rows as dicts."""
    try:
        import pyarrow.parquet as pq
        import io

        r = session.get(parquet_url, timeout=120)
        if not r.ok:
            logger.warning(f"Failed to download parquet: HTTP {r.status_code}")
            return

        buf = io.BytesIO(r.content)
        table = pq.read_table(buf)
        columns = table.column_names

        for i in range(table.num_rows):
            row = {}
            for col in columns:
                val = table.column(col)[i].as_py()
                row[col] = val
            yield row

    except ImportError:
        logger.error("pyarrow not installed. Installing...")
        os.system(f"{sys.executable} -m pip install pyarrow -q")
        import pyarrow.parquet as pq
        import io

        r = session.get(parquet_url, timeout=120)
        if not r.ok:
            return
        buf = io.BytesIO(r.content)
        table = pq.read_table(buf)
        columns = table.column_names

        for i in range(table.num_rows):
            row = {}
            for col in columns:
                val = table.column(col)[i].as_py()
                row[col] = val
            yield row

    except Exception as e:
        logger.error(f"Error reading parquet {parquet_url}: {e}")


# ---------------------------------------------------------------------------
# URL Pattern Discovery
# ---------------------------------------------------------------------------
def discover_url_pattern(session, test_ids):
    """Try each URL pattern with test IDs to find the working download URL."""
    from bs4 import BeautifulSoup

    logger.info(f"Testing patterns with real GET requests on {len(test_ids)} IDs...")
    # Try direct download patterns using GET
    for pattern in URL_PATTERNS:
        for tid in test_ids:
            url = pattern.format(id=tid)
            try:
                r = session.get(url, timeout=10, stream=True, allow_redirects=True)
                if r.status_code == 200:
                    ct = r.headers.get("Content-Type", "").lower()
                    if "text/html" not in ct and any(x in ct for x in ["presentation", "octet", "powerpoint", "zip", "application"]):
                        logger.info(f"✅ Direct download pattern works: {pattern} (CT: {ct})")
                        r.close()
                        return pattern
                r.close()
            except Exception:
                continue

    # Try page scraping to find download button
    logger.info("Direct patterns failed, trying page scraping...")
    for tid in test_ids:
        for base in ["https://ppt-online.org/", "https://en.ppt-online.org/"]:
            try:
                url = f"{base}{tid}"
                r = session.get(url, timeout=15)
                logger.info(f"GET {url} -> HTTP {r.status_code}")
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "html.parser")
                    all_links = [(a.get_text("", strip=True), a.get("href", "")) for a in soup.find_all("a", href=True)]
                    logger.info(f"Found {len(all_links)} links on {url}. Top links: {all_links[:20]}")

                    for text, href in all_links:
                        t_low = text.lower()
                        h_low = href.lower()
                        if any(x in t_low for x in ["download", "скачать", "загрузить"]) or any(x in h_low for x in ["download", "files", "cdn"]):
                            if not href.startswith("http"):
                                href = base.rstrip("/") + (href if href.startswith("/") else f"/{href}")
                            pattern = href.replace(str(tid), "{id}")
                            logger.info(f"✅ Discovered download pattern: {pattern} from link ({text}, {href})")
                            return pattern
            except Exception as e:
                logger.warning(f"Scraping failed on {base}{tid}: {e}")
                continue

    return None


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
def download_ppt(session, url, title, row_id, seen, content_seen, stats):
    """Download a single PPT file with all filters."""
    tag = hashlib.sha1(url.encode()).hexdigest()[:10]
    if tag in seen:
        stats["dup"] += 1
        return False

    if is_blocked(title):
        stats["blocked"] += 1
        return False

    ext = ".ppt" if url.lower().endswith(".ppt") else ".pptx"
    safe = re.sub(r"[^\w\-]", "_", (title or "untitled")[:35])
    fname = f"{tag}_pon_{row_id}_{safe}{ext}"
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
            ct = h.headers.get("Content-Type", "").lower()
            # Skip HTML responses (not a real file)
            if "text/html" in ct and "download" not in url:
                stats["invalid"] += 1
                return False
        except Exception:
            pass

        r = session.get(url, timeout=90, stream=True)
        if not r.ok:
            stats["errors"] += 1
            return False

        # Check Content-Type of response
        ct = r.headers.get("Content-Type", "").lower()
        if "text/html" in ct:
            stats["invalid"] += 1
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
            stats["blocked"] += 1
            return False
        if has_us_content(dest):
            dest.unlink(missing_ok=True)
            stats["blocked"] += 1
            return False

        seen.add(tag)
        save_tag(tag)
        content_seen.add(file_sha256)
        save_content_hash(file_sha256)

        stats["downloaded"] += 1
        sz_kb = sz // 1024
        print(f"   💾 [{stats['downloaded']}] {fname} ({sz_kb}KB)")
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
    parser = argparse.ArgumentParser(description="PPTOnline Local Downloader (1.4M)")
    parser.add_argument("--target", type=int, default=500000)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--skip-discovery", action="store_true",
                        help="Skip URL pattern discovery, use cached pattern")
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
        "checked": 0, "downloaded": 0, "small": 0,
        "blocked": 0, "invalid": 0, "dup": 0, "errors": 0,
    }

    print(f"🚀 PPTOnline Local Downloader")
    print(f"   Dataset: {HF_DATASET} (1,418,349 entries)")
    print(f"   Output:  {OUTPUT_DIR}/")
    print(f"   Target:  {args.target}")
    print(f"   Seen:    {len(seen)} tags | {len(content_seen)} master content hashes")
    print(f"   Resume:  shard {progress.get('shard_idx', 0)}, "
          f"row {progress.get('row_idx', 0)}")

    # Step 1: Get parquet shard URLs
    print(f"\n📦 Fetching parquet shard URLs...")
    parquet_urls = get_parquet_urls(session)
    if not parquet_urls:
        print("❌ Could not get parquet URLs")
        sys.exit(1)
    print(f"   Found {len(parquet_urls)} shards")

    # Step 2: Discover URL pattern
    url_pattern = progress.get("url_pattern")

    if not url_pattern or not args.skip_discovery:
        print(f"\n🔍 Discovering download URL pattern...")
        # Get 20 test IDs sampled across the first 2000 rows
        test_ids = []
        for ri, row in enumerate(stream_parquet_rows(session, parquet_urls[0])):
            if ri % 100 == 0:
                rid = row.get("id") or row.get("ID") or row.get("file_id")
                if rid:
                    test_ids.append(str(rid))
                if len(test_ids) >= 20:
                    break

        if not test_ids:
            # Try common column names
            print("   ⚠️ Could not find ID column. Listing available columns...")
            for row in stream_parquet_rows(session, parquet_urls[0]):
                print(f"   Columns: {list(row.keys())}")
                # Use any available identifier
                for key in row:
                    if row[key] and isinstance(row[key], (str, int)):
                        test_ids.append(str(row[key]))
                        break
                break

        if test_ids:
            print(f"   Test IDs: {test_ids[:3]}")
            url_pattern = discover_url_pattern(session, test_ids[:3])
        else:
            print("   ❌ No test IDs found")

        if url_pattern:
            progress["url_pattern"] = url_pattern
            save_progress(progress)
            print(f"   ✅ Using: {url_pattern}")
        else:
            print("   ❌ Could not discover download URL pattern")
            print("   The ppt-online.org site may be down.")
            print("   Attempting direct parquet file download instead...")
            # Fallback: check if parquet contains actual file data
            url_pattern = None

    if not url_pattern:
        print("\n⚠️  No download URL pattern found.")
        print("   Checking if parquet files contain actual PPT file data...")

        # Check first row for binary content
        for row in stream_parquet_rows(session, parquet_urls[0]):
            cols = list(row.keys())
            print(f"   Columns: {cols}")
            for col in cols:
                val = row[col]
                if isinstance(val, bytes) and len(val) > 1000:
                    print(f"   Found binary column: {col} ({len(val)} bytes)")
                    url_pattern = "__BINARY__"
                    progress["binary_column"] = col
                    break
            break

        if url_pattern != "__BINARY__":
            print("   ❌ Dataset contains metadata only, not actual files.")
            print("   Need ppt-online.org to be accessible for downloads.")
            sys.exit(1)

    # Step 3: Bulk download
    start_shard = progress.get("shard_idx", 0)
    start_row = progress.get("row_idx", 0)

    print(f"\n⬇️  Starting bulk download...")
    print(f"{'=' * 65}")

    for si in range(start_shard, len(parquet_urls)):
        if stats["downloaded"] >= args.target:
            break

        purl = parquet_urls[si]
        shard_name = purl.split("/")[-1] if "/" in purl else f"shard-{si}"
        print(f"\n📄 Shard [{si + 1}/{len(parquet_urls)}] {shard_name}")

        row_offset = start_row if si == start_shard else 0

        for ri, row in enumerate(stream_parquet_rows(session, purl)):
            if ri < row_offset:
                continue
            if stats["downloaded"] >= args.target:
                break

            stats["checked"] += 1

            # Extract fields (flexible column mapping)
            rid = str(row.get("id") or row.get("ID") or row.get("file_id") or ri)
            title = str(row.get("title") or row.get("Title") or "untitled")
            category = str(row.get("category") or row.get("Category") or "")

            # Check metadata for blocked content
            if is_blocked(title) or is_blocked(category):
                stats["blocked"] += 1
                continue

            if url_pattern == "__BINARY__":
                # Direct binary extraction from parquet
                binary_col = progress.get("binary_column", "")
                data = row.get(binary_col)
                if not data or not isinstance(data, bytes):
                    continue
                _save_binary(data, rid, title, seen, content_seen, stats)
            else:
                # Download from URL
                url = url_pattern.format(id=rid)
                download_ppt(session, url, title, rid, seen, content_seen, stats)

            # Rate limit
            if stats["checked"] % 10 == 0:
                time.sleep(0.5)

            # Save progress every 500 rows
            if stats["checked"] % 500 == 0:
                progress["shard_idx"] = si
                progress["row_idx"] = ri
                progress["downloaded"] = stats["downloaded"]
                save_progress(progress)

                with open(STATS_FILE, "w") as f:
                    json.dump(stats, f, indent=2)

            # Status every 1000 rows
            if stats["checked"] % 1000 == 0:
                print(f"   📊 Checked: {stats['checked']} | "
                      f"Downloaded: {stats['downloaded']} | "
                      f"Small: {stats['small']} | "
                      f"Blocked: {stats['blocked']} | "
                      f"Dup: {stats['dup']} | "
                      f"Err: {stats['errors']}")

        # Mark shard complete
        progress["shard_idx"] = si + 1
        progress["row_idx"] = 0
        save_progress(progress)

    # Final report
    print(f"\n{'=' * 65}")
    print(f"📊 PPTONLINE DOWNLOAD COMPLETE")
    print(f"{'=' * 65}")
    for k, v in stats.items():
        print(f"   {k:20s}: {v:>8,}")
    print(f"{'=' * 65}")
    print(f"📁 Files saved to: {OUTPUT_DIR}/")

    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)


def _save_binary(data, rid, title, seen, content_seen, stats):
    """Save binary PPT data directly from parquet."""
    tag = hashlib.sha1(data[:1000]).hexdigest()[:10]
    if tag in seen:
        stats["dup"] += 1
        return False

    if len(data) < MIN_SIZE:
        stats["small"] += 1
        return False

    # --- Master Content Hash Dedup Check ---
    file_sha256 = hashlib.sha256(data).hexdigest()
    if file_sha256 in content_seen:
        stats["dup"] += 1
        return False

    ext = ".pptx" if data[:2] == b"PK" else ".ppt"
    safe = re.sub(r"[^\w\-]", "_", (title or "untitled")[:35])
    fname = f"{tag}_pon_{rid}_{safe}{ext}"
    dest = OUTPUT_DIR / fname

    if dest.exists():
        seen.add(tag)
        return False

    with open(dest, "wb") as f:
        f.write(data)

    if not valid_ppt(dest):
        dest.unlink(missing_ok=True)
        stats["invalid"] += 1
        return False
    if has_chinese_chars(dest):
        dest.unlink(missing_ok=True)
        stats["blocked"] += 1
        return False
    if has_us_content(dest):
        dest.unlink(missing_ok=True)
        stats["blocked"] += 1
        return False

    seen.add(tag)
    save_tag(tag)
    content_seen.add(file_sha256)
    save_content_hash(file_sha256)

    stats["downloaded"] += 1
    sz_kb = len(data) // 1024
    print(f"   💾 [{stats['downloaded']}] {fname} ({sz_kb}KB)")
    return True


if __name__ == "__main__":
    main()
