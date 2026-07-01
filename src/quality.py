"""
Content quality assessment — classifies files as HIGH / MEDIUM / LOW
per criteria1 §3-4.

Analyzes PPTX slide XML for:
  - Charts (ppt/charts/)
  - Tables (<a:tbl> elements)
  - Diagrams / SmartArt
  - Text density vs visual structure
  - Reasoning quality signals
"""
import logging
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

# XML Namespaces used in OOXML
NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "dgm": "http://schemas.openxmlformats.org/drawingml/2006/diagram",
}


@dataclass
class SlideAnalysis:
    """Analysis result for a single slide."""
    slide_number: int = 0
    has_chart: bool = False
    has_table: bool = False
    has_diagram: bool = False
    has_smartart: bool = False
    has_image: bool = False
    text_length: int = 0
    shape_count: int = 0

    @property
    def is_analytical(self) -> bool:
        return self.has_chart or self.has_table or self.has_diagram or self.has_smartart

    @property
    def is_text_heavy(self) -> bool:
        return self.text_length > 500 and not self.is_analytical

    @property
    def is_photo_heavy(self) -> bool:
        return self.has_image and not self.is_analytical and self.text_length < 100


@dataclass
class QualityResult:
    """Quality classification result for a file."""
    classification: str = "LOW"  # HIGH, MEDIUM, LOW
    slide_count: int = 0
    analytical_slides: int = 0
    chart_slides: int = 0
    table_slides: int = 0
    diagram_slides: int = 0
    text_heavy_slides: int = 0
    photo_heavy_slides: int = 0
    analytical_pct: float = 0.0
    text_heavy_pct: float = 0.0
    photo_heavy_pct: float = 0.0
    reasoning_score: float = 0.0
    details: Dict[str, float] = field(default_factory=dict)

    def __str__(self):
        return (
            f"{self.classification}: {self.analytical_slides}/{self.slide_count} analytical "
            f"({self.analytical_pct:.0%}), {self.chart_slides} charts, "
            f"{self.table_slides} tables, {self.diagram_slides} diagrams"
        )


# Reasoning-quality keywords (criteria1 §4)
REASONING_KEYWORDS = {
    "process", "workflow", "decision", "comparison", "cause", "effect",
    "framework", "architecture", "structure", "analysis", "kpi",
    "metric", "benchmark", "statistical", "correlation", "regression",
    "hypothesis", "methodology", "evaluation", "assessment",
    "organizational", "hierarchy", "flowchart", "pipeline",
}


class QualityAssessor:
    """Classifies PPTX/PPT files into HIGH/MEDIUM/LOW quality tiers."""

    def __init__(
        self,
        high_analytical_pct=0.50,
        high_min_charts=3,
        medium_analytical_pct=0.40,
        medium_min_charts=1,
        reject_text_only_pct=0.75,
        reject_photo_heavy_pct=0.50,
    ):
        self.high_analytical_pct = high_analytical_pct
        self.high_min_charts = high_min_charts
        self.medium_analytical_pct = medium_analytical_pct
        self.medium_min_charts = medium_min_charts
        self.reject_text_only_pct = reject_text_only_pct
        self.reject_photo_heavy_pct = reject_photo_heavy_pct

    def classify_quality(self, file_path: Path) -> QualityResult:
        """Classify a file's quality tier."""
        ext = file_path.suffix.lower()
        if ext == ".pptx":
            return self._classify_pptx(file_path)
        elif ext == ".ppt":
            return self._classify_ppt_fallback(file_path)
        return QualityResult(classification="LOW")

    def _classify_pptx(self, file_path: Path) -> QualityResult:
        """Analyze PPTX internals for quality classification."""
        result = QualityResult()
        try:
            with zipfile.ZipFile(file_path) as z:
                names = z.namelist()

                # Count chart files
                chart_files = [n for n in names if n.startswith("ppt/charts/")]
                total_charts = len(chart_files)

                # Analyze each slide
                slide_files = sorted([
                    n for n in names
                    if n.startswith("ppt/slides/slide") and n.endswith(".xml")
                ])
                result.slide_count = len(slide_files)
                if result.slide_count == 0:
                    return result

                slides: List[SlideAnalysis] = []
                all_text = []

                for i, sf in enumerate(slide_files, 1):
                    sa = self._analyze_slide_xml(z, sf, i, names)
                    slides.append(sa)
                    # Collect text for reasoning analysis
                    try:
                        root = ET.fromstring(z.read(sf).decode("utf-8", errors="ignore"))
                        for t in root.iter(f"{{{NS['a']}}}t"):
                            if t.text:
                                all_text.append(t.text)
                    except Exception:
                        pass

                # Aggregate metrics
                result.analytical_slides = sum(1 for s in slides if s.is_analytical)
                result.chart_slides = sum(1 for s in slides if s.has_chart) + total_charts
                result.table_slides = sum(1 for s in slides if s.has_table)
                result.diagram_slides = sum(1 for s in slides if s.has_diagram or s.has_smartart)
                result.text_heavy_slides = sum(1 for s in slides if s.is_text_heavy)
                result.photo_heavy_slides = sum(1 for s in slides if s.is_photo_heavy)

                result.analytical_pct = result.analytical_slides / result.slide_count
                result.text_heavy_pct = result.text_heavy_slides / result.slide_count
                result.photo_heavy_pct = result.photo_heavy_slides / result.slide_count

                # Reasoning score
                full_text = " ".join(all_text).lower()
                reasoning_hits = sum(1 for kw in REASONING_KEYWORDS if kw in full_text)
                result.reasoning_score = min(1.0, reasoning_hits / 5.0)

                # Classify
                result.classification = self._classify(result, total_charts)

        except Exception as e:
            logger.warning(f"Quality analysis failed for {file_path.name}: {e}")
            result.classification = "LOW"

        return result

    def _analyze_slide_xml(self, z, slide_file, num, all_names) -> SlideAnalysis:
        """Analyze a single slide XML for analytical elements."""
        sa = SlideAnalysis(slide_number=num)
        try:
            content = z.read(slide_file).decode("utf-8", errors="ignore")
            root = ET.fromstring(content)

            # Text length
            for t in root.iter(f"{{{NS['a']}}}t"):
                if t.text:
                    sa.text_length += len(t.text)

            # Tables: <a:tbl>
            if root.iter(f"{{{NS['a']}}}tbl"):
                for _ in root.iter(f"{{{NS['a']}}}tbl"):
                    sa.has_table = True
                    break

            # Charts: check for chart relationships
            content_lower = content.lower()
            if "chart" in content_lower:
                sa.has_chart = True

            # Diagrams / SmartArt
            if "dgm" in content_lower or "diagram" in content_lower:
                sa.has_diagram = True

            # Images: <p:pic> or blipFill
            if "blipfill" in content_lower or "<p:pic" in content_lower:
                sa.has_image = True

            # Shape count
            sa.shape_count = content_lower.count("<p:sp>") + content_lower.count("<p:sp ")

        except Exception:
            pass
        return sa

    def _classify(self, r: QualityResult, chart_count: int) -> str:
        """Apply classification rules."""
        # Rejection checks (LOW)
        if r.text_heavy_pct >= self.reject_text_only_pct:
            return "LOW"
        if r.photo_heavy_pct >= self.reject_photo_heavy_pct:
            return "LOW"

        total_chart_diag = max(r.chart_slides, chart_count) + r.diagram_slides
        analytical_count = r.analytical_slides

        # HIGH: >=50% analytical, >=3 charts/diagrams
        if (r.analytical_pct >= self.high_analytical_pct
                and total_chart_diag >= self.high_min_charts):
            return "HIGH"

        # MEDIUM: ~40%+ analytical, >=1 chart/diagram
        if (r.analytical_pct >= self.medium_analytical_pct
                and total_chart_diag >= self.medium_min_charts):
            return "MEDIUM"

        # If we have some analytical content but not enough for MEDIUM
        if r.analytical_pct >= 0.20 and total_chart_diag >= 1:
            return "MEDIUM"

        return "LOW"

    def _classify_ppt_fallback(self, file_path: Path) -> QualityResult:
        """Heuristic quality check for legacy PPT (no XML introspection)."""
        result = QualityResult()
        size = file_path.stat().st_size

        # Large PPT files tend to have more visual content
        if size > 5_000_000:  # >5MB
            result.classification = "MEDIUM"
        elif size > 2_000_000:  # >2MB
            result.classification = "MEDIUM"
        else:
            result.classification = "LOW"

        # Try python-pptx for slide count
        try:
            from pptx import Presentation
            prs = Presentation(str(file_path))
            result.slide_count = len(prs.slides)
        except Exception:
            pass

        return result
