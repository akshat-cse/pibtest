#!/usr/bin/env bash
# Runner script for daily PIB scraper execution (e.g. via crontab)
set -e

# Change directory to the script's root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Execute scraper with default arguments (fetches previous day in IST)
python3 pib_scraper.py "$@"
