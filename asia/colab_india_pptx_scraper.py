#!/usr/bin/env python3
"""
Google Colab Edition: India-focused PPTX Scraper (Search-Engine-Driven)

HOW TO RUN ON GOOGLE COLAB:
---------------------------
1. Open Google Colab (https://colab.research.google.com).
2. Create a new notebook.
3. In the first cell, install dependencies:
   !pip install ddgs beautifulsoup4 requests lxml

4. Upload this script to Colab or copy-paste the code into a cell.
5. Run the cell. It will:
   - Ask for permission to mount your Google Drive.
   - Automatically download .pptx and .ppt files to '/content/drive/MyDrive/downloaded_ppts_india'.

6. To customize (e.g. increase target), change the 'target' variable in the main() call at the bottom.
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
from typing import Iterator, List, Optional, Set
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Attempt to mount Google Drive if in Colab
try:
    from google.colab import drive
    print("Running in Google Colab. Mounting Google Drive...")
    drive.mount('/content/drive')
    DEFAULT_OUT_DIR = "/content/drive/MyDrive/downloaded_ppts_india"
except ImportError:
    DEFAULT_OUT_DIR = "downloaded_ppts_india"

try:
    from ddgs import DDGS
    try:
        from ddgs.exceptions import RatelimitException, DuckDuckGoSearchException
    except ImportError:
        class RatelimitException(Exception): pass
        class DuckDuckGoSearchException(Exception): pass
except ImportError:
    print("Error: 'ddgs' library not found. Please run: !pip install ddgs")
    DDGS = None

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex constants
# ---------------------------------------------------------------------------

PRESENTATION_RE = re.compile(r"\.pptx?($|[?#&\s])", re.IGNORECASE)
PPT_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

BITSTREAM_RE = re.compile(
    r"/(?:bitstream(?:/handle)?/[\d./]+|retrieve/\d+)/[^\"\'\s>{}\[\]\\]+\.pptx?",
    re.IGNORECASE,
)
RAW_PPT_URL_RE = re.compile(
    r"https?://[^\"\'\s>{}\[\]\\]+\.pptx?", re.IGNORECASE
)

SKIP_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".css", ".js", ".ico", ".woff", ".woff2", ".ttf",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".mp4", ".mp3", ".avi", ".mov",
)

# ---------------------------------------------------------------------------
# Query matrix
# ---------------------------------------------------------------------------

TOPICS: List[str] = [
    "lecture slides", "research presentation", "seminar slides",
    "workshop presentation", "course notes presentation",
    "engineering lecture slides", "science presentation",
    "computer science slides", "machine learning lecture",
    "physics lecture slides", "chemistry lecture slides",
    "biology lecture slides", "mathematics lecture slides",
    "statistics lecture slides", "economics lecture slides",
    "management presentation", "medical lecture slides",
    "civil engineering presentation", "electrical engineering slides",
    "mechanical engineering lecture", "data structures lecture",
    "algorithms lecture slides", "artificial intelligence slides",
    "environmental science slides", "biotechnology lecture slides",
]

SITE_DOMAINS: List[str] = [
    "site:ac.in", "site:gov.in", "site:res.in",
    "site:iitb.ac.in", "site:iitd.ac.in", "site:iitm.ac.in",
    "site:iitk.ac.in", "site:iitg.ac.in", "site:iitr.ac.in",
    "site:iitkgp.ac.in", "site:iisc.ac.in", "site:iiit.ac.in",
    "site:du.ac.in", "site:bits-pilani.ac.in", "site:vit.ac.in",
    "site:manipal.edu", "site:amrita.edu", "site:nptel.ac.in",
]

def build_query_list() -> List[str]:
    """Return a list of all topic×domain query strings, prioritizing broader domains."""
    queries: List[str] = []
    priority_domains = ["site:ac.in", "site:gov.in", "site:res.in"]
    
    for domain in priority_domains:
        for topic in TOPICS:
            queries.append(f'"{topic}" filetype:pptx {domain}')
            if random.random() < 0.2:
                queries.append(f'"{topic}" filetype:ppt {domain}')
    
    remaining_queries = []
    other_domains = [d for d in SITE_DOMAINS if d not in priority_domains]
    for domain in other_domains:
        for topic in TOPICS:
            remaining_queries.append(f'"{topic}" filetype:pptx {domain}')
    
    random.shuffle(remaining_queries)
    return queries + remaining_queries

# ---------------------------------------------------------------------------
# Main scraper
# ---------------------------------------------------------------------------

class SearchEngineIndiaScraper:
    def __init__(
        self,
        out_dir: str = DEFAULT_OUT_DIR,
        request_timeout: int = 20,
        delay_seconds: float = 1.0,
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
        """Scan the output directory and extract the 10-char hash tags from filenames."""
        if not self.out_dir.exists():
            return
        count = 0
        for p in self.out_dir.glob("*_*"):
            tag = p.name.split("_")[0]
            if len(tag) == 10:
                self._seen_tags.add(tag)
                count += 1
        if count > 0:
            print(f"Resuming: Preloaded {count} existing files from disk.")

    def _build_session(self) -> requests.Session:
        s = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
        s.mount("https://", HTTPAdapter(max_retries=retries))
        s.mount("http://",  HTTPAdapter(max_retries=retries))
        s.headers.update({"User-Agent": "Mozilla/5.0 (Colab; Linux x86_64) AppleWebKit/537.36"})
        return s

    def _get(self, url: str, **kwargs) -> Optional[requests.Response]:
        kwargs.setdefault("timeout", self.timeout)
        kwargs["verify"] = self.verify_ssl
        try:
            resp = self.session.get(url, **kwargs)
            return resp if resp.ok else None
        except:
            try:
                kwargs["verify"] = False
                resp = self.session.get(url, **kwargs)
                return resp if resp.ok else None
            except: return None

    def _safe_filename(self, url: str) -> str:
        name = Path(urlparse(url).path).name or "file.pptx"
        if not name.lower().endswith((".pptx", ".ppt")): name = f"{name}.pptx"
        clean = re.sub(r'[^\w.\-]', '_', name)
        tag = hashlib.sha1(url.encode()).hexdigest()[:10]
        return tag, f"{tag}_{clean}"

    def _search_ddgs(self, query: str) -> List[str]:
        if DDGS is None: return []
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
                time.sleep(30 * (attempt + 1))
            except: break
        return found

    def _extract_pptx_from_page(self, url: str) -> List[str]:
        resp = self._get(url)
        if not resp: return []
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if PRESENTATION_RE.search(resp.url) or PPT_MIME in ctype: return [resp.url]
        if "html" not in ctype: return []
        
        html = resp.text
        found: List[str] = []
        for m in RAW_PPT_URL_RE.finditer(html): found.append(m.group(0))
        for m in BITSTREAM_RE.finditer(html): found.append(urljoin(url, m.group(0)))
        
        soup = BeautifulSoup(html, "lxml")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if PRESENTATION_RE.search(href): found.append(urljoin(url, href))
        return list(set(found))

    def _download(self, url: str) -> Optional[Path]:
        tag, fname = self._safe_filename(url)
        dest = self.out_dir / fname
        if dest.exists() and dest.stat().st_size > 0:
            self._seen_tags.add(tag)
            return dest
        try:
            resp = self.session.get(url, timeout=self.timeout, stream=True, verify=self.verify_ssl)
            if not resp.ok: return None
            with open(dest, "wb") as fh:
                for chunk in resp.iter_content(65536): fh.write(chunk)
            if dest.stat().st_size == 0:
                dest.unlink(missing_ok=True)
                return None
            print(f"Downloaded: {dest.name} ({dest.stat().st_size // 1024} KB)")
            return dest
        except: return None

    def scrape(self, target: int = 7000, download: bool = True, follow_pages: bool = False):
        all_links: List[str] = []
        downloaded: List[Path] = []
        queries = build_query_list()
        
        print(f"Starting Scrape: Target={target}")
        
        for qi, query in enumerate(queries, 1):
            if len(all_links) >= target: break
            print(f"Query [{qi}/{len(queries)}]: {query}")
            
            raw_results = self._search_ddgs(query)
            for url in raw_results:
                if len(all_links) >= target: break
                
                tag = hashlib.sha1(url.encode()).hexdigest()[:10]
                if url in self._seen_urls or tag in self._seen_tags:
                    continue
                
                self._seen_urls.add(url)
                self._seen_tags.add(tag)

                if PRESENTATION_RE.search(url):
                    pptx_urls = [url]
                elif not follow_pages:
                    continue
                elif any(url.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
                    continue
                else:
                    pptx_urls = self._extract_pptx_from_page(url)
                    pptx_urls = [u for u in pptx_urls if u not in self._seen_urls and PRESENTATION_RE.search(u)]
                    for u in pptx_urls: self._seen_urls.add(u)

                for pptx_url in pptx_urls:
                    if len(all_links) >= target: break
                    all_links.append(pptx_url)
                    if download:
                        fp = self._download(pptx_url)
                        if fp: downloaded.append(fp)

            time.sleep(self.delay + random.uniform(0.1, 0.5))

        print(f"\nDONE! Discovered: {len(all_links)} new, Downloaded: {len(downloaded)}")
        return all_links, downloaded

def main():
    scraper = SearchEngineIndiaScraper(
        out_dir=DEFAULT_OUT_DIR,
        verify_ssl=False,
        max_results_per_query=100
    )
    scraper.scrape(target=10000, download=True, follow_pages=False)

if __name__ == "__main__":
    main()
