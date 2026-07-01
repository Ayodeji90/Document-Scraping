# Suggestions for Faster PPTX Downloading

Based on the current architecture of the scraper (including the parallel orchestrator), here are several strategies to significantly increase the download throughput. 

## 1. Network & IP Rotation (The Biggest Bottleneck)
Right now, you are running ~70 scrapers simultaneously from a single IP address. Most academic repositories, APIs (like Figshare/Zenodo), and search engines (Google/Bing) will heavily rate-limit or temporarily ban your IP when they see this much traffic.
- **Suggestion:** Implement a **rotating residential proxy network** (e.g., BrightData, Oxylabs, or Smartproxy). By routing each country's scraper through a different IP address, you avoid rate limits and CAPTCHAs.
- **Suggestion:** Distribute the workload across multiple cheap VPS instances (like DigitalOcean droplets or AWS EC2) instead of running 70 processes on one machine.

## 2. Asynchronous Downloading (AsyncIO / Aiohttp)
Currently, inside each individual scraper, downloads happen synchronously (it finds a file, downloads it, waits for it to finish, then finds the next). 
- **Suggestion:** Rewrite the download logic to use Python's `asyncio` and `aiohttp`. This allows a single country script to download 10-20 files concurrently instead of waiting for one to finish before starting the next.

## 3. Tune the "Politeness" Delays
To avoid bans, the base scrapers usually include `time.sleep()` delays between requests (e.g., waiting 1.5 to 3.5 seconds between downloads).
- **Suggestion:** If you implement a proxy pool (Suggestion 1), you can safely reduce or completely remove these artificial delays, allowing the scrapers to pull files as fast as your bandwidth allows.

## 4. Optimize the Verification Pipeline
The new compliance verification pipeline introspects the ZIP structure of every `.pptx` file and extracts text to check for PII, COPPA, and prohibited content. 
- **Suggestion:** Run the downloads in a rapid "Acquisition Phase" where you just save the files to disk as fast as possible. Then, run the "Verification Phase" as a separate offline background process that churns through the downloaded files. This unblocks the network pipeline from CPU-bound tasks.

## 5. Direct Source APIs vs Search Engine Scraping
If the country scrapers are using search engines (Google Dorks) to find files, they will get blocked very quickly. 
- **Suggestion:** Shift focus to bulk metadata datasets (like the CORE dataset, Unpaywall, or Crossref). You can download a massive JSON dump of academic records, filter it locally for `.pptx` URLs in milliseconds, and then feed those URLs directly into an asynchronous downloader, bypassing the search phase entirely.

## 6. Bandwidth Limitations
Downloading hundreds of megabytes concurrently will quickly saturate a standard home or standard cloud network interface.
- **Suggestion:** Ensure the machine running the scraper has at least a 1Gbps or 10Gbps network interface. If bandwidth is saturated, adding more parallel scrapers will actually *slow down* the total download speed due to packet loss and TCP window shrinking.
