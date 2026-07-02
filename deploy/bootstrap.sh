#!/usr/bin/env bash
# Run this ON THE VM (after `gcloud compute ssh ckan-scraper`).
# Installs system deps + rclone, clones the repo, sets up the venv.
#
# Usage on the VM:
#   curl -fsSL https://raw.githubusercontent.com/Ayodeji90/Document-Scraping/main/deploy/bootstrap.sh | bash
# or, if you scp'd the repo over already, just: bash deploy/bootstrap.sh
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Ayodeji90/Document-Scraping.git}"
REPO_DIR="${REPO_DIR:-$HOME/Document-Scraping}"

echo "[1/4] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv python3-pip git curl unzip tmux

echo "[2/4] Installing rclone..."
if ! command -v rclone >/dev/null 2>&1; then
  curl -fsSL https://rclone.org/install.sh | sudo bash
fi

echo "[3/4] Cloning repo..."
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" pull
else
  git clone "$REPO_URL" "$REPO_DIR"
fi

echo "[4/4] Setting up Python venv..."
cd "$REPO_DIR"
python3 -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo ""
echo "Done. Next steps:"
echo "  1. Configure rclone's Google Drive remote (one-time, interactive):"
echo "       rclone config"
echo "     If this VM has no browser, run 'rclone authorize \"drive\"' on your"
echo "     LOCAL machine instead, sign in there, then paste the resulting"
echo "     token back into the 'rclone config' prompt running on this VM."
echo "     Name the remote 'gdrive' to match deploy/run_ckan_pipeline.sh."
echo "  2. cd $REPO_DIR && bash deploy/run_ckan_pipeline.sh"
