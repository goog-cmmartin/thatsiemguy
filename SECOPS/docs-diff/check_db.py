import sqlite3
from config import DB_NAME

def check_fts_index():
    """Checks the status of the FTS index."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Check how many summaries should be indexed
    cursor.execute("SELECT COUNT(*) FROM change_log WHERE summary IS NOT NULL")
    total_summaries = cursor.fetchone()[0]
    print(f"Total summaries in change_log: {total_summaries}")

    # Check how many summaries are actually in the FTS index
    cursor.execute("SELECT COUNT(*) FROM change_log_fts")
    indexed_summaries = cursor.fetchone()[0]
    print(f"Total entries in FTS index: {indexed_summaries}")

    if total_summaries > 0 and indexed_summaries == 0:
        print("\nConclusion: The FTS index is empty. It needs to be populated with existing data.")
    elif total_summaries == indexed_summaries:
        print("\nConclusion: The FTS index seems to be populated correctly. The issue might be with the search query itself.")
    else:
        print("\nConclusion: The FTS index is partially populated or there's a discrepancy.")

    conn.close()

if __name__ == "__main__":
    check_fts_index()
