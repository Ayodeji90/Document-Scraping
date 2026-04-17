"""
Metadata-based filtering for geography (No USA) and language (English only).
"""
import logging
import re

logger = logging.getLogger(__name__)

# Keywords that strongly indicate US content
US_KEYWORDS = {
    "nasa", "pentagon", "congress", "senate", "white house", "fbi", "cia",
    "california", "texas", "florida", "new york city", "washington dc",
    "united states of america", "us army", "us navy", "us air force",
    "department of defense", "department of energy", "national laboratory",
    "sandia", "los alamos", "oak ridge", "lawrence livermore"
}

# Common English words to identify English content
ENGLISH_MARKERS = {
    " the ", " and ", " with ", " for ", " from ", " that ", " this ", " which ", 
    " results ", " analysis ", " research ", " development ", " system "
}

class GeoFilter:
    def __init__(self, exclude_usa: bool = True, require_english: bool = True):
        self.exclude_usa = exclude_usa
        self.require_english = require_english

    def is_allowed(self, title: str, abstract: str = "") -> bool:
        """Check if metadata indicates allowed content."""
        text = (title + " " + abstract).lower()

        # 1. Check for US keywords
        if self.exclude_usa:
            if any(kw in text for kw in US_KEYWORDS):
                logger.debug(f"Blocked by US metadata keyword: {title}")
                return False

        # 2. Heuristic English check
        if self.require_english:
            # We look for at least 2 common English markers
            matches = sum(1 for marker in ENGLISH_MARKERS if marker in text)
            if matches < 1: # At least one marker must be present for confidence
                # If no markers found, check if it contains any non-latin characters
                # if it has Cyrillic, Hanzi, Kanji, etc., it's definitely not English
                if re.search(r'[^\x00-\x7F]+', text):
                    logger.debug(f"Blocked as non-English (non-latin chars): {title}")
                    return False
                
                # If it's purely latin but no markers, we might allow it if it's very short
                if len(text.split()) > 5:
                    logger.debug(f"Blocked as potentially non-English (no markers): {title}")
                    return False

        return True
