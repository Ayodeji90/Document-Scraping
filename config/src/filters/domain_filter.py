"""
Domain filter: blocks US corporate/commercial domains.
Trusted academic API hosts always bypass the filter.
"""
import json
import logging
import tldextract
from urllib.parse import urlparse
from pathlib import Path

logger = logging.getLogger(__name__)

# These hosts are always allowed regardless of the blocklist.
# They are the authoritative API hosts for our academic scrapers.
TRUSTED_HOSTS = {
    "zenodo.org",
    "api.figshare.com",
    "figshare.com",
    "ndownloader.figshare.com",
    "api.archives-ouvertes.fr",
    "hal.science",
    "hal.archives-ouvertes.fr",
    "archive.org",
    "files.archive.org",
    "ia800x.us.archive.org",  # IA CDN nodes
    "cern.ch",
    "files.cern.ch",
}


class DomainFilter:
    """Filters URLs based on a US company domain blocklist."""

    def __init__(self, blocklist_path=None):
        self.blocklist_path = blocklist_path or (
            Path(__file__).parent.parent.parent / "config" / "us_domains_blocklist.json"
        )
        self.blocked_domains: set = set()
        self.blocked_tlds: set = set()
        self._load_blocklist()

    def _load_blocklist(self):
        try:
            with open(self.blocklist_path) as f:
                data = json.load(f)
            self.blocked_domains = {d.lower() for d in data.get("blocked_domains", [])}
            self.blocked_tlds = {t.lower() for t in data.get("blocked_tlds", [])}
            logger.debug(
                f"Loaded {len(self.blocked_domains)} blocked domains, "
                f"{len(self.blocked_tlds)} blocked TLDs"
            )
        except FileNotFoundError:
            logger.warning(f"Blocklist not found at {self.blocklist_path}. Filter disabled.")

    def is_blocked(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            hostname = parsed.netloc.lower().split(":")[0]  # strip port

            if not hostname:
                return True  # empty hostname → block

            if hostname.startswith("www."):
                hostname = hostname[4:]

            # Always allow trusted academic API hosts
            if hostname in TRUSTED_HOSTS:
                return False
            # Also allow subdomains of trusted hosts
            for trusted in TRUSTED_HOSTS:
                if hostname.endswith("." + trusted):
                    return False

            ext = tldextract.extract(hostname)
            full_domain = f"{ext.domain}.{ext.suffix}".lower()

            # Check blocked TLDs
            if f".{ext.suffix}" in self.blocked_tlds:
                return True

            # Check blocked domains (including subdomains)
            for blocked in self.blocked_domains:
                if full_domain == blocked or hostname.endswith("." + blocked):
                    return True

            return False

        except Exception as e:
            logger.debug(f"Error checking URL {url}: {e}")
            return False  # Default ALLOW on error (don't block legitimate sources)

    def is_allowed(self, url: str) -> bool:
        return not self.is_blocked(url)

    def get_domain(self, url: str) -> str:
        try:
            hostname = urlparse(url).netloc.lower().split(":")[0]
            return hostname.lstrip("www.") or "unknown"
        except Exception:
            return "unknown"
