#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Nigeria-focused PPTX scraper — Search-Engine-Driven (Africa Series)
Discovers and downloads academic .pptx / .ppt files from Nigerian institutions (.ng).

Strategies:
  1. Priority focus on University of Lagos, University of Ibadan, Obafemi Awolowo University.
  2. English + Yoruba/Igbo academic keywords.
  3. Stealth Mode: 5.0s delay and 300-result depth.
  4. Deep Discovery: Follows HTML pages to find embedded bitstream links.
"""

import sys
import os
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import argparse
import hashlib
import logging
import random
import re
import time
import warnings
from pathlib import Path
from typing import List, Optional, Set
from urllib.parse import urljoin, urlparse

from src.utils.persistence import load_master_tags, save_new_tag
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

PRESENTATION_RE = re.compile(r"\.pptx?($|[?#&\s])", re.IGNORECASE)
BITSTREAM_RE = re.compile(
    r"/(?:bitstream(?:/handle)?/[\d./]+|retrieve/\d+|download/\d+|file|attachment|get)/[^\"'\s>{}[\]\\]+\.pptx?",
    re.IGNORECASE,
)
RAW_PPT_URL_RE = re.compile(r"https?://[^\"'\s>{}[\]\\]+\.pptx?", re.IGNORECASE)
SKIP_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".css", ".js", ".ico", ".zip", ".pdf", ".doc", ".docx",
    ".mp4", ".mp3", ".avi", ".mov", ".woff", ".ttf",
)

TOPICS: List[str] = [
    "lecture slides", "presentation", "course materials", "seminar", "tutorial",
    "computer science", "artificial intelligence", "machine learning", "deep learning",
    "engineering", "mechanical engineering", "electrical engineering", "civil engineering",
    "physics", "quantum mechanics", "thermodynamics", "optics",
    "chemistry", "organic chemistry", "biochemistry",
    "biology", "genetics", "biotechnology", "microbiology",
    "mathematics", "statistics", "calculus", "algebra",
    "medicine", "anatomy", "physiology", "pharmacology",
    "economics", "business administration", "marketing", "finance", "accounting",
    "history", "philosophy", "psychology", "sociology", "law", "political science",
    "agriculture", "petroleum engineering", "environmental science",
]

SITE_DOMAINS: List[str] = [
    "site:unilag.edu.ng",      # University of Lagos
    "site:ui.edu.ng",          # University of Ibadan
    "site:oauife.edu.ng",      # Obafemi Awolowo University
    "site:unn.edu.ng",         # University of Nigeria Nsukka
    "site:abu.edu.ng",         # Ahmadu Bello University
    "site:uniben.edu.ng",      # University of Benin
    "site:uniport.edu.ng",     # University of Port Harcourt
    "site:lasu.edu.ng",        # Lagos State University
    "site:covenantuniversity.edu.ng",  # Covenant University
    "site:lmu.edu.ng",         # Landmark University
]

def build_query_list() -> List[str]:
    queries: List[str] = []
    broad = ["site:edu.ng", "site:ac.ng", "site:unilag.edu.ng", "site:ui.edu.ng"]
    for b in broad:
        queries.append(f"filetype:pptx {b}")
        queries.append(f"filetype:ppt {b}")
        queries.append(f"lecture slides filetype:pptx {b}")

    remaining = []
    for domain in SITE_DOMAINS:
        for topic in TOPICS:
            remaining.append(f'"{topic}" filetype:pptx {domain}')
            if random.random() < 0.2:
                remaining.append(f'"{topic}" filetype:ppt {domain}')
    random.shuffle(remaining)
    return queries + remaining

class NigeriaScraper:
    def __init__(self, out_dir="downloaded_ppts_nigeria", request_timeout=45,
                 delay_seconds=2.0, verify_ssl=True, max_results_per_query=300):
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
        master_tags = load_master_tags()
        self._seen_tags.update(master_tags)
        if self.out_dir.exists():
            for p in self.out_dir.glob("*_*"):
                tag = p.name.split("_")[0]
                if len(tag) == 10: self._seen_tags.add(tag)
        if len(self._seen_tags) > 0:
            logger.info("Resuming: Loaded %d seen tags (Global + Local).", len(self._seen_tags))

    def _build_session(self) -> requests.Session:
        s = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
        s.mount("https://", HTTPAdapter(max_retries=retries))
        s.mount("http://", HTTPAdapter(max_retries=retries))
        s.headers.update({"User-Agent": "Mozilla/5.0 NG_Scraper/1.0 (Academic Research)"})
        return s


    def _search_bing(self, query):
        """Fallback search via Bing when DuckDuckGo is rate-limited."""
        found = []
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            url = f"https://www.bing.com/search?q={requests.utils.quote(query)}&count=50"
            resp = self.session.get(url, headers=headers, timeout=15, verify=self.verify_ssl)
            if resp.ok:
                soup = BeautifulSoup(resp.text, "lxml")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if PRESENTATION_RE.search(href) and href.startswith("http"):
                        found.append(href)
        except:
            pass
        return found

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
            except RatelimitException: time.sleep(45 * (attempt + 1))
            except Exception as exc:
                if "Timeout" in str(exc) and attempt < 2: time.sleep(5); continue
                break
        return found

    def _extract_from_page(self, url: str) -> List[str]:
        try:
            resp = self.session.get(url, timeout=self.timeout, verify=self.verify_ssl)
            if not resp.ok or "html" not in resp.headers.get("Content-Type", "").lower(): return []
            html = resp.text
            found = []
            for m in RAW_PPT_URL_RE.finditer(html): found.append(m.group(0))
            for m in BITSTREAM_RE.finditer(html): found.append(urljoin(url, m.group(0)))
            soup = BeautifulSoup(html, "lxml")
            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if PRESENTATION_RE.search(href): found.append(urljoin(url, href))
            return list(set(found))
        except: return []

    def _safe_filename(self, url: str):
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
            # Pre-check file size via HEAD request to avoid wasting bandwidth
            try:
                head = self.session.head(url, timeout=10, verify=self.verify_ssl, allow_redirects=True)
                cl = int(head.headers.get("Content-Length", 0))
                if 0 < cl < 2097152:  # Skip files confirmed under 5MB
                    return None
            except: pass
            resp = self.session.get(url, timeout=self.timeout, stream=True, verify=self.verify_ssl)
            if not resp.ok: return None
            if "text/html" in resp.headers.get("Content-Type", "").lower() and not PRESENTATION_RE.search(url): return None
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(65536): f.write(chunk)
            if dest.stat().st_size < 2097152:
                dest.unlink(missing_ok=True)
                return None
            save_new_tag(tag)
            logger.info("  Downloaded: %s (%d KB)", dest.name, dest.stat().st_size // 1024)
            return dest
        except: return None

    def scrape(self, target=10000, follow_pages=True):
        queries = build_query_list()
        count = 0
        logger.info("Starting Nigeria Scale-Up: Target=%d, Queries=%d", target, len(queries))
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
                if PRESENTATION_RE.search(url): to_download.append(url)
                elif follow_pages and not any(url.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
                    inner_urls = self._extract_from_page(url)
                    for iu in inner_urls:
                        itag = hashlib.sha1(iu.encode()).hexdigest()[:10]
                        if iu not in self._seen_urls and itag not in self._seen_tags:
                            to_download.append(iu); self._seen_urls.add(iu)
                for dl_url in to_download:
                    if count >= target: break
                    if self._download(dl_url):
                        count += 1
                        logger.info("  Total Downloaded: [%d]", count)
            time.sleep(self.delay + random.uniform(0.1, 0.4))

def main():
    parser = argparse.ArgumentParser(description="Nigeria Academic PPTX Scraper")
    parser.add_argument("--target", type=int, default=10000)
    parser.add_argument("--no-verify-ssl", action="store_true")
    parser.add_argument("--no-follow", action="store_true")
    args = parser.parse_args()
    scraper = NigeriaScraper(verify_ssl=not args.no_verify_ssl)
    scraper.scrape(target=args.target, follow_pages=not args.no_follow)

if __name__ == "__main__":
    main()
