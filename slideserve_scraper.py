import argparse
import asyncio
import hashlib
import logging
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from tqdm.asyncio import tqdm

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
        level=level,
        stream=sys.stderr,
    )

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

# Keywords to strictly reject
REJECT_KEYWORDS = [
    # USA / Geolocation
    r"\busa\b", r"united-states", r"america",
    # Gov / Edu
    r"\bgov\b", r"\bedu\b", r"university", r"college", r"dept", r"institute",
    # Top Major Companies
    r"apple", r"google", r"microsoft", r"amazon", r"facebook", r"meta", r"netflix", r"tesla"
]
REJECT_REGEX = re.compile("|".join(REJECT_KEYWORDS), re.IGNORECASE)
CHINESE_REGEX = re.compile(r"[\u4e00-\u9fff]+")

def is_allowed_url(url: str) -> bool:
    """Check if the URL contains rejected keywords or Chinese characters."""
    if REJECT_REGEX.search(url):
        return False
    if CHINESE_REGEX.search(url):
        return False
    return True

# ---------------------------------------------------------------------------
# Scraper Logic
# ---------------------------------------------------------------------------

class SlideServeScraper:
    def __init__(self, download_dir: str = "downloaded_ppts", concurrency: int = 10):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.concurrency = concurrency
        self.session: aiohttp.ClientSession = None
        self.semaphore = asyncio.Semaphore(concurrency)
        
        self.stats = {
            "sitemaps_processed": 0,
            "urls_extracted": 0,
            "urls_filtered": 0,
            "downloaded": 0,
            "failed": 0,
            "skipped_duplicate": 0
        }

    async def __aenter__(self):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        self.session = aiohttp.ClientSession(headers=headers, connector=aiohttp.TCPConnector(limit=self.concurrency))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def fetch_sitemap_index(self) -> list[str]:
        """Fetch the main sitemap index and extract sub-sitemap URLs (docs-*.xml.gz)."""
        url = "https://www.slideserve.com/sitemap.xml"
        logger.info(f"Fetching sitemap index: {url}")
        
        async with self.session.get(url) as resp:
            if not resp.ok:
                logger.error(f"Failed to fetch sitemap index: {resp.status}")
                return []
            
            content = await resp.text()
            
        sitemaps = []
        try:
            root = ET.fromstring(content)
            # Handle XML namespace
            ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            for sitemap in root.findall("ns:sitemap", ns):
                loc = sitemap.find("ns:loc", ns)
                if loc is not None and "docs-" in loc.text:
                    sitemaps.append(loc.text)
        except ET.ParseError as e:
            logger.error(f"Error parsing sitemap index XML: {e}")
            
        logger.info(f"Found {len(sitemaps)} document sitemaps.")
        return sitemaps

    async def fetch_and_parse_sitemap(self, sitemap_url: str) -> list[str]:
        """Fetch a .xml.gz sitemap and return the list of presentation URLs."""
        urls = []
        try:
            async with self.session.get(sitemap_url) as resp:
                if not resp.ok:
                    return urls
                
                # Sitemaps might be compressed (gz)
                if sitemap_url.endswith(".gz"):
                    import gzip
                    content = gzip.decompress(await resp.read())
                else:
                    content = await resp.read()

                root = ET.fromstring(content)
                ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                for url_element in root.findall("ns:url", ns):
                    loc = url_element.find("ns:loc", ns)
                    if loc is not None:
                        urls.append(loc.text)
        except Exception as e:
            logger.debug(f"Failed to parse sitemap {sitemap_url}: {e}")

        self.stats["sitemaps_processed"] += 1
        self.stats["urls_extracted"] += len(urls)
        return urls

    async def get_download_url(self, presentation_url: str, presentation_id: str) -> str:
        """
        Attempt to resolve the actual download endpoint for a presentation.
        Since SlideServe's exact endpoint isn't fully documented, we first
        check a known pattern or fetch the HTML to find the download link.
        """
        # A common pattern for secondary download routes might look like:
        # https://www.slideserve.com/download/{presentation_id}
        # For now, let's try to fetch the presentation page and parse the download link.
        try:
            async with self.session.get(presentation_url) as resp:
                if not resp.ok:
                    logger.debug(f"Failed to fetch presentation page {presentation_url} (Status: {resp.status})")
                    if resp.status in (403, 429):
                        logger.warning(f"Blocked by SlideServe (Status {resp.status}). Rate limit or Cloudflare block.")
                        # Wait a bit if we hit a rate limit
                        await asyncio.sleep(2)
                    return None
                
                html = await resp.text()
                
                # Check for standard download links in HTML
                # <a ... href="https://www.slideserve.com/download/123456">Download</a>
                match = re.search(r'href=["\'](https?://[^"\']*?download[^"\']*?\.pptx?)["\']', html, re.IGNORECASE)
                if match:
                    return match.group(1)
                
                match = re.search(r'href=["\']([^"\']*?export[^"\']*?\.pptx?)["\']', html, re.IGNORECASE)
                if match:
                    return match.group(1)
                    
                # If no direct .ppt link is found, we can try to guess the download URL
                # based on the ID.
                if presentation_id:
                    return f"https://www.slideserve.com/download/{presentation_id}"
                
        except Exception as e:
            logger.debug(f"Error fetching presentation page {presentation_url}: {e}")
        
        return None

    async def process_presentation(self, url: str):
        """Process a single presentation URL: extract ID, find download link, and download."""
        async with self.semaphore:
            if not is_allowed_url(url):
                self.stats["urls_filtered"] += 1
                return

            # Extract ID from URL (e.g., .../title-123456)
            match = re.search(r'-(\d+)$', url)
            presentation_id = match.group(1) if match else None

            download_url = await self.get_download_url(url, presentation_id)
            if not download_url:
                self.stats["failed"] += 1
                return

            await self.download_file(download_url)

    async def download_file(self, download_url: str):
        """Download the file, compute MD5 hash, and save it to disk."""
        try:
            async with self.session.get(download_url) as resp:
                if not resp.ok:
                    logger.debug(f"Failed to download {download_url} (Status: {resp.status})")
                    self.stats["failed"] += 1
                    return
                
                # Validate content type to ensure it's a presentation/binary
                ct = resp.headers.get("Content-Type", "").lower()
                if "text/html" in ct:
                    # Not a valid file
                    self.stats["failed"] += 1
                    return

                # Read content and compute hash on the fly
                hasher = hashlib.md5()
                chunks = []
                async for chunk in resp.content.iter_chunked(65536):
                    hasher.update(chunk)
                    chunks.append(chunk)

                if not chunks:
                    self.stats["failed"] += 1
                    return

                file_hash = hasher.hexdigest()
                dest_path = self.download_dir / f"{file_hash}.pptx"

                if dest_path.exists():
                    self.stats["skipped_duplicate"] += 1
                    return

                with open(dest_path, "wb") as f:
                    for chunk in chunks:
                        f.write(chunk)

                self.stats["downloaded"] += 1
                logger.debug(f"Downloaded: {dest_path.name}")
        except Exception as e:
            logger.debug(f"Failed to download {download_url}: {e}")
            self.stats["failed"] += 1


async def main():
    parser = argparse.ArgumentParser(description="SlideServe Sharded Scraper")
    parser.add_argument("--shard", type=int, default=0, help="Shard index (0-based)")
    parser.add_argument("--total-shards", type=int, default=1, help="Total number of shards")
    parser.add_argument("--target", type=int, default=1000, help="Target number of files to download for this shard")
    parser.add_argument("--concurrency", type=int, default=20, help="Number of concurrent downloads")
    parser.add_argument("--dir", type=str, default="downloaded_ppts", help="Download directory")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose debug logging")
    
    args = parser.parse_args()
    setup_logging(args.verbose)

    logger.info(f"Starting SlideServe scraper (Shard {args.shard}/{args.total_shards})")
    logger.info(f"Concurrency: {args.concurrency}, Target: {args.target}")

    async with SlideServeScraper(download_dir=args.dir, concurrency=args.concurrency) as scraper:
        sitemaps = await scraper.fetch_sitemap_index()
        
        if not sitemaps:
            logger.error("No sitemaps found. Exiting.")
            return

        # Shard the sitemaps
        shard_size = max(1, len(sitemaps) // args.total_shards)
        start_idx = args.shard * shard_size
        end_idx = start_idx + shard_size if args.shard < args.total_shards - 1 else len(sitemaps)
        
        assigned_sitemaps = sitemaps[start_idx:end_idx]
        logger.info(f"Assigned {len(assigned_sitemaps)} sitemaps to this shard.")

        # Process sitemaps
        for sitemap_url in assigned_sitemaps:
            if scraper.stats["downloaded"] >= args.target:
                break
                
            logger.info(f"Processing sitemap: {sitemap_url}")
            urls = await scraper.fetch_and_parse_sitemap(sitemap_url)
            
            # Create download tasks
            tasks = [scraper.process_presentation(url) for url in urls]
            
            # Run tasks with progress bar
            for f in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Downloading"):
                await f
                if scraper.stats["downloaded"] >= args.target:
                    logger.info("Target reached! Stopping.")
                    break
        
        # Summary
        print("\n" + "="*50)
        print("📊 SCRAPE SUMMARY")
        print("="*50)
        for k, v in scraper.stats.items():
            print(f"  {k}: {v}")
        print("="*50)

if __name__ == "__main__":
    asyncio.run(main())
