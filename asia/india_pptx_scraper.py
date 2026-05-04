#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
India-focused PPTX scraper — Search-Engine-Driven (v2 - SCALE UP)
Discovers and downloads academic .pptx / .ppt files from Indian institutions (.ac.in).

Strategies for 10,000+ files:
  1. Massive topic matrix (60+ academic subjects).
  2. Deep Discovery: Follows HTML pages to find embedded bitstream links (DSpace/Shodhganga).
  3. Broad wildcard domains (site:*.ac.in).
  4. Resume Mode: Preloads existing file hashes from disk.
"""

import argparse
import hashlib
import logging
import os
import random
import re
import time
import warnings
from pathlib import Path
from typing import List, Optional, Set
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from ddgs import DDGS
    try:
        from ddgs.exceptions import RatelimitException
    except ImportError:
        class RatelimitException(Exception): pass
except ImportError:
    raise SystemExit("ddgs not installed. Run: pip install ddgs --break-system-packages")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

# ---------------------------------------------------------------------------
# Constants & Regex
# ---------------------------------------------------------------------------

PRESENTATION_RE = re.compile(r"\.pptx?($|[?#&\s])", re.IGNORECASE)
BITSTREAM_RE = re.compile(
    r"/(?:bitstream(?:/handle)?/[\d./]+|retrieve/\d+)/[^\"\'\s>{}\[\]\\]+\.pptx?",
    re.IGNORECASE,
)
RAW_PPT_URL_RE = re.compile(
    r"https?://[^\"\'\s>{}\[\]\\]+\.pptx?", re.IGNORECASE
)

SKIP_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".css", ".js", ".ico", ".zip", ".pdf", ".doc", ".docx",
    ".mp4", ".mp3", ".avi", ".mov", ".woff", ".ttf",
)

# Expanded India Academic Topics (60+)
TOPICS: List[str] = [
    "lecture slides", "research presentation", "seminar slides", "workshop presentation",
    "course notes presentation", "engineering lecture slides", "science presentation",
    "computer science slides", "machine learning lecture", "artificial intelligence",
    "data science", "robotics", "iot", "blockchain", "cybersecurity", "cloud computing",
    "physics lecture slides", "quantum physics", "thermodynamics", "optics", "nuclear physics",
    "chemistry lecture slides", "organic chemistry", "inorganic chemistry", "biochemistry",
    "biology lecture slides", "biotechnology", "microbiology", "genetics", "ecology",
    "mathematics lecture slides", "statistics lecture slides", "algebra", "calculus",
    "civil engineering", "electrical engineering", "mechanical engineering", "chemical engineering",
    "economics lecture slides", "management presentation", "medical lecture slides",
    "public health", "nursing presentation", "pharmacy lecture", "anatomy", "physiology",
    "history of india", "ancient india", "medieval india", "modern india", "political science",
    "sociology", "psychology", "geography", "environmental studies", "disaster management",
    "law presentation", "constitutional law", "intellectual property", "commerce", "accounting",
]

# Major Indian Academic Domains
SITE_DOMAINS: List[str] = [
    "site:ac.in", "site:gov.in", "site:res.in", "site:edu.in", "site:nic.in",
    "site:iitb.ac.in", "site:iitd.ac.in", "site:iitm.ac.in", "site:iitk.ac.in",
    "site:iitg.ac.in", "site:iitr.ac.in", "site:iitkgp.ac.in", "site:iisc.ac.in",
    "site:iiit.ac.in", "site:du.ac.in", "site:jnu.ac.in", "site:bhu.ac.in",
    "site:uohyd.ac.in", "site:bits-pilani.ac.in", "site:vit.ac.in",
    "site:manipal.edu", "site:amrita.edu", "site:nptel.ac.in",
]

def build_query_list() -> List[str]:
    """Return a massive list of prioritized queries for India."""
    queries: List[str] = []
    
    # 1. Broad Catch-all (Highest Priority)
    broad = ["site:ac.in", "site:gov.in", "site:res.in"]
    for b in broad:
        queries.append(f"filetype:pptx {b}")
        queries.append(f"filetype:ppt {b}")
        queries.append(f"lecture presentation filetype:pptx {b}")

    # 2. Topic × Domain matrix (Broad domains)
    for topic in TOPICS:
        queries.append(f'"{topic}" filetype:pptx site:ac.in')
        if random.random() < 0.2:
            queries.append(f'"{topic}" filetype:ppt site:ac.in')
    
    # 3. Specific University Shuffled
    remaining = []
    for domain in SITE_DOMAINS:
        if domain == "site:ac.in": continue
        for topic in ["lecture slides", "presentation", "course notes"]:
            remaining.append(f'"{topic}" filetype:pptx {domain}')
            
    random.shuffle(remaining)
    return queries + remaining

# ---------------------------------------------------------------------------
# Scraper Logic
# ---------------------------------------------------------------------------

class SearchEngineIndiaScraper:
    def __init__(
        self,
        out_dir: str = "downloaded_ppts_india",
        request_timeout: int = 20,
        delay_seconds: float = 1.5,
        verify_ssl: bool = True,
        max_results_per_query: int = 100,
    ):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = request_timeout
        self.delay = delay_seconds
        self.verify_ssl = verify_ssl
        self.max_results_per_query = max_results_per_query
        self.session = self._build_session()
        self._seen_urls: Set[str] = set()
        self._seen_tags: Set[str] = set()
        self._preload_seen_from_disk()

        if not verify_ssl:
            warnings.filterwarnings("ignore", category=urllib3.exceptions.InsecureRequestWarning)

    def _preload_seen_from_disk(self):
        if not self.out_dir.exists(): return
        count = 0
        for p in self.out_dir.glob("*_*"):
            tag = p.name.split("_")[0]
            if len(tag) == 10:
                self._seen_tags.add(tag)
                count += 1
        if count > 0:
            logger.info("Resuming: Preloaded %d existing files from disk.", count)

    def _build_session(self) -> requests.Session:
        s = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
        s.mount("https://", HTTPAdapter(max_retries=retries))
        s.mount("http://",  HTTPAdapter(max_retries=retries))
        s.headers.update({"User-Agent": "Mozilla/5.0 IndiaScraper/2.0 (Academic Research)"})
        return s

    def _search_ddgs(self, query: str) -> List[str]:
        found: List[str] = []
        for attempt in range(3):
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=self.max_results_per_query))
                for r in results:
                    href = r.get("href", "")
                    if href: found.append(href)
                break
            except RatelimitException:
                time.sleep(45 * (attempt + 1))
            except Exception as exc:
                if "Timeout" in str(exc) and attempt < 2:
                    time.sleep(5); continue
                break
        return found

    def _extract_from_page(self, url: str) -> List[str]:
        """Deep scan a page for embedded pptx links (DSpace support)."""
        try:
            resp = self.session.get(url, timeout=self.timeout, verify=self.verify_ssl)
            if not resp.ok or "html" not in resp.headers.get("Content-Type", "").lower():
                return []
            
            html = resp.text
            found = []
            for m in RAW_PPT_URL_RE.finditer(html): found.append(m.group(0))
            for m in BITSTREAM_RE.finditer(html): found.append(urljoin(url, m.group(0)))
            
            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if PRESENTATION_RE.search(href):
                    found.append(urljoin(url, href))
            return list(set(found))
        except: return []

    def _safe_filename(self, url: str) -> str:
        tag = hashlib.sha1(url.encode()).hexdigest()[:10]
        name = Path(urlparse(url).path).name or "file.pptx"
        if not name.lower().endswith((".pptx", ".ppt")): name += ".pptx"
        clean = re.sub(r'[^\w.\-]', '_', name)
        return tag, f"{tag}_{clean}"

    def _download(self, url: str) -> Optional[Path]:
        tag, fname = self._safe_filename(url)
        dest = self.out_dir / fname
        if dest.exists(): 
            self._seen_tags.add(tag)
            return dest
        try:
            resp = self.session.get(url, timeout=self.timeout, stream=True, verify=self.verify_ssl)
            if not resp.ok: return None
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(65536): f.write(chunk)
            logger.info("  Downloaded: %s (%d KB)", dest.name, dest.stat().st_size // 1024)
            return dest
        except: return None

    def scrape(self, target: int = 10000, follow_pages: bool = True):
        queries = build_query_list()
        count = 0
        
        logger.info("Starting India Scale-Up: Target=%d, Queries=%d", target, len(queries))
        
        for i, query in enumerate(queries, 1):
            if count >= target: break
            logger.info("[%d/%d] %s", i, len(queries), query)
            
            urls = self._search_ddgs(query)
            for url in urls:
                if count >= target: break
                
                tag = hashlib.sha1(url.encode()).hexdigest()[:10]
                if url in self._seen_urls or tag in self._seen_tags: continue
                self._seen_urls.add(url)
                
                to_download = []
                if PRESENTATION_RE.search(url):
                    to_download.append(url)
                elif follow_pages and not any(url.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
                    inner_urls = self._extract_from_page(url)
                    for iu in inner_urls:
                        itag = hashlib.sha1(iu.encode()).hexdigest()[:10]
                        if iu not in self._seen_urls and itag not in self._seen_tags:
                            to_download.append(iu)
                            self._seen_urls.add(iu)

                for dl_url in to_download:
                    if count >= target: break
                    logger.info("  [%d] %s", count+1, dl_url)
                    if self._download(dl_url):
                        count += 1
                    
            time.sleep(self.delay + random.uniform(0.1, 0.4))

def main():
    parser = argparse.ArgumentParser(description="India Academic PPTX Scraper (Scale-Up Edition)")
    parser.add_argument("--target", type=int, default=10000)
    parser.add_argument("--no-verify-ssl", action="store_true")
    parser.add_argument("--no-follow", action="store_true", help="Disable deep page scanning")
    args = parser.parse_args()

    # Default to NO-VERIFY for India as many institutional sites have expired certs
    scraper = SearchEngineIndiaScraper(verify_ssl=not args.no_verify_ssl)
    scraper.scrape(target=args.target, follow_pages=not args.no_follow)

if __name__ == "__main__":
    main()
