"""
Filters to block non-academic domains and handle URL normalization.
"""
import json
import logging
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Essential academic/research domains that must never be blocked, 
# even if they use commercial CDNs (e.g., Cloudflare, Akamai, etc)
TRUSTED_HOSTS = {
    "zenodo.org",
    "figshare.com",
    "archives-ouvertes.fr",
    "hal.science",
    "archive.org",
    "dataverse.harvard.edu",
    "nature.com",
    "sciencedirect.com",
    "springer.com",
    "wiley.com",
    "academic.oup.com",
    "cambridge.org",
    "arxiv.org",
    "researchgate.net",
    "academia.edu",
}

class DomainFilter:
    """Filter out commercial US domains that shouldn't be scraped."""
    
    def __init__(self, blocklist_path: Path = None):
        if not blocklist_path:
            # Default to the config file in the project
            project_root = Path(__file__).parent.parent.parent
            blocklist_path = project_root / "config" / "us_domains_blocklist.json"
            
        self.blocked_domains = set()
        self.blocked_tlds = set()
        self._load_blocklist(blocklist_path)

    def _load_blocklist(self, path: Path):
        """Load blocked domains from JSON configuration."""
        if not path.exists():
            logger.warning(f"Blocklist not found at {path}, using empty filter")
            return
            
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            # Allow for nested category structure or flat list
            if isinstance(data, dict):
                for category, domains in data.items():
                    if isinstance(domains, list):
                        self._parse_entries(domains)
            elif isinstance(data, list):
                self._parse_entries(data)
                
            logger.debug(f"Loaded {len(self.blocked_domains)} blocked domains, {len(self.blocked_tlds)} blocked TLDs")
        except Exception as e:
            logger.error(f"Failed to load blocklist {path}: {e}")
            
    def _parse_entries(self, entries: list):
        """Parse domain entries into specific domains and TLDs."""
        for entry in entries:
            entry = str(entry).strip().lower()
            if not entry:
                continue
                
            if entry.startswith("*."):
                self.blocked_tlds.add(entry[2:])
            else:
                self.blocked_domains.add(entry)

    def is_blocked(self, url: str) -> bool:
        """Check if a URL belongs to a blocked domain."""
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            if not hostname:
                return False
                
            hostname = hostname.lower()
            
            # 1. Immediate whitelist check (overrides blocklist)
            for trusted in TRUSTED_HOSTS:
                if hostname == trusted or hostname.endswith(f".{trusted}"):
                    return False
            
            # 2. Check exact domain or subdomain match
            parts = hostname.split('.')
            for i in range(len(parts)):
                sub_domain = '.'.join(parts[i:])
                if sub_domain in self.blocked_domains:
                    return True
                    
            # 3. Check TLDs
            for tld in self.blocked_tlds:
                if hostname.endswith(f".{tld}"):
                    return True
                    
            return False
        except Exception as e:
            logger.warning(f"Error checking domain for {url}: {e}")
            # Fail open - on error, allow the domain rather than blocking everything
            return False

    def is_allowed(self, url: str) -> bool:
        """Check if a URL is permitted (not blocked)."""
        return not self.is_blocked(url)
