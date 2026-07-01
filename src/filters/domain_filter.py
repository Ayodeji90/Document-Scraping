"""
Domain filtering logic — enhanced for criteria2 compliance.

Excludes:
  - US government/military TLDs (.gov, .mil, .us)
  - Elite US universities
  - US national research laboratories and think tanks
  - Fortune 500 companies and subsidiaries
  - Pirate / blacklisted sites
"""
import json
import logging
from pathlib import Path
from urllib.parse import urlparse
from typing import Set

logger = logging.getLogger(__name__)

# ── Defaults (used if JSON blocklists are missing) ───────────────────────
_DEFAULT_US_TLDS = {".gov", ".mil", ".us"}

_DEFAULT_US_INSTITUTIONS = {
    "mit.edu", "stanford.edu", "harvard.edu", "berkeley.edu", "princeton.edu",
    "yale.edu", "columbia.edu", "caltech.edu", "uchicago.edu", "upenn.edu",
    "cornell.edu", "ucla.edu", "umich.edu", "cmu.edu", "washington.edu",
    "nyu.edu", "gatech.edu", "utexas.edu", "northwestern.edu", "purdue.edu",
    "johnshopkins.edu", "duke.edu", "wisc.edu", "ucsd.edu", "illinois.edu",
}

# International TLDs to prioritize
TARGET_TLDS = {
    ".eu", ".uk", ".fr", ".de", ".nl", ".no", ".se", ".dk", ".fi", ".be",
    ".it", ".es", ".pt", ".at", ".ch", ".ie", ".pl", ".cz", ".ro", ".bg",
    ".hr", ".sk", ".si", ".lt", ".lv", ".ee", ".hu", ".gr",
    ".kr", ".cn", ".in", ".sg", ".hk", ".tw", ".jp", ".my", ".th", ".vn",
    ".id", ".ph", ".pk", ".bd", ".lk",
    ".au", ".nz", ".za", ".ng", ".ke", ".gh", ".eg", ".ma", ".tn",
    ".br", ".mx", ".ar", ".cl", ".co", ".pe",
    ".il", ".tr", ".ae", ".sa", ".qa", ".jo", ".lb",
    ".ru", ".ua", ".kz",
}


def _load_json_list(path: Path, key: str) -> Set[str]:
    """Load a list from a JSON config file, returning a set."""
    if not path.exists():
        logger.warning(f"Blocklist not found: {path}")
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        items = data.get(key, [])
        return {item.lower() for item in items}
    except Exception as e:
        logger.error(f"Failed to load blocklist {path}: {e}")
        return set()


class DomainFilter:
    """URL-level filtering for geographic, corporate, and piracy exclusions."""

    def __init__(
        self,
        exclude_usa: bool = True,
        config_dir: Path = Path("config"),
    ):
        self.exclude_usa = exclude_usa
        self.config_dir = config_dir

        # ── Load US blocklists ───────────────────────────────────────────
        us_path = config_dir / "us_domains_blocklist.json"
        self.us_tlds = _load_json_list(us_path, "blocked_tlds") or _DEFAULT_US_TLDS
        self.us_commercial = _load_json_list(us_path, "blocked_domains")
        self.us_institutions = (
            _load_json_list(us_path, "blocked_us_institutions") or _DEFAULT_US_INSTITUTIONS
        )
        self.us_research = _load_json_list(us_path, "blocked_us_research_centers")

        # ── Load Fortune 500 blocklist ───────────────────────────────────
        f500_path = config_dir / "fortune500_blocklist.json"
        self.fortune500 = _load_json_list(f500_path, "blocked_domains")

        # ── Load pirate site blocklist ───────────────────────────────────
        pirate_path = config_dir / "pirate_domains_blocklist.json"
        self.pirate_domains = _load_json_list(pirate_path, "blocked_domains")

        # Merge all blocked domains for fast lookup
        self._all_blocked: Set[str] = set()
        self._all_blocked.update(self.us_commercial)
        self._all_blocked.update(self.fortune500)
        self._all_blocked.update(self.pirate_domains)
        self._all_blocked.update(self.us_research)

        logger.info(
            f"DomainFilter loaded: {len(self._all_blocked)} blocked domains, "
            f"{len(self.us_institutions)} blocked US institutions, "
            f"{len(self.pirate_domains)} pirate domains"
        )

    def _extract_domain(self, url: str) -> str:
        """Extract the lowercased netloc from a URL."""
        parsed = urlparse(url)
        return parsed.netloc.lower()

    def is_allowed(self, url: str) -> bool:
        """Check if a URL passes all domain-level filters."""
        domain = self._extract_domain(url)
        if not domain:
            return True

        # 1. Pirate site check (always enforced)
        if self._is_in_blocklist(domain, self.pirate_domains):
            logger.debug(f"Blocked pirate domain: {domain}")
            return False

        # 2. Fortune 500 check (always enforced)
        if self._is_in_blocklist(domain, self.fortune500):
            logger.debug(f"Blocked Fortune 500 domain: {domain}")
            return False

        # 3. US-specific exclusions
        if self.exclude_usa:
            # US TLDs
            if any(domain.endswith(tld) for tld in self.us_tlds):
                logger.debug(f"Blocked US TLD: {domain}")
                return False

            # US institutions
            if self._is_in_blocklist(domain, self.us_institutions):
                logger.debug(f"Blocked US institution: {domain}")
                return False

            # US research centers
            if self._is_in_blocklist(domain, self.us_research):
                logger.debug(f"Blocked US research center: {domain}")
                return False

            # US commercial domains
            if self._is_in_blocklist(domain, self.us_commercial):
                logger.debug(f"Blocked US commercial domain: {domain}")
                return False

            # Generic .edu is heuristically US
            if domain.endswith(".edu") and not any(
                domain.endswith(t) for t in TARGET_TLDS
            ):
                logger.debug(f"Blocked generic .edu (assumed US): {domain}")
                return False

        return True

    def is_pirate_site(self, url: str) -> bool:
        """Check if a URL originates from a pirate / blacklisted site."""
        domain = self._extract_domain(url)
        return self._is_in_blocklist(domain, self.pirate_domains)

    def is_fortune500(self, url: str) -> bool:
        """Check if a URL originates from a Fortune 500 company."""
        domain = self._extract_domain(url)
        return self._is_in_blocklist(domain, self.fortune500)

    def get_priority(self, url: str) -> int:
        """Return a priority score (higher = better) for international targets."""
        domain = self._extract_domain(url)
        if any(domain.endswith(tld) for tld in TARGET_TLDS):
            return 10
        return 5

    @staticmethod
    def _is_in_blocklist(domain: str, blocklist: Set[str]) -> bool:
        """Check if domain or any parent domain is in a blocklist."""
        if domain in blocklist:
            return True
        # Check if domain is a subdomain of a blocked domain
        for blocked in blocklist:
            if domain.endswith("." + blocked):
                return True
        return False
