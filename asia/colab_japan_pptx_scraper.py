#!/usr/bin/env python3
"""
Google Colab Edition: Japan-focused PPTX Scraper

HOW TO RUN:
1. Open Colab.
2. !pip install ddgs beautifulsoup4 requests
3. Run this script. It will mount Google Drive and save to 'downloaded_ppts_japan'.
"""

import hashlib
import os
import random
import re
import time
import warnings
from pathlib import Path
from typing import List, Optional, Set
from urllib.parse import urlparse

from src.utils.persistence import load_master_tags, save_new_tag
import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Attempt to mount Google Drive if in Colab
try:
    from google.colab import drive
    print("Mounting Google Drive...")
    drive.mount('/content/drive')
    DEFAULT_OUT_DIR = "/content/drive/MyDrive/downloaded_ppts_japan"
except ImportError:
    DEFAULT_OUT_DIR = "downloaded_ppts_japan"

try:
    from ddgs import DDGS
    from ddgs.exceptions import RatelimitException
except ImportError:
    print("Error: Run !pip install ddgs first")
    DDGS = None

PRESENTATION_RE = re.compile(r"\.pptx?($|[?#&\s])", re.IGNORECASE)

TOPICS = [
    "lecture slides", "講義", "スライド", "発表", "ゼミ", "演習",
    "研究発表", "資料", "教材", "講義ノート", "シンポジウム", "学会",
    "OCW", "research presentation", "人工知能", "機械学習", 
    "工学", "理学", "情報学", "医学", "経済学", "文学", "歴史"
]

DOMAINS = [
    "site:ac.jp", "site:go.jp", "site:ed.jp", "site:kyoto-u.ac.jp", 
    "site:u-tokyo.ac.jp", "site:osaka-u.ac.jp", "site:keio.ac.jp", 
    "site:waseda.jp", "site:u-air.ac.jp", "site:cir.nii.ac.jp",
    "site:irdb.nii.ac.jp", "site:data.go.jp", "site:e-stat.go.jp",
    "site:digital.go.jp", "site:mext.go.jp", "site:mhlw.go.jp",
    "site:slideshare.net"
]

def build_query_list():
    queries = []
    
    # 1. Broad Catch-all
    broad = [
        "site:ac.jp", "site:go.jp", "site:irdb.nii.ac.jp", "site:cir.nii.ac.jp",
        "site:data.go.jp", "site:e-stat.go.jp", "site:digital.go.jp", 
        "site:mext.go.jp", "site:mhlw.go.jp", "site:slideshare.net"
    ]
    for b in broad:
        queries.append(f"filetype:pptx {b}")
        queries.append(f"filetype:ppt {b}")
        queries.append(f"講義 スライド filetype:pptx {b}")

    # 2. Topic x Domain
    for domain in ["site:ac.jp", "site:go.jp"]:
        for topic in TOPICS:
            queries.append(f'"{topic}" filetype:pptx {domain}')
            
    # 3. Specific domains
    remaining = []
    for domain in DOMAINS:
        if domain in ["site:ac.jp", "site:go.jp"]: continue
        for topic in ["講義", "スライド", "lecture slides"]:
            remaining.append(f'"{topic}" filetype:pptx {domain}')
            
    random.shuffle(remaining)
    return queries + remaining

class JapanScraper:
    def __init__(self, out_dir=DEFAULT_OUT_DIR):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=3))
        self._seen = set()
        self._seen_tags = set()
        self._preload_seen_from_disk()

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

    def _search(self, q):
        if not DDGS: return []
        try:
            with DDGS() as ddgs:
                return [r['href'] for r in ddgs.text(q, max_results=300)]
        except: return []

    def _download(self, url):
        tag = hashlib.sha1(url.encode()).hexdigest()[:10]
        name = Path(urlparse(url).path).name or 'f.pptx'
        if not name.lower().endswith((".pptx", ".ppt")): name += ".pptx"
        clean = re.sub(r'[^\w.\-]', '_', name)
        fname = f"{tag}_{clean}"
        dest = self.out_dir / fname
        
        if dest.exists() and dest.stat().st_size > 0:
            self._seen_tags.add(tag)
            return
            
        try:
            resp = self.session.get(url, timeout=20, stream=True, verify=False)
            if resp.ok:
                with open(dest, "wb") as f:
                    for c in resp.iter_content(65536): f.write(c)
                print(f"  Saved: {fname}")
        except: pass

    def run(self, target=10000):
        qs = build_query_list()
        count = 0
        for i, q in enumerate(qs, 1):
            if count >= target: break
            print(f"[{i}/{len(qs)}] {q}")
            urls = self._search(q)
            for u in urls:
                if count >= target: break
                
                tag = hashlib.sha1(u.encode()).hexdigest()[:10]
                if u in self._seen or tag in self._seen_tags: continue
                
                self._seen.add(u)
                self._seen_tags.add(tag)
                
                if not PRESENTATION_RE.search(u): continue
                self._download(u)
                count += 1
            time.sleep(1)

if __name__ == "__main__":
    JapanScraper().run()
