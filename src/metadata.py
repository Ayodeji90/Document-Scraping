"""
Metadata preservation module — captures and persists all available metadata
per file as required by criteria2 §3.

Every downloaded file gets a JSON sidecar with the full metadata record.
"""
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FileMetadata:
    """All metadata fields for a single file, per criteria2 §3."""

    # ── Mandatory ────────────────────────────────────────────────────────
    source_url: str = ""

    # ── Preferred fields ─────────────────────────────────────────────────
    source_domain: str = ""
    download_url: str = ""
    original_filename: str = ""
    collection_timestamp: str = ""
    download_timestamp: str = ""
    publication_date: str = ""
    author_info: str = ""
    organization_name: str = ""
    document_title: str = ""
    language: str = ""
    file_size: int = 0
    file_format: str = ""
    tags_categories: List[str] = field(default_factory=list)

    # ── Crawl / processing metadata ──────────────────────────────────────
    scraper_source: str = ""          # figshare, zenodo, hal, etc.
    search_query: str = ""            # the query that found this file
    api_record_id: str = ""           # source-specific record ID
    batch_id: str = ""                # assigned during delivery packaging
    quality_classification: str = ""  # HIGH / MEDIUM / LOW
    delivery_status: str = ""         # DELIVER / REVIEW / REJECT
    slide_count: int = 0
    file_hash: str = ""               # SHA-256

    # ── Extra source-specific fields ─────────────────────────────────────
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to a plain dictionary, filtering empty values."""
        d = asdict(self)
        return {k: v for k, v in d.items() if v or v == 0}


class MetadataStore:
    """
    Manages metadata sidecar files alongside downloaded presentations.

    Each file `foo.pptx` gets a companion `foo.pptx.meta.json` in the same
    directory containing the full FileMetadata record.
    """

    def __init__(self, sidecar_ext: str = ".meta.json"):
        self.sidecar_ext = sidecar_ext

    def sidecar_path(self, file_path: Path) -> Path:
        """Return the sidecar metadata path for a given file."""
        return file_path.parent / (file_path.name + self.sidecar_ext)

    def save(self, file_path: Path, metadata: FileMetadata):
        """Write metadata to the sidecar JSON file."""
        sidecar = self.sidecar_path(file_path)
        try:
            with open(sidecar, "w", encoding="utf-8") as f:
                json.dump(metadata.to_dict(), f, indent=2, ensure_ascii=False)
            logger.debug(f"Metadata saved: {sidecar.name}")
        except Exception as e:
            logger.error(f"Failed to save metadata for {file_path.name}: {e}")

    def load(self, file_path: Path) -> Optional[FileMetadata]:
        """Load metadata from the sidecar JSON file."""
        sidecar = self.sidecar_path(file_path)
        if not sidecar.exists():
            return None
        try:
            with open(sidecar, "r", encoding="utf-8") as f:
                data = json.load(f)
            meta = FileMetadata()
            for k, v in data.items():
                if hasattr(meta, k):
                    setattr(meta, k, v)
            return meta
        except Exception as e:
            logger.error(f"Failed to load metadata for {file_path.name}: {e}")
            return None

    def exists(self, file_path: Path) -> bool:
        """Check if metadata already exists for a file."""
        return self.sidecar_path(file_path).exists()

    def export_manifest(self, directory: Path, output_path: Path):
        """Export all metadata in a directory to a single JSON manifest."""
        records = []
        for sidecar in sorted(directory.glob(f"*{self.sidecar_ext}")):
            try:
                with open(sidecar, "r", encoding="utf-8") as f:
                    records.append(json.load(f))
            except Exception as e:
                logger.warning(f"Skipping corrupt sidecar {sidecar.name}: {e}")

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        logger.info(f"Exported {len(records)} metadata records to {output_path}")


def build_metadata_from_api(
    source: str,
    record: Dict,
    download_url: str,
    filename: str,
) -> FileMetadata:
    """
    Build a FileMetadata object from an API response record.

    Each scraper calls this with its source-specific record dict.
    This function extracts as many fields as possible from common patterns.
    """
    from urllib.parse import urlparse

    meta = FileMetadata(
        source_url=record.get("source_url", record.get("url", download_url)),
        download_url=download_url,
        original_filename=filename,
        collection_timestamp=datetime.utcnow().isoformat() + "Z",
        download_timestamp=datetime.utcnow().isoformat() + "Z",
        document_title=record.get("title", record.get("document_title", "")),
        scraper_source=source,
        search_query=record.get("query", ""),
        api_record_id=str(record.get("record_id", record.get("article_id",
                          record.get("id", record.get("hal_id",
                          record.get("identifier", record.get("file_id", ""))))))),
        language=record.get("language", ""),
        publication_date=record.get("publication_date", record.get("published_date", "")),
        author_info=record.get("author_info", record.get("authors", "")),
        organization_name=record.get("organization_name", record.get("publisher", "")),
        file_format=Path(filename).suffix.lstrip(".").upper(),
    )

    # Extract source domain
    try:
        parsed = urlparse(download_url)
        meta.source_domain = parsed.netloc.lower()
    except Exception:
        pass

    # Tags / categories
    tags = record.get("tags", record.get("keywords", record.get("subjects", [])))
    if isinstance(tags, list):
        meta.tags_categories = [str(t) for t in tags]
    elif isinstance(tags, str):
        meta.tags_categories = [tags]

    # Extra fields: anything not already captured
    known_keys = {
        "url", "title", "query", "record_id", "article_id", "id",
        "hal_id", "identifier", "file_id", "language", "publication_date",
        "published_date", "author_info", "authors", "organization_name",
        "publisher", "tags", "keywords", "subjects", "source_url",
        "document_title", "source", "filename", "key", "ext",
    }
    meta.extra = {k: v for k, v in record.items() if k not in known_keys and v}

    return meta
