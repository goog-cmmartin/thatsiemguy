import sqlite3
import logging
from config import DB_NAME, DOC_SOURCES

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def backfill_source_tags():
    """Backfills the 'source_tag' column in the change_log table based on URL patterns."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Get all entries from change_log that are missing a source_tag
    cursor.execute("SELECT log_id, url FROM change_log WHERE source_tag IS NULL OR source_tag = ''")
    records_to_update = cursor.fetchall()

    if not records_to_update:
        logging.info("No change_log entries found with missing source_tag. Backfill not needed.")
        conn.close()
        return

    logging.info(f"Found {len(records_to_update)} change_log entries with missing source_tag. Starting backfill...")

    updated_count = 0
    for log_id, url in records_to_update:
        source_tag = "Unknown"
        for tag, base_url in DOC_SOURCES.items():
            if url.startswith(base_url):
                source_tag = tag
                break
        
        if source_tag != "Unknown":
            cursor.execute("UPDATE change_log SET source_tag = ? WHERE log_id = ?", (source_tag, log_id))
            updated_count += 1
            if updated_count % 100 == 0: # Log progress
                logging.info(f"  Updated {updated_count}/{len(records_to_update)} entries...")

    conn.commit()
    conn.close()
    logging.info(f"Backfill complete. Updated {updated_count} change_log entries with source_tag.")

if __name__ == "__main__":
    backfill_source_tags()