#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dashboard Orchestrator for Academic Document Scraping.
Provides a clean, summarizing view of downloads per country.
"""

import os
import subprocess
import time
import sys
from pathlib import Path

SCRAPERS = [
    "africa/south_africa_pptx_scraper.py",
    "asia/india_pptx_scraper.py", "asia/japan_pptx_scraper.py", "asia/south_korea_pptx_scraper.py",
    "asia/israel_pptx_scraper.py", "asia/saudi_arabia_pptx_scraper.py", "asia/thailand_pptx_scraper.py",
    "asia/vietnam_pptx_scraper.py", "asia/singapore_pptx_scraper.py", "asia/malaysia_pptx_scraper.py",
    "asia/turkey_pptx_scraper.py", "asia/hong_kong_pptx_scraper.py", "asia/taiwan_pptx_scraper.py",
    "europe/uk_pptx_scraper.py", "europe/france_pptx_scraper.py", "europe/germany_pptx_scraper.py",
    "europe/italy_pptx_scraper.py", "europe/spain_pptx_scraper.py", "europe/netherlands_pptx_scraper.py",
    "europe/switzerland_pptx_scraper.py", "europe/belgium_pptx_scraper.py", "europe/austria_pptx_scraper.py",
    "europe/nordics_pptx_scraper.py", "europe/norway_pptx_scraper.py", "europe/denmark_pptx_scraper.py",
    "europe/finland_pptx_scraper.py", "europe/ireland_pptx_scraper.py", "europe/portugal_pptx_scraper.py",
    "europe/greece_pptx_scraper.py", "europe/poland_pptx_scraper.py", "europe/czech_republic_pptx_scraper.py",
    "europe/hungary_pptx_scraper.py",
    "north_america/canada_pptx_scraper.py", "north_america/mexico_pptx_scraper.py",
    "south_america/brazil_pptx_scraper.py", "south_america/argentina_pptx_scraper.py",
    "south_america/chile_pptx_scraper.py",
    "oceania/australia_pptx_scraper.py", "oceania/new_zealand_pptx_scraper.py"
]

# Track session progress
stats = {s: 0 for s in SCRAPERS}
status = {s: "Pending" for s in SCRAPERS}

def get_dir_count(scraper_path):
    # Extract country name and look for its download folder
    country = scraper_path.split("/")[-1].replace("_pptx_scraper.py", "")
    out_dir = Path(f"downloaded_ppts_{country}")
    if not out_dir.exists(): return 0
    return sum(1 for f in out_dir.glob("*.*") if f.is_file())

def print_dashboard():
    os.system('clear' if os.name == 'posix' else 'cls')
    print("="*50)
    print("🌍 GLOBAL SCRAPER DASHBOARD (Live Session)")
    print(f"   Time: {time.strftime('%H:%M:%S')}")
    print("="*50)
    print(f"{'Country':<25} | {'New Downloads':<15} | {'Status'}")
    print("-" * 50)
    
    for s in SCRAPERS:
        name = s.split("/")[-1].replace("_pptx_scraper.py", "").replace("_", " ").title()
        print(f"{name:<25} | {stats[s]:<15} | {status[s]}")
    
    print("-" * 50)
    print(f"Total Session Downloads: {sum(stats.values()):,}")
    print("="*50)

def run_orchestrator(target=10000):
    # Get initial counts to track only "New" downloads
    start_counts = {s: get_dir_count(s) for s in SCRAPERS}
    
    for scraper_path in SCRAPERS:
        status[scraper_path] = "Running..."
        print_dashboard()
        
        try:
            # Run scraper in background/silent mode
            process = subprocess.Popen(
                ["python3", scraper_path, "--target", str(target), "--no-verify-ssl"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # While it runs, we refresh the dashboard every 30 seconds
            while process.poll() is None:
                # Update current count
                current = get_dir_count(scraper_path)
                stats[scraper_path] = current - start_counts[scraper_path]
                print_dashboard()
                time.sleep(30) # Refresh rate

            status[scraper_path] = "Finished"
            # Final count update
            stats[scraper_path] = get_dir_count(scraper_path) - start_counts[scraper_path]
            print_dashboard()

        except KeyboardInterrupt:
            print("\n🛑 Stopped by user.")
            sys.exit(0)
        except Exception as e:
            status[scraper_path] = "Error"
            print_dashboard()
            time.sleep(2)

if __name__ == "__main__":
    run_orchestrator()
