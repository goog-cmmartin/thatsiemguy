import sqlite3
import os
import google.generativeai as genai
import logging
import difflib
import argparse
import time
from datetime import datetime
from config import DB_NAME

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)

# --- Gemini API Setup ---
_gemini_model = None

def get_gemini_model():
    global _gemini_model
    if _gemini_model:
        return _gemini_model
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set.")
        genai.configure(api_key=api_key)
        _gemini_model = genai.GenerativeModel('gemini-2.5-flash')
        logging.info("Gemini model initialized.")
        return _gemini_model
    except Exception as e:
        logging.error(f"Failed to initialize Gemini model: {e}")
        return None

def get_changes(filter_url=None, backfill=False):
    """Fetches changes from the database, intelligently skipping 'new' items on the first day."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    params = []
    
    if backfill:
        # Backfill all 'updated' and 'new' items, except for 'new' items from the very first scrape date.
        query = """
            SELECT log_id, url, change_type 
            FROM change_log 
            WHERE summary IS NULL 
            AND (change_type = 'updated' OR (change_type = 'new' AND scrape_date > (SELECT MIN(scrape_date) FROM change_log)))
        """
    else:
        # For a normal run, get the latest scrape date.
        cursor.execute("SELECT MAX(scrape_date) FROM change_log")
        latest_scrape_date = cursor.fetchone()[0]
        if not latest_scrape_date:
            conn.close()
            return []
        params.append(latest_scrape_date)

        # Get the earliest scrape date to check if this is the first run.
        cursor.execute("SELECT MIN(scrape_date) FROM change_log")
        earliest_scrape_date = cursor.fetchone()[0]

        # Base query
        query = "SELECT log_id, url, change_type FROM change_log WHERE scrape_date = ?"
        
        # If it's the first day, only summarize updates (of which there will be none).
        # Otherwise, summarize both new and updated items.
        if latest_scrape_date == earliest_scrape_date:
            query += " AND change_type = 'updated'"
        else:
            query += " AND change_type IN ('new', 'updated')"

    if filter_url:
        query += " AND url LIKE ?"
        params.append(f'%{filter_url}%')

    cursor.execute(query, tuple(params))
    changes = cursor.fetchall()
    conn.close()
    return changes

def get_content_versions(url, change_type):
    """Fetches content for a given URL based on the change type."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    current_content = None
    archived_content = None

    if change_type in ['new', 'updated']:
        cursor.execute("SELECT content FROM pages WHERE url=?", (url,))
        current_row = cursor.fetchone()
        if current_row:
            current_content = current_row[0]

    if change_type == 'updated':
        cursor.execute("""
            SELECT content FROM pages_archive 
            WHERE url=? 
            ORDER BY archived_at DESC 
            LIMIT 1
        """, (url,))
        archive_row = cursor.fetchone()
        if archive_row:
            archived_content = archive_row[0]

    conn.close()
    return current_content, archived_content

def summarize_with_gemini(change_type, current_content, archived_content=None):
    """Summarizes content change using Gemini API with retry logic for rate limiting."""
    model = get_gemini_model()
    if not model:
        return "Error: Gemini model not available."

    if change_type == 'new':
        prompt = f"Summarize the key information in this new document:\n\n--- NEW CONTENT ---\n{current_content}\n--- END CONTENT ---"
    elif change_type == 'updated':
        diff = "".join(difflib.unified_diff(
            (archived_content or "").splitlines(keepends=True),
            (current_content or "").splitlines(keepends=True),
            fromfile='archived',
            tofile='current',
        ))
        if not diff.strip():
            return "No textual changes detected."
        prompt = f"Summarize the key changes in this document based on the following diff:\n\n--- DIFF ---\n{diff}\n--- END DIFF ---"
    else:
        return "Unsupported change type."

    max_retries = 5
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            if "429" in str(e): # Check for rate limit error
                logging.warning(f"Rate limit hit. Waiting 60 seconds before retry {attempt + 1}/{max_retries}...")
                time.sleep(60)
            else:
                logging.error(f"API call for summarization failed: {e}")
                return "Error: Failed to generate summary."
    
    logging.error(f"Failed to generate summary after {max_retries} retries.")
    return "Error: Failed to generate summary after multiple retries."

from datetime import datetime

def update_summary_in_db(log_id, summary):
    """Updates the summary for a specific log_id in the change_log table."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE change_log SET summary = ? WHERE log_id = ?", (summary, log_id))
    conn.commit()
    conn.close()

def main():
    parser = argparse.ArgumentParser(
        description="Analyze and summarize changes from the change_log table.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        '-f', '--filter',
        type=str,
        help="Optional. Filter changes by a substring in the URL."
    )
    parser.add_argument(
        '--backfill',
        action='store_true',
        help="If set, summarizes all historical changes that are missing a summary."
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="Estimate the number of changes to be processed without running the summarizer."
    )
    args = parser.parse_args()

    changes = get_changes(args.filter, args.backfill)

    if args.dry_run:
        logging.info("--- DRY RUN MODE ---")
        if not changes:
            logging.info("No changes found that would be processed.")
        else:
            logging.info(f"Found {len(changes)} changes that would be processed.")
        return

    if not changes:
        logging.info("No new or updated items found to summarize.")
        return

    for log_id, url, change_type in changes:
        logging.info(f"Processing {change_type.upper()} change for: {url} (Log ID: {log_id})")
        current_content, archived_content = get_content_versions(url, change_type)

        if not current_content:
            logging.warning(f"Could not retrieve current content for {url}. Skipping.")
            continue

        summary = summarize_with_gemini(change_type, current_content, archived_content)
        
        if summary and not summary.startswith("Error:"):
            update_summary_in_db(log_id, summary)
            logging.info(f"Successfully generated and saved summary for: {url}")
        else:
            logging.error(f"Failed to generate a valid summary for {url}. Skipping database update.")


if __name__ == "__main__":
    main()

