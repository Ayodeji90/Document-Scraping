"""
Base scraper class with:
- (connect, read) timeout split to kill TCP stalls
- Cross-instance URL + filename deduplication
- Exponential backoff retries with 429 handling
- No sidecar JSON files (removed per user request)
"""
import logging
import random
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.filters.domain_filter import DomainFilter
from src.filters.geo_filter import GeoFilter

logger = logging.getLogger(__name__)

# Shared cross-instance deduplication sets
_seen_urls: set = set()
_seen_files: set = set()


class BaseScraper:
    """Base class for all document scrapers."""

    _seen_urls = _seen_urls
    _seen_files = _seen_files

    def __init__(
        self,
        download_dir: str = "downloaded_ppts",
        api_delay: Tuple[float, float] = (0.5, 1.5),
        download_delay: Tuple[float, float] = (1.5, 3.5),
        timeout: int = 60,
    ):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.api_delay = api_delay
        self.download_delay = download_delay
        self.timeout = timeout
        # (connect_timeout, read_timeout) — kills TCP stalls after read_timeout seconds
        self._timeout = (10, min(timeout, 30))
        self.domain_filter = DomainFilter(exclude_usa=True)
        self.geo_filter = GeoFilter(exclude_usa=True, require_english=True)

        self.session = requests.Session()
        adapter = HTTPAdapter(
            max_retries=Retry(
                total=3,
                backoff_factor=1.5,
                status_forcelist=[500, 502, 503, 504],
                allowed_methods=["GET", "POST"],
            )
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (compatible; AcademicScraper/2.0; "
                "+https://github.com/academic-scraper)"
            )
        })

        # Per-instance stats
        self._downloaded = 0
        self._skipped = 0
        self._failed = 0

    @classmethod
    def preload_seen_from_dir(cls, directory: Path):
        """Pre-populate seen-files from an existing download directory (resume support)."""
        if not directory.exists():
            return
        for f in directory.iterdir():
            if f.suffix.lower() in (".ppt", ".pptx"):
                cls._seen_files.add(f.name.lower())
        logger.info(f"Resume: pre-loaded {len(cls._seen_files)} known filenames")

    def _api_sleep(self):
        time.sleep(random.uniform(*self.api_delay))

    def _download_sleep(self):
        time.sleep(random.uniform(*self.download_delay))

    def _handle_rate_limit(self, attempt: int):
        wait = 10 * (attempt + 1)
        logger.warning(f"Rate limited (429). Waiting {wait}s…")
        time.sleep(wait)

    def _fetch_json(self, url: str, params: Dict = None, bypass_filter: bool = False) -> Optional[Dict]:
        """GET JSON from a URL with retries."""
        if not bypass_filter and not self.domain_filter.is_allowed(url):
            logger.debug(f"Blocked by domain filter: {url}")
            return None

        self._api_sleep()
        for attempt in range(3):
            try:
                resp = self.session.get(url, params=params, timeout=self._timeout)
                if resp.status_code == 429:
                    self._handle_rate_limit(attempt)
                    continue
                if not resp.ok:
                    logger.warning(f"GET failed ({resp.status_code}): {url}")
                    return None
                return resp.json()
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout on attempt {attempt+1}: {url}")
                time.sleep(2 ** attempt)
            except Exception as e:
                logger.warning(f"GET error on attempt {attempt+1} [{url}]: {e}")
                time.sleep(2 ** attempt)
        return None

    def _post_json(self, url: str, payload: Dict, bypass_filter: bool = False) -> Optional[Dict]:
        """POST JSON payload and return JSON response."""
        if not bypass_filter and not self.domain_filter.is_allowed(url):
            return None

        self._api_sleep()
        for attempt in range(3):
            try:
                resp = self.session.post(url, json=payload, timeout=self._timeout)
                if resp.status_code == 429:
                    self._handle_rate_limit(attempt)
                    continue
                if not resp.ok:
                    logger.warning(f"POST failed ({resp.status_code}): {url}")
                    return None
                return resp.json()
            except requests.exceptions.Timeout:
                logger.warning(f"POST timeout on attempt {attempt+1}: {url}")
                time.sleep(2 ** attempt)
            except Exception as e:
                logger.warning(f"POST error on attempt {attempt+1} [{url}]: {e}")
                time.sleep(2 ** attempt)
        return None

    def _download_file(self, url: str, filename: str, meta: Dict = None) -> Optional[Path]:
        """Download a file, skip if already downloaded or URL already seen."""
        # URL deduplication
        if url in BaseScraper._seen_urls:
            self._skipped += 1
            return None
        BaseScraper._seen_urls.add(url)

        # Filename deduplication
        filename_lower = filename.lower()
        if filename_lower in BaseScraper._seen_files:
            self._skipped += 1
            return None

        if not self.domain_filter.is_allowed(url):
            self._skipped += 1
            return None

        # Geo & Language Filter
        if meta and not self.geo_filter.is_allowed(meta.get("title", ""), meta.get("description", "")):
            self._skipped += 1
            return None

        dest = self.download_dir / filename
        if dest.exists() and dest.stat().st_size > 0:
            BaseScraper._seen_files.add(filename_lower)
            self._skipped += 1
            return None

        self._download_sleep()
        for attempt in range(3):
            try:
                resp = self.session.get(
                    url, stream=True, timeout=self._timeout, allow_redirects=True
                )
                if resp.status_code == 429:
                    self._handle_rate_limit(attempt)
                    continue
                if not resp.ok:
                    logger.warning(f"Download failed ({resp.status_code}): {url}")
                    self._failed += 1
                    return None

                # Validate content type
                ct = resp.headers.get("Content-Type", "").lower()
                ppt_types = {
                    "application/vnd.ms-powerpoint",
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    "application/octet-stream",
                    "application/zip",
                    "application/x-zip-compressed",
                }
                if ct and not any(t in ct for t in ppt_types) and "stream" not in ct:
                    logger.debug(f"Unexpected Content-Type '{ct}' for {url}")

                # Stream to disk
                with open(dest, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)

                # Verify non-empty
                if dest.stat().st_size == 0:
                    dest.unlink()
                    self._failed += 1
                    return None

                BaseScraper._seen_files.add(filename_lower)
                self._downloaded += 1
                logger.info(f"Downloaded: {filename} ({dest.stat().st_size:,} bytes)")
                return dest

            except requests.exceptions.Timeout:
                logger.warning(f"Download timeout attempt {attempt+1}: {url}")
                time.sleep(2 ** attempt)
            except Exception as e:
                logger.warning(f"Download error attempt {attempt+1} [{url}]: {e}")
                time.sleep(2 ** attempt)
                if dest.exists():
                    dest.unlink()

        self._failed += 1
        return None

    def get_stats(self) -> Dict:
        return {
            "downloaded": self._downloaded,
            "skipped": self._skipped,
            "failed": self._failed,
        }

    def scrape(self, max_docs: int = 1500) -> List[Path]:
        raise NotImplementedError("Subclasses must implement scrape()")
