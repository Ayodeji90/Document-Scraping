"""
Metadata-based filtering — geography, language, PII, COPPA, and prohibited content.

Implements criteria1 §2 compliance checks that operate on text metadata
(title, abstract, slide content) rather than URL domains.
"""
import logging
import re
from typing import Tuple

logger = logging.getLogger(__name__)

# ── US Keyword Indicators ────────────────────────────────────────────────
US_KEYWORDS = {
    "nasa", "pentagon", "congress", "senate", "white house", "fbi", "cia",
    "california", "texas", "florida", "new york city", "washington dc",
    "united states of america", "us army", "us navy", "us air force",
    "department of defense", "department of energy", "national laboratory",
    "sandia", "los alamos", "oak ridge", "lawrence livermore",
    "national science foundation", "national institutes of health",
    "centers for disease control", "usda", "us census",
    "fort bragg", "fort hood", "joint chiefs",
}

# ── English Markers ──────────────────────────────────────────────────────
ENGLISH_MARKERS = {
    " the ", " and ", " with ", " for ", " from ", " that ", " this ",
    " which ", " results ", " analysis ", " research ", " development ",
    " system ", " however ", " therefore ", " presented ", " study ",
    " method ", " approach ", " conclusion ",
}

# ── PII Patterns ─────────────────────────────────────────────────────────
_EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE
)
_PHONE_PATTERN = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}"
)
_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# ── COPPA / Minor-related Keywords ───────────────────────────────────────
COPPA_KEYWORDS = {
    "child abuse", "child exploitation", "minor personal data",
    "parental consent", "children under 13", "student records",
    "juvenile", "underage",
}

# ── Prohibited Content Keywords ──────────────────────────────────────────
PROHIBITED_KEYWORDS = {
    "classified material", "top secret", "confidential - do not distribute",
    "internal only", "proprietary and confidential",
    "restricted access", "nda required", "not for public release",
}


class GeoFilter:
    """Metadata-based filtering for geography, language, PII, and content screening."""

    def __init__(self, exclude_usa: bool = True, require_english: bool = True):
        self.exclude_usa = exclude_usa
        self.require_english = require_english

    def is_allowed(self, title: str, abstract: str = "") -> bool:
        """Check if metadata indicates allowed content (geo + language)."""
        text = (title + " " + abstract).lower()

        # 1. Check for US keywords
        if self.exclude_usa:
            if any(kw in text for kw in US_KEYWORDS):
                logger.debug(f"Blocked by US metadata keyword: {title[:80]}")
                return False

        # 2. Heuristic English check
        if self.require_english:
            matches = sum(1 for marker in ENGLISH_MARKERS if marker in text)
            if matches < 1:
                if re.search(r"[^\x00-\x7F]+", text):
                    logger.debug(f"Blocked non-English (non-latin chars): {title[:80]}")
                    return False
                if len(text.split()) > 5:
                    logger.debug(f"Blocked potentially non-English: {title[:80]}")
                    return False

        return True

    @staticmethod
    def screen_for_pii(text: str) -> Tuple[bool, str]:
        """
        Screen text for personally identifiable information.

        Returns:
            (has_pii, detail_message)
        """
        findings = []
        emails = _EMAIL_PATTERN.findall(text)
        if len(emails) > 2:  # Allow 1-2 author emails in metadata
            findings.append(f"{len(emails)} email addresses")

        ssns = _SSN_PATTERN.findall(text)
        if ssns:
            findings.append(f"{len(ssns)} SSN-like patterns")

        # Excessive phone numbers suggest a contact list
        phones = _PHONE_PATTERN.findall(text)
        if len(phones) > 3:
            findings.append(f"{len(phones)} phone numbers")

        if findings:
            return True, "; ".join(findings)
        return False, ""

    @staticmethod
    def screen_for_minors(text: str) -> Tuple[bool, str]:
        """
        Screen for COPPA-related content involving minors.

        Returns:
            (has_concern, detail_message)
        """
        text_lower = text.lower()
        hits = [kw for kw in COPPA_KEYWORDS if kw in text_lower]
        if hits:
            return True, f"COPPA keywords found: {', '.join(hits)}"
        return False, ""

    @staticmethod
    def screen_for_prohibited(text: str) -> Tuple[bool, str]:
        """
        Screen for prohibited / restricted content.

        Returns:
            (has_prohibited, detail_message)
        """
        text_lower = text.lower()
        hits = [kw for kw in PROHIBITED_KEYWORDS if kw in text_lower]
        if hits:
            return True, f"Prohibited content keywords: {', '.join(hits)}"
        return False, ""
