"""
Domain filtering logic to exclude specific regions (USA) and prioritize others.
"""
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Hard blocklist for US-based content
US_TLDS = {".gov", ".mil", ".us"}

# Selection of top US universities to block (even if they use .edu)
US_INSTITUTIONS = {
    "mit.edu", "stanford.edu", "harvard.edu", "berkeley.edu", "princeton.edu",
    "yale.edu", "columbia.edu", "caltech.edu", "uchicago.edu", "upenn.edu",
    "cornell.edu", "ucla.edu", "umich.edu", "cmu.edu", "washington.edu",
    "nyu.edu", "gatech.edu", "utexas.edu", "northwestern.edu", "purdue.edu",
    "johnshopkins.edu", "duke.edu", "wisc.edu", "ucsd.edu", "illinois.edu"
}

# Whitelist for target regions to prioritize
TARGET_TLDS = {
    ".eu", ".uk", ".fr", ".de", ".nl", ".no", ".se", ".dk", ".fi", ".be", ".it", ".es", # Europe
    ".kr", ".cn", ".in", ".sg", ".hk", ".tw", ".jp", ".my", ".th", ".vn",               # Asia
    ".au", ".nz", ".za"                                                                 # Others
}

class DomainFilter:
    def __init__(self, exclude_usa: bool = True):
        self.exclude_usa = exclude_usa

    def is_allowed(self, url: str) -> bool:
        """Check if a URL is allowed based on geographic constraints."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if not domain:
            return True

        # 1. Check US TLDs
        if self.exclude_usa:
            if any(domain.endswith(tld) for tld in US_TLDS):
                logger.debug(f"Blocked US TLD: {domain}")
                return False

            # 2. Check major US institutions
            if any(domain == inst or domain.endswith("." + inst) for inst in US_INSTITUTIONS):
                logger.debug(f"Blocked US Institution: {domain}")
                return False
            
            # 3. Special case for generic .edu (heuristically US)
            if domain.endswith(".edu") and not any(domain.endswith(t) for t in TARGET_TLDS):
                # Most non-US unis use country TLDs (e.g. .edu.au, .ac.uk)
                # Pure .edu is 95% US.
                logger.debug(f"Blocked generic .edu (assumed US): {domain}")
                return False

        return True

    def get_priority(self, url: str) -> int:
        """Return a priority score (higher is better) for international targets."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        if any(domain.endswith(tld) for tld in TARGET_TLDS):
            return 10
        
        return 5
