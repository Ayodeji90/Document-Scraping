#!/usr/bin/env python3
"""
Adds Bing search as a fallback engine to all scrapers.
When DuckDuckGo rate-limits, the scraper will automatically try Bing instead.
"""
from pathlib import Path

SCRAPER_DIRS = ["africa", "asia", "europe", "north_america", "south_america", "oceania"]

# The Bing search method to inject
BING_METHOD = '''
    def _search_bing(self, query):
        """Fallback search via Bing when DuckDuckGo is rate-limited."""
        found = []
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            url = f"https://www.bing.com/search?q={requests.utils.quote(query)}&count=50"
            resp = self.session.get(url, headers=headers, timeout=15, verify=self.verify_ssl)
            if resp.ok:
                soup = BeautifulSoup(resp.text, "lxml")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if PRESENTATION_RE.search(href) and href.startswith("http"):
                        found.append(href)
        except:
            pass
        return found
'''

# Updated _search_ddgs that falls back to Bing on rate limit
UPDATED_SEARCH = '''    def _search_ddgs(self, query):
        found = []
        for attempt in range(3):
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=self.max_results_per_query))
                for r in results:
                    if r.get("href"): found.append(r["href"])
                break
            except RatelimitException:
                logger.warning("DuckDuckGo rate-limited. Falling back to Bing...")
                return self._search_bing(query)
            except Exception as exc:
                if "Timeout" in str(exc) and attempt < 2: time.sleep(5); continue
                break
        return found
'''

def patch_file(file_path: Path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    original = content

    # Skip if already patched
    if "_search_bing" in content:
        print(f"⏭️  Already has Bing: {file_path}")
        return

    # 1. Inject the _search_bing method right before _search_ddgs
    if "def _search_ddgs" in content:
        content = content.replace("    def _search_ddgs", BING_METHOD + "\n    def _search_ddgs")

    # 2. Update _search_ddgs to fallback to Bing on rate limit
    # Find and replace the existing _search_ddgs method
    import re
    pattern = r'    def _search_ddgs\(self, query\):.*?(?=\n    def _)'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        content = content[:match.start()] + UPDATED_SEARCH + content[match.end():]

    if content != original:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"⚡ Added Bing fallback: {file_path}")
    else:
        print(f"⚠️  Could not patch: {file_path}")

def main():
    count = 0
    for sdir in SCRAPER_DIRS:
        d = Path(sdir)
        if not d.exists(): continue
        for f in d.glob("*_scraper.py"):
            patch_file(f)
            count += 1
    print(f"\nDone! Processed {count} scrapers.")

if __name__ == "__main__":
    main()
