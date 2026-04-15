# PPT Document Scraper

Automated scraper to collect up to 1,500 .ppt/.pptx presentation files and upload directly to Google Drive. Filters out US company domains to focus on international and academic sources.

## Features

- **Multi-source scraping**: SlideShare (Selenium) + Zenodo API
- **JavaScript rendering**: Selenium for modern web apps
- **API-based scraping**: Zenodo REST API for reliable downloads
- **US domain filtering**: Automatically blocks major US company domains
- **Google Drive integration**: Direct upload to organized folders
- **Rate limiting**: Respectful scraping with configurable delays
- **Resume support**: Tracks progress via manifests

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Setup Google Drive

Follow [GOOGLE_SETUP.md](GOOGLE_SETUP.md) to create OAuth credentials.

### 3. Run the Scraper

```bash
# Default: Scrape all sources, target 1500 files
python run.py

# Scrape specific source only
python run.py --source slideshare --target 500
python run.py --source zenodo --target 1000

# Test mode (no uploads)
python run.py --target 10 --dry-run

# Download only, skip Google Drive
python run.py --no-upload --target 100
```

## Command Options

```
python run.py [OPTIONS]

Options:
  -t, --target INT        Target number of PPT files (default: 1500)
  -s, --source {all,slideshare,zenodo}
                          Source to scrape (default: all)
  --delay-min FLOAT       Min seconds between requests (default: 2)
  --delay-max FLOAT       Max seconds between requests (default: 5)
  --dry-run               Test mode without uploads
  --no-upload             Download only, skip Drive upload
  -h, --help              Show help
```

## Project Structure

```
.
├── config/
│   └── us_domains_blocklist.json  # Blocked US company domains
├── src/
│   ├── scraper/
│   │   ├── base.py                # Base scraper class
│   │   ├── slideshare_selenium.py # SlideShare Selenium scraper
│   │   └── zenodo.py              # Zenodo API scraper
│   ├── filters/
│   │   └── domain_filter.py       # US domain filter logic
│   └── storage/
│       └── gdrive.py              # Google Drive upload
├── downloaded_ppts/               # Local download folder
├── logs/                          # Manifests and logs
├── run.py                         # Main entry point
├── requirements.txt
├── GOOGLE_SETUP.md
└── README.md
```

## Blocked US Company Domains

The scraper automatically blocks URLs from:
- Major tech: Google, Apple, Microsoft, Amazon, Meta, etc.
- Finance: Goldman Sachs, JPMorgan, Bank of America, etc.
- Telecom: Verizon, AT&T, Comcast, T-Mobile
- Retail: Walmart, Target, Best Buy, Home Depot
- And 200+ more domains

Edit `config/us_domains_blocklist.json` to customize.

## Sources

### SlideShare (Selenium)
- JavaScript rendering for modern web app
- Searches 30+ popular topics
- Downloads both `.ppt` and `.pptx` files
- Respects rate limits with Selenium

### Zenodo (API)
- CERN research repository with public API
- Searches for presentation files
- Reliable direct downloads
- No JavaScript rendering needed

## Safety & Ethics

- Rate limiting: 2-5 second delays between requests
- Respects `robots.txt` (via requests library)
- Only downloads publicly accessible files
- User-Agent identification
- No authenticated/paywalled content

## Output

Files are:
1. Downloaded to `downloaded_ppts/`
2. Uploaded to Google Drive: `PPT_Scraper_Downloads/`
3. Manifest saved to `logs/manifest_YYYYMMDD_HHMMSS.json`

## Troubleshooting

**ImportError**: Ensure all dependencies installed:
```bash
pip install -r requirements.txt
```

**Google auth fails**: Follow GOOGLE_SETUP.md carefully, verify `credentials.json` exists

**No files downloaded**: Check domain filter logs - US domains are being blocked correctly

**Rate limited**: Increase `--delay-min` and `--delay-max`

## License

For educational/research use. Respect robots.txt and terms of service.
