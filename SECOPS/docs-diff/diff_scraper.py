import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import logging
import time
import sqlite3
import hashlib
import re
from datetime import datetime
import argparse
from config import DB_NAME, DOC_SOURCES, EXCLUDED_PATTERNS

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def create_session_with_retries():
    """Creates a requests.Session with a robust retry strategy."""
    session = requests.Session()
    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

def setup_database():
    """Initializes the database and creates/updates tables for pages, archive, and change log."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pages (
            url TEXT PRIMARY KEY, content TEXT NOT NULL, content_hash TEXT NOT NULL,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, source_tag TEXT,
            summary TEXT, llm_generated_tags TEXT
        )
    ''')
    cursor.execute("PRAGMA table_info(pages)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'content_hash' not in columns:
        cursor.execute('ALTER TABLE pages ADD COLUMN content_hash TEXT')
        cursor.execute("SELECT url, content FROM pages WHERE content_hash IS NULL")
        rows_to_update = cursor.fetchall()
        if rows_to_update:
            for url, content in rows_to_update:
                cleaned_content = clean_content(content)
                content_hash = calculate_hash(cleaned_content)
                cursor.execute("UPDATE pages SET content_hash = ? WHERE url = ?", (content_hash, url))
            conn.commit()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pages_archive (
            archive_id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL,
            content TEXT NOT NULL, archived_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS change_log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT, scrape_date DATE NOT NULL,
            url TEXT NOT NULL, change_type TEXT NOT NULL, content_hash TEXT,
            summary TEXT
        )
    ''')
    cursor.execute("PRAGMA table_info(change_log)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'summary' not in columns:
        cursor.execute('ALTER TABLE change_log ADD COLUMN summary TEXT')
    if 'source_tag' not in columns:
        cursor.execute('ALTER TABLE change_log ADD COLUMN source_tag TEXT')

    # Create broken_links table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS broken_links (
            link_id INTEGER PRIMARY KEY AUTOINCREMENT,
            scrape_date DATE NOT NULL,
            source_url TEXT NOT NULL,
            target_url TEXT NOT NULL
        )
    ''')
    # --- FTS5 Setup for Search ---
    # Drop existing FTS table and triggers to ensure a clean rebuild
    cursor.execute("DROP TRIGGER IF EXISTS t_change_log_summary_update")
    cursor.execute("DROP TABLE IF EXISTS change_log_fts")

    # Create a virtual table for full-text search on the 'summary' column
    cursor.execute('''
        CREATE VIRTUAL TABLE change_log_fts USING fts5(
            summary,
            content='change_log',
            content_rowid='log_id'
        );
    ''')

    # Create triggers to keep the FTS index up-to-date
    cursor.execute('''
        CREATE TRIGGER t_change_log_summary_update AFTER UPDATE OF summary ON change_log
        BEGIN
            INSERT INTO change_log_fts(change_log_fts, rowid) VALUES('delete', old.log_id);
            INSERT INTO change_log_fts(rowid, summary) VALUES (new.log_id, new.summary);
        END;
    ''')
    
    # Populate the FTS index with existing non-null summaries
    cursor.execute('''
        INSERT INTO change_log_fts (rowid, summary)
        SELECT log_id, summary FROM change_log WHERE summary IS NOT NULL;
    ''')

    conn.commit()
    conn.close()
    logging.info(f"Database '{DB_NAME}' is ready.")

def clean_content(text):
    if not text: return ""
    return re.sub(r"Last updated \d{4}-\d{2}-\d{2} UTC", "", text).strip()

def calculate_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def is_excluded(url, patterns):
    """Checks if a given URL matches any of the exclusion patterns."""
    for pattern in patterns:
        if pattern.endswith('/') and url.startswith(pattern):
            return True
        elif pattern.startswith('%') and pattern.endswith('%'):
            # Convert SQL-like % wildcard to regex .*
            regex_pattern = pattern.replace('%', '.*')
            if re.search(regex_pattern, url):
                return True
        elif url.startswith(pattern):
            return True
    return False

def get_all_links(url, base_url, session, conn, current_page_url=None):
    links = set()
    try:
        with session.get(url, timeout=10) as response:
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            for a_tag in soup.find_all('a', href=True):
                link = urljoin(url, a_tag['href']).split('#')[0]
                if link.startswith(base_url) and not is_excluded(link, EXCLUDED_PATTERNS):
                    links.add(link)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logging.warning(f"Broken link found: {url} (from {current_page_url or 'start'})")
            cursor = conn.cursor()
            scrape_date = datetime.now().date()
            cursor.execute(
                "INSERT INTO broken_links (scrape_date, source_url, target_url) VALUES (?, ?, ?)",
                (scrape_date, current_page_url or 'start', url)
            )
            conn.commit()
        else:
            logging.warning(f"Could not fetch links from {url} (found on {current_page_url or 'start'}): {e}")
    except requests.exceptions.RequestException as e:
        logging.warning(f"Could not fetch links from {url} (found on {current_page_url or 'start'}): {e}")
    return links

def scrape_text(url, session):
    try:
        with session.get(url, timeout=10) as response:
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            content_area = soup.find('div', class_='devsite-article-body') or soup.find('article') or soup.find('main')
            return content_area.get_text(separator=' ', strip=True) if content_area else ""
    except requests.exceptions.RequestException as e:
        logging.warning(f"Could not scrape text from {url}: {e}")
        return ""

def main():
    parser = argparse.ArgumentParser(description="Scrape websites and log changes to a database.")
    parser.add_argument(
        '--setup-only',
        action='store_true',
        help="Run only the database setup function and exit."
    )
    args = parser.parse_args()

    if args.setup_only:
        setup_database()
        return

    setup_database()
    session = create_session_with_retries()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    scrape_date = datetime.now().date()
    logging.info(f"--- Starting scrape for {scrape_date} ---")

    cursor.execute("SELECT url, content_hash FROM pages")
    db_state = {row[0]: row[1] for row in cursor.fetchall()}
    logging.info(f"Found {len(db_state)} pages in the local database.")

    all_live_urls = set()
    for source_tag, base_url in DOC_SOURCES.items():
        logging.info(f"Crawling source: {source_tag}...")
        # Use a dictionary to track {url_to_visit: source_url}
        urls_to_visit = {base_url: 'start'}
        visited_urls = set()
        
        while urls_to_visit:
            # Pop an item to get both the URL and its source
            url, source_url = urls_to_visit.popitem()
            
            if url in visited_urls:
                continue
            visited_urls.add(url)
            all_live_urls.add(url)

            if len(visited_urls) % 50 == 0: # Log progress every 50 pages
                logging.info(f"  Discovered {len(visited_urls)} pages for {source_tag}...")

            # Pass the actual source_url to the logging function
            new_links = get_all_links(url, base_url, session, conn, current_page_url=source_url)
            
            # Add new links to the dictionary, with the current URL as their source
            for new_link in new_links:
                if new_link not in visited_urls and new_link not in urls_to_visit:
                    urls_to_visit[new_link] = url
    logging.info(f"Crawl complete. Found {len(all_live_urls)} live URLs.")

    db_urls = set(db_state.keys())
    new_urls = all_live_urls - db_urls
    removed_urls = db_urls - all_live_urls
    existing_urls = all_live_urls.intersection(db_urls)

    logging.info(f"Found {len(removed_urls)} removed URLs.")
    for url in removed_urls:
        cursor.execute("INSERT INTO change_log (scrape_date, url, change_type) VALUES (?, ?, ?)", (scrape_date, url, 'removed'))
    conn.commit()

    logging.info(f"Found {len(new_urls)} new URLs to scrape.")
    for i, url in enumerate(new_urls):
        logging.info(f"  Scraping new page {i+1}/{len(new_urls)}: {url}")
        content = scrape_text(url, session)
        if content:
            cleaned_content = clean_content(content)
            new_hash = calculate_hash(cleaned_content)
            source_tag = next((tag for tag, base in DOC_SOURCES.items() if url.startswith(base)), "Unknown")
            cursor.execute("INSERT INTO pages (url, content, content_hash, source_tag) VALUES (?, ?, ?, ?)", (url, content, new_hash, source_tag))
            cursor.execute("INSERT INTO change_log (scrape_date, url, change_type, content_hash, source_tag) VALUES (?, ?, ?, ?, ?)", (scrape_date, url, 'new', new_hash, source_tag))
    conn.commit()

    logging.info(f"Checking {len(existing_urls)} existing URLs for content changes...")
    for i, url in enumerate(existing_urls):
        if i % 50 == 0 and i > 0: logging.info(f"  Checked {i}/{len(existing_urls)} existing pages...")
        old_hash = db_state.get(url)
        live_content = scrape_text(url, session)
        if not live_content:
            logging.warning(f"  Could not fetch content for existing URL, skipping: {url}")
            continue
        cleaned_content = clean_content(live_content)
        new_hash = calculate_hash(cleaned_content)
        if new_hash != old_hash:
            logging.info(f"  Change detected for: {url}")
            cursor.execute("SELECT content FROM pages WHERE url=?", (url,))
            old_content_row = cursor.fetchone()
            if old_content_row:
                cursor.execute("INSERT INTO pages_archive (url, content) VALUES (?, ?)", (url, old_content_row[0]))
            cursor.execute("UPDATE pages SET content=?, content_hash=?, scraped_at=CURRENT_TIMESTAMP WHERE url=?", (live_content, new_hash, url))
            source_tag = next((tag for tag, base in DOC_SOURCES.items() if url.startswith(base)), "Unknown")
            cursor.execute("INSERT INTO change_log (scrape_date, url, change_type, content_hash, source_tag) VALUES (?, ?, ?, ?, ?)", (scrape_date, url, 'updated', new_hash, source_tag))
        else:
            source_tag = next((tag for tag, base in DOC_SOURCES.items() if url.startswith(base)), "Unknown")
            cursor.execute("INSERT INTO change_log (scrape_date, url, change_type, content_hash, source_tag) VALUES (?, ?, ?, ?, ?)", (scrape_date, url, 'unchanged', old_hash, source_tag))
    conn.commit()

    logging.info("--- Scrape and diff process complete. ---")
    conn.close()
    session.close()

if __name__ == "__main__":
    main()
