"""
Audit logging system — implements criteria1 §1 and §6 requirements.

Every file processed (downloaded, skipped, or rejected) receives a structured
JSON log entry in an append-only audit log file.
"""
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from src.config import get_config
from src.metadata import FileMetadata
from src.verification import VerificationResult

logger = logging.getLogger(__name__)


@dataclass
class AuditRecord:
    """Structured audit record for a single file."""
    timestamp: str = ""
    filename: str = ""
    file_hash: str = ""
    source_url: str = ""
    batch_id: str = ""
    
    # Validation
    slide_count: int = 0
    file_size_bytes: int = 0
    
    # Verification Stages (PASS/FAIL/REVIEW/PENDING)
    file_integrity: str = ""
    source_verification: str = ""
    public_availability: str = ""
    pirate_screening: str = ""
    robots_access: str = ""
    rights_review: str = ""
    personal_data: str = ""
    coppa_screening: str = ""
    prohibited_content: str = ""
    quality_assessment: str = ""
    reasoning_quality: str = ""

    # Quality & Final Decision
    quality_classification: str = ""  # HIGH, MEDIUM, LOW
    decision: str = ""                # DELIVER, REVIEW, REJECT
    rejection_reasons: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class AuditLogger:
    """Manages the append-only JSONL audit log."""

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_record(self, record: AuditRecord):
        """Append a single record to the audit log."""
        if not record.timestamp:
            record.timestamp = datetime.utcnow().isoformat() + "Z"
            
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                json.dump(record.to_dict(), f, ensure_ascii=False)
                f.write("\n")
        except Exception as e:
            logger.error(f"Failed to write audit record for {record.filename}: {e}")

    def log_file(
        self,
        filename: str,
        metadata: FileMetadata,
        verification: VerificationResult,
    ):
        """Build and append an audit record from metadata and verification results."""
        record = AuditRecord(
            timestamp=datetime.utcnow().isoformat() + "Z",
            filename=filename,
            file_hash=metadata.file_hash,
            source_url=metadata.source_url or metadata.download_url,
            batch_id=metadata.batch_id,
            
            slide_count=metadata.slide_count,
            file_size_bytes=metadata.file_size,
            
            file_integrity=verification.file_integrity,
            source_verification=verification.source_verification,
            public_availability=verification.public_availability,
            pirate_screening=verification.pirate_screening,
            robots_access=verification.robots_access,
            rights_review=verification.rights_review,
            personal_data=verification.personal_data,
            coppa_screening=verification.coppa_screening,
            prohibited_content=verification.prohibited_content,
            quality_assessment=verification.quality_assessment,
            reasoning_quality=verification.reasoning_quality,
            
            quality_classification=verification.quality.classification if verification.quality else "",
            decision=verification.decision,
            rejection_reasons=verification.rejection_reasons,
        )
        self.log_record(record)
