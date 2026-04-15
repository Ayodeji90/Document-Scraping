"""
Internet Archive scraper for PowerPoint files.

Uses:
  1. archive.org/advancedsearch.php — search for items with PowerPoint format
  2. archive.org/metadata/{id}     — get exact filenames per item
  3. archive.org/download/{id}/{f} — direct file download
"""
import logging
import re
from pathlib import Path
from typing import Dict, List, Set
from urllib.parse import quote

from .base import BaseScraper

logger = logging.getLogger(__name__)

SEARCH_URL = "https://archive.org/advancedsearch.php"
METADATA_URL_TMPL = "https://archive.org/metadata/{}"
DOWNLOAD_URL_TMPL = "https://archive.org/download/{}/{}"

# IA item identifiers we have already fully processed — skip to avoid hangs
SKIP_IDENTIFIERS: Set[str] = {
    "2019-nCoV", "25YearsOfMindfulnessPracticeWithASpinalInjury-WhyIDeveloped",
    "AccompanyingPowerpointSlidesFortheMultiverseWhosAfraid", "ai-and-art-libraries",
    "ANA-BNA-DIG-ACURIL-SLAVERY-DATABASE-2024", "BrewsterKahleSlovenianPresentation5-13-2008",
    "brucon2010slides", "comm-academy", "day2", "dplbirthday", "eme2020",
    "FoundationHousing", "HenryWill", "ICNC2019", "LawStudentsTweetingBadly",
    "pda2017", "platform-2000-11-8-2000-conference-spokane-resources-and-presentation-content",
    "RoguelikeCelebration2021", "RoguelikeCelebration2022",
    "shmoocon2006slides", "shmoocon2007slides", "shmoocon2009slides", "shmoocon2010slides",
    "SvetlanaC", "viva-frei-check-out-this-guy-12-ppg-flyers",
    "wamea-presentation-march-2022", "WesternInfluencesAndNationalChar18thHunWomen",
    "zooming_in_2020-08",
}

QUERIES = [
    'format:"Microsoft PowerPoint" subject:medicine',
    'format:"Microsoft PowerPoint" subject:biology',
    'format:"Microsoft PowerPoint" subject:engineering',
    'format:"Microsoft PowerPoint" subject:agriculture',
    'format:"Microsoft PowerPoint" subject:law',
    'format:"Microsoft PowerPoint" subject:climate',
    'format:"Microsoft PowerPoint" subject:nutrition',
    'format:"Microsoft PowerPoint" subject:psychology',
    'format:"Microsoft PowerPoint" subject:sociology',
    'format:"Microsoft PowerPoint" subject:architecture',
    'format:"Microsoft PowerPoint" subject:physics',
    'format:"Microsoft PowerPoint" subject:chemistry',
    'format:"Microsoft PowerPoint" subject:mathematics',
    'format:"Microsoft PowerPoint" subject:geography',
    'format:"Microsoft PowerPoint" subject:history',
    'format:"Microsoft PowerPoint" subject:economics',
    'format:"Microsoft PowerPoint" subject:management',
    'format:"Microsoft PowerPoint" subject:communications',
    'format:"Microsoft PowerPoint" subject:nonprofit',
    'format:"Microsoft PowerPoint" subject:policy',
    'format:"PowerPoint" medical hospital clinical',
    'format:"PowerPoint" renewable solar wind energy',
    'format:"PowerPoint" artificial intelligence machine learning',
    'format:"PowerPoint" United Nations development goals',
    'format:"PowerPoint" water sanitation environment',
    'format:"PowerPoint" training safety emergency',
    'format:"PowerPoint" literacy reading curriculum',
    'format:"PowerPoint" biodiversity conservation wildlife',
    'format:"PowerPoint" financial management accounting',
    'format:"PowerPoint" human rights social justice',
]


class InternetArchiveScraper(BaseScraper):
    """Scraper for Internet Archive PowerPoint files."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _search_items(self, query: str, rows: int = 50, start: int = 0) -> List[str]:
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
        return [
            d["identifier"] for d in docs
            if "identifier" in d and d["identifier"] not in SKIP_IDENTIFIERS
        ]

    def _get_ppt_files(self, identifier: str) -> List[Dict]:
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
                ppt_files.append({
                    "identifier": identifier,
                    "filename": name,
                    "title": str(item_title)[:200],
                    "url": DOWNLOAD_URL_TMPL.format(identifier, quote(name, safe="")),
                    "source": "internet_archive",
                })
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
                results.extend(self._get_ppt_files(ident))
            if len(identifiers) < rows:
                break
            start += rows
            if start > 500:
                break

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
                safe_file = re.sub(r"[^\w\-.]", "_", r["filename"])
                filename = f"ia_{r['identifier']}_{safe_file}"
                fp = self._download_file(r["url"], filename)
                if fp:
                    downloaded.append(fp)
                    print(f"  [IA] {len(downloaded)}/{max_docs} — {fp.name}")

        stats = self.get_stats()
        logger.info(f"[InternetArchive] Done — {stats}")
        return downloaded
