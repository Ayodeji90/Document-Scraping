#!/usr/bin/env python3
"""
Optimizes all scrapers for speed:
1. Check Content-Length header BEFORE downloading (skip small files without wasting bandwidth)
2. Reduce inter-query delay from 5.0s to 2.0s (parallel mode spreads the load)  
3. Increase download timeout for large files
"""
from pathlib import Path
import re

SCRAPER_DIRS = ["africa", "asia", "europe", "north_america", "south_america", "oceania"]

def optimize_file(file_path: Path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    original = content

    # 1. Add Content-Length pre-check BEFORE downloading
    # Find the download method and add a HEAD request check
    old_download = 'resp = self.session.get(url, timeout=self.timeout, stream=True, verify=self.verify_ssl)'
    new_download = '''# Pre-check file size via HEAD request to avoid wasting bandwidth
            try:
                head = self.session.head(url, timeout=10, verify=self.verify_ssl, allow_redirects=True)
                cl = int(head.headers.get("Content-Length", 0))
                if 0 < cl < 5242880:  # Skip files confirmed under 5MB
                    return None
            except: pass
            resp = self.session.get(url, timeout=self.timeout, stream=True, verify=self.verify_ssl)'''
    content = content.replace(old_download, new_download)
    
    # 2. Reduce delay from 5.0 to 2.0 seconds
    content = content.replace('delay_seconds: float = 5.0', 'delay_seconds: float = 2.0')
    content = content.replace('delay_seconds=5.0', 'delay_seconds=2.0')
    
    # 3. Increase download timeout for large files
    content = content.replace('request_timeout: int = 20', 'request_timeout: int = 45')
    content = content.replace('request_timeout=20', 'request_timeout=45')
    
    if content != original:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"⚡ Optimized: {file_path}")
    else:
        print(f"⏭️  Already optimized: {file_path}")

def main():
    count = 0
    for sdir in SCRAPER_DIRS:
        d = Path(sdir)
        if not d.exists(): continue
        for f in d.glob("*_scraper.py"):
            optimize_file(f)
            count += 1
    print(f"\nDone! Optimized {count} scrapers.")

if __name__ == "__main__":
    main()
