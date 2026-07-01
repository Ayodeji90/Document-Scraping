import requests
from bs4 import BeautifulSoup

url = "https://www.slideserve.com/jagan/what-is-marketing"
resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"})
if resp.ok:
    print("Fetched successfully.")
    soup = BeautifulSoup(resp.text, "html.parser")
    # Search for all links with download
    for a in soup.find_all("a", href=True):
        if "download" in a.get("href").lower() or "export" in a.get("href").lower() or ".ppt" in a.get("href").lower():
            print("Found link:", a.get("href"))
    
    dl = soup.find(id="download-presentation")
    if dl:
        print("Download link by ID:", dl.get("href"))
else:
    print("Error:", resp.status_code)
