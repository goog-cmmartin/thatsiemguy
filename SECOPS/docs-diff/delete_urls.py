import sqlite3
import logging

# --- Configuration ---
DB_NAME = 'doc_content.db'

# Add any URL patterns you want to delete. 
# The '%' is a SQL wildcard that matches any sequence of characters.
URLS_TO_DELETE = [
    '%gtidocs.virustotal.com%',
    'https://cloud.google.com/chronicle/docs/reference/rest/%',
    'https://cloud.google.com/chronicle/docs/ingestion/parser-list/%',
    'https://cloud.google.com/chronicle/docs/ingestion/default-parsers/%',
    'https://cloud.google.com/chronicle/docs/soar/marketplace-integrations/%',
    'https://cloud.google.com/security-command-center/docs/reference/rest/%',
    'https://cloud.google.com/security-command-center/docs/reference/securityposture/rest/%',
    'https://cloud.google.com/security-command-center/docs/reference/security-center-management/rest/%',
    'https://gtidocs.virustotal.com/reference/%',
    '%/rest/%'
]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def delete_urls_by_pattern():
    """
    Connects to the database and deletes records from all relevant tables
    that match the specified URL patterns.
    """
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        logging.info(f"Starting deletion process for {len(URLS_TO_DELETE)} URL patterns.")

        for pattern in URLS_TO_DELETE:
            print("-" * 60)
            logging.info(f"Processing pattern: {pattern}")

            # --- Step 1: Clean up the 'topic_doc_mapping' table first ---
            # This is important to maintain relational integrity.
            try:
                cursor.execute("SELECT COUNT(*) FROM topic_doc_mapping WHERE doc_url LIKE ?", (pattern,))
                count = cursor.fetchone()[0]
                
                if count > 0:
                    logging.info(f"Found {count} matching records in 'topic_doc_mapping'. Deleting them now...")
                    cursor.execute("DELETE FROM topic_doc_mapping WHERE doc_url LIKE ?", (pattern,))
                    logging.info(f"Deleted {cursor.rowcount} records from 'topic_doc_mapping'.")
                else:
                    logging.info("No matching records found in 'topic_doc_mapping'.")
            except sqlite3.OperationalError:
                logging.warning("Table 'topic_doc_mapping' not found, skipping cleanup for this table.")

            # --- Step 2: Clean up the 'change_log' table ---
            try:
                cursor.execute("SELECT COUNT(*) FROM change_log WHERE url LIKE ?", (pattern,))
                count = cursor.fetchone()[0]
                
                if count > 0:
                    logging.info(f"Found {count} matching records in 'change_log'. Deleting them now...")
                    cursor.execute("DELETE FROM change_log WHERE url LIKE ?", (pattern,))
                    logging.info(f"Deleted {cursor.rowcount} records from 'change_log'.")
                else:
                    logging.info("No matching records found in 'change_log'.")
            except sqlite3.OperationalError:
                logging.warning("Table 'change_log' not found, skipping cleanup for this table.")

            # --- Step 3: Clean up the main 'pages' table ---
            cursor.execute("SELECT COUNT(*) FROM pages WHERE url LIKE ?", (pattern,))
            count = cursor.fetchone()[0]

            if count > 0:
                logging.info(f"Found {count} matching records in 'pages'. Deleting them now...")
                cursor.execute("DELETE FROM pages WHERE url LIKE ?", (pattern,))
                logging.info(f"Deleted {cursor.rowcount} records from 'pages'.")
            else:
                logging.info("No matching records found in 'pages'.")

        print("-" * 60)
        logging.info("Committing all changes to the database.")
        conn.commit()

    except sqlite3.OperationalError as e:
        logging.error(f"An error occurred: {e}")
        logging.error("Please ensure the database file exists and the table names are correct.")
    finally:
        if conn:
            conn.close()
            logging.info("Database connection closed. Deletion process complete.")

if __name__ == "__main__":
    delete_urls_by_pattern()
