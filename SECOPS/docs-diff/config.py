# --- Database Configuration ---
DB_NAME = 'doc_content.db'

# --- Crawler Configuration ---
DOC_SOURCES = {
    "Chronicle": "https://cloud.google.com/chronicle/docs/",
    "Security Command Center": "https://cloud.google.com/security-command-center/docs/",
    "GCP Cloud Logging": "https://cloud.google.com/logging/docs/",
    "GCP Cloud Monitoring": "https://cloud.google.com/monitoring/docs",
    "GCP Cloud IDS": "https://docs.cloud.google.com/intrusion-detection-system/docs"
}
EXCLUDED_PATTERNS = [
    "https://cloud.google.com/chronicle/docs/ingestion/default-parsers/",
    "https://cloud.google.com/chronicle/docs/ingestion/parser-list/",
    "https://cloud.google.com/chronicle/docs/reference/rest/",
    "https://cloud.google.com/chronicle/docs/soar/marketplace-integrations/",
    "https://cloud.google.com/security-command-center/docs/reference/rest/",
    "https://cloud.google.com/security-command-center/docs/reference/securityposture/rest/",
    "https://cloud.google.com/security-command-center/docs/reference/security-center-management/rest/",
    "https://cloud.google.com/logging/docs/api/",
    "https://cloud.google.com/logging/docs/audit/api/",
    "%/rest/%"
]
