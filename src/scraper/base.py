"""
Base scraper class with integrated criteria verification and audit logging.
"""
import logging
import random
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import get_config
from src.metadata import FileMetadata, MetadataStore
from src.audit import AuditLogger
from src.verification import VerificationPipeline

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
        metadata_store: MetadataStore,
        verification_pipeline: VerificationPipeline,
        audit_logger: AuditLogger,
    ):
        self.config = get_config()
        self.download_dir = self.config.download_dir
        self.rejected_dir = self.config.rejected_dir
        self.metadata_store = metadata_store
        self.verification_pipeline = verification_pipeline
        self.audit_logger = audit_logger

        self.api_delay = self.config.api_delay
        self.download_delay = self.config.download_delay
        self._timeout = (10, min(self.config.timeout, 30))

        self.session = requests.Session()
        adapter = HTTPAdapter(
            max_retries=Retry(
                total=self.config.max_retries,
                backoff_factor=self.config.backoff_factor,
                status_forcelist=[500, 502, 503, 504],
                allowed_methods=["GET", "POST"],
            )
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (compatible; AcademicScraper/3.0; "
                "+https://github.com/academic-scraper)"
            )
        })

        # Per-instance stats
        self._stats = {
            "downloaded": 0,
            "delivered": 0,
            "review": 0,
            "rejected": 0,
            "skipped": 0,
            "failed": 0,
            "high_count": 0,
            "medium_count": 0,
            "low_count": 0,
        }

    @classmethod
    def preload_seen_from_dir(cls, directory: Path):
        """Pre-populate seen-files from an existing download directory (resume support)."""
        if not directory.exists():
            return
        for f in directory.iterdir():
            if f.suffix.lower() in (".ppt", ".pptx", ".pdf"):
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

    def _fetch_json(self, url: str, params: Dict = None, headers: Dict = None, bypass_filter: bool = False) -> Optional[Dict]:
        """GET JSON from a URL with retries."""
        if not bypass_filter and not self.verification_pipeline.compliance.domain_filter.is_allowed(url):
            logger.debug(f"Blocked by domain filter: {url}")
            return None

        self._api_sleep()
        for attempt in range(3):
            try:
                resp = self.session.get(url, params=params, headers=headers, timeout=self._timeout)
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

    def _post_json(self, url: str, payload: Dict, headers: Dict = None, bypass_filter: bool = False) -> Optional[Dict]:
        """POST JSON payload and return JSON response."""
        if not bypass_filter and not self.verification_pipeline.compliance.domain_filter.is_allowed(url):
            return None

        self._api_sleep()
        for attempt in range(3):
            try:
                resp = self.session.post(url, json=payload, headers=headers, timeout=self._timeout)
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

    def _download_file(self, url: str, filename: str, meta: FileMetadata) -> Optional[Path]:
        """
        Download a file, run verification pipeline, write metadata and audit log.
        """
        # URL deduplication
        if url in BaseScraper._seen_urls:
            self._stats["skipped"] += 1
            return None
        BaseScraper._seen_urls.add(url)

        # Filename deduplication
        filename_lower = filename.lower()
        if filename_lower in BaseScraper._seen_files:
            self._stats["skipped"] += 1
            return None

        # Domain/Pirate filter pre-check before downloading
        if not self.verification_pipeline.compliance.domain_filter.is_allowed(url):
            self._stats["skipped"] += 1
            return None

        dest = self.download_dir / filename
        if dest.exists() and dest.stat().st_size > 0:
            BaseScraper._seen_files.add(filename_lower)
            self._stats["skipped"] += 1
            return None

        self._download_sleep()
        file_downloaded = False
        
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
                    self._stats["failed"] += 1
                    return None

                # Validate content type
                ct = resp.headers.get("Content-Type", "").lower()
                ppt_types = {
                    "application/vnd.ms-powerpoint",
                    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    "application/pdf",
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

                file_downloaded = True
                break

            except requests.exceptions.Timeout:
                logger.warning(f"Download timeout attempt {attempt+1}: {url}")
                time.sleep(2 ** attempt)
            except Exception as e:
                logger.warning(f"Download error attempt {attempt+1} [{url}]: {e}")
                time.sleep(2 ** attempt)
                if dest.exists():
                    dest.unlink()

        if not file_downloaded:
            self._stats["failed"] += 1
            return None

        BaseScraper._seen_files.add(filename_lower)
        self._stats["downloaded"] += 1

        # Run Verification Pipeline
        verification = self.verification_pipeline.verify(dest, meta)
        
        # Update metadata with verification results
        if verification.validation:
            meta.file_size = verification.validation.file_size
            meta.slide_count = verification.validation.slide_count
            meta.file_hash = verification.validation.file_hash
            
        if verification.quality:
            meta.quality_classification = verification.quality.classification
            if meta.quality_classification == "HIGH":
                self._stats["high_count"] += 1
            elif meta.quality_classification == "MEDIUM":
                self._stats["medium_count"] += 1
            else:
                self._stats["low_count"] += 1
                
        meta.delivery_status = verification.decision

        # Log Audit Record
        self.audit_logger.log_file(filename, meta, verification)

        # Handle decision
        if verification.decision == "REJECT":
            self._stats["rejected"] += 1
            # Move to rejected directory
            rej_path = self.rejected_dir / dest.name
            dest.replace(rej_path)
            # We don't save metadata for rejected files to avoid clutter,
            # their info is in the audit log.
            return None
        elif verification.decision == "REVIEW":
            self._stats["review"] += 1
        else:
            self._stats["delivered"] += 1

        # Save metadata sidecar
        self.metadata_store.save(dest, meta)
        logger.info(f"Downloaded & Verified [{meta.delivery_status}]: {filename} ({dest.stat().st_size:,} bytes)")
        return dest

    def get_stats(self) -> Dict:
        return self._stats

    def scrape(self, max_docs: int = 1500) -> List[Path]:
        raise NotImplementedError("Subclasses must implement scrape()")
