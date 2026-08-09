#!/usr/bin/env python3
"""
PIB Summarization Pipeline - UPSC Evaluation
---------------------------------------------
Reads daily PIB press releases from "<Month YYYY> - Daily fetch/dd-mm-yyyy.json"
and evaluates each article for UPSC relevance using Google Gemini.

- By default targets previous day in IST (UTC+5:30)
- Accepts optional YYYY-MM-DD argument / --date / --today
- Uses SUMMARY_API_KEY from environment (Google GenAI)
- Appends results to:
    a) Summaries/<Month YYYY> - Summary.json
    b) Summaries/All_Combined_Summary.json
- Deduplicates by `prid` (idempotent)

Usage:
    python summarizer.py
    python summarizer.py 2026-08-08
    python summarizer.py --date 2026-08-08
    python summarizer.py --today

Env:
    SUMMARY_API_KEY  (required) - Google GenAI / Gemini API key
    SUMMARY_MODEL    (optional) - override model name
"""

import argparse
import datetime
import json
import os
import sys
import time

# ---------------------------------------------------------------------------
# IST date helpers (mirrors pib_scraper.py)
# ---------------------------------------------------------------------------

def get_ist_now():
    """Current datetime in IST (UTC+5:30)."""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    return utc_now + datetime.timedelta(hours=5, minutes=30)

def get_today_ist():
    ist_now = get_ist_now()
    return ist_now.year, ist_now.month, ist_now.day, ist_now.strftime("%Y-%m-%d")

def get_previous_day_ist():
    ist_prev = get_ist_now() - datetime.timedelta(days=1)
    return ist_prev.year, ist_prev.month, ist_prev.day, ist_prev.strftime("%Y-%m-%d")

def get_input_path(date_str):
    """
    Returns input JSON path for date_str (YYYY-MM-DD):
    "<Month YYYY> - Daily fetch/dd-mm-yyyy.json"
    Does NOT create directories (read-only).
    """
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    month_name = dt.strftime("%B")
    year_str = dt.strftime("%Y")
    folder_name = f"{month_name} {year_str} - Daily fetch"
    file_name = dt.strftime("%d-%m-%Y.json")
    return os.path.join(folder_name, file_name)

def get_month_summary_path(date_str):
    """Summaries/<Month YYYY> - Summary.json"""
    dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    month_name = dt.strftime("%B")
    year_str = dt.strftime("%Y")
    folder = "Summaries"
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{month_name} {year_str} - Summary.json")

def get_combined_path():
    folder = "Summaries"
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "All_Combined_Summary.json")

def load_existing_summaries(path):
    """Load existing summary JSON array, return [] if missing/invalid."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except (json.JSONDecodeError, OSError) as e:
        print(f"[!] Warning: Could not read {path}: {e}. Starting fresh.", file=sys.stderr)
        return []

def save_summaries(path, data):
    """Save summary list to JSON file pretty-printed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as out:
        json.dump(data, out, indent=2, ensure_ascii=False)
        out.write("\n")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="PIB Summarization Pipeline (UPSC evaluation via Gemini)"
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
        help="Date in YYYY-MM-DD format (alternative to positional)",
    )
    parser.add_argument(
        "--today",
        action="store_true",
        help="Target today's date in IST instead of previous day",
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
        print(f"[-] Error: Invalid date format '{target_date}'. Expected YYYY-MM-DD.", file=sys.stderr)
        sys.exit(1)

    input_path = get_input_path(target_date)
    print(f"[*] Target date (IST): {target_date}")
    print(f"[*] Looking for input file: {input_path}")

    if not os.path.exists(input_path):
        print(f"[-] Error: Daily fetch file not found: {input_path}", file=sys.stderr)
        print(f"    Run pib_scraper.py for {target_date} first, or check the folder name.", file=sys.stderr)
        sys.exit(1)

    # Load articles
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            articles_list = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[-] Error reading {input_path}: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(articles_list, list):
        print(f"[-] Error: Expected JSON array in {input_path}", file=sys.stderr)
        sys.exit(1)

    total_articles = len(articles_list)
    print(f"[*] Loaded {total_articles} articles from {input_path}")

    if total_articles == 0:
        print("[!] No articles to summarize. Exiting.")
        # Still ensure Summaries files exist (empty)
        month_path = get_month_summary_path(target_date)
        combined_path = get_combined_path()
        # create empty files if missing
        if not os.path.exists(month_path):
            save_summaries(month_path, [])
        if not os.path.exists(combined_path):
            save_summaries(combined_path, [])
        sys.exit(0)

    # Check API key
    api_key = os.environ.get("SUMMARY_API_KEY")
    if not api_key:
        print("[-] Error: SUMMARY_API_KEY environment variable not set.", file=sys.stderr)
        print("    Set it locally: export SUMMARY_API_KEY='your_gemini_api_key'", file=sys.stderr)
        print("    Or add it as a GitHub repository secret (Settings > Secrets and variables > Actions).", file=sys.stderr)
        sys.exit(1)

    # Initialize GenAI client
    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        print(f"[-] Error: google-genai package not installed: {e}", file=sys.stderr)
        print("    Install with: pip install google-genai", file=sys.stderr)
        sys.exit(1)

    try:
        client = genai.Client(api_key=api_key)
    except Exception as e:
        print(f"[-] Error initializing GenAI client: {e}", file=sys.stderr)
        sys.exit(1)

    # Model selection: prefer env override, then original spec gemini-3.6-flash,
    # fallback to stable models if unavailable.
    primary_model = os.environ.get("SUMMARY_MODEL", "gemini-3.6-flash")
    candidate_models = []
    # Build candidate list deduplicated, preserving order
    for m in [primary_model, "gemini-3.6-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
        if m not in candidate_models:
            candidate_models.append(m)
    # Also add gemini-2.0-flash-latest as extra fallback
    if "gemini-2.0-flash-latest" not in candidate_models:
        candidate_models.append("gemini-2.0-flash-latest")

    final_web_app_data = []
    batch_size = 15

    for i in range(0, total_articles, batch_size):
        batch = articles_list[i:i + batch_size]
        print(f"[*] Processing articles {i+1} to {min(i + batch_size, total_articles)} of {total_articles}...")

        clean_batch_data = []
        for article in batch:
            clean_batch_data.append({
                "prid": article.get("prid"),
                "title": article.get("title"),
                "ministry": article.get("ministry"),
                "date": article.get("date"),
                "url": article.get("url"),
                "content": article.get("content")
            })

        upsc_json_prompt = f"""
    You are a backend API service evaluating PIB articles for the UPSC Civil Services Examination.
    Analyze the array of articles provided below. Evaluate their direct relevance to the UPSC CSE syllabus (GS Papers I, II, III, IV).

    Return a valid JSON array containing an evaluation object for EVERY single article in the input data. Do not skip any.

    Each object in your output array MUST strictly follow this JSON schema structure:
    {{
        "prid": (integer, match the exact 'prid' from the input data),
        "title": (string, match the exact 'title' from the input data),
        "date": (string, match the exact 'date' string from the input data),
        "url": (string, match the exact 'url' string from the input data),
        "verdict": (string, exactly "READ" only if the article contains a substantial, reusable UPSC point: a new or major policy decision, legislation, constitutional issue, official report or data, significant scheme change, important international agreement, major national economic/security/environmental development, or a concept directly usable in Mains answers. Return exactly "LEAVE" if it is only an event, meeting, launch, statement, award, personality interaction, routine implementation update, regional activity, or merely repeats an existing scheme without a major new policy, data, or development. Do not mark an article as "READ" merely because it mentions a ministry, scheme, government programme, or GS syllabus keyword. Use "READ" only for priority 7–10; priority 1–6 must always be "LEAVE".),
        "priority": (integer, exactly between 1-10, where 10 is most important/high-yield for UPSC and 1 is least important),
        "syllabus_mapping": (array of strings, choose one or more from:
["Economy", "Polity", "Governance", "Geography", "History", "Culture", "International Relations", "Science & Technology", "Environment", "Society", "Disaster Management", "Ethics", "Sports", "Miscellaneous"].
Use ["Miscellaneous"] if none fit.)
        "upsc_summary": (array of strings, structured summary of the article in short detailing schemes, ministries, data, or policies. If the verdict is LEAVE, return an empty array [])
    }}

    Input Articles Data:
    {json.dumps(clean_batch_data, ensure_ascii=False)}
    """

        # Attempt generation with fallback models
        batch_success = False
        last_error = None
        for model_name in candidate_models:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=upsc_json_prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
                # Extract text
                text = getattr(response, "text", None)
                if not text:
                    # Fallback: try candidates
                    try:
                        text = response.candidates[0].content.parts[0].text
                    except Exception:
                        text = str(response)
                batch_output_json = json.loads(text)
                if not isinstance(batch_output_json, list):
                    print(f"[!] Warning: Model {model_name} returned non-list JSON for batch {i}, skipping batch.")
                    last_error = "non-list response"
                    continue
                final_web_app_data.extend(batch_output_json)
                print(f"    [✓] Batch {i//batch_size + 1} completed with model {model_name} ({len(batch_output_json)} items)")
                batch_success = True
                break
            except json.JSONDecodeError as e:
                print(f"[!] Warning: Failed to parse JSON for batch starting at {i} with model {model_name}: {e}", file=sys.stderr)
                last_error = e
                # try next model? but JSON error is content, not model; break to avoid infinite
                # Still try next model once in case model-specific formatting differs
                continue
            except Exception as e:
                # Common for model not found / quota / API error
                last_error = e
                err_str = str(e)
                # If model not found, try next
                if "not found" in err_str.lower() or "404" in err_str or "unsupported" in err_str.lower():
                    print(f"    [!] Model {model_name} not available, trying fallback...", file=sys.stderr)
                    continue
                else:
                    print(f"[!] Warning: API error for batch starting at {i} with model {model_name}: {e}", file=sys.stderr)
                    # For rate/ quota errors, we attempt one retry with same model after wait? Simplify: break and try next model
                    continue

        if not batch_success:
            print(f"[!] Warning: All model candidates failed for batch starting at {i}. Last error: {last_error}", file=sys.stderr)
            print("    Skipping this batch. Check SUMMARY_API_KEY and model availability.", file=sys.stderr)

        # Respect free-tier RPM: sleep 6s between batches
        if i + batch_size < total_articles:
            print("    Sleeping 6s to respect rate limits...")
            time.sleep(6)

    print(f"\n[*] Summarization complete. Generated {len(final_web_app_data)} evaluations.")

    if not final_web_app_data:
        print("[!] No summaries generated (all batches failed). Not updating files.")
        sys.exit(1)

    # Deduplication and append to two files
    month_path = get_month_summary_path(target_date)
    combined_path = get_combined_path()

    print(f"[*] Monthly summary file: {month_path}")
    print(f"[*] Combined summary file: {combined_path}")

    # Helper to dedup and save
    def update_summary_file(path, new_data, label):
        existing = load_existing_summaries(path)
        existing_prids = {str(item.get("prid")) for item in existing if item.get("prid") is not None}
        # Also consider int variant for safety
        existing_prids_int = set()
        for item in existing:
            pid = item.get("prid")
            if pid is not None:
                try:
                    existing_prids_int.add(int(pid))
                except:
                    pass
        deduped_new = []
        seen_in_batch = set()
        for item in new_data:
            pid = item.get("prid")
            if pid is None:
                continue
            pid_str = str(pid)
            try:
                pid_int = int(pid)
            except:
                pid_int = None
            # dedup against existing and within new batch
            if pid_str in existing_prids or (pid_int is not None and pid_int in existing_prids_int):
                continue
            if pid_str in seen_in_batch:
                continue
            seen_in_batch.add(pid_str)
            deduped_new.append(item)

        if deduped_new:
            updated = existing + deduped_new
            save_summaries(path, updated)
            print(f"    [✓] {label}: Added {len(deduped_new)} new, total {len(updated)} (from {len(existing)} existing)")
        else:
            print(f"    [=] {label}: No new entries (all {len(new_data)} already present, existing total {len(existing)})")
            # Ensure file exists
            if not os.path.exists(path):
                save_summaries(path, existing)
        return deduped_new

    monthly_new = update_summary_file(month_path, final_web_app_data, "Monthly")
    combined_new = update_summary_file(combined_path, final_web_app_data, "Combined")

    print(f"\n[✓] Success! Summaries written.")
    print(f"    Input: {input_path} ({total_articles} articles)")
    print(f"    Generated: {len(final_web_app_data)} summaries")
    print(f"    Monthly ({month_path}): +{len(monthly_new)} new")
    print(f"    Combined ({combined_path}): +{len(combined_new)} new")
    print(f"    Dedup by prid: idempotent (rerunning adds 0)")

if __name__ == "__main__":
    main()
