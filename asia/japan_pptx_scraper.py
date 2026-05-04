#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Japan-focused PPTX scraper — Search-Engine-Driven (v2 - SCALE UP)
Discovers and downloads academic .pptx / .ppt files from Japanese institutions (.ac.jp).

Strategies for 10,000+ files:
  1. Massive bilingual query matrix (70+ topics).
  2. Deep Discovery: Follows HTML pages to find embedded bitstream links.
  3. National aggregator targets (IRDB, JAIRO).
  4. Broad wildcard domains (site:*.ac.jp).
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

# Expanded Japanese Academic Topics (70+)
TOPICS: List[str] = [
    "lecture slides", "presentation", "research presentation", "conference slides",
    "講義", "スライド", "発表", "ゼミ", "演習", "研究発表", "資料", "教材", "講義ノート",
    "人工知能", "機械学習", "アルゴリズム", "データ構造", "ロボット工学", "制御工学",
    "情報理論", "ネットワーク", "セキュリティ", "データベース", "ソフトウェア工学",
    "物理学", "量子力学", "相対性理論", "熱力学", "光学", "素粒子物理学",
    "化学", "有機化学", "無機化学", "分析化学", "物理化学", "生化学",
    "生物学", "分子生物学", "細胞生物学", "遺伝学", "生態学", "進化学",
    "医学", "解剖学", "生理学", "薬理学", "内科学", "外科学", "公衆衛生",
    "数学", "代数学", "幾何学", "解析学", "統計学", "応用数学",
    "工学", "機械工学", "電気工学", "電子工学", "土木工学", "建築学",
    "経済学", "ミクロ経済", "マクロ経済", "計量経済", "経営学", "会計学",
    "法学", "憲法", "民法", "刑法", "国際法", "政治学", "行政学",
    "文学", "日本文学", "英文学", "比較文学", "言語学", "哲学", "倫理学",
    "歴史学", "日本史", "世界史", "考古学", "地理学", "社会学", "心理学",
    "教育学", "教育心理", "特別支援教育", "芸術", "美術史", "音楽学",
]

# Major Japanese Academic Domains
SITE_DOMAINS: List[str] = [
    "site:ac.jp", "site:go.jp", "site:ed.jp", "site:res.jp",
    "site:kyoto-u.ac.jp", "site:u-tokyo.ac.jp", "site:osaka-u.ac.jp",
    "site:tohoku.ac.jp", "site:keio.ac.jp", "site:titech.ac.jp",
    "site:waseda.jp", "site:nagoya-u.ac.jp", "site:kyushu-u.ac.jp",
    "site:hokudai.ac.jp", "site:tsukuba.ac.jp", "site:kobe-u.ac.jp",
    "site:hiroshima-u.ac.jp", "site:nii.ac.jp", "site:irdb.nii.ac.jp",
    "site:cir.nii.ac.jp", "site:data.go.jp", "site:e-stat.go.jp",
    "site:digital.go.jp", "site:mext.go.jp", "site:mhlw.go.jp",
    "site:slideshare.net",
]

def build_query_list() -> List[str]:
    """Return a massive list of prioritized queries for Japan."""
    queries: List[str] = []
    
    # 1. Broad Catch-all (Highest Priority)
    broad = [
        "site:ac.jp", "site:go.jp", "site:irdb.nii.ac.jp", "site:cir.nii.ac.jp",
        "site:data.go.jp", "site:e-stat.go.jp", "site:digital.go.jp", 
        "site:mext.go.jp", "site:mhlw.go.jp", "site:slideshare.net"
    ]
    for b in broad:
        queries.append(f"filetype:pptx {b}")
        queries.append(f"filetype:ppt {b}")
        queries.append(f"講義 スライド filetype:pptx {b}")

    # 2. Bilingual Topic × Domain matrix
    # We focus on ac.jp first as it has 90% of materials
    for topic in TOPICS:
        queries.append(f'"{topic}" filetype:pptx site:ac.jp')
        if random.random() < 0.2:
            queries.append(f'"{topic}" filetype:ppt site:ac.jp')
    
    # 3. University-specific Shuffled
    remaining = []
    for domain in SITE_DOMAINS:
        if domain == "site:ac.jp": continue
        for topic in ["講義", "スライド", "lecture slides"]:
            remaining.append(f'"{topic}" filetype:pptx {domain}')
            
    random.shuffle(remaining)
    return queries + remaining

# ---------------------------------------------------------------------------
# Scraper Logic
# ---------------------------------------------------------------------------

class SearchEngineJapanScraper:
    def __init__(
        self,
        out_dir: str = "downloaded_ppts_japan",
        request_timeout: int = 20,
        delay_seconds: float = 1.2,
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
            print(f"Resuming: Preloaded {count} existing files from disk.")

    def _build_session(self) -> requests.Session:
        s = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
        s.mount("https://", HTTPAdapter(max_retries=retries))
        s.headers.update({"User-Agent": "Mozilla/5.0 JapanScraper/2.0 (Academic Research)"})
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
        """Deep scan a page for embedded pptx links (DSpace/WEKO support)."""
        try:
            resp = self.session.get(url, timeout=self.timeout, verify=self.verify_ssl)
            if not resp.ok or "html" not in resp.headers.get("Content-Type", "").lower():
                return []
            
            html = resp.text
            found = []
            # 1. Regex for raw links
            for m in RAW_PPT_URL_RE.finditer(html): found.append(m.group(0))
            for m in BITSTREAM_RE.finditer(html): found.append(urljoin(url, m.group(0)))
            
            # 2. BeautifulSoup for <a> tags
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
            print(f"  Downloaded: {dest.name} ({dest.stat().st_size // 1024} KB)")
            return dest
        except: return None

    def scrape(self, target: int = 10000, follow_pages: bool = True):
        queries = build_query_list()
        count = 0
        
        print(f"Starting Japan Scale-Up: Target={target}, Queries={len(queries)}")
        
        for i, query in enumerate(queries, 1):
            if count >= target: break
            print(f"[{i}/{len(queries)}] {query}")
            
            urls = self._search_ddgs(query)
            for url in urls:
                if count >= target: break
                
                tag = hashlib.sha1(url.encode()).hexdigest()[:10]
                if url in self._seen_urls or tag in self._seen_tags: continue
                self._seen_urls.add(url)
                
                # Discovery logic
                to_download = []
                if PRESENTATION_RE.search(url):
                    to_download.append(url)
                elif follow_pages and not any(url.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
                    # It's an HTML page, look inside
                    inner_urls = self._extract_from_page(url)
                    for iu in inner_urls:
                        itag = hashlib.sha1(iu.encode()).hexdigest()[:10]
                        if iu not in self._seen_urls and itag not in self._seen_tags:
                            to_download.append(iu)
                            self._seen_urls.add(iu)

                for dl_url in to_download:
                    if count >= target: break
                    print(f"  [{count+1}] {dl_url}")
                    if self._download(dl_url):
                        count += 1
                    
            time.sleep(self.delay + random.uniform(0.1, 0.4))

def main():
    parser = argparse.ArgumentParser(description="Japan Academic PPTX Scraper (Scale-Up Edition)")
    parser.add_argument("--target", type=int, default=10000)
    parser.add_argument("--no-verify-ssl", action="store_true")
    parser.add_argument("--no-follow", action="store_true", help="Disable deep page scanning")
    args = parser.parse_args()

    scraper = SearchEngineJapanScraper(verify_ssl=not args.no_verify_ssl)
    scraper.scrape(target=args.target, follow_pages=not args.no_follow)

if __name__ == "__main__":
    main()
