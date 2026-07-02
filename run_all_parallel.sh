#!/bin/bash
# Launches ALL country scrapers + bulk sources in parallel tmux windows.
# Auto-discovers every *_scraper.py in region folders (skips colab_* scripts).
#
# Usage:
#   bash run_all_parallel.sh              # default target 10000
#   TARGET=5000 bash run_all_parallel.sh  # custom target
#
# Inside tmux:
#   Attach      : tmux attach -t scrapers
#   List windows: tmux list-windows -t scrapers
#   Switch      : Ctrl+B then W
#   Detach      : Ctrl+B then D
#   Kill all    : tmux kill-session -t scrapers

SESSION="scrapers"
ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/venv/bin/activate"
TARGET="${TARGET:-10000}"
FLAGS="--target $TARGET --no-verify-ssl"

# Kill any existing session cleanly
tmux kill-session -t "$SESSION" 2>/dev/null
sleep 1

REGIONS="africa asia europe north_america south_america oceania"
FIRST=1
COUNT=0

echo "Launching country scrapers..."

for region in $REGIONS; do
  for script in "$ROOT/$region/"*_scraper.py; do
    [ -f "$script" ] || continue

    # Skip colab-specific scripts (not meant for server)
    basename "$script" | grep -q "^colab_" && continue

    name=$(basename "$script" _pptx_scraper.py)
    cmd="cd $ROOT && source $VENV && python3 $script $FLAGS; bash"

    if [ $FIRST -eq 1 ]; then
      tmux new-session -d -s "$SESSION" -n "$name" "bash -c \"$cmd\""
      FIRST=0
    else
      tmux new-window -t "$SESSION" -n "$name" "bash -c \"$cmd\""
    fi

    COUNT=$((COUNT + 1))
  done
done

echo "  $COUNT country scrapers launched."
echo ""
echo "Launching bulk/archive sources..."

# Common Crawl — scans billions of crawled pages for PPTX (highest volume)
tmux new-window -t "$SESSION" -n "commoncrawl" \
  "bash -c \"cd $ROOT && source $VENV && python3 commoncrawl_pptx_scraper.py --target 30000 --crawls 3; bash\""

# Mega scraper — Archive.org + OAI-PMH institutional repos + direct URLs
tmux new-window -t "$SESSION" -n "mega" \
  "bash -c \"cd $ROOT && source $VENV && python3 mega_pptx_scraper.py --target 20000; bash\""

# Wayback Machine / Internet Archive CDX
tmux new-window -t "$SESSION" -n "wayback" \
  "bash -c \"cd $ROOT && source $VENV && python3 wayback_pptx_scraper.py --target 15000; bash\""

# PPT-Online — 1.4M entries from HuggingFace dataset
tmux new-window -t "$SESSION" -n "pptonline" \
  "bash -c \"cd $ROOT && source $VENV && python3 pptonline_scraper.py; bash\""

# Delivery packager — validates and pushes to /root/gdrive/BATCH_02/
tmux new-window -t "$SESSION" -n "delivery" \
  "bash -c \"cd $ROOT && source $VENV && python3 deliver_to_gdrive.py --gdrive-path /root/gdrive/BATCH_02 --watch; bash\""

echo "  Bulk sources + delivery packager launched."
echo ""
echo "======================================================"
echo "  ALL DONE — $(tmux list-windows -t $SESSION | wc -l) windows running"
echo "======================================================"
echo ""
echo "  Attach to watch : tmux attach -t $SESSION"
echo "  Switch windows  : Ctrl+B then W"
echo "  Detach          : Ctrl+B then D"
echo "  Kill everything : tmux kill-session -t $SESSION"
echo ""
echo "  Monitor progress:"
echo "    find $ROOT -name 'BATCH_02_*.pptx' | wc -l"
