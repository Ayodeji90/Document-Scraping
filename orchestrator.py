#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Global Orchestrator for Academic Document Scraping.
Runs all regional scrapers sequentially and provides a live dashboard of progress.
"""

import os
import subprocess
import time
import sys
from pathlib import Path

# List of all implemented scrapers
SCRAPERS = [
    # Africa
    "africa/south_africa_pptx_scraper.py",
    # Asia
    "asia/india_pptx_scraper.py", "asia/japan_pptx_scraper.py", "asia/south_korea_pptx_scraper.py",
    "asia/israel_pptx_scraper.py", "asia/saudi_arabia_pptx_scraper.py", "asia/thailand_pptx_scraper.py",
    "asia/vietnam_pptx_scraper.py", "asia/singapore_pptx_scraper.py", "asia/malaysia_pptx_scraper.py",
    "asia/turkey_pptx_scraper.py", "asia/hong_kong_pptx_scraper.py", "asia/taiwan_pptx_scraper.py",
    # Europe
    "europe/uk_pptx_scraper.py", "europe/france_pptx_scraper.py", "europe/germany_pptx_scraper.py",
    "europe/italy_pptx_scraper.py", "europe/spain_pptx_scraper.py", "europe/netherlands_pptx_scraper.py",
    "europe/switzerland_pptx_scraper.py", "europe/belgium_pptx_scraper.py", "europe/austria_pptx_scraper.py",
    "europe/nordics_pptx_scraper.py", "europe/norway_pptx_scraper.py", "europe/denmark_pptx_scraper.py",
    "europe/finland_pptx_scraper.py", "europe/ireland_pptx_scraper.py", "europe/portugal_pptx_scraper.py",
    "europe/greece_pptx_scraper.py", "europe/poland_pptx_scraper.py", "europe/czech_republic_pptx_scraper.py",
    "europe/hungary_pptx_scraper.py",
    # Americas
    "north_america/canada_pptx_scraper.py", "north_america/mexico_pptx_scraper.py",
    "south_america/brazil_pptx_scraper.py", "south_america/argentina_pptx_scraper.py",
    "south_america/chile_pptx_scraper.py",
    # Oceania
    "oceania/australia_pptx_scraper.py", "oceania/new_zealand_pptx_scraper.py"
]

MASTER_LOG = Path("logs/master_seen_tags.txt")

def get_total_count():
    if not MASTER_LOG.exists(): return 0
    with open(MASTER_LOG, "r") as f:
        return sum(1 for line in f if line.strip())

def run_all(target=10000):
    total_start = get_total_count()
    print("\n" + "="*60)
    print("🌍 GLOBAL ACADEMIC SCRAPER ORCHESTRATOR")
    print(f"   Initial Total Files: {total_start:,}")
    print("="*60 + "\n")

    for i, scraper_path in enumerate(SCRAPERS, 1):
        country = scraper_path.split("/")[-1].replace("_pptx_scraper.py", "").replace("_", " ").title()
        
        print("\n" + "-"*40)
        print(f"🌍 [{i}/{len(SCRAPERS)}] RUNNING: {country}")
        print("-"*40)
        
        try:
            # Run the scraper and stream output
            process = subprocess.Popen(
                ["python3", scraper_path, "--target", str(target), "--no-verify-ssl"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1  # Line buffered
            )

            # Stream the output live to the terminal
            for line in process.stdout:
                sys.stdout.write(f"[{country}] {line}")
                sys.stdout.flush()

            process.wait()
            
            new_total = get_total_count()
            print(f"\n✨ {country} session finished.")
            print(f"📊 Global Dataset Total: {new_total:,}")
            
            # 5-second breath before next country
            time.sleep(5)

        except KeyboardInterrupt:
            print("\n🛑 Orchestrator stopped by user.")
            sys.exit(0)
        except Exception as e:
            print(f"❌ Error running {country}: {e}")

    print("="*60)
    print(f"🏁 ALL SCRAPERS FINISHED!")
    print(f"   Final Total Count: {get_total_count():,}")
    print("="*60)

if __name__ == "__main__":
    run_all()
