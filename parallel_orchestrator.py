#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Parallel Orchestrator for Academic Document Scraping.
WARNING: Running all scrapers at once may lead to IP bans.
"""

import os
import subprocess
import time
import sys
from pathlib import Path

SCRAPERS = [
    # Africa (7)
    "africa/south_africa_pptx_scraper.py", "africa/nigeria_pptx_scraper.py",
    "africa/egypt_pptx_scraper.py", "africa/kenya_pptx_scraper.py",
    "africa/morocco_pptx_scraper.py", "africa/ghana_pptx_scraper.py",
    "africa/tunisia_pptx_scraper.py",
    # Asia (19) — China, Hong Kong, Taiwan excluded per client request
    "asia/india_pptx_scraper.py", "asia/japan_pptx_scraper.py", "asia/south_korea_pptx_scraper.py",
    "asia/israel_pptx_scraper.py", "asia/saudi_arabia_pptx_scraper.py", "asia/thailand_pptx_scraper.py",
    "asia/vietnam_pptx_scraper.py", "asia/singapore_pptx_scraper.py", "asia/malaysia_pptx_scraper.py",
    "asia/turkey_pptx_scraper.py",
    "asia/indonesia_pptx_scraper.py", "asia/philippines_pptx_scraper.py", "asia/pakistan_pptx_scraper.py",
    "asia/bangladesh_pptx_scraper.py", "asia/uae_pptx_scraper.py",
    "asia/iran_pptx_scraper.py",
    "asia/jordan_pptx_scraper.py", "asia/lebanon_pptx_scraper.py", "asia/qatar_pptx_scraper.py",
    "asia/sri_lanka_pptx_scraper.py", "asia/kazakhstan_pptx_scraper.py",
    # Europe (28)
    "europe/uk_pptx_scraper.py", "europe/france_pptx_scraper.py", "europe/germany_pptx_scraper.py",
    "europe/italy_pptx_scraper.py", "europe/spain_pptx_scraper.py", "europe/netherlands_pptx_scraper.py",
    "europe/switzerland_pptx_scraper.py", "europe/belgium_pptx_scraper.py", "europe/austria_pptx_scraper.py",
    "europe/nordics_pptx_scraper.py", "europe/norway_pptx_scraper.py", "europe/denmark_pptx_scraper.py",
    "europe/finland_pptx_scraper.py", "europe/ireland_pptx_scraper.py", "europe/portugal_pptx_scraper.py",
    "europe/greece_pptx_scraper.py", "europe/poland_pptx_scraper.py", "europe/czech_republic_pptx_scraper.py",
    "europe/hungary_pptx_scraper.py", "europe/romania_pptx_scraper.py", "europe/ukraine_pptx_scraper.py",
    "europe/croatia_pptx_scraper.py", "europe/serbia_pptx_scraper.py",
    "europe/russia_pptx_scraper.py", "europe/bulgaria_pptx_scraper.py",
    "europe/slovakia_pptx_scraper.py", "europe/lithuania_pptx_scraper.py",
    "europe/slovenia_pptx_scraper.py", "europe/estonia_pptx_scraper.py",
    # Americas (11)
    "north_america/canada_pptx_scraper.py", "north_america/mexico_pptx_scraper.py",
    "south_america/brazil_pptx_scraper.py", "south_america/argentina_pptx_scraper.py",
    "south_america/chile_pptx_scraper.py", "south_america/colombia_pptx_scraper.py",
    "south_america/peru_pptx_scraper.py", "south_america/ecuador_pptx_scraper.py",
    "south_america/venezuela_pptx_scraper.py", "south_america/costa_rica_pptx_scraper.py",
    "south_america/uruguay_pptx_scraper.py", "south_america/cuba_pptx_scraper.py",
    # Oceania (2)
    "oceania/australia_pptx_scraper.py", "oceania/new_zealand_pptx_scraper.py"
]

def get_dir_count(scraper_path):
    country = scraper_path.split("/")[-1].replace("_pptx_scraper.py", "")
    out_dir = Path(f"downloaded_ppts_{country}")
    if not out_dir.exists(): return 0
    return sum(1 for f in out_dir.glob("*.*") if f.is_file())

def print_dashboard(start_counts, processes):
    os.system('clear' if os.name == 'posix' else 'cls')
    print("="*65)
    print(f"🚀 GLOBAL PARALLEL SCRAPER DASHBOARD ({len(SCRAPERS)} COUNTRIES)")
    print(f"   Time: {time.strftime('%H:%M:%S')} | Active: {len([p for p in processes.values() if p.poll() is None])}")
    print("="*65)
    print(f"{'Country':<25} | {'New Downloads':<15} | {'Status'}")
    print("-" * 65)
    
    total_new = 0
    for s in SCRAPERS:
        name = s.split("/")[-1].replace("_pptx_scraper.py", "").replace("_", " ").title()
        current = get_dir_count(s)
        diff = max(0, current - start_counts[s])
        total_new += diff
        
        proc = processes.get(s)
        status = "Waiting"
        if proc:
            status = "Running" if proc.poll() is None else "Finished"
            if proc.poll() is not None and proc.returncode != 0:
                status = "Error"
        
        print(f"{name:<25} | {diff:<15} | {status}")
    
    print("-" * 65)
    print(f"Total Session Downloads (Parallel): {total_new:,}")
    print("="*65)
    print("NOTE: Close terminal or Ctrl+C to stop all processes.")

def run_parallel(target=10000):
    # Reset start counts to 0 so we count total files, not just new ones
    # This avoids negatives when aggregate_downloads.py moves files mid-run
    start_counts = {s: 0 for s in SCRAPERS}
    processes = {}

    print(f"🛰️ Launching all {len(SCRAPERS)} countries in parallel... please wait...")

    
    for s in SCRAPERS:
        try:
            # Launch all scrapers at once
            proc = subprocess.Popen(
                ["python3", s, "--target", str(target), "--no-verify-ssl"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            processes[s] = proc
            time.sleep(0.5) # Minimal stagger to prevent CPU spike
        except Exception as e:
            print(f"Failed to launch {s}: {e}")

    try:
        while True:
            print_dashboard(start_counts, processes)
            time.sleep(60) # Refresh every minute
            
            # Check if all are finished
            if all(p.poll() is not None for p in processes.values()):
                print_dashboard(start_counts, processes)
                print("\n🏁 All parallel processes have completed.")
                break
    except KeyboardInterrupt:
        print("\n🛑 Shutting down all parallel processes...")
        for p in processes.values():
            p.terminate()
        sys.exit(0)

if __name__ == "__main__":
    run_parallel()
