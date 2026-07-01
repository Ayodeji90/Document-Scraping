"""
Harvard Dataverse scraper for PowerPoint files.
"""
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional

from .base import BaseScraper
from .keywords import ACADEMIC_DISCIPLINES
from src.metadata import build_metadata_from_api

logger = logging.getLogger(__name__)

# International Dataverse Instances (Direct API Endpoints)
INTERNATIONAL_DATAVERSES = [
    "https://dataverse.no",           # DataverseNO (Norway / EU) - Reliable
    "https://heidata.uni-heidelberg.de", # HeiDATA (Germany / EU)
    "https://dataverse.uclouvain.be",  # UCLouvain (Belgium / EU)
    "https://dataverse.nl",           # DataverseNL (Netherlands / EU) - 403 prone but large
    "https://dataverse.fudan.edu.cn",  # Fudan (China / Asia)
    "https://opendata.pku.edu.cn",     # Peking Uni (China / Asia)
    "https://data.mendeley.com/api/research-data/datasets" # Mendeley Data (Fallback)
]

DOWNLOAD_TMPL = "{}/api/access/datafile/{}"

class DataverseScraper(BaseScraper):
    """Scraper for International Dataverse repositories."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_instance = INTERNATIONAL_DATAVERSES[0]

    def search_api(self, query: str, rows: int = 100, start: int = 0) -> List[Dict]:
        """Search current Dataverse instance for PPT/PPTX files."""
        # Use filter query for file extensions
        params = {
            "q": query,
            "type": "file",
            "fq": "fileExtension:pptx", 
            "per_page": rows,
            "start": start,
        }
        
        search_url = f"{self.current_instance}/api/search"
        try:
            data = self._fetch_json(search_url, params=params, bypass_filter=True)
            
            if not data or data.get("status") != "OK":
                params["fq"] = "fileExtension:ppt"
                data = self._fetch_json(search_url, params=params, bypass_filter=True)
                if not data or data.get("status") != "OK":
                    return []
        except Exception as e:
            logger.warning(f"Failed to search Dataverse instance {self.current_instance}: {e}")
            return []

        items = data.get("data", {}).get("items", [])
        results = []
        for item in items:
            file_id = item.get("file_id")
            if not file_id:
                continue
                
            name = item.get("name", "file.pptx")
            if not name.lower().endswith((".ppt", ".pptx")):
                continue

            results.append({
                "url": DOWNLOAD_TMPL.format(self.current_instance, file_id),
                "filename": name,
                "title": item.get("description", item.get("dataset_name", name)),
                "file_id": file_id,
                "source": "dataverse",
                "query": query,
            })
        return results

    def search(self, query: str = None, max_results: int = 100) -> List[Dict]:
        import random
        if not query:
            query = random.choice(ACADEMIC_DISCIPLINES)

        results: List[Dict] = []
        rows = 100
        start = 0

        while len(results) < max_results:
            page = self.search_api(query, rows=rows, start=start)
            if not page:
                break
            results.extend(page)
            start += rows
            if start > 500: # Safety cap per keyword
                break

        return results[:max_results]

    def scrape(self, max_docs: int = 1500) -> List[Path]:
        downloaded: List[Path] = []
        logger.info(f"[Dataverse] Starting — target {max_docs} files")

        # Cycle through international instances
        for instance in INTERNATIONAL_DATAVERSES:
            if len(downloaded) >= max_docs:
                break
                
            self.current_instance = instance
            logger.info(f"[Dataverse] Switching to instance: {instance}")
            
            error_count = 0
            try:
                # Use broad disciplines for coverage
                for query in ACADEMIC_DISCIPLINES:
                    if len(downloaded) >= max_docs or error_count > 5:
                        break
                    
                    remaining = max_docs - len(downloaded)
                    # Use a smaller search per query to cycle faster through instances
                    results = self.search(query, max_results=min(20, remaining))

                    for r in results:
                        if len(downloaded) >= max_docs:
                            break
                        
                        # Sanitize filename
                        safe_title = re.sub(r"[^\w\-]", "_", r["title"][:60])
                        safe_name = re.sub(r"[^\w\-.]", "_", r["filename"])
                        final_filename = f"dataverse_{r['file_id']}_{safe_title}_{safe_name}"
                        if len(final_filename) > 200:
                            final_filename = final_filename[:190] + Path(r["filename"]).suffix

                        meta = build_metadata_from_api("dataverse", r, r["url"], final_filename)
                        fp = self._download_file(r["url"], final_filename, meta)
                        if fp:
                            downloaded.append(fp)
                            print(f"  [Dataverse] {len(downloaded)}/{max_docs} — {fp.name}")
            except Exception as e:
                logger.error(f"[Dataverse] Error on instance {instance}: {e}")
                continue

        return downloaded
