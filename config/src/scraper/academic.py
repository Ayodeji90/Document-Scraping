"""
AcademicScraper has been replaced by InternetArchiveScraper.
This stub exists for backwards compatibility.
"""
import warnings
from .internet_archive import InternetArchiveScraper


class AcademicScraper(InternetArchiveScraper):
    def __init__(self, **kwargs):
        warnings.warn(
            "AcademicScraper is deprecated. Use InternetArchiveScraper instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(**kwargs)
