"""
HAL (Archives Ouvertes) scraper for PowerPoint files.

Key facts verified April 2026:
  - `fileMainFormat_s` is NEVER indexed — cannot filter by it.
  - `files_s` is a list of direct file URLs: https://hal.science/{id}/file/{name}
  - We fetch `files_s` and filter client-side by URL extension (.ppt/.pptx).
"""
import logging
import re
from pathlib import Path
from typing import Dict, List
from urllib.parse import unquote

from .base import BaseScraper
from src.metadata import build_metadata_from_api

logger = logging.getLogger(__name__)

HAL_SEARCH = "https://api.archives-ouvertes.fr/search/"

QUERIES = [
    "conference presentation",
    "slides conférence",
    "séminaire exposé",
    "workshop tutorial",
    "lecture cours",
    "symposium colloque",
    "powerpoint pptx",
    "présentation scientifique",
    "research presentation",
    "talk science",
    "journée étude",
    "school summer winter",
    "invited talk keynote",
    "communications poster",
    "colloque journée",
]


class HALScraper(BaseScraper):
    """Scraper for HAL using their Solr API with files_s field."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _is_ppt_url(self, url: str) -> bool:
        path = url.split("?")[0].lower()
        return path.endswith(".ppt") or path.endswith(".pptx")

    def _ext_from_url(self, url: str) -> str:
        path = unquote(url.split("?")[0]).lower()
        return ".ppt" if path.endswith(".ppt") else ".pptx"

    def search_api(self, query: str, rows: int = 100, start: int = 0) -> List[Dict]:
        params = {
            "q": query,
            "fl": "halId_s,title_s,files_s,producedDate_tdate",
            "wt": "json",
            "rows": rows,
            "start": start,
            "sort": "producedDate_tdate desc",
        }
        data = self._fetch_json(HAL_SEARCH, params=params, bypass_filter=True)
        if not data:
            return []

        docs = data.get("response", {}).get("docs", [])
        results = []

        for doc in docs:
            hal_id = doc.get("halId_s", "")
            titles = doc.get("title_s") or ["untitled"]
            title = titles[0] if isinstance(titles, list) else str(titles)
            files_s = doc.get("files_s") or []
            if isinstance(files_s, str):
                files_s = [files_s]

            for file_url in files_s:
                if self._is_ppt_url(file_url):
                    record = dict(doc)
                    record.update({
                        "url": file_url,
                        "title": title[:200],
                        "hal_id": hal_id,
                        "ext": self._ext_from_url(file_url),
                        "source": "hal",
                        "query": query,
                    })
                    results.append(record)
        return results

    def search(self, query: str = None, max_results: int = 100) -> List[Dict]:
        import random
        if not query:
            query = random.choice(QUERIES)

        results: List[Dict] = []
        rows = 100
        start = 0

        while len(results) < max_results:
            page = self.search_api(query, rows=rows, start=start)
            if not page:
                break
            results.extend(page)
            start += rows
            if start > 2000:
                break

        return results[:max_results]

    def scrape(self, max_docs: int = 1500) -> List[Path]:
        downloaded: List[Path] = []
        logger.info(f"[HAL] Starting — target {max_docs} files")

        for query in QUERIES:
            if len(downloaded) >= max_docs:
                break
            remaining = max_docs - len(downloaded)
            results = self.search(query, max_results=min(100, remaining + 10))

            for r in results:
                if len(downloaded) >= max_docs:
                    break
                ext = r["ext"]
                safe = re.sub(r"[^\w\-]", "_", r["title"][:80])
                hal_safe = re.sub(r"[^\w\-]", "_", r["hal_id"])
                filename = f"hal_{hal_safe}_{safe}{ext}"
                
                # Build rich metadata
                meta = build_metadata_from_api("hal", r, r["url"], filename)
                
                fp = self._download_file(r["url"], filename, meta)
                if fp:
                    downloaded.append(fp)
                    print(f"  [HAL] {len(downloaded)}/{max_docs} — {fp.name}")

        stats = self.get_stats()
        logger.info(f"[HAL] Done — {stats}")
        return downloaded
