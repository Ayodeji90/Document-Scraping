#!/usr/bin/env bash
# Run this ON THE VM, from the repo root, after bootstrap.sh and `rclone config`.
# Launches three tmux windows:
#   scraper   - ckan_pptx_scraper.py, harvesting + downloading to joint_downloaded/
#   delivery  - deliver_to_gdrive.py --watch, validating + packaging into a local
#               staging folder (kept local so the Python process never depends
#               on a live FUSE mount for writes)
#   drivesync - a loop pushing the staging folder to Google Drive via
#               `rclone copy` every SYNC_INTERVAL seconds (resumable, retries
#               on its own — more robust than a live mount for a days-long run)
#
# Usage:
#   TARGET=300000 DRIVE_REMOTE=gdrive DRIVE_FOLDER=CKAN_PPTX bash deploy/run_ckan_pipeline.sh
#
# Requires: `rclone config` already run once with a remote literally named
# "gdrive" (or override DRIVE_REMOTE to match whatever you named it).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SESSION="ckan-pipeline"
TARGET="${TARGET:-300000}"
DRIVE_REMOTE="${DRIVE_REMOTE:-gdrive}"
DRIVE_FOLDER="${DRIVE_FOLDER:-CKAN_PPTX}"
SYNC_INTERVAL="${SYNC_INTERVAL:-300}"
STAGING_DIR="$ROOT/gdrive_staging"

if ! rclone listremotes | grep -q "^${DRIVE_REMOTE}:$"; then
  echo "ERROR: rclone remote '${DRIVE_REMOTE}:' not found. Run 'rclone config' first" >&2
  echo "       (see deploy/bootstrap.sh output for the headless-auth steps)." >&2
  exit 1
fi

mkdir -p "$STAGING_DIR"
tmux kill-session -t "$SESSION" 2>/dev/null || true

tmux new-session -d -s "$SESSION" -n scraper \
  "cd $ROOT && source venv/bin/activate && python3 -u ckan_pptx_scraper.py --target $TARGET; bash"

tmux new-window -t "$SESSION" -n delivery \
  "cd $ROOT && source venv/bin/activate && python3 -u deliver_to_gdrive.py --gdrive-path $STAGING_DIR --watch --interval 120; bash"

tmux new-window -t "$SESSION" -n drivesync \
  "while true; do echo \"[\$(date)] syncing to ${DRIVE_REMOTE}:${DRIVE_FOLDER}\"; rclone copy $STAGING_DIR ${DRIVE_REMOTE}:${DRIVE_FOLDER} --transfers 8 --checkers 8 -P; sleep $SYNC_INTERVAL; done"

echo "Started tmux session '$SESSION' with windows: scraper, delivery, drivesync"
echo "  Attach : tmux attach -t $SESSION"
echo "  Switch : Ctrl+B then W"
echo "  Detach : Ctrl+B then D   (safe to close your SSH session after detaching)"
echo "  Drive folder: ${DRIVE_REMOTE}:${DRIVE_FOLDER}"
