# PIB (Press Information Bureau) Daily Press Release Scraper

An automated Python scraper that fetches daily press releases from [pib.gov.in](https://www.pib.gov.in), handling ASP.NET session tokens, postbacks, ministry grouping, and full release body extraction.

---

## Features

- **Automated Previous Day Fetch**: By default, automatically targets the previous day in IST (Indian Standard Time, UTC+5:30) when run in the morning at 6:00 AM.
- **Dynamic Month Folder Organization**: Automatically creates and maintains folders by month, e.g., `July 2026 - Daily fetch/`, `August 2026 - Daily fetch/`.
- **Standardized JSON Filenames**: Daily dumps are saved as `dd-mm-yyyy.json` (e.g. `31-07-2026.json`, `08-08-2026.json`).
- **Complete Article Content**: Extracts Title, Subtitle, Ministry, DateTime, Body Text/HTML, and canonical PIB URL for each press release.
- **ASP.NET Session & Postback Handling**: Manages `__VIEWSTATE`, `__VIEWSTATEGENERATOR`, and `__EVENTVALIDATION` tokens for reliable date querying.
- **Automated Scheduling Ready**: Includes GitHub Actions workflow (`.github/workflows/daily_scrape.yml`) and cron script (`run_daily.sh`).

---

## Installation

Ensure Python 3.8+ is installed, then install the required dependencies:

```bash
pip install -r requirements.txt
```

---

## Usage

### 1. Default Daily Run (Previous Day)
Running the script without arguments automatically targets the **previous day in IST** and saves the dump to `<Month YYYY> - Daily fetch/<dd-mm-yyyy>.json`:
```bash
python pib_scraper.py
```

### 2. Fetch for a Specific Date
To fetch press releases for a specific date (format `YYYY-MM-DD`):
```bash
python pib_scraper.py 2026-07-31
# Or using the -d / --date flag:
python pib_scraper.py --date 2026-07-31
```
This will automatically create `July 2026 - Daily fetch/31-07-2026.json`.

### 3. Fetch Today's Releases
To scrape today's releases instead of yesterday's:
```bash
python pib_scraper.py --today
```

### 4. Custom Output Path
To output to a custom JSON file instead of the default folder structure:
```bash
python pib_scraper.py 2026-07-31 --out custom_output.json
```

### 5. Metadata-Only Mode (Fast)
To scrape only the list of press releases without fetching full article bodies:
```bash
python pib_scraper.py 2026-07-31 --no-body
```

---

## Automation (Every Day at 6:00 AM)

### Option A: GitHub Actions (Recommended)
A pre-configured GitHub Actions workflow file is provided in `workflows/daily_scrape.yml`.
To enable it in your repository:
1. Move or copy `workflows/daily_scrape.yml` into `.github/workflows/daily_scrape.yml` (or create it via GitHub web interface / repository settings).
2. **Schedule**: It triggers daily at `06:00 AM IST` (`00:30 UTC`).
3. **Workflow**: Clones the repository, installs dependencies, executes `pib_scraper.py`, and commits the newly fetched JSON file directly back to the repo.
4. **Manual Trigger**: Supports running on-demand via the GitHub Actions UI (`workflow_dispatch`) with an optional custom date input.

### Option B: Linux Crontab
To run every morning at 6:00 AM on your Linux machine or server, add the following cron entry (`crontab -e`):

**If server is in IST:**
```cron
0 6 * * * /usr/bin/bash /path/to/pibtest/run_daily.sh >> /path/to/pibtest/scraper.log 2>&1
```

**If server is in UTC (6:00 AM IST = 00:30 UTC):**
```cron
30 0 * * * /usr/bin/bash /path/to/pibtest/run_daily.sh >> /path/to/pibtest/scraper.log 2>&1
```

---

## Output JSON Schema

Each item in the saved JSON array contains:

```json
[
  {
    "prid": 2292386,
    "title": "THE PRESIDENT INTERACTS WITH A GROUP OF GRASSROOTS INNOVATORS",
    "subtitle": "GRASSROOTS INNOVATIONS ARE WELL-SUITED TO SOCIETY’S NEEDS...",
    "ministry": "President's Secretariat",
    "date": "प्रविष्टि तिथि: 31 JUL 2026 3:32PM by PIB Delhi",
    "content": "A group of grassroots innovators of Atal Innovations Mission...",
    "url": "https://pib.gov.in/PressReleasePage.aspx?PRID=2292386"
  }
]
```
