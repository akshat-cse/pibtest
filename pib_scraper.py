#!/usr/bin/env python3
"""
PIB (Press Information Bureau) Daily Press Release Scraper
---------------------------------------------------------
Fetches all press releases for a given date from pib.gov.in by handling:
1. ASP.NET session cookies and tokens (__VIEWSTATE, __VIEWSTATEGENERATOR, __EVENTVALIDATION)
2. ASP.NET postback for custom dates (Year, Month, Day)
3. Parsing all releases grouped by Ministry (Title, PRID, Link)
4. Fetching full article content (Title, Subtitle, Ministry, DateTime, Body Text/HTML)

Requirements:
    pip install requests beautifulsoup4 urllib3

Usage:
    # Fetch previous day's releases (default for 6:00 AM daily run):
    python pib_scraper.py

    # Fetch today's releases:
    python pib_scraper.py --today

    # Fetch a specific date (creates folder '<Month YYYY> - Daily fetch/<dd-mm-yyyy>.json'):
    python pib_scraper.py 2026-07-31

    # Save to a custom JSON file:
    python pib_scraper.py 2026-07-31 --out releases.json
"""

import sys
import os
import json
import re
import argparse
import datetime
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
import urllib3

# Suppress HTTPS certificate warnings if government certificates fail SSL check
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PIB_BASE = "https://www.pib.gov.in"
ALL_REL_URL = f"{PIB_BASE}/Allrel.aspx?reg=3&lang=1"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": PIB_BASE,
    "Referer": ALL_REL_URL,
}


def get_ist_now():
    """Returns current datetime in IST (UTC+5:30)."""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    return utc_now + datetime.timedelta(hours=5, minutes=30)


def get_today_ist():
    """Returns today's date tuple (year, month, day, 'YYYY-MM-DD') in IST (UTC+5:30)."""
    ist_now = get_ist_now()
    return ist_now.year, ist_now.month, ist_now.day, ist_now.strftime("%Y-%m-%d")


def get_previous_day_ist():
    """Returns yesterday's date tuple (year, month, day, 'YYYY-MM-DD') in IST (UTC+5:30)."""
    ist_prev = get_ist_now() - datetime.timedelta(days=1)
    return ist_prev.year, ist_prev.month, ist_prev.day, ist_prev.strftime("%Y-%m-%d")


def get_default_output_path(date_str):
    """
    Computes the default output file path for a given date_str ('YYYY-MM-DD').
    Creates a folder like '<Month> <YYYY> - Daily fetch' (e.g. 'July 2026 - Daily fetch')
    and sets the filename as 'dd-mm-yyyy.json' (e.g. '31-07-2026.json').
    """
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    month_name = dt.strftime("%B")  # e.g. July
    year_str = dt.strftime("%Y")    # e.g. 2026
    folder_name = f"{month_name} {year_str} - Daily fetch"
    file_name = f"{dt.strftime('%d-%m-%Y')}.json"

    os.makedirs(folder_name, exist_ok=True)
    return os.path.join(folder_name, file_name)


def parse_allrel_html(html):
    """Parses releases grouped by ministry from Allrel.aspx HTML."""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    content_area = soup.find("div", class_="content-area")
    if not content_area:
        content_area = soup

    # Each ministry block is an unordered list inside the content area
    for ul in content_area.find_all("ul"):
        # Ministry heading is inside h3 (or class font104)
        ministry_el = ul.find("h3")
        if not ministry_el:
            continue
        ministry = ministry_el.get_text(strip=True) or "General"

        # Article links are inside ul.num li a
        for a in ul.find_all("a"):
            title = a.get_text(strip=True)
            href = a.get("href", "")
            prid_match = re.search(r"PRID=(\d+)", href, re.IGNORECASE)
            if prid_match and title:
                prid = int(prid_match.group(1))
                full_url = href if href.startswith("http") else urljoin(PIB_BASE, href)
                items.append({
                    "prid": prid,
                    "title": title,
                    "ministry": ministry,
                    "url": full_url,
                })
    return items


def fetch_release_list(target_date=None):
    """
    Fetches the list of all press releases for target_date ('YYYY-MM-DD').
    Returns a list of dicts: [{'prid': int, 'title': str, 'ministry': str, 'url': str}, ...]
    """
    if target_date:
        dt = datetime.datetime.strptime(target_date, "%Y-%m-%d")
        year, month, day = dt.year, dt.month, dt.day
    else:
        year, month, day, _ = get_previous_day_ist()

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    # Step 1: Initial GET to establish session cookies and load tokens
    try:
        r1 = session.get(ALL_REL_URL, timeout=20, verify=False)
        r1.raise_for_status()
    except Exception as e:
        print(f"[-] Error loading initial page: {e}", file=sys.stderr)
        return []

    soup1 = BeautifulSoup(r1.text, "html.parser")

    # Step 2: Check if current selection matches requested date
    cur_year = soup1.find("select", id=re.compile(r"ddlYear", re.I))
    cur_month = soup1.find("select", id=re.compile(r"ddlMonth", re.I))
    cur_day = soup1.find("select", id=re.compile(r"ddlday", re.I))

    def get_selected(sel):
        if not sel:
            return ""
        opt = sel.find("option", selected=True)
        return opt["value"] if opt else ""

    if (
        get_selected(cur_year) == str(year)
        and get_selected(cur_month) == str(month)
        and get_selected(cur_day) == str(day)
    ):
        return parse_allrel_html(r1.text)

    # Step 3: Extract ASP.NET postback tokens
    def get_hidden_val(name):
        inp = soup1.find("input", {"name": name})
        return inp.get("value", "") if inp else ""

    viewstate = get_hidden_val("__VIEWSTATE")
    viewstate_gen = get_hidden_val("__VIEWSTATEGENERATOR")
    event_val = get_hidden_val("__EVENTVALIDATION")

    payload = {
        "script_HiddenField": "",
        "__EVENTTARGET": "ctl00$ContentPlaceHolder1$ddlday",
        "__EVENTARGUMENT": "",
        "__LASTFOCUS": "",
        "__VIEWSTATE": viewstate,
        "__VIEWSTATEGENERATOR": viewstate_gen,
        "__VIEWSTATEENCRYPTED": "",
        "__EVENTVALIDATION": event_val,
        "ctl00$Bar1$ddlregion": "3",
        "ctl00$Bar1$ddlLang": "1",
        "ctl00$ContentPlaceHolder1$ddlMinistry": "0",
        "ctl00$ContentPlaceHolder1$ddlYear": str(year),
        "ctl00$ContentPlaceHolder1$ddlMonth": str(month),
        "ctl00$ContentPlaceHolder1$ddlday": str(day),
        "ctl00$ContentPlaceHolder1$hydregionid": "3",
        "ctl00$ContentPlaceHolder1$hydLangid": "1",
    }

    try:
        r2 = session.post(ALL_REL_URL, data=payload, timeout=25, verify=False)
        r2.raise_for_status()
        return parse_allrel_html(r2.text)
    except Exception as e:
        print(f"[-] Error during ASP.NET postback: {e}", file=sys.stderr)
        return []


def fetch_article_detail(prid, session=None):
    """
    Fetches full article body, subtitle, and date/time for a single PRID.
    """
    url = f"{PIB_BASE}/PressReleaseIframePage.aspx?PRID={prid}"
    req = session if session is not None else requests
    try:
        res = req.get(url, headers={"User-Agent": UA}, timeout=15, verify=False)
        if not res.ok:
            return None
        soup = BeautifulSoup(res.text, "html.parser")

        def hidden_val(name):
            el = soup.find("input", {"name": name})
            return el.get("value", "").strip() if el else ""

        title = hidden_val("ltrTitlee")
        if not title:
            t_el = soup.find(id="Titleh2")
            title = t_el.get_text(strip=True) if t_el else ""

        subtitle = hidden_val("ltrSubtitlee")
        if not subtitle:
            s_el = soup.find(id="ltrSubtitle")
            subtitle = s_el.get_text(strip=True) if s_el else ""

        ministry_el = soup.find(id="MinistryName")
        ministry = ministry_el.get_text(strip=True) if ministry_el else ""

        date_el = soup.find(id="PrDateTime")
        date_str = date_el.get_text(strip=True) if date_el else ""

        body_html = hidden_val("ltrDescriptionn")
        body_text = ""
        if body_html:
            bs = BeautifulSoup(body_html, "html.parser")
            for tag in bs(["script", "style", "iframe", "object", "embed"]):
                tag.decompose()
            body_text = bs.get_text(separator="\n", strip=True)
        else:
            body_text = soup.get_text(separator="\n", strip=True)

        return {
            "prid": prid,
            "title": title,
            "subtitle": subtitle,
            "ministry": ministry,
            "date": date_str,
            "content": body_text,
            "url": f"https://pib.gov.in/PressReleasePage.aspx?PRID={prid}",
        }
    except Exception as e:
        print(f"[-] Error fetching PRID #{prid}: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Scrape daily PIB (Press Information Bureau) press releases."
    )
    parser.add_argument(
        "date",
        nargs="?",
        default=None,
        help="Date in YYYY-MM-DD format (default: previous day in IST)",
    )
    parser.add_argument(
        "--date",
        "-d",
        dest="opt_date",
        default=None,
        help="Date in YYYY-MM-DD format (alternative to positional date argument)",
    )
    parser.add_argument(
        "--today",
        action="store_true",
        help="Fetch today's releases instead of previous day",
    )
    parser.add_argument(
        "--out",
        "-o",
        default=None,
        help="Output JSON file path (default: '<Month YYYY> - Daily fetch/<dd-mm-yyyy>.json')",
    )
    parser.add_argument(
        "--no-body",
        action="store_true",
        help="Fetch release list only without downloading full text",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print JSON dump to stdout in addition to saving file",
    )
    args = parser.parse_args()

    # Determine target date
    target_date = args.opt_date or args.date
    if not target_date:
        if args.today:
            _, _, _, target_date = get_today_ist()
        else:
            _, _, _, target_date = get_previous_day_ist()

    # Validate date format
    try:
        datetime.datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        print(f"[-] Error: Invalid date format '{target_date}'. Expected format: YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)

    # Determine output file path
    if args.out:
        out_path = args.out
        parent = os.path.dirname(out_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
    else:
        out_path = get_default_output_path(target_date)

    print(f"[*] Scraping PIB for date: {target_date}")
    print(f"[*] Destination file: {out_path}")

    releases = fetch_release_list(target_date)
    print(f"[*] Found {len(releases)} press releases.")

    if not releases:
        print(f"[!] No releases found for date: {target_date}.")
        # Save empty array to record that the fetch was attempted
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("[]\n")
        print(f"[✓] Saved empty release list to {out_path}")
        return

    results = []
    if args.no_body:
        results = releases
    else:
        detail_session = requests.Session()
        for i, item in enumerate(releases, 1):
            prid = item["prid"]
            print(f"    [{i}/{len(releases)}] PRID #{prid}: {item['title'][:60]}...")
            detail = fetch_article_detail(prid, session=detail_session)
            if detail:
                results.append({
                    "prid": prid,
                    "title": detail["title"] or item["title"],
                    "subtitle": detail["subtitle"],
                    "ministry": detail["ministry"] or item["ministry"],
                    "date": detail["date"],
                    "content": detail["content"],
                    "url": detail["url"],
                })
            else:
                results.append(item)

    output_json = json.dumps(results, indent=2, ensure_ascii=False)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(output_json)
    print(f"[✓] Successfully saved {len(results)} releases to {out_path}")

    if args.stdout:
        print(output_json)


if __name__ == "__main__":
    main()
