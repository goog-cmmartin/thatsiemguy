import sqlite3
import requests
import xml.etree.ElementTree as ET
import time
import json
import sys
from datetime import datetime, timedelta, timezone
import gemini_summary

# --- Configuration & Database Files ---
CONFIG_FILE = "config.json"
DB_FILE = "whats_new.db"

def parse_date(date_string):
    if not date_string: return None
    formats_to_try = [
        "%a, %d %b %Y %H:%M:%S %z",    # RFC 1123 (e.g., "Wed, 10 Sep 2025 11:29:54 +0200")
        "%a, %d %b %Y %H:%M:%S %Z",     # RFC 1123 with timezone name (e.g., "Sat, 14 May 2022 18:44:18 GMT")
        "%Y-%m-%dT%H:%M:%S%z",         # ISO 8601 variant
        "%Y-%m-%dT%H:%M:%S.%f%z",      # ISO 8601 with microseconds
    ]
    if date_string and ":" == date_string[-3:-2]:
        date_string = date_string[:-3] + date_string[-2:]
    for date_format in formats_to_try:
        try:
            dt_object = datetime.strptime(date_string, date_format)
            return dt_object.isoformat()
        except (ValueError, TypeError): continue
    try:
        dt_object = datetime.fromisoformat(date_string.replace('Z', '+00:00'))
        return dt_object.isoformat()
    except (ValueError, TypeError):
        print(f"Warning: Could not parse date string '{date_string}' with any known format.")
        return None

def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        if 'instances' not in config: config['instances'] = []
        if 'globalPollingIntervalMinutes' not in config: config['globalPollingIntervalMinutes'] = 60
        if 'exportDestinations' not in config: config['exportDestinations'] = []
        return config
    except (FileNotFoundError, json.JSONDecodeError):
        return {"instances": [], "globalPollingIntervalMinutes": 60, "exportDestinations": []}

def save_config(config_data):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config_data, f, indent=4)
        print("Configuration saved successfully.")
        return True
    except Exception as e:
        print(f"Error saving configuration: {e}")
        return False

def setup_database():
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY, 
            title TEXT, 
            link TEXT UNIQUE, 
            description TEXT,
            publishDate TEXT, 
            sourceTitle TEXT, 
            ingestedAt TEXT, 
            rawXml TEXT, 
            instanceTitle TEXT,
            summary TEXT,
            sentiment TEXT,
            category TEXT
        )
    ''')
    cur.execute("PRAGMA table_info(results);")
    columns = [info[1] for info in cur.fetchall()]
    
    # Add new columns if they don't exist (for migration)
    if 'rawXml' not in columns:
        cur.execute("ALTER TABLE results ADD COLUMN rawXml TEXT;")
    if 'instanceTitle' not in columns:
        cur.execute("ALTER TABLE results ADD COLUMN instanceTitle TEXT;")
    if 'summary' not in columns:
        cur.execute("ALTER TABLE results ADD COLUMN summary TEXT;")
    if 'sentiment' not in columns:
        cur.execute("ALTER TABLE results ADD COLUMN sentiment TEXT;")
    if 'category' not in columns:
        cur.execute("ALTER TABLE results ADD COLUMN category TEXT;")
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS export_tracker (
            destination_name TEXT PRIMARY KEY,
            last_run_timestamp TEXT
        )
    ''')
    con.commit()
    con.close()

def apply_filters(item, rules):
    for rule in rules:
        key, condition, value = rule.get('key'), rule.get('condition'), rule.get('value')
        if not all([key, condition, value]): continue
        item_value_unformatted = item.get(key)
        if not item_value_unformatted: return False
        item_value, rule_value = item_value_unformatted.lower(), value.lower()
        if (condition == 'contains' and rule_value not in item_value) or \
           (condition == 'equals' and item_value != rule_value) or \
           (condition == 'starts_with' and not item_value.startswith(rule_value)) or \
           (condition == 'ends_with' and not item_value.endswith(rule_value)) or \
           (condition == 'does_not_contain' and rule_value in item_value) or \
           (condition == 'not_equals' and item_value == rule_value) or \
           (condition == 'not_starts_with' and item_value.startswith(rule_value)) or \
           (condition == 'not_ends_with' and item_value.endswith(rule_value)):
            return False
    return True

def get_element_text(element, paths, ns=None):
    for path in paths:
        found = element.find(path, ns)
        if found is not None:
            return ''.join(found.itertext()).strip()
    return None

def fetch_and_process_source(source_config, instance_title):
    source_title = source_config.get('title', 'Untitled Source')
    source_url = source_config.get('url')
    date_field_key = source_config.get('dateFieldKey')
    ignore_source_date = source_config.get('ignoreSourceDate', False)

    if not source_url: return
    print(f"Fetching: '{source_title}' for instance '{instance_title}'")
    try:
        response = requests.get(source_url, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL '{source_url}': {e}")
        return

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as e:
        print(f"Error parsing XML for source '{source_title}': {e}")
        return

    new_items_found = 0
    ns = {'atom': 'http://www.w3.org/2005/Atom'}
    items = root.findall('./channel/item') or root.findall('atom:entry', ns)
    
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()

    for item_xml in items:
        raw_xml_str = ET.tostring(item_xml, encoding='unicode')
        
        title = get_element_text(item_xml, ['title', 'atom:title'], ns)
        link_element = item_xml.find('atom:link', ns)
        link = link_element.get('href') if link_element is not None else get_element_text(item_xml, ['link'])

        description = get_element_text(item_xml, ['description', 'atom:content', 'atom:summary'], ns)
        item_data = {child.tag.split('}')[-1]: ''.join(child.itertext()).strip() for child in item_xml}
        
        if not title or not link: continue

        ingestion_time = datetime.now(timezone.utc).isoformat()
        publish_date_str = None
        if not ignore_source_date:
            date_keys = [date_field_key] if date_field_key else []
            date_keys.extend(['pubDate', 'updated', 'published'])
            for key in date_keys:
                date_val = get_element_text(item_xml, [key, f"atom:{key}"], ns)
                if date_val:
                    publish_date_str = parse_date(date_val)
                    if publish_date_str: break
        
        final_publish_date = publish_date_str or ingestion_time

        if apply_filters(item_data, source_config.get('filterRules', [])):
            try:
                # Attempt to insert the new item
                cur.execute(
                    "INSERT INTO results (title, link, description, publishDate, sourceTitle, ingestedAt, rawXml, instanceTitle) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (title, link, description[:500] if description else '', final_publish_date, source_title, ingestion_time, raw_xml_str, instance_title)
                )
                if cur.rowcount > 0:
                    # If insert is successful, then (and only then) run analysis
                    new_items_found += 1
                    print(f"  -> Found new item: {title}")
                    try:
                        print(f"  -> Generating analysis for new item...")
                        analysis = gemini_summary.get_analysis(title, link, description)
                        
                        # Save the analysis back to the database
                        cur.execute(
                            "UPDATE results SET summary = ?, sentiment = ?, category = ? WHERE link = ?",
                            (analysis.get('summary'), analysis.get('sentiment'), analysis.get('category'), link)
                        )
                        print(f"  -> Analysis complete. Sentiment: {analysis.get('sentiment')}, Category: {analysis.get('category')}")
                    except Exception as e:
                        # If analysis fails, log it but do NOT roll back the transaction
                        print(f"  -> ERROR: Failed to generate analysis for '{title}'. Error: {e}")
                        # The item remains in the DB without analysis, will be backfilled later if needed
            
            except sqlite3.IntegrityError: 
                # This triggers if the link (UNIQUE constraint) already exists.
                pass # Item already exists, ignore.
    
    con.commit() # Commit all successful inserts/updates for this source at the end
    con.close()
    print(f"  -> Processing complete for '{source_title}'. Found {new_items_found} new items.")


def run_polling_cycle():
    print(f"\n--- Running Polling Cycle at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
    app_config = load_config()
    for instance in app_config.get('instances', []):
        if instance.get('isActive', True):
            for source in instance.get('sources', []):
                fetch_and_process_source(source, instance['title'])
    print("--- Polling Cycle Complete ---")

def generate_report_data(target_instance_titles, start_date, date_field_to_filter):
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    placeholders = ','.join('?' for _ in target_instance_titles)
    # Select all new analysis fields as well
    query = f"""
        SELECT 
            id, title, link, description, sourceTitle, ingestedAt, publishDate, rawXml, instanceTitle,
            summary, sentiment, category 
        FROM results 
        WHERE {date_field_to_filter} >= ? AND instanceTitle IN ({placeholders}) 
        ORDER BY publishDate DESC
    """
    params = (start_date, *target_instance_titles)
    cur.execute(query, params)
    results = [dict(row) for row in cur.fetchall()]
    con.close()
    
    results_by_source = {}
    for row in results:
        source_title = row['sourceTitle']
        if source_title not in results_by_source: results_by_source[source_title] = []
        results_by_source[source_title].append(row)
    
    return {"resultsBySource": results_by_source, "instanceTitles": target_instance_titles}

def delete_results_by_source_titles(source_titles):
    if not source_titles: return
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    placeholders = ','.join('?' for _ in source_titles)
    cur.execute(f"DELETE FROM results WHERE sourceTitle IN ({placeholders})", source_titles)
    con.commit()
    con.close()
    print(f"Deleted results for sources: {source_titles}")

# --- Export Formatters ---

def format_for_google_chat(report_data, report_title, icon_url):
    header = {"title": report_title, "subtitle": "Latest Updates"}
    if icon_url: header["imageUrl"] = icon_url
    sections = []
    total_items = sum(len(items) for items in report_data.values())
    
    if total_items == 0:
        sections.append({"widgets": [{"textParagraph": {"text": "No new items found for this report."}}]})
    else:
        for source_title, items in report_data.items():
            if not items: continue
            widgets = [{"decoratedText": {"topLabel": "", "text": f"<b>{source_title}</b>"}}]
            for item in items:
                # Use the pre-generated summary from the database
                summary = item.get('summary') or item.get('description', 'No summary available.')
                
                # --- NEW CHIP LOGIC ---
                chips_html = ""
                category = item.get('category')
                sentiment = item.get('sentiment')

                if category:
                    chips_html += f"<font color=\"#B0B0B0\"><b>{category.upper()}</b></font>  " # Gray
                
                if sentiment == 'Positive':
                    chips_html += f"<font color=\"#059669\"><b>Positive</b></font>" # Green
                elif sentiment == 'Negative':
                    chips_html += f"<font color=\"#DC2626\"><b>Negative</b></font>" # Red
                elif sentiment == 'Neutral':
                    chips_html += f"<font color=\"#B0B0B0\"><b>Neutral</b></font>" # Gray

                if chips_html:
                    chips_html += "<br><br>" # Add spacing after chips, before summary
                # --- END NEW CHIP LOGIC ---

                # Combine title, chips, and summary into one block for the main text field
                final_text_block = f"<b>{item['title']}</b><br><br>{chips_html}{summary}"

                widgets.append({
                    "decoratedText": {
                        "text": final_text_block, # This now contains the title, chips, and summary
                        "wrapText": True, 
                        "button": {"text": "Read More", "onClick": {"openLink": {"url": item['link']}}}
                    }
                })
            sections.append({"widgets": widgets})
    return {"cardsV2": [{"card": {"header": header, "sections": sections}}]}


def format_report_as_json(report_data):
    """Formats the final report data into a simple list of enriched items for JSON export."""
    all_items = []
    for source_title, items in report_data.items():
        all_items.extend(items)
    return all_items

def save_report_to_json_file(file_path, report_data):
    if not file_path:
        print("Export Error: File path for JSON export is not configured.")
        return False
    try:
        # Use the dedicated JSON formatter
        json_payload = format_report_as_json(report_data)
        with open(file_path, 'w') as f:
            json.dump(json_payload, f, indent=4)
        print(f"Successfully saved JSON report to {file_path}")
        return True
    except Exception as e:
        print(f"Error saving report to JSON file: {e}")
        return False

# --- Export Dispatchers ---

def post_to_google_chat(url, payload):
    if not url:
        print("Webhook Error: URL is not configured.")
        return False
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("Successfully posted report to Google Chat.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error posting to Google Chat: {e}")
        if e.response: print(f"Response body: {e.response.text}")
        return False

def run_single_export(destination_config, is_manual_run=False):
    dest_name = destination_config.get('name', '').strip()
    if not dest_name:
        print("Export Error: Destination name is missing from config.")
        return False
        
    print(f"Running export for: {dest_name}")

    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()

    if is_manual_run:
        freq_unit = destination_config.get('runFrequencyUnit', 'days')
        freq_val = destination_config.get('runFrequency', 1)
        if freq_unit == 'minutes': lookback_delta = timedelta(minutes=freq_val)
        elif freq_unit == 'hours': lookback_delta = timedelta(hours=freq_val)
        else: lookback_delta = timedelta(days=freq_val)
        start_date = (datetime.now(timezone.utc) - lookback_delta).isoformat()
    else: # Scheduled run, use last run timestamp
        cur.execute("SELECT last_run_timestamp FROM export_tracker WHERE destination_name = ?", (dest_name,))
        result = cur.fetchone()
        if result and result[0]:
            start_date = result[0]
        else: # First run, use the lookback period as a default
            freq_unit = destination_config.get('runFrequencyUnit', 'days')
            freq_val = destination_config.get('runFrequency', 1)
            if freq_unit == 'minutes': lookback_delta = timedelta(minutes=freq_val)
            elif freq_unit == 'hours': lookback_delta = timedelta(hours=freq_val)
            else: lookback_delta = timedelta(days=freq_val)
            start_date = (datetime.now(timezone.utc) - lookback_delta).isoformat()
            
    print(f"DEBUG: Using start date for report: {start_date}")

    # Fetch data. Analysis (summary, etc.) is already in the database.
    report_data = generate_report_data(
        target_instance_titles=destination_config.get('instances', []),
        start_date=start_date,
        date_field_to_filter='ingestedAt' # Scheduled/automated reports ALWAYS filter by ingest time
    )
    
    item_count = sum(len(items) for items in report_data.get('resultsBySource', {}).values())

    if item_count == 0 and not destination_config.get('sendEmptyReports', False):
        print(f"No new items found for '{dest_name}'. Skipping notification.")
        con.close()
        return True # Considered success as there's nothing to do

    # --- Dispatch based on type ---
    success = False
    export_type = destination_config.get('type')
    enriched_results = report_data.get('resultsBySource', {})


    if export_type == 'googleChatWebhook':
        chat_payload = format_for_google_chat(enriched_results, dest_name, destination_config.get('iconUrl'))
        success = post_to_google_chat(destination_config.get('url'), chat_payload)
    elif export_type == 'jsonFile':
        success = save_report_to_json_file(destination_config.get('filePath'), enriched_results)
    else:
        print(f"Error: Unknown export type '{export_type}' for destination '{dest_name}'.")

    if success and not is_manual_run:
        new_last_run = datetime.now(timezone.utc).isoformat()
        cur.execute("INSERT OR REPLACE INTO export_tracker (destination_name, last_run_timestamp) VALUES (?, ?)",
                    (dest_name, new_last_run))
        con.commit()
        print(f"DEBUG: Updated last run time for '{dest_name}' to {new_last_run}")
    
    con.close()
    return success

def generate_and_dispatch_reports():
    print("Checking for scheduled reports...")
    config = load_config()
    for destination in config.get('exportDestinations', []):
        run_single_export(destination, is_manual_run=False)

# --- New Helper Functions for On-Demand API Calls ---

def get_item_by_link(link):
    """Fetches a single item's details from the DB by its unique link."""
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT * FROM results WHERE link = ?", (link,))
    result = cur.fetchone()
    con.close()
    return dict(result) if result else None

def save_analysis_to_db(link, analysis_data):
    """Saves analysis data for a specific item identified by its link."""
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute(
        "UPDATE results SET summary = ?, sentiment = ?, category = ? WHERE link = ?",
        (
            analysis_data.get('summary'), 
            analysis_data.get('sentiment'), 
            analysis_data.get('category'), 
            link
        )
    )
    con.commit()
    con.close()
    print(f"DEBUG: Saved on-demand analysis to DB for link: {link}")

