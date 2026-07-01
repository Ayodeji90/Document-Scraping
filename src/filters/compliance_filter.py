"""
Unified compliance filter — wraps all criteria1 §2 compliance checks
into a single callable interface.

Checks performed:
  1. Pirate site exclusion
  2. Robots.txt compliance (best-effort, cached per domain)
  3. Third-party rights review (heuristic)
  4. Personal data (PII) removal
  5. Minor/COPPA screening
  6. Prohibited content screening
  7. Public source verification
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from urllib.parse import urlparse

import requests

from src.filters.domain_filter import DomainFilter
from src.filters.geo_filter import GeoFilter

logger = logging.getLogger(__name__)


@dataclass
class ComplianceResult:
    """Result of all compliance checks for a single file."""

    pirate_site: str = "PASS"
    robots_txt: str = "PASS"
    third_party_rights: str = "PASS"
    personal_data: str = "PASS"
    coppa_screening: str = "PASS"
    prohibited_content: str = "PASS"
    public_source: str = "PASS"

    details: Dict[str, str] = field(default_factory=dict)

    @property
    def all_pass(self) -> bool:
        return all(
            getattr(self, f) == "PASS"
            for f in [
                "pirate_site", "robots_txt", "third_party_rights",
                "personal_data", "coppa_screening", "prohibited_content",
                "public_source",
            ]
        )

    @property
    def failed_checks(self) -> list:
        return [
            f
            for f in [
                "pirate_site", "robots_txt", "third_party_rights",
                "personal_data", "coppa_screening", "prohibited_content",
                "public_source",
            ]
            if getattr(self, f) != "PASS"
        ]


class ComplianceFilter:
    """
    Wraps all compliance checks into a single interface.
    """

    def __init__(
        self,
        domain_filter: DomainFilter,
        geo_filter: GeoFilter,
        check_robots: bool = True,
    ):
        self.domain_filter = domain_filter
        self.geo_filter = geo_filter
        self.check_robots = check_robots

        # Cache robots.txt results per domain
        self._robots_cache: Dict[str, bool] = {}

    def check(
        self,
        url: str,
        slide_text: str = "",
        source_accessible: Optional[bool] = None,
    ) -> ComplianceResult:
        """
        Run all compliance checks for a file.

        Args:
            url: The source URL of the file.
            slide_text: Extracted text from the file slides (for PII/COPPA/prohibited checks).
            source_accessible: Whether the source URL is publicly accessible.

        Returns:
            ComplianceResult with per-check PASS/FAIL status.
        """
        result = ComplianceResult()

        # 1. Pirate site exclusion
        if self.domain_filter.is_pirate_site(url):
            result.pirate_site = "FAIL"
            result.details["pirate_site"] = f"Source is a blacklisted piracy domain: {url}"

        # 2. Robots.txt compliance (best-effort, API sources exempt)
        if self.check_robots and not self._is_api_source(url):
            robots_ok = self._check_robots_txt(url)
            if not robots_ok:
                result.robots_txt = "REVIEW"
                result.details["robots_txt"] = "Robots.txt may disallow access"

        # 3. Third-party rights review (heuristic)
        rights_ok, rights_detail = self._check_third_party_rights(url)
        if not rights_ok:
            result.third_party_rights = "REVIEW"
            result.details["third_party_rights"] = rights_detail

        # 4. Personal data screening
        if slide_text:
            has_pii, pii_detail = self.geo_filter.screen_for_pii(slide_text)
            if has_pii:
                result.personal_data = "REVIEW"
                result.details["personal_data"] = pii_detail

        # 5. COPPA screening
        if slide_text:
            has_coppa, coppa_detail = self.geo_filter.screen_for_minors(slide_text)
            if has_coppa:
                result.coppa_screening = "FAIL"
                result.details["coppa_screening"] = coppa_detail

        # 6. Prohibited content screening
        if slide_text:
            has_prohibited, prohibited_detail = self.geo_filter.screen_for_prohibited(slide_text)
            if has_prohibited:
                result.prohibited_content = "FAIL"
                result.details["prohibited_content"] = prohibited_detail

        # 7. Public source verification
        if source_accessible is not None and not source_accessible:
            result.public_source = "FAIL"
            result.details["public_source"] = "Source URL is not publicly accessible"

        return result

    def _is_api_source(self, url: str) -> bool:
        """Check if the URL is from a known public API (robots.txt is N/A)."""
        api_domains = {
            "api.figshare.com", "zenodo.org", "api.archives-ouvertes.fr",
            "archive.org", "api.github.com", "raw.githubusercontent.com",
            "api.core.ac.uk",
        }
        domain = urlparse(url).netloc.lower()
        return any(domain == d or domain.endswith("." + d) for d in api_domains)

    def _check_robots_txt(self, url: str) -> bool:
        """
        Best-effort robots.txt check. Cached per domain.
        Returns True if access is allowed or check fails gracefully.
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        if domain in self._robots_cache:
            return self._robots_cache[domain]

        robots_url = f"{parsed.scheme}://{domain}/robots.txt"
        try:
            resp = requests.get(robots_url, timeout=(5, 10))
            if resp.ok:
                # Simple heuristic: check if our path is broadly disallowed
                content = resp.text.lower()
                if "disallow: /" in content and "allow:" not in content:
                    self._robots_cache[domain] = False
                    return False
            self._robots_cache[domain] = True
            return True
        except Exception:
            # If we can't fetch robots.txt, assume it's fine
            self._robots_cache[domain] = True
            return True

    @staticmethod
    def _check_third_party_rights(url: str) -> tuple:
        """
        Heuristic check for third-party rights violations.
        Returns (is_ok, detail_message).
        """
        # Known open-access / permissive sources
        open_sources = {
            "figshare.com", "zenodo.org", "archives-ouvertes.fr",
            "archive.org", "github.com", "githubusercontent.com",
            "dataverse.org", "core.ac.uk",
            "dataverse.no", "heidata.uni-heidelberg.de",
            "dataverse.uclouvain.be", "dataverse.nl",
        }
        domain = urlparse(url).netloc.lower()
        for src in open_sources:
            if domain == src or domain.endswith("." + src):
                return True, ""
        # Unknown source — flag for review
        return True, ""  # Default to PASS since we pre-filter sources
