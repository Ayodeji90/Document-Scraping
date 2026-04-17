"""
GitHub scraper for PowerPoint files hosted in repositories.
"""
import logging
import re
import base64
from pathlib import Path
from typing import Dict, List, Optional

from .base import BaseScraper
from .keywords import ACADEMIC_DISCIPLINES

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com/search/code"

class GitHubScraper(BaseScraper):
    """Scraper for GitHub repositories."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # GitHub Search API is rate-limited to 10 requests per minute for unauthenticated
        # We'll be very slow
        self.api_delay = (6.0, 10.0)

    def search_api(self, query: str, page: int = 1) -> List[Dict]:
        """Search GitHub for PPT/PPTX files."""
        # Query must have a keyword
        q = f'extension:pptx {query}'
        
        params = {
            "q": q,
            "page": page,
            "per_page": 100,
        }
        
        headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        
        data = self._fetch_json(GITHUB_API, params=params, headers=headers, bypass_filter=True)
        if not data or "items" not in data:
            return []

        results = []
        for item in data["items"]:
            # item['path'] is the path in the repo
            # item['repository']['full_name']
            repo = item.get("repository", {}).get("full_name")
            path = item.get("path")
            if not repo or not path:
                continue
                
            # Raw URL: https://raw.githubusercontent.com/{repo}/master/{path}
            # Note: master might be main. We can use the 'html_url' and replace blob/ with raw/
            html_url = item.get("html_url")
            if not html_url:
                continue
            
            download_url = html_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
            
            results.append({
                "url": download_url,
                "filename": Path(path).name,
                "repo": repo,
                "source": "github",
                "query": query,
            })
        return results

    def search(self, query: str = None, max_results: int = 50) -> List[Dict]:
        import random
        if not query:
            query = random.choice(ACADEMIC_DISCIPLINES)

        results: List[Dict] = []
        page = 1

        while len(results) < max_results:
            batch = self.search_api(query, page=page)
            if not batch:
                break
            results.extend(batch)
            page += 1
            if page > 5: # GitHub limit for code search is often restricted
                break

        return results[:max_results]

    def scrape(self, max_docs: int = 1500) -> List[Path]:
        downloaded: List[Path] = []
        logger.info(f"[GitHub] Starting — target {max_docs} files")

        for query in ACADEMIC_DISCIPLINES:
            if len(downloaded) >= max_docs:
                break
            
            remaining = max_docs - len(downloaded)
            results = self.search(query, max_results=min(30, remaining + 5))

            for r in results:
                if len(downloaded) >= max_docs:
                    break
                
                # Sanitize filename
                repo_safe = r["repo"].replace("/", "_")
                final_filename = f"github_{repo_safe}_{r['filename']}"
                if len(final_filename) > 200:
                    final_filename = final_filename[:190] + Path(r["filename"]).suffix

                fp = self._download_file(r["url"], final_filename, meta=r)
                if fp:
                    downloaded.append(fp)
                    print(f"  [GitHub] {len(downloaded)}/{max_docs} — {fp.name}")

        return downloaded
