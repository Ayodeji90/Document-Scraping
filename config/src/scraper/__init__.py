"""Scraper modules."""
from .base import BaseScraper
from .zenodo import ZenodoScraper
from .figshare import FigshareScraper
from .hal import HALScraper
from .internet_archive import InternetArchiveScraper

__all__ = [
    "BaseScraper",
    "ZenodoScraper",
    "FigshareScraper",
    "HALScraper",
    "InternetArchiveScraper",
]
