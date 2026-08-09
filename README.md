# PIB (Press Information Bureau) Daily Press Release Scraper

An automated Python scraper that fetches daily press releases from [pib.gov.in](https://www.pib.gov.in), handling ASP.NET session tokens, postbacks, ministry grouping, and full release body extraction. Includes an optional **UPSC-focused summarization pipeline** that evaluates each release with Google Gemini and maintains monthly & combined summary archives.

---

## Features

- **Automated Previous Day Fetch**: By default, automatically targets the previous day in IST (Indian Standard Time, UTC+5:30) when run in the morning at 6:00 AM.
- **Dynamic Month Folder Organization**: Automatically creates and maintains folders by month, e.g., `July 2026 - Daily fetch/`, `August 2026 - Daily fetch/`.
- **Standardized JSON Filenames**: Daily dumps are saved as `dd-mm-yyyy.json` (e.g. `31-07-2026.json`, `08-08-2026.json`).
- **Complete Article Content**: Extracts Title, Subtitle, Ministry, DateTime, Body Text/HTML, and canonical PIB URL for each press release.
- **ASP.NET Session & Postback Handling**: Manages `__VIEWSTATE`, `__VIEWSTATEGENERATOR`, and `__EVENTVALIDATION` tokens for reliable date querying.
- **Automated Scheduling Ready**: Includes GitHub Actions workflow (`.github/workflows/daily_scrape.yml`) and cron script (`run_daily.sh`).
- **UPSC Summarization Pipeline (NEW)**: `summarizer.py` evaluates daily releases for UPSC relevance (GS I–IV) via Gemini, storing results in `Summaries/<Month YYYY> - Summary.json` and `Summaries/All_Combined_Summary.json` with deduplication by `prid`.

---

## Installation

Ensure Python 3.8+ is installed, then install the required dependencies:

```bash
pip install -r requirements.txt
```

`requirements.txt` includes:
```
requests>=2.28.0
beautifulsoup4>=4.11.0
urllib3>=1.26.0
google-genai>=0.3.0
```

For summarization you also need a Google GenAI API key (see below).

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

## PIB Summarization Pipeline (UPSC Evaluation)

`summarizer.py` reads the daily JSON file produced by `pib_scraper.py` and evaluates every article for UPSC Civil Services relevance using **Google Gemini** (via `google-genai`). It batches articles (15 per API call) with a 6s pause to stay under free-tier RPM limits and produces a web-ready JSON dataset.

### Setting up `SUMMARY_API_KEY`

#### Locally
```bash
export SUMMARY_API_KEY="your_gemini_api_key_here"
# Optional model override (default: gemini-3.6-flash with fallback to 2.0/1.5):
export SUMMARY_MODEL="gemini-2.0-flash"
python summarizer.py --date 2026-08-08
```

Get your key from: https://aistudio.google.com/app/apikey

#### On GitHub (Repository Secret)
1. Go to your GitHub repository → **Settings** → **Secrets and variables** → **Actions**.
2. Click **New repository secret**.
3. Name: `SUMMARY_API_KEY`
4. Value: your Gemini API key → **Add secret**.
5. (Optional) Also add `SUMMARY_MODEL` secret if you want to pin a model name.
6. The workflow `.github/workflows/daily_summary.yml` automatically injects it as `env.SUMMARY_API_KEY`.

> **Never commit your API key.** The script reads it only from `os.environ.get("SUMMARY_API_KEY")` and will error with instructions if missing. The workflow uses `${{ secrets.SUMMARY_API_KEY }}`.

### Summary File Structure

All outputs go into the `Summaries/` directory (auto-created):

```
Summaries/
  August 2026 - Summary.json        # monthly archive
  July 2026 - Summary.json
  All_Combined_Summary.json         # master file with every day's summaries
```

Each file is a JSON **array** of evaluation objects. Example entry:

```json
[
  {
    "prid": 2296546,
    "title": "GeM completes 10 years...",
    "date": "प्रविष्टि तिथि: 08 AUG 2026 5:54PM by PIB Delhi",
    "url": "https://pib.gov.in/PressReleasePage.aspx?PRID=2296546",
    "verdict": "READ",
    "priority": 8,
    "syllabus_mapping": ["Economy", "Governance"],
    "upsc_summary": [
      "GeM celebrates 10 years as India's unified public procurement portal...",
      "Highlights policy shift toward AI-integrated, transparent procurement..."
    ]
  },
  {
    "prid": 2296571,
    "title": "Union Minister Shri Jagat Prakash Nadda Chairs CEO Roundtable...",
    "date": "प्रविष्टि तिथि: 08 AUG 2026 5:54PM by PIB Delhi",
    "url": "https://pib.gov.in/PressReleasePage.aspx?PRID=2296571",
    "verdict": "LEAVE",
    "priority": 4,
    "syllabus_mapping": ["Miscellaneous"],
    "upsc_summary": []
  }
]
```

**Fields:**
- `prid` (int) – exact PIB Release ID matched from input
- `title`, `date`, `url` – copied verbatim from source
- `verdict` – `"READ"` (high-yield UPSC: policy/legislation/report/data/scheme-change/IR/economy/security/environment concept for Mains) or `"LEAVE"` (event/meeting/launch/statement/award/routine update)
- `priority` – 1–10 (10 most important; 7–10 allowed only for `READ`, 1–6 forces `LEAVE`)
- `syllabus_mapping` – array from `["Economy","Polity","Governance","Geography","History","Culture","International Relations","Science & Technology","Environment","Society","Disaster Management","Ethics","Sports","Miscellaneous"]`
- `upsc_summary` – array of short bullet strings (empty if `LEAVE`)

**Deduplication:** Before appending, the script loads each destination file and skips any `prid` already present (string/int normalized). Rerunning for the same date is idempotent — no duplicates.

### Running `summarizer.py` Locally

**Prerequisites:** Daily fetch JSON must exist, e.g. `August 2026 - Daily fetch/08-08-2026.json` (create via `pib_scraper.py`).

```bash
# 1. Install deps and set key
pip install -r requirements.txt
export SUMMARY_API_KEY="your_key"

# 2. Previous day in IST (default)
python summarizer.py

# 3. Specific date (positional or --date)
python summarizer.py 2026-08-08
python summarizer.py --date 2026-08-08

# 4. Today's releases
python summarizer.py --today

# 5. Check outputs
ls -lh Summaries/
cat "Summaries/August 2026 - Summary.json" | head -n 50
cat Summaries/All_Combined_Summary.json | python3 -m json.tool | head -n 80
```

Batch behavior: processes 15 articles per Gemini call with 6s sleep; handles `SUMMARY_API_KEY` missing, input file missing, and JSON parse errors gracefully; tries model fallback list (`gemini-3.6-flash` → `gemini-2.0-flash` → `gemini-1.5-flash`) if a model is unavailable.

### Running via GitHub Actions

#### Automatic (Recommended)
Workflow `.github/workflows/daily_summary.yml`:
- **Trigger:** `workflow_run` → when **“PIB Daily Scraper”** (`daily_scrape.yml`) completes successfully.
- **Action:** checks out repo, installs deps, runs `python summarizer.py` (previous day IST) with `SUMMARY_API_KEY` from secrets, then commits & pushes `Summaries/` back to the repo.
- **Condition:** `if: github.event.workflow_run.conclusion == 'success'`

No manual setup needed after adding the secret — it chains automatically after each daily scrape at 06:00 AM IST (00:30 UTC).

#### Manual
1. Go to **Actions** tab → **PIB Daily Summary** workflow.
2. Click **Run workflow** → optionally enter `target_date` (YYYY-MM-DD).
3. If blank, defaults to previous day IST (same as `pib_scraper.py`).
4. Workflow runs `summarizer.py --date <input>` or bare `summarizer.py`, then commits `Summaries/*.json`.

Manual example via `gh` CLI:
```bash
gh workflow run "PIB Daily Summary" --field target_date=2026-08-08
```

The commit message will be `Automated PIB summary: <date>` and will only push if `Summaries/` changed (dedup ensures reruns don’t create empty commits).

---

## Automation (Every Day at 6:00 AM)

### Option A: GitHub Actions (Recommended)
A pre-configured GitHub Actions workflow file is provided in `workflows/daily_scrape.yml`.
To enable it in your repository:
1. Move or copy `workflows/daily_scrape.yml` into `.github/workflows/daily_scrape.yml` (or create it via GitHub web interface / repository settings).
2. **Schedule**: It triggers daily at `06:00 AM IST` (`00:30 UTC`).
3. **Workflow**: Clones the repository, installs dependencies, executes `pib_scraper.py`, and commits the newly fetched JSON file directly back to the repo.
4. **Manual Trigger**: Supports running on-demand via the GitHub Actions UI (`workflow_dispatch`) with an optional custom date input.

**Summarizer chaining:** After the scraper succeeds, `daily_summary.yml` runs automatically as above. Ensure `SUMMARY_API_KEY` is set or the summary job will fail with a clear error.

### Option B: Linux Crontab
To run every morning at 6:00 AM on your Linux machine or server, add the following cron entry (`crontab -e`):

**If server is in IST:**
```cron
0 6 * * * /usr/bin/bash /path/to/pibtest/run_daily.sh >> /path/to/pibtest/scraper.log 2>&1
# then summarize (after scrape finishes):
30 6 * * * cd /path/to/pibtest && SUMMARY_API_KEY=your_key /usr/bin/python3 summarizer.py >> /path/to/pibtest/summarizer.log 2>&1
```

**If server is in UTC (6:00 AM IST = 00:30 UTC):**
```cron
30 0 * * * /usr/bin/bash /path/to/pibtest/run_daily.sh >> /path/to/pibtest/scraper.log 2>&1
45 0 * * * cd /path/to/pibtest && SUMMARY_API_KEY=your_key /usr/bin/python3 summarizer.py >> /path/to/pibtest/summarizer.log 2>&1
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

Summary outputs (`Summaries/*.json`) use the `prid/title/date/url/verdict/priority/syllabus_mapping/upsc_summary` schema described above.
