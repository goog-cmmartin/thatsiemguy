import sqlite3
import requests
import xml.etree.ElementTree as ET
import time
import json
import sys
from datetime import datetime, timedelta
import gemini_summary

# --- Configuration & Database Files ---
CONFIG_FILE = "config.json"
DB_FILE = "whats_new.db"

def parse_date(date_string):
    if not date_string: return None
    formats_to_try = [
        "%a, %d %b %Y %H:%M:%S %z",    # RFC 1123 (e.g., "Wed, 10 Sep 2025 11:29:54 +0200")
        "%a, %d %b %Y %H:%M:%S %Z",    # RFC 1123 with timezone name (e.g., "Sat, 14 May 2022 18:44:18 GMT")
        "%Y-%m-%dT%H:%M:%S%z",        # ISO 8601 variant
    ]
    if date_string and ":" == date_string[-3:-2]:
        date_string = date_string[:-3] + date_string[-2:]
    for date_format in formats_to_try:
        try:
            dt_object = datetime.strptime(date_string, date_format)
            return dt_object.isoformat()
        except (ValueError, TypeError):
            continue
    print(f"Warning: Could not parse date string '{date_string}'")
    return None

def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        if 'instances' not in config: config['instances'] = []
        if 'globalPollingIntervalMinutes' not in config: config['globalPollingIntervalMinutes'] = 60
        return config
    except (FileNotFoundError, json.JSONDecodeError):
        return {"instances": [], "globalPollingIntervalMinutes": 60, "exportDestinations": []}

def save_config(config_data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=4)
    return True

def setup_database():
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("PRAGMA table_info(results)")
    columns = [col[1] for col in cur.fetchall()]
    if 'instanceTitle' not in columns:
        cur.execute("ALTER TABLE results ADD COLUMN instanceTitle TEXT")
    if 'rawXml' not in columns:
        cur.execute("ALTER TABLE results ADD COLUMN rawXml TEXT")
    cur.execute('''
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY, title TEXT, link TEXT UNIQUE, description TEXT,
            publishDate TEXT, sourceTitle TEXT, ingestedAt TEXT, instanceTitle TEXT, rawXml TEXT
        )''')
    # New table to track items sent to export destinations
    cur.execute('''
        CREATE TABLE IF NOT EXISTS sent_items (
            result_id INTEGER,
            destination_name TEXT,
            PRIMARY KEY (result_id, destination_name)
        )''')
    con.commit()
    con.close()

def apply_filters(item, rules):
    for rule in rules:
        key, condition, value = rule.get('key'), rule.get('condition'), rule.get('value')
        if not all([key, condition, value]): continue
        item_value_unformatted = item.get(key)
        if not item_value_unformatted: return False
        item_value, rule_value = item_value_unformatted.lower(), value.lower()
        if condition == 'contains' and rule_value not in item_value: return False
        elif condition == 'equals' and item_value != rule_value: return False
        elif condition == 'starts_with' and not item_value.startswith(rule_value): return False
        elif condition == 'ends_with' and not item_value.endswith(rule_value): return False
        elif condition == 'does_not_contain' and rule_value in item_value: return False
        elif condition == 'not_equals' and item_value == rule_value: return False
        elif condition == 'not_starts_with' and item_value.startswith(rule_value): return False
        elif condition == 'not_ends_with' and item_value.endswith(rule_value): return False
    return True

def fetch_and_process_source(source_config, instance_title):
    source_title, source_url = source_config.get('title', 'Untitled'), source_config.get('url')
    if not source_url: return
    print(f"Fetching: '{source_title}' for instance '{instance_title}'")
    try:
        response = requests.get(source_url, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL '{source_url}': {e}"); return

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as e:
        print(f"Error parsing XML for source '{source_title}': {e}"); return
    
    ns_map = {'atom': 'http://www.w3.org/2005/Atom'}
    items = root.findall('./channel/item') or root.findall('atom:entry', ns_map)
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    new_items_found = 0

    for item_xml in items:
        item_data = {child.tag.split('}')[-1]: ''.join(child.itertext()).strip() for child in item_xml}
        raw_xml_string = ET.tostring(item_xml, encoding='unicode')
        
        link_element = item_xml.find('link')
        item_data['link'] = link_element.get('href') if link_element is not None and link_element.get('href') else item_data.get('link')
        if not item_data.get('title') or not item_data.get('link'): continue

        ingestion_time = datetime.now().isoformat()
        publish_date_str = None
        if not source_config.get('ignoreSourceDate'):
            date_key = source_config.get('dateFieldKey')
            keys_to_try = [date_key] + ['pubDate', 'updated', 'published'] if date_key else ['pubDate', 'updated', 'published']
            for key in keys_to_try:
                if item_data.get(key):
                    publish_date_str = parse_date(item_data.get(key))
                    if publish_date_str: break
        
        final_publish_date = publish_date_str or ingestion_time
        description = (item_data.get('description') or item_data.get('content') or '')[:500]

        if apply_filters(item_data, source_config.get('filterRules', [])):
            try:
                cur.execute(
                    "INSERT INTO results (title, link, description, publishDate, sourceTitle, ingestedAt, instanceTitle, rawXml) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (item_data.get('title'), item_data.get('link'), description, final_publish_date, source_title, ingestion_time, instance_title, raw_xml_string)
                )
                if cur.rowcount > 0:
                    print(f"  -> Found new item: {item_data['title']}")
                    new_items_found += 1
            except sqlite3.IntegrityError: pass
    
    con.commit()
    con.close()
    print(f"  -> Processing complete for '{source_title}'. Found {new_items_found} new items.")

def delete_results_by_source_titles(source_titles):
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute(f"DELETE FROM results WHERE sourceTitle IN ({','.join('?' for _ in source_titles)})", source_titles)
    con.commit()
    con.close()
    print(f"Deleted results for sources: {source_titles}")

def generate_report_data(target_instance_titles, days_ago, date_field_to_filter):
    start_date = (datetime.now() - timedelta(days=days_ago)).isoformat()
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    
    query = f"SELECT * FROM results WHERE {date_field_to_filter} >= ? AND instanceTitle IN ({','.join('?' for _ in target_instance_titles)}) ORDER BY publishDate DESC"
    params = [start_date] + target_instance_titles
    cur.execute(query, params)
    
    results = cur.fetchall()
    con.close()
    results_by_source = {}
    for row in results:
        row_dict = dict(row)
        source_title = row_dict['sourceTitle']
        if source_title not in results_by_source: results_by_source[source_title] = []
        results_by_source[source_title].append(row_dict)
    return {'resultsBySource': results_by_source, 'instanceTitles': target_instance_titles}

def run_polling_cycle(target_instance_titles=None):
    print(f"\n--- Running Polling Cycle at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
    config = load_config()
    instances_to_poll = config.get('instances', [])
    if target_instance_titles:
        instances_to_poll = [inst for inst in instances_to_poll if inst['title'] in target_instance_titles]
    
    for instance in instances_to_poll:
        for source in instance.get('sources', []):
            fetch_and_process_source(source, instance['title'])
    print("--- Polling Cycle Complete ---")

def enrich_and_summarize_report(report_data):
    enriched_results = {}
    for source_title, items in report_data.get('resultsBySource', {}).items():
        enriched_items = []
        for item in items:
            print(f"  -> Summarizing for export: {item['title']}")
            summary = gemini_summary.get_summary(item['title'], item['link'], item['description'])
            item['summary'] = summary
            enriched_items.append(item)
        enriched_results[source_title] = enriched_items
    return enriched_results

def format_for_google_chat(report_data, report_title):
    card = {"cardsV2": [{"cardId": "whatsNewCard", "card": {
        "header": {"title": "What's New Report", "subtitle": report_title, "imageUrl": "https://img.icons8.com/fluency/48/news.png", "imageType": "CIRCLE"},
        "sections": []
    }}]}

    if not report_data or not any(report_data.values()):
        card['cardsV2'][0]['card']['sections'].append({
            "widgets": [{"textParagraph": {"text": "No new items found for this report."}}]
        })
        return card

    for source_title, items in report_data.items():
        section = {"header": source_title, "widgets": []}
        for item in items:
            widget = {
                "decoratedText": {
                    "startIcon": {"knownIcon": "DESCRIPTION"},
                    "topLabel": item['title'],
                    "text": item['summary'] or "No summary available.",
                    "wrapText": True,
                    "button": {"text": "Read More", "onClick": {"openLink": {"url": item['link']}}}
                }
            }
            section['widgets'].append(widget)
        card['cardsV2'][0]['card']['sections'].append(section)
    return card

def post_to_google_chat(webhook_url, card_json):
    if not webhook_url:
        print("Webhook Error: URL not provided.")
        return False
    try:
        response = requests.post(webhook_url, json=card_json)
        response.raise_for_status()
        print("Successfully posted report to Google Chat.")
        return True
    except requests.exceptions.RequestException as e:
        print("--- ERROR: Failed to post to Google Chat ---")
        print(f"Error: {e}")
        print("--- PAYLOAD SENT ---")
        print(json.dumps(card_json, indent=2))
        print("--- RESPONSE FROM GOOGLE ---")
        if e.response is not None:
            print(f"Status Code: {e.response.status_code}")
            print(f"Response Body: {e.response.text}")
        print("---------------------------------")
        return False

def filter_unsent_items(report_data, destination_name):
    print(f"DEBUG: Filtering sent items for destination: {destination_name}")
    all_item_ids = [item['id'] for source in report_data.get('resultsBySource', {}).values() for item in source]
    print(f"DEBUG: Found {len(all_item_ids)} total items in report. IDs: {all_item_ids}")

    if not all_item_ids:
        return ({'resultsBySource': {}, 'instanceTitles': report_data.get('instanceTitles', [])}, [])

    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    query = f"SELECT result_id FROM sent_items WHERE destination_name = ? AND result_id IN ({','.join('?' for _ in all_item_ids)})"
    cur.execute(query, [destination_name] + all_item_ids)
    sent_ids = {row[0] for row in cur.fetchall()}
    con.close()
    print(f"DEBUG: Found {len(sent_ids)} already sent IDs in DB: {sent_ids}")

    new_report_data = {'resultsBySource': {}, 'instanceTitles': report_data.get('instanceTitles', [])}
    new_item_ids = []
    for source_title, items in report_data.get('resultsBySource', {}).items():
        unsent_items = [item for item in items if item['id'] not in sent_ids]
        if unsent_items:
            new_report_data['resultsBySource'][source_title] = unsent_items
            new_item_ids.extend([item['id'] for item in unsent_items])
            
    print(f"DEBUG: Identified {len(new_item_ids)} new items to be sent. IDs: {new_item_ids}")
    return new_report_data, new_item_ids

def mark_items_as_sent(item_ids, destination_name):
    if not item_ids: 
        print("DEBUG: No new items to mark as sent.")
        return
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    data_to_insert = [(item_id, destination_name) for item_id in item_ids]
    cur.executemany("INSERT OR IGNORE INTO sent_items (result_id, destination_name) VALUES (?, ?)", data_to_insert)
    con.commit()
    con.close()
    print(f"DEBUG: Marked {len(item_ids)} items as sent for destination '{destination_name}'. IDs: {item_ids}")

def run_single_export(destination_config):
    destination_name = destination_config.get('name')
    print(f"--- Running single export for: {destination_name} ---")
    
    report_data = generate_report_data(
        target_instance_titles=destination_config.get('instances', []),
        days_ago=destination_config.get('reportDays', 7),
        date_field_to_filter=destination_config.get('dateField', 'publishDate')
    )

    new_report_data, new_item_ids = filter_unsent_items(report_data, destination_name)

    if not new_item_ids:
        print(f"No new items to report for destination '{destination_name}'.")
        # To avoid confusion, don't send an empty report unless explicitly configured to do so.
        return True

    print(f"Found {len(new_item_ids)} new items to report for '{destination_name}'.")
    
    enriched_results = enrich_and_summarize_report(new_report_data)
    
    success = False
    if destination_config['type'] == 'googleChatWebhook':
        chat_card = format_for_google_chat(enriched_results, destination_name)
        success = post_to_google_chat(destination_config.get('url'), chat_card)

    if success:
        mark_items_as_sent(new_item_ids, destination_name)
    
    print(f"--- Finished export for: {destination_name} ---")
    return success

def generate_and_dispatch_reports():
    print("--- Checking for scheduled reports... ---")
    config = load_config()
    for destination in config.get('exportDestinations', []):
        run_single_export(destination)

