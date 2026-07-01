import asyncio
import aiohttp
import sys

async def main():
    # A known URL format from SlideServe
    url = "https://www.slideserve.com/jagan/what-is-marketing-123456"
    # Actually, from the user's output, ID 13600 is a valid presentation. We'll search the first sitemap.
    sitemap_url = "https://www.slideserve.com/sitemap/docs-1.xml.gz"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        print(f"Fetching sitemap {sitemap_url} to get a real presentation URL...")
        async with session.get(sitemap_url) as resp:
            if resp.status == 200:
                import gzip
                import xml.etree.ElementTree as ET
                content = gzip.decompress(await resp.read())
                root = ET.fromstring(content)
                ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                urls = [el.find("ns:loc", ns).text for el in root.findall("ns:url", ns)]
                
                if urls:
                    target_url = urls[0]
                    print(f"Fetching presentation: {target_url}")
                    async with session.get(target_url) as p_resp:
                        print(f"Status: {p_resp.status}")
                        html = await p_resp.text()
                        with open("debug_page.html", "w", encoding="utf-8") as f:
                            f.write(html)
                        print("Saved to debug_page.html")
                        
                        # Print any links that might look like a download
                        from bs4 import BeautifulSoup
                        soup = BeautifulSoup(html, "html.parser")
                        links = soup.find_all("a", href=True)
                        for a in links:
                            h = a['href'].lower()
                            if 'download' in h or 'export' in h or '.ppt' in h:
                                print(f"Found potential link: {a['href']}")
                        
                        buttons = soup.find_all("button")
                        for b in buttons:
                            if b.get('id') and 'download' in b.get('id').lower():
                                print(f"Found button: {b}")

if __name__ == "__main__":
    asyncio.run(main())
