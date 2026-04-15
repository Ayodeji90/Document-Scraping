"""
Internet Archive scraper for PowerPoint files.

The Internet Archive (archive.org) contains millions of publicly-donated
documents including many academic and conference presentation PPT/PPTX files.

Approach:
  1. Search archive.org's advancedsearch API for items tagged with
     PowerPoint formats.
  2. For each matching item, fetch its metadata to get exact filenames.
  3. Construct the direct download URL and save the file.

API docs: https://archive.org/advancedsearch.php
Metadata:  https://archive.org/metadata/{identifier}
Download:  https://archive.org/download/{identifier}/{filename}
"""
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote

from .base import BaseScraper

logger = logging.getLogger(__name__)

SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL_TMPL = "https://archive.org/metadata/{}"
DOWNLOAD_URL_TMPL = "https://archive.org/download/{}/{}"

# Search queries tuned to yield academic/international PPT files
QUERIES = [
    'format:"Microsoft PowerPoint" subject:education',
    'format:"Microsoft PowerPoint" subject:science',
    'format:"Microsoft PowerPoint" subject:health',
    'format:"Microsoft PowerPoint" subject:technology',
    'format:"Microsoft PowerPoint" subject:environment',
    'format:"Microsoft PowerPoint" subject:economics',
    'format:"Microsoft PowerPoint" subject:conference',
    'format:"Microsoft PowerPoint" subject:research',
    'format:"Microsoft PowerPoint" subject:development',
    'format:"Microsoft PowerPoint" subject:energy',
    'format:"PowerPoint" conference presentation',
    'format:"PowerPoint" lecture slides university',
    'format:"PowerPoint" workshop seminar training',
    'format:"PowerPoint" United Nations WHO UNICEF',
    'format:"PowerPoint" academic journal publication',
]


class InternetArchiveScraper(BaseScraper):
    """Scraper for PowerPoint files hosted on the Internet Archive."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _search_items(self, query: str, rows: int = 50, start: int = 0) -> List[str]:
        """Return a list of item identifiers matching the query."""
        params = {
            "q": query,
            "fl[]": "identifier",
            "output": "json",
            "rows": rows,
            "start": start,
            "sort[]": "downloads desc",
        }
        data = self._fetch_json(SEARCH_URL, params=params, bypass_filter=True)
        if not data:
            return []
        docs = data.get("response", {}).get("docs", [])
        return [d["identifier"] for d in docs if "identifier" in d]

    def _get_ppt_files(self, identifier: str) -> List[Dict]:
        """Fetch item metadata; return PPT/PPTX file entries only."""
        url = METADATA_URL_TMPL.format(identifier)
        data = self._fetch_json(url, bypass_filter=True)
        if not data:
            return []

        item_title = data.get("metadata", {}).get("title", identifier)
        if isinstance(item_title, list):
            item_title = item_title[0]

        ppt_files = []
        for f in data.get("files", []):
            name = f.get("name", "")
            if name.lower().endswith((".ppt", ".pptx")):
                # Skip derivative files produced by IA (thumbnails etc.)
                if f.get("source", "original") in ("original", "derivative"):
                    ppt_files.append(
                        {
                            "identifier": identifier,
                            "filename": name,
                            "title": str(item_title)[:200],
                            "size": int(f.get("size", 0)),
                            "url": DOWNLOAD_URL_TMPL.format(
                                identifier, quote(name, safe="")
                            ),
                            "source": "internet_archive",
                        }
                    )
        return ppt_files

    def search(self, query: str = None, max_results: int = 100) -> List[Dict]:
        import random

        if not query:
            query = random.choice(QUERIES)

        results: List[Dict] = []
        rows = 50
        start = 0

        while len(results) < max_results:
            identifiers = self._search_items(query, rows=rows, start=start)
            if not identifiers:
                break

            for ident in identifiers:
                if len(results) >= max_results:
                    break
                files = self._get_ppt_files(ident)
                results.extend(files)

            if len(identifiers) < rows:
                break
            start += rows
            if start > 500:
                break  # Avoid excessively deep pagination

        return results[:max_results]

    def scrape(self, max_docs: int = 1500) -> List[Path]:
        downloaded: List[Path] = []
        logger.info(f"[InternetArchive] Starting — target {max_docs} files")

        for query in QUERIES:
            if len(downloaded) >= max_docs:
                break
            remaining = max_docs - len(downloaded)
            results = self.search(query, max_results=min(120, remaining + 20))

            for r in results:
                if len(downloaded) >= max_docs:
                    break
                ext = ".ppt" if r["filename"].lower().endswith(".ppt") else ".pptx"
                safe_title = re.sub(r"[^\w\-]", "_", r["title"][:80])
                safe_file = re.sub(r"[^\w\-.]", "_", r["filename"])
                filename = f"ia_{r['identifier']}_{safe_file}"

                meta = {
                    "source": "internet_archive",
                    "source_url": f"https://archive.org/details/{r['identifier']}",
                    "title": r["title"],
                    "identifier": r["identifier"],
                    "original_filename": r["filename"],
                    "query": query,
                }
                fp = self._download_file(r["url"], filename, meta)
                if fp:
                    downloaded.append(fp)
                    print(f"  [IA] {len(downloaded)}/{max_docs} — {fp.name}")

        stats = self.get_stats()
        logger.info(
            f"[InternetArchive] Done — downloaded={stats['downloaded']} "
            f"skipped={stats['skipped']} failed={stats['failed']}"
        )
        return downloaded
