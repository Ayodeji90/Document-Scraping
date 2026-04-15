"""
Figshare API scraper for PowerPoint presentations.

Confirmed item_type mapping (verified via live API, April 2026):
  1=Figure, 2=Media, 3=Dataset, 5=Poster, 6=Journal contribution,
  7=Presentation ✓, 8=Thesis, 9=Software, 11=Online resource,
  12=Preprint, 13=Book

Pagination: use 'page' + 'page_size' (NOT 'offset' + 'page_size').
"""
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from .base import BaseScraper

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.figshare.com/v2/articles/search"
FILES_URL_TMPL = "https://api.figshare.com/v2/articles/{}/files"

# Confirmed: 7=Presentation, 5=Poster (both carry PPT files)
PPT_ITEM_TYPES = [7, 5]

QUERIES = [
    "presentation conference workshop",
    "climate change environment",
    "machine learning artificial intelligence",
    "public health epidemiology medicine",
    "renewable energy solar wind",
    "economics finance development",
    "genetics genomics biology",
    "urban planning smart cities",
    "educational technology learning",
    "data science visualization",
    "materials engineering nanotechnology",
    "global health nutrition food",
    "political science governance policy",
    "astrophysics cosmology physics",
    "neuroscience brain cognitive",
]


class FigshareScraper(BaseScraper):
    """Scraper for Figshare presentation files via their public API v2."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _search_page(
        self, query: str, item_type: int, page: int, page_size: int = 25
    ) -> List[Dict]:
        """Search Figshare for one page of results."""
        payload = {
            "search_for": query,
            "item_type": item_type,
            "page_size": page_size,
            "page": page,
            "order": "published_date",
            "order_direction": "desc",
        }
        data = self._post_json(SEARCH_URL, payload, bypass_filter=True)
        if not data or not isinstance(data, list):
            return []
        return data

    def _get_ppt_files(self, article_id: int) -> List[Dict]:
        """Return only PPT/PPTX file entries for a given article."""
        url = FILES_URL_TMPL.format(article_id)
        data = self._fetch_json(url, bypass_filter=True)
        if not isinstance(data, list):
            return []
        return [
            f
            for f in data
            if isinstance(f, dict)
            and f.get("name", "").lower().endswith((".ppt", ".pptx"))
            and f.get("download_url")
        ]

    def search(self, query: str = None, max_results: int = 100) -> List[Dict]:
        import random

        if not query:
            query = random.choice(QUERIES)

        results: List[Dict] = []
        page_size = 25

        for item_type in PPT_ITEM_TYPES:
            page = 1
            while len(results) < max_results:
                articles = self._search_page(query, item_type, page, page_size)
                if not articles:
                    break

                for article in articles:
                    article_id = article.get("id")
                    title = article.get("title", "untitled")
                    ppt_files = self._get_ppt_files(article_id)

                    for f in ppt_files:
                        results.append(
                            {
                                "url": f["download_url"],
                                "title": title,
                                "filename": f.get("name", "file.pptx"),
                                "article_id": article_id,
                                "source": "figshare",
                                "item_type": item_type,
                                "query": query,
                            }
                        )
                        if len(results) >= max_results:
                            break
                    if len(results) >= max_results:
                        break

                if len(articles) < page_size:
                    break  # no more pages for this type/query
                page += 1
                if page > 20:
                    break  # safety cap: 500 articles max per query/type

        return results[:max_results]

    def scrape(self, max_docs: int = 1500) -> List[Path]:
        downloaded: List[Path] = []
        logger.info(f"[Figshare] Starting — target {max_docs} files")

        for query in QUERIES:
            if len(downloaded) >= max_docs:
                break
            remaining = max_docs - len(downloaded)
            # Request more candidates than needed to account for non-PPT articles
            results = self.search(query, max_results=min(200, remaining * 3))

            for r in results:
                if len(downloaded) >= max_docs:
                    break
                ext = ".ppt" if r["filename"].lower().endswith(".ppt") else ".pptx"
                safe = re.sub(r"[^\w\-]", "_", r["title"][:80])
                filename = f"figshare_{r['article_id']}_{safe}{ext}"
                meta = {
                    "source": "figshare",
                    "source_url": f"https://figshare.com/articles/presentation/{r['article_id']}",
                    "title": r["title"],
                    "query": r["query"],
                }
                fp = self._download_file(r["url"], filename, meta)
                if fp:
                    downloaded.append(fp)
                    print(f"  [Figshare] {len(downloaded)}/{max_docs} — {fp.name}")

        stats = self.get_stats()
        logger.info(
            f"[Figshare] Done — downloaded={stats['downloaded']} "
            f"skipped={stats['skipped']} failed={stats['failed']}"
        )
        return downloaded
