"""
File validation module — integrity checks, slide counting, format verification.

Implements criteria1 §1 and §5 validation requirements:
  - File opens without corruption
  - Slide count >= 5
  - Minimum file size
  - ZIP/OLE structural validation
  - HTML false-positive detection
"""
import hashlib
import logging
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of all validation checks for a single file."""
    is_valid: bool = True
    file_size: int = 0
    slide_count: int = 0
    file_hash: str = ""
    integrity_ok: bool = True
    size_ok: bool = True
    slide_count_ok: bool = True
    format_ok: bool = True
    rejection_reason: str = ""

    def __str__(self):
        s = "VALID" if self.is_valid else "INVALID"
        return f"{s}: {self.slide_count} slides, {self.file_size:,}B — {self.rejection_reason or 'OK'}"


class FileValidator:
    """Validates downloaded PPT/PPTX files against delivery requirements."""

    def __init__(self, min_size_bytes=5120, min_slides=5, max_slides=None):
        self.min_size_bytes = min_size_bytes
        self.min_slides = min_slides
        self.max_slides = max_slides

    def validate(self, file_path: Path) -> ValidationResult:
        r = ValidationResult()
        if not file_path.exists():
            r.is_valid = False
            r.rejection_reason = "File does not exist"
            return r

        r.file_size = file_path.stat().st_size
        if r.file_size < self.min_size_bytes:
            r.size_ok = r.is_valid = False
            r.rejection_reason = f"Below min size ({r.file_size} < {self.min_size_bytes}B)"
            return r

        r.file_hash = self._compute_hash(file_path)

        if self._is_html_content(file_path):
            r.integrity_ok = r.format_ok = r.is_valid = False
            r.rejection_reason = "HTML content detected (likely error page)"
            return r

        ext = file_path.suffix.lower()
        if ext == ".pptx":
            ok, reason = self._validate_pptx(file_path)
        elif ext == ".ppt":
            ok, reason = self._validate_ppt(file_path)
        else:
            ok, reason = False, f"Unsupported format: {ext}"
        if not ok:
            r.integrity_ok = r.format_ok = r.is_valid = False
            r.rejection_reason = reason
            return r

        r.slide_count = self.count_slides(file_path)
        if r.slide_count < self.min_slides:
            r.slide_count_ok = r.is_valid = False
            r.rejection_reason = f"Insufficient slides ({r.slide_count} < {self.min_slides})"
            return r
        if self.max_slides and r.slide_count > self.max_slides:
            r.slide_count_ok = r.is_valid = False
            r.rejection_reason = f"Exceeds max slides ({r.slide_count} > {self.max_slides})"
            return r

        return r

    def count_slides(self, file_path: Path) -> int:
        ext = file_path.suffix.lower()
        if ext == ".pptx":
            return self._count_pptx_slides(file_path)
        elif ext == ".ppt":
            return self._count_ppt_slides(file_path)
        return 0

    @staticmethod
    def _count_pptx_slides(fp: Path) -> int:
        try:
            with zipfile.ZipFile(fp) as z:
                return len([f for f in z.namelist()
                           if f.startswith("ppt/slides/slide") and f.endswith(".xml")])
        except Exception as e:
            logger.warning(f"PPTX slide count failed {fp.name}: {e}")
            return 0

    @staticmethod
    def _count_ppt_slides(fp: Path) -> int:
        try:
            from pptx import Presentation
            return len(Presentation(str(fp)).slides)
        except Exception:
            pass
        try:
            import olefile
            if olefile.isOleFile(str(fp)):
                ole = olefile.OleFileIO(str(fp))
                streams = ole.listdir()
                n = len([s for s in streams if any("slide" in p.lower() for p in s)])
                ole.close()
                return max(n, 1)
        except Exception:
            pass
        return 0

    @staticmethod
    def _validate_pptx(fp: Path):
        if not zipfile.is_zipfile(fp):
            return False, "Invalid ZIP structure"
        try:
            with zipfile.ZipFile(fp) as z:
                names = z.namelist()
                if "[Content_Types].xml" not in names:
                    return False, "Missing [Content_Types].xml"
                if not any(n.startswith("ppt/slides/slide") for n in names):
                    return False, "No slide XML found"
        except Exception as e:
            return False, f"ZIP read error: {e}"
        return True, ""

    @staticmethod
    def _validate_ppt(fp: Path):
        try:
            import olefile
            if not olefile.isOleFile(str(fp)):
                return False, "Invalid OLE structure"
            ole = olefile.OleFileIO(str(fp))
            ole.close()
            return True, ""
        except ImportError:
            return True, ""
        except Exception as e:
            return False, f"OLE error: {e}"

    @staticmethod
    def _is_html_content(fp: Path) -> bool:
        try:
            with open(fp, "rb") as f:
                head = f.read(1024).lower()
            return b"<!doctype html" in head or b"<html" in head
        except Exception:
            return False

    @staticmethod
    def _compute_hash(fp: Path) -> str:
        sha = hashlib.sha256()
        try:
            with open(fp, "rb") as f:
                while chunk := f.read(65536):
                    sha.update(chunk)
            return sha.hexdigest()
        except Exception:
            return ""


def extract_text_from_pptx(file_path: Path) -> str:
    """Extract all text from a PPTX for compliance screening."""
    try:
        with zipfile.ZipFile(file_path) as z:
            parts = []
            ns_t = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"
            for name in sorted(z.namelist()):
                if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                    try:
                        root = ET.fromstring(z.read(name).decode("utf-8", errors="ignore"))
                        for t in root.iter(ns_t):
                            if t.text:
                                parts.append(t.text)
                    except Exception:
                        continue
            return " ".join(parts)
    except Exception as e:
        logger.warning(f"Text extraction failed {file_path.name}: {e}")
        return ""
