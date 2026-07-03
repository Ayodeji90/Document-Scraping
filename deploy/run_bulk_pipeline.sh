#!/usr/bin/env bash
# Run this ON THE VM, from the repo root, after bootstrap.sh and `rclone config`.
# Launches pptonline_scraper.py + commoncrawl_pptx_scraper.py — these two are
# the highest-volume sources toward a 300K target (pptonline draws from a
# 1.4M-entry HuggingFace dataset; commoncrawl mines ~70 institutional domains
# via the Common Crawl columnar index). Unlike the CKAN pipeline, these use
# the EXISTING deliver_to_gdrive.py (BATCH_02) since they were always meant to
# feed the same consolidated batch as your other 73 scrapers, not a separate one.
#
# tmux windows:
#   pptonline   - pptonline_scraper.py, writing to hf_pptonline/
#   commoncrawl - commoncrawl_pptx_scraper.py, writing to joint_downloaded/
#   delivery    - deliver_to_gdrive.py --watch, BATCH_02 numbering, validating
#                 into a local staging folder (not a live FUSE mount — see
#                 the CKAN pipeline's comments for why)
#   drivesync   - `rclone copy` loop pushing the staging folder to
#                 gdrive:BATCH_02 every SYNC_INTERVAL seconds
#
# Usage:
#   PPTONLINE_TARGET=250000 COMMONCRAWL_TARGET=50000 bash deploy/run_bulk_pipeline.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SESSION="bulk-pipeline"
PPTONLINE_TARGET="${PPTONLINE_TARGET:-250000}"
COMMONCRAWL_TARGET="${COMMONCRAWL_TARGET:-50000}"
COMMONCRAWL_CRAWLS="${COMMONCRAWL_CRAWLS:-5}"
DRIVE_REMOTE="${DRIVE_REMOTE:-gdrive}"
DRIVE_FOLDER="${DRIVE_FOLDER:-BATCH_02}"
SYNC_INTERVAL="${SYNC_INTERVAL:-300}"
STAGING_DIR="$ROOT/gdrive_staging_bulk"

if ! rclone listremotes | grep -q "^${DRIVE_REMOTE}:$"; then
  echo "ERROR: rclone remote '${DRIVE_REMOTE}:' not found. Run 'rclone config' first" >&2
  exit 1
fi

mkdir -p "$STAGING_DIR"
tmux kill-session -t "$SESSION" 2>/dev/null || true

tmux new-session -d -s "$SESSION" -n pptonline \
  "cd $ROOT && source venv/bin/activate && python3 -u pptonline_scraper.py --target $PPTONLINE_TARGET; bash"

tmux new-window -t "$SESSION" -n commoncrawl \
  "cd $ROOT && source venv/bin/activate && python3 -u commoncrawl_pptx_scraper.py --target $COMMONCRAWL_TARGET --crawls $COMMONCRAWL_CRAWLS; bash"

tmux new-window -t "$SESSION" -n delivery \
  "cd $ROOT && source venv/bin/activate && python3 -u deliver_to_gdrive.py --gdrive-path $STAGING_DIR --watch --interval 120; bash"

tmux new-window -t "$SESSION" -n drivesync \
  "while true; do echo \"[\$(date)] syncing to ${DRIVE_REMOTE}:${DRIVE_FOLDER}\"; rclone copy $STAGING_DIR ${DRIVE_REMOTE}:${DRIVE_FOLDER} --transfers 8 --checkers 8 -P; sleep $SYNC_INTERVAL; done"

echo "Started tmux session '$SESSION' with windows: pptonline, commoncrawl, delivery, drivesync"
echo "  Attach : tmux attach -t $SESSION"
echo "  Switch : Ctrl+B then W"
echo "  Detach : Ctrl+B then D"
echo "  Drive folder: ${DRIVE_REMOTE}:${DRIVE_FOLDER}"
