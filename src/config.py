"""
Central configuration for the Document-Scraping pipeline.

All tunable parameters live here so they can be overridden via CLI,
environment variables, or a config file without touching source code.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class PipelineConfig:
    """Master configuration for the scraping + verification + delivery pipeline."""

    # ── Directories ──────────────────────────────────────────────────────
    download_dir: Path = field(default_factory=lambda: Path("downloaded_ppts"))
    rejected_dir: Path = field(default_factory=lambda: Path("rejected"))
    delivery_dir: Path = field(default_factory=lambda: Path("delivery"))
    logs_dir: Path = field(default_factory=lambda: Path("logs"))
    config_dir: Path = field(default_factory=lambda: Path("config"))

    # ── Scraping ─────────────────────────────────────────────────────────
    target: int = 3000
    api_delay: tuple = (0.5, 1.5)
    download_delay: tuple = (1.5, 3.5)
    timeout: int = 60
    max_retries: int = 3
    backoff_factor: float = 1.5

    # ── File Validation ──────────────────────────────────────────────────
    min_file_size_bytes: int = 5120           # 5 KB
    min_slide_count: int = 5                  # criteria1 & criteria2
    max_slide_count: Optional[int] = None     # criteria2: no max

    # ── Quality Thresholds ───────────────────────────────────────────────
    # HIGH quality
    high_analytical_pct: float = 0.50         # ≥50% analytical pages
    high_min_charts: int = 3                  # ≥3 chart/diagram pages

    # MEDIUM quality
    medium_analytical_pct: float = 0.40       # ~40%+ analytical pages
    medium_min_charts: int = 1                # ≥1 meaningful chart

    # LOW quality (rejection thresholds)
    reject_text_only_pct: float = 0.75        # ≥75% text-only → reject
    reject_photo_heavy_pct: float = 0.50      # ≥50% photo-heavy → reject

    # ── Delivery Composition ─────────────────────────────────────────────
    delivery_high_pct: float = 0.70           # 70%+ HIGH quality
    delivery_medium_pct: float = 0.30         # 20-30% MEDIUM quality
    batch_size: int = 500                     # files per batch

    # ── Blocklist Config Files ───────────────────────────────────────────
    us_blocklist_file: str = "us_domains_blocklist.json"
    fortune500_blocklist_file: str = "fortune500_blocklist.json"
    pirate_blocklist_file: str = "pirate_domains_blocklist.json"

    # ── Audit ────────────────────────────────────────────────────────────
    audit_log_file: str = "audit_log.jsonl"
    metadata_sidecar_ext: str = ".meta.json"

    # ── Flags ────────────────────────────────────────────────────────────
    exclude_usa: bool = True
    require_english: bool = True
    check_robots_txt: bool = True
    skip_quality_check: bool = False
    dry_run: bool = False
    resume: bool = False
    no_upload: bool = False
    verbose: bool = False

    def ensure_dirs(self):
        """Create all required directories."""
        for d in [self.download_dir, self.rejected_dir, self.delivery_dir, self.logs_dir]:
            d.mkdir(parents=True, exist_ok=True)

    @property
    def audit_log_path(self) -> Path:
        return self.logs_dir / self.audit_log_file

    @property
    def us_blocklist_path(self) -> Path:
        return self.config_dir / self.us_blocklist_file

    @property
    def fortune500_blocklist_path(self) -> Path:
        return self.config_dir / self.fortune500_blocklist_file

    @property
    def pirate_blocklist_path(self) -> Path:
        return self.config_dir / self.pirate_blocklist_file


# Singleton default config — overridden by run.py at startup
_config: Optional[PipelineConfig] = None


def get_config() -> PipelineConfig:
    """Return the global pipeline config, creating a default if needed."""
    global _config
    if _config is None:
        _config = PipelineConfig()
    return _config


def set_config(cfg: PipelineConfig):
    """Replace the global pipeline config."""
    global _config
    _config = cfg
