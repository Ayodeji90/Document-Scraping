#!/usr/bin/env python3
"""
Live status dashboard for the scraper pipeline — one command, continuously
updating table, instead of hand-running tmux/ls/rclone commands separately.

Columns: source, files downloaded (raw), files staged/validated, process
status (RUNNING / TERMINATED / STOPPED). Bottom rows aggregate totals and
what's actually confirmed landed in Google Drive.

Usage:
    python3 dashboard.py                # refresh every 5s (default)
    python3 dashboard.py --interval 10
    python3 dashboard.py --once         # print one snapshot and exit
"""
import argparse
import glob
import subprocess
import time
from datetime import datetime

DRIVE_CHECK_INTERVAL = 60  # rclone calls are slow — don't refresh every tick

SOURCES = [
    # name, raw_glob, staged_glob, process_pattern, tmux_session, tmux_window
    ("CKAN",        "ckan_downloaded/*.ppt*",            "gdrive_staging_ckan/files/*.ppt*", "ckan_pptx_scraper.py",      "ckan-pipeline", "scraper"),
    ("PPTOnline",   "hf_pptonline/*.ppt*",                "gdrive_staging_bulk/files/*.ppt*", "pptonline_scraper.py",      "bulk-pipeline", "pptonline"),
    ("CommonCrawl", "joint_downloaded/*_cc_*.ppt*",       "gdrive_staging_bulk/files/*.ppt*", "commoncrawl_pptx_scraper.py","bulk-pipeline", "commoncrawl"),
]

DRIVE_TARGETS = [
    ("CKAN_PPTX", "gdrive:CKAN_PPTX"),
    ("BATCH_02", "gdrive:BATCH_02"),
]


def count_glob(pattern: str) -> int:
    return len(glob.glob(pattern))


def tmux_session_exists(session: str) -> bool:
    r = subprocess.run(["tmux", "has-session", "-t", session], capture_output=True)
    return r.returncode == 0


def tmux_window_exists(session: str, window: str) -> bool:
    r = subprocess.run(["tmux", "list-windows", "-t", session, "-F", "#{window_name}"], capture_output=True, text=True)
    if r.returncode != 0:
        return False
    return window in r.stdout.split()


def process_running(pattern: str) -> bool:
    r = subprocess.run(["pgrep", "-f", pattern], capture_output=True)
    return r.returncode == 0


def get_status(process_pattern: str, session: str, window: str) -> str:
    if not tmux_session_exists(session) or not tmux_window_exists(session, window):
        return "STOPPED"
    if process_running(process_pattern):
        return "RUNNING"
    return "TERMINATED"


def rclone_count(remote_path: str) -> int:
    try:
        r = subprocess.run(
            ["rclone", "lsf", remote_path], capture_output=True, text=True, timeout=30
        )
        if r.returncode != 0:
            return -1
        return len([l for l in r.stdout.splitlines() if l.strip()])
    except Exception:
        return -1


def render(drive_counts: dict, drive_checked_at: float):
    now = datetime.now().strftime("%H:%M:%S")
    lines = []
    lines.append(f"Pipeline status — {now}")
    lines.append("=" * 74)
    lines.append(f"{'SOURCE':<14}{'DOWNLOADED':>14}{'STAGED':>12}{'STATUS':>16}")
    lines.append("-" * 74)

    total_downloaded = 0
    total_staged = 0
    for name, raw_glob, staged_glob, proc_pattern, session, window in SOURCES:
        downloaded = count_glob(raw_glob)
        staged = count_glob(staged_glob)
        status = get_status(proc_pattern, session, window)
        total_downloaded += downloaded
        total_staged += staged
        lines.append(f"{name:<14}{downloaded:>14,}{staged:>12,}{status:>16}")

    lines.append("-" * 74)
    lines.append(f"{'TOTAL':<14}{total_downloaded:>14,}{total_staged:>12,}")
    lines.append("=" * 74)

    drive_total = sum(v for v in drive_counts.values() if v >= 0)
    drive_parts = "   ".join(
        f"{name}: {drive_counts.get(name, -1):,}" if drive_counts.get(name, -1) >= 0 else f"{name}: ?"
        for name, _ in DRIVE_TARGETS
    )
    age = int(time.time() - drive_checked_at) if drive_checked_at else 0
    lines.append(f"On Google Drive — {drive_parts}   |   TOTAL: {drive_total:,}   (checked {age}s ago)")
    lines.append("=" * 74)
    lines.append("Ctrl+C to exit")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Live pipeline status dashboard")
    parser.add_argument("--interval", type=float, default=5.0, help="Local refresh interval in seconds")
    parser.add_argument("--once", action="store_true", help="Print one snapshot and exit")
    args = parser.parse_args()

    drive_counts = {name: -1 for name, _ in DRIVE_TARGETS}
    drive_checked_at = 0.0

    while True:
        if time.time() - drive_checked_at >= DRIVE_CHECK_INTERVAL:
            for name, remote in DRIVE_TARGETS:
                drive_counts[name] = rclone_count(remote)
            drive_checked_at = time.time()

        output = render(drive_counts, drive_checked_at)

        if args.once:
            print(output)
            return

        print("\033[2J\033[H" + output, flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
