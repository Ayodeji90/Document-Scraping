"""
Base scraper with tenacity retries, cross-instance deduplication,
and metadata sidecar files.
"""
import json
import logging
import random
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from ..filters.domain_filter import DomainFilter

logger = logging.getLogger(__name__)

# Minimum valid file size — even an empty PPTX is ~25 KB
MIN_FILE_SIZE_BYTES = 10_240  # 10 KB

VALID_PPT_MIMES = {
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.presentationml.slideshow",
    "application/x-mspowerpoint",
    "application/mspowerpoint",
}


class BaseScraper(ABC):
    """Base class for all PPT scrapers."""

    # Class-level deduplication shared across all instances
    _seen_urls: Set[str] = set()
    _seen_files: Set[str] = set()

    def __init__(
        self,
        download_dir: str = "downloaded_ppts",
        api_delay: tuple = (0.5, 1.5),
        download_delay: tuple = (1.5, 3.5),
        timeout: int = 60,
    ):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.api_delay = api_delay
        self.download_delay = download_delay
        self.timeout = timeout
        # Use (connect, read) tuple: connect fast, read up to `timeout` seconds
        self._timeout = (10, min(timeout, 30))
        self.domain_filter = DomainFilter()

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (compatible; AcademicPPTScraper/2.0; "
                    "+https://github.com/academic-research; research@openacademic.org)"
                ),
                "Accept": "application/json, */*",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

        self.downloaded_count = 0
        self.skipped_count = 0
        self.failed_count = 0

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _api_sleep(self):
        time.sleep(random.uniform(*self.api_delay))

    def _download_sleep(self):
        time.sleep(random.uniform(*self.download_delay))

    def _handle_rate_limit(self, attempt: int):
        wait = 60 * (attempt + 1)
        logger.warning(f"Rate-limited. Waiting {wait}s before retry {attempt + 1}…")
        time.sleep(wait)

    # ------------------------------------------------------------------ #
    # HTTP helpers                                                         #
    # ------------------------------------------------------------------ #

    def _fetch_json(
        self, url: str, params: Dict = None, bypass_filter: bool = False
    ) -> Optional[Dict]:
        """GET JSON with retry logic and rate-limit handling."""
        if not bypass_filter and not self.domain_filter.is_allowed(url):
            logger.debug(f"Blocked by domain filter: {url[:60]}")
            self.skipped_count += 1
            return None

        self._api_sleep()

        for attempt in range(3):
            try:
                resp = self.session.get(url, params=params, timeout=self._timeout)
                if resp.status_code == 429:
                    self._handle_rate_limit(attempt)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.HTTPError as e:
                code = e.response.status_code if e.response else 0
                if code in (403, 404, 410):
                    logger.debug(f"HTTP {code}: {url[:60]}")
                    return None
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    logger.warning(f"GET failed ({code}): {url[:60]}")
                    self.failed_count += 1
                    return None
            except requests.RequestException as e:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    logger.warning(f"GET error: {e}")
                    self.failed_count += 1
                    return None
        return None

    def _post_json(
        self, url: str, payload: Dict, bypass_filter: bool = False
    ) -> Optional[object]:
        """POST JSON with retry logic."""
        if not bypass_filter and not self.domain_filter.is_allowed(url):
            return None

        self._api_sleep()

        for attempt in range(3):
            try:
                resp = self.session.post(url, json=payload, timeout=self._timeout)
                if resp.status_code == 429:
                    self._handle_rate_limit(attempt)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.HTTPError as e:
                code = e.response.status_code if e.response else 0
                if code in (403, 404):
                    return None
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    self.failed_count += 1
                    return None
            except requests.RequestException:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    self.failed_count += 1
                    return None
        return None

    # ------------------------------------------------------------------ #
    # File download                                                        #
    # ------------------------------------------------------------------ #

    def _download_file(
        self, url: str, filename: str, metadata: Dict = None
    ) -> Optional[Path]:
        """Download a PPT/PPTX file. Returns Path on success, None otherwise."""

        # URL-level deduplication
        if url in BaseScraper._seen_urls:
            logger.debug(f"Duplicate URL skipped: {url[:60]}")
            return None
        BaseScraper._seen_urls.add(url)

        filename = self._safe_filename(filename)

        # Resolve filename collision
        if filename in BaseScraper._seen_files:
            stem, ext = Path(filename).stem, Path(filename).suffix
            filename = f"{stem}_{random.randint(1000, 9999)}{ext}"

        file_path = self.download_dir / filename

        if file_path.exists() and file_path.stat().st_size >= MIN_FILE_SIZE_BYTES:
            logger.debug(f"Already exists: {filename}")
            BaseScraper._seen_files.add(filename)
            return file_path

        self._download_sleep()

        for attempt in range(3):
            try:
                resp = self.session.get(
                    url, stream=True, timeout=self._timeout, allow_redirects=True
                )
                if resp.status_code == 429:
                    self._handle_rate_limit(attempt)
                    continue
                resp.raise_for_status()

                content_type = resp.headers.get("Content-Type", "").lower()
                final_url = str(resp.url)

                if not self._is_ppt(content_type, final_url, url):
                    logger.debug(f"Not a PPT ({content_type}): {url[:60]}")
                    return None

                # Stream to disk
                with open(file_path, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=65_536):
                        if chunk:
                            fh.write(chunk)

                # Validate size
                size = file_path.stat().st_size
                if size < MIN_FILE_SIZE_BYTES:
                    logger.warning(
                        f"File too small ({size} B) — likely an error page: {filename}"
                    )
                    file_path.unlink(missing_ok=True)
                    return None

                # Persist metadata sidecar
                if metadata:
                    sidecar = file_path.with_suffix(file_path.suffix + ".meta.json")
                    with open(sidecar, "w", encoding="utf-8") as fh:
                        json.dump(
                            {
                                **metadata,
                                "download_url": url,
                                "final_url": final_url,
                                "filename": filename,
                                "file_size_bytes": size,
                                "scraped_at": datetime.utcnow().isoformat() + "Z",
                            },
                            fh,
                            indent=2,
                            ensure_ascii=False,
                        )

                BaseScraper._seen_files.add(filename)
                self.downloaded_count += 1
                logger.info(f"✓ {filename}  ({size // 1024} KB)")
                return file_path

            except requests.HTTPError as e:
                code = e.response.status_code if e.response else 0
                if code in (403, 404, 410):
                    self.failed_count += 1
                    return None
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    self.failed_count += 1
                    return None
            except Exception as e:
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    logger.warning(f"Download error: {e}")
                    self.failed_count += 1
                    return None

        return None

    # ------------------------------------------------------------------ #
    # Utilities                                                            #
    # ------------------------------------------------------------------ #

    def _is_ppt(self, content_type: str, final_url: str, original_url: str) -> bool:
        """Return True if the response looks like a PPT/PPTX file."""
        for mime in VALID_PPT_MIMES:
            if mime in content_type:
                return True
        # octet-stream / binary — trust the URL extension
        if "octet-stream" in content_type or "binary" in content_type or not content_type:
            for check_url in (final_url.split("?")[0], original_url.split("?")[0]):
                if check_url.lower().endswith(".ppt") or check_url.lower().endswith(".pptx"):
                    return True
        return False

    @staticmethod
    def _safe_filename(name: str) -> str:
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
        name = re.sub(r"_+", "_", name).strip("_. ")
        stem = Path(name).stem[:160]
        suffix = Path(name).suffix.lower()
        if suffix not in (".ppt", ".pptx"):
            suffix = ".pptx"
        return f"{stem}{suffix}"

    # ------------------------------------------------------------------ #
    # Class-level state management                                        #
    # ------------------------------------------------------------------ #

    @classmethod
    def reset_seen(cls):
        cls._seen_urls.clear()
        cls._seen_files.clear()

    @classmethod
    def preload_seen_from_dir(cls, download_dir: Path):
        """Pre-populate dedup set from already-downloaded files (resume support)."""
        for f in download_dir.glob("*.ppt*"):
            cls._seen_files.add(f.name)
        logger.info(f"Resume: {len(cls._seen_files)} existing files registered.")

    # ------------------------------------------------------------------ #
    # Abstract interface                                                   #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def search(self, query: str = None, max_results: int = 100) -> List[Dict]:
        """Return list of candidate dicts with at least 'url', 'title', 'source'."""

    @abstractmethod
    def scrape(self, max_docs: int = 1500) -> List[Path]:
        """Download up to max_docs PPT files. Return list of saved Paths."""

    def get_stats(self) -> Dict:
        return {
            "downloaded": self.downloaded_count,
            "skipped": self.skipped_count,
            "failed": self.failed_count,
        }
