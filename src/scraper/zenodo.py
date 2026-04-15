"""
Zenodo scraper for PowerPoint files.

Key facts verified April 2026:
  - Query  : filename:*.pptx returns 16,490+ records, every hit has a PPT file inline.
  - Files  : returned inline in `record['files']` as a list of
             {key, links: {self: '.../{filename}'}, size, checksum}
  - Download URL: links.self + '/content'  (NOT links.self alone — that's metadata)
"""
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from .base import BaseScraper

logger = logging.getLogger(__name__)

API_SEARCH = "https://zenodo.org/api/records"

# Verified: every hit from filename:*.pptx has an actual PPTX file inline
QUERIES = [
    "filename:*.pptx",
    "filename:*.ppt",
    "filename:*.pptx resource_type.type:presentation",
    "filename:*.pptx climate",
    "filename:*.pptx health medicine",
    "filename:*.pptx machine learning",
    "filename:*.pptx economics finance",
    "filename:*.pptx biology ecology",
    "filename:*.pptx education university",
    "filename:*.pptx engineering technology",
    "filename:*.pptx environment renewable",
    "filename:*.pptx social science",
    "filename:*.pptx urban development",
    "filename:*.ppt conference workshop",
]


class ZenodoScraper(BaseScraper):
    """Scraper for Zenodo open-access repository."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _extract_ppt_files(self, record: Dict) -> List[Dict]:
        """
        Extract PPT/PPTX entries from a Zenodo record.

        API response (April 2026): record['files'] is a list of:
          {"key": "file.pptx", "links": {"self": "https://zenodo.org/api/records/{id}/files/{name}"}}

        Download URL = links['self'] + '/content'
        """
        ppt_files = []
        files_obj = record.get("files")

        if isinstance(files_obj, list):
            for entry in files_obj:
                key = entry.get("key", "")
                if key.lower().endswith((".ppt", ".pptx")):
                    links = entry.get("links", {})
                    self_url = links.get("self", "")
                    # Append /content to get the actual binary download
                    if self_url and not self_url.endswith("/content"):
                        url = self_url + "/content"
                    else:
                        url = self_url or links.get("content")
                    if url:
                        ppt_files.append({"key": key, "url": url})

        elif isinstance(files_obj, dict):
            entries = files_obj.get("entries", {})
            items = entries.items() if isinstance(entries, dict) else enumerate(entries)
            for key_or_idx, entry in items:
                key = entry.get("key", str(key_or_idx))
                if key.lower().endswith((".ppt", ".pptx")):
                    links = entry.get("links", {})
                    self_url = links.get("self", "")
                    url = (self_url + "/content") if self_url and not self_url.endswith("/content") else (self_url or links.get("content"))
                    if url:
                        ppt_files.append({"key": key, "url": url})

        return ppt_files

    def search(self, query: str = None, max_results: int = 100) -> List[Dict]:
        import random
        if not query:
            query = random.choice(QUERIES)

        results: List[Dict] = []
        page = 1
        page_size = 25

        while len(results) < max_results:
            params = {
                "q": query,
                "sort": "mostrecent",
                "page": page,
                "size": page_size,
                "access_right": "open",
            }
            data = self._fetch_json(API_SEARCH, params=params, bypass_filter=True)
            if not data:
                break

            hits = data.get("hits", {}).get("hits", [])
            if not hits:
                break

            for record in hits:
                record_id = record.get("id")
                meta = record.get("metadata", {})
                title = meta.get("title", "untitled")
                ppt_files = self._extract_ppt_files(record)

                for f in ppt_files:
                    results.append({
                        "url": f["url"],
                        "key": f["key"],
                        "title": title,
                        "record_id": record_id,
                        "source": "zenodo",
                        "query": query,
                    })
                    if len(results) >= max_results:
                        break
                if len(results) >= max_results:
                    break

            if len(hits) < page_size:
                break
            page += 1
            if page > 20:
                break

        return results[:max_results]

    def scrape(self, max_docs: int = 1500) -> List[Path]:
        downloaded: List[Path] = []
        logger.info(f"[Zenodo] Starting — target {max_docs} files")

        for query in QUERIES:
            if len(downloaded) >= max_docs:
                break
            remaining = max_docs - len(downloaded)
            results = self.search(query, max_results=min(100, remaining + 10))

            for r in results:
                if len(downloaded) >= max_docs:
                    break
                ext = ".ppt" if r["key"].lower().endswith(".ppt") else ".pptx"
                safe = re.sub(r"[^\w\-]", "_", r["title"][:80])
                filename = f"zenodo_{r['record_id']}_{safe}{ext}"
                fp = self._download_file(r["url"], filename)
                if fp:
                    downloaded.append(fp)
                    print(f"  [Zenodo] {len(downloaded)}/{max_docs} — {fp.name}")

        stats = self.get_stats()
        logger.info(f"[Zenodo] Done — {stats}")
        return downloaded
