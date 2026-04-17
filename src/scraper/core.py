"""
CORE.ac.uk scraper for PowerPoint files.
"""
import logging
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

from .base import BaseScraper
from .keywords import ACADEMIC_DISCIPLINES

logger = logging.getLogger(__name__)

CORE_API = "https://api.core.ac.uk/v3/search/works"

class CoreScraper(BaseScraper):
    """Scraper for CORE.ac.uk aggregator."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # CORE v3 public limit is effectively low; we need to be polite
        self.api_delay = (5.0, 10.0) 

    def search_api(self, query: str, limit: int = 20, offset: int = 0) -> List[Dict]:
        """Search CORE for PPTX files."""
        # Query: find works with presentation in title/abstract AND pptx extension in references or links
        # Note: 'fullText' search for 'pptx' is a good heuristic
        q = f'"{query}" AND (fullText:"pptx" OR title:"presentation")'
        
        params = {
            "q": q,
            "limit": limit,
            "offset": offset,
        }
        
        data = self._fetch_json(CORE_API, params=params, bypass_filter=True)
        if not data or "results" not in data:
            return []

        results = []
        for item in data["results"]:
            # Check for download links
            download_url = item.get("downloadUrl")
            if not download_url:
                # Try to find in 'links'
                links = item.get("links", [])
                for link in links:
                    if link.get("type") == "download":
                        download_url = link.get("url")
                        break
            
            if not download_url:
                continue

            # We need to verify it's a PPTX by heading or filename
            # CORE often has PDFs too. We'll filter during download.
            name = item.get("title", "core_file")
            
            results.append({
                "url": download_url,
                "filename": name,
                "id": item.get("id"),
                "source": "core",
                "query": query,
            })
        return results

    def search(self, query: str = None, max_results: int = 50) -> List[Dict]:
        import random
        if not query:
            query = random.choice(ACADEMIC_DISCIPLINES)

        results: List[Dict] = []
        limit = 20
        offset = 0

        while len(results) < max_results:
            page = self.search_api(query, limit=limit, offset=offset)
            if not page:
                break
            results.extend(page)
            offset += limit
            if offset > 200: 
                break
            time.sleep(2) # Extra politeness for CORE

        return results[:max_results]

    def scrape(self, max_docs: int = 1500) -> List[Path]:
        downloaded: List[Path] = []
        logger.info(f"[CORE] Starting — target {max_docs} files")

        for query in ACADEMIC_DISCIPLINES:
            if len(downloaded) >= max_docs:
                break
            
            remaining = max_docs - len(downloaded)
            results = self.search(query, max_results=min(50, remaining + 5))

            for r in results:
                if len(downloaded) >= max_docs:
                    break
                
                # We don't know the extension for sure yet, so we append .pptx if missing
                # and let the download filter check the magic bytes/header
                name = re.sub(r"[^\w\-]", "_", r["filename"][:100])
                if not name.lower().endswith((".ppt", ".pptx")):
                    name += ".pptx"
                
                final_filename = f"core_{r['id']}_{name}"

                fp = self._download_file(r["url"], final_filename, meta=r)
                if fp:
                    downloaded.append(fp)
                    print(f"  [CORE] {len(downloaded)}/{max_docs} — {fp.name}")

        return downloaded
