#!/bin/bash
# Runs all country scrapers in parallel tmux windows.
# Usage: bash run_all_parallel.sh
# Reattach anytime with: tmux attach -t scrapers

SESSION="scrapers"
VENV="$(dirname "$0")/venv/bin/activate"
ROOT="$(cd "$(dirname "$0")" && pwd)"
TARGET="${TARGET:-10000}"
FLAGS="--target $TARGET --no-verify-ssl"

# Kill existing session if present
tmux kill-session -t "$SESSION" 2>/dev/null

# All scrapers grouped: [window_name]="script_path"
declare -A SCRAPERS=(
  # Asia
  [india]="asia/india_pptx_scraper.py"
  [japan]="asia/japan_pptx_scraper.py"
  [south_korea]="asia/south_korea_pptx_scraper.py"
  [china]="asia/china_pptx_scraper.py"
  [indonesia]="asia/indonesia_pptx_scraper.py"
  [thailand]="asia/thailand_pptx_scraper.py"
  [vietnam]="asia/vietnam_pptx_scraper.py"
  [malaysia]="asia/malaysia_pptx_scraper.py"
  [singapore]="asia/singapore_pptx_scraper.py"
  [taiwan]="asia/taiwan_pptx_scraper.py"
  [hong_kong]="asia/hong_kong_pptx_scraper.py"
  [philippines]="asia/philippines_pptx_scraper.py"
  [bangladesh]="asia/bangladesh_pptx_scraper.py"
  [pakistan]="asia/pakistan_pptx_scraper.py"
  [sri_lanka]="asia/sri_lanka_pptx_scraper.py"
  [israel]="asia/israel_pptx_scraper.py"
  [turkey]="asia/turkey_pptx_scraper.py"
  [saudi_arabia]="asia/saudi_arabia_pptx_scraper.py"
  [uae]="asia/uae_pptx_scraper.py"
  [iran]="asia/iran_pptx_scraper.py"
  [jordan]="asia/jordan_pptx_scraper.py"
  [lebanon]="asia/lebanon_pptx_scraper.py"
  [qatar]="asia/qatar_pptx_scraper.py"
  [kazakhstan]="asia/kazakhstan_pptx_scraper.py"
  # Europe
  [uk]="europe/uk_pptx_scraper.py"
  [germany]="europe/germany_pptx_scraper.py"
  [france]="europe/france_pptx_scraper.py"
  [italy]="europe/italy_pptx_scraper.py"
  [spain]="europe/spain_pptx_scraper.py"
  [netherlands]="europe/netherlands_pptx_scraper.py"
  [switzerland]="europe/switzerland_pptx_scraper.py"
  [austria]="europe/austria_pptx_scraper.py"
  [belgium]="europe/belgium_pptx_scraper.py"
  [poland]="europe/poland_pptx_scraper.py"
  [portugal]="europe/portugal_pptx_scraper.py"
  [greece]="europe/greece_pptx_scraper.py"
  [czech_republic]="europe/czech_republic_pptx_scraper.py"
  [denmark]="europe/denmark_pptx_scraper.py"
  [norway]="europe/norway_pptx_scraper.py"
  [finland]="europe/finland_pptx_scraper.py"
  [ireland]="europe/ireland_pptx_scraper.py"
  [hungary]="europe/hungary_pptx_scraper.py"
  [bulgaria]="europe/bulgaria_pptx_scraper.py"
  [croatia]="europe/croatia_pptx_scraper.py"
  [estonia]="europe/estonia_pptx_scraper.py"
  # Africa
  [nigeria]="africa/nigeria_pptx_scraper.py"
  [kenya]="africa/kenya_pptx_scraper.py"
  [ghana]="africa/ghana_pptx_scraper.py"
  [egypt]="africa/egypt_pptx_scraper.py"
  [morocco]="africa/morocco_pptx_scraper.py"
  [tunisia]="africa/tunisia_pptx_scraper.py"
  # Americas
  [canada]="north_america/canada_pptx_scraper.py"
  [mexico]="north_america/mexico_pptx_scraper.py"
  [brazil]="south_america/brazil_pptx_scraper.py"
  [argentina]="south_america/argentina_pptx_scraper.py"
  [chile]="south_america/chile_pptx_scraper.py"
  # Oceania
  [australia]="oceania/australia_pptx_scraper.py"
  [new_zealand]="oceania/new_zealand_pptx_scraper.py"
)

FIRST=1
for name in "${!SCRAPERS[@]}"; do
  script="${SCRAPERS[$name]}"
  # Skip if script doesn't exist
  [ -f "$ROOT/$script" ] || continue

  cmd="cd $ROOT && source $VENV && python3 $script $FLAGS; echo 'DONE: $name — press Enter to close'; read"

  if [ $FIRST -eq 1 ]; then
    tmux new-session -d -s "$SESSION" -n "$name" "bash -c '$cmd'"
    FIRST=0
  else
    tmux new-window -t "$SESSION" -n "$name" "bash -c '$cmd'"
  fi
done

echo ""
echo "All scrapers launched in tmux session '$SESSION'."
echo ""
echo "  Attach to watch:  tmux attach -t $SESSION"
echo "  List windows:     tmux list-windows -t $SESSION"
echo "  Switch windows:   Ctrl+B then W (inside tmux)"
echo "  Detach (keep running): Ctrl+B then D"
echo "  Kill all:         tmux kill-session -t $SESSION"
