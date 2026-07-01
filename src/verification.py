"""
Multi-stage verification pipeline — criteria1 §5.

Runs all verification steps in sequence for each file and produces
a VerificationResult with per-step PASS/FAIL statuses.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from src.filters.compliance_filter import ComplianceFilter, ComplianceResult
from src.quality import QualityAssessor, QualityResult
from src.validators import FileValidator, ValidationResult, extract_text_from_pptx
from src.metadata import FileMetadata

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """Result of the complete multi-stage verification pipeline."""

    # Per-step statuses
    file_integrity: str = "PENDING"
    source_verification: str = "PENDING"
    public_availability: str = "PENDING"
    pirate_screening: str = "PENDING"
    robots_access: str = "PENDING"
    rights_review: str = "PENDING"
    personal_data: str = "PENDING"
    coppa_screening: str = "PENDING"
    prohibited_content: str = "PENDING"
    quality_assessment: str = "PENDING"
    reasoning_quality: str = "PENDING"

    # Detailed results
    validation: Optional[ValidationResult] = None
    compliance: Optional[ComplianceResult] = None
    quality: Optional[QualityResult] = None

    # Final decision
    decision: str = "PENDING"  # DELIVER, REVIEW, REJECT
    rejection_reasons: list = field(default_factory=list)

    @property
    def all_pass(self) -> bool:
        steps = [
            self.file_integrity, self.source_verification,
            self.public_availability, self.pirate_screening,
            self.robots_access, self.rights_review,
            self.personal_data, self.coppa_screening,
            self.prohibited_content, self.quality_assessment,
            self.reasoning_quality,
        ]
        return all(s == "PASS" for s in steps)

    def to_dict(self) -> Dict:
        return {
            "file_integrity": self.file_integrity,
            "source_verification": self.source_verification,
            "public_availability": self.public_availability,
            "pirate_screening": self.pirate_screening,
            "robots_access": self.robots_access,
            "rights_review": self.rights_review,
            "personal_data": self.personal_data,
            "coppa_screening": self.coppa_screening,
            "prohibited_content": self.prohibited_content,
            "quality_assessment": self.quality_assessment,
            "reasoning_quality": self.reasoning_quality,
            "decision": self.decision,
            "rejection_reasons": self.rejection_reasons,
            "quality_classification": self.quality.classification if self.quality else "",
        }


class VerificationPipeline:
    """
    Runs the complete verification chain defined in criteria1 §5.
    """

    def __init__(
        self,
        validator: FileValidator,
        compliance_filter: ComplianceFilter,
        quality_assessor: QualityAssessor,
        skip_quality: bool = False,
    ):
        self.validator = validator
        self.compliance = compliance_filter
        self.quality_assessor = quality_assessor
        self.skip_quality = skip_quality

    def verify(
        self,
        file_path: Path,
        metadata: FileMetadata,
    ) -> VerificationResult:
        """Run all verification steps on a downloaded file."""
        result = VerificationResult()

        # Step 1: File Integrity Check
        val = self.validator.validate(file_path)
        result.validation = val
        if val.is_valid:
            result.file_integrity = "PASS"
        else:
            result.file_integrity = "FAIL"
            result.rejection_reasons.append(f"Integrity: {val.rejection_reason}")
            result.decision = "REJECT"
            return result

        # Step 2: Source Verification
        if metadata.source_url:
            result.source_verification = "PASS"
        else:
            result.source_verification = "REVIEW"
            result.rejection_reasons.append("Missing source URL")

        # Step 3: Public Availability Verification
        result.public_availability = "PASS"  # Pre-filtered by domain filter

        # Steps 4-9: Compliance checks
        slide_text = ""
        if file_path.suffix.lower() == ".pptx":
            slide_text = extract_text_from_pptx(file_path)

        comp = self.compliance.check(
            url=metadata.source_url or metadata.download_url,
            slide_text=slide_text,
        )
        result.compliance = comp

        result.pirate_screening = comp.pirate_site
        result.robots_access = comp.robots_txt
        result.rights_review = comp.third_party_rights
        result.personal_data = comp.personal_data
        result.coppa_screening = comp.coppa_screening
        result.prohibited_content = comp.prohibited_content
        result.public_availability = comp.public_source

        # Check for hard failures
        for check_name in ["pirate_site", "coppa_screening", "prohibited_content"]:
            if getattr(comp, check_name) == "FAIL":
                result.decision = "REJECT"
                result.rejection_reasons.append(
                    f"{check_name}: {comp.details.get(check_name, 'FAIL')}"
                )
                return result

        # Step 10: Quality Assessment
        if self.skip_quality:
            result.quality_assessment = "PASS"
            result.reasoning_quality = "PASS"
            result.quality = QualityResult(classification="MEDIUM")
        else:
            qr = self.quality_assessor.classify_quality(file_path)
            result.quality = qr

            if qr.classification == "LOW":
                result.quality_assessment = "FAIL"
                result.rejection_reasons.append(f"Quality: LOW ({qr})")
            else:
                result.quality_assessment = "PASS"

            # Step 11: Reasoning Quality
            if qr.reasoning_score >= 0.3:
                result.reasoning_quality = "PASS"
            elif qr.classification == "HIGH":
                result.reasoning_quality = "PASS"
            else:
                result.reasoning_quality = "REVIEW"

        # Final decision
        if result.decision == "PENDING":
            has_fail = any(
                getattr(result, f) == "FAIL"
                for f in [
                    "file_integrity", "pirate_screening", "coppa_screening",
                    "prohibited_content", "quality_assessment",
                ]
            )
            has_review = any(
                getattr(result, f) == "REVIEW"
                for f in [
                    "source_verification", "robots_access", "rights_review",
                    "personal_data", "reasoning_quality",
                ]
            )

            if has_fail:
                result.decision = "REJECT"
            elif has_review:
                result.decision = "REVIEW"
            else:
                result.decision = "DELIVER"

        return result
