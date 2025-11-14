# SOAR Agentic Tagging Tools

This repository contains a collection of Python scripts designed to interact with Google Chronicle and Siemplify SOAR platforms. These tools facilitate automated investigation processes, including fetching investigations, retrieving alert details, correlating with Siemplify cases, and tagging cases within Siemplify.

## Project Structure

```
.
├── .env                 # Environment variables for API keys and configuration
├── .gitignore           # Specifies intentionally untracked files to ignore
├── README.md            # This file
├── requirements.txt     # Python dependencies
├── search_cases.py      # Script to search for cases in Siemplify
└── get_soar_case_ids.py # Script to fetch Chronicle alerts, resolve Siemplify Case IDs, and tag them
```

## Prerequisites

Before you begin, ensure you have the following installed:

*   **Python 3.x**: (e.g., Python 3.9+)
*   **Google Cloud CLI**: Required for setting up Google Application Default Credentials (ADC). Follow the installation guide [here](https://cloud.google.com/sdk/docs/install).

## Setup

1.  **Clone the repository (or copy manually)**:
    Since you'll be copying the content manually, ensure all the files from this project (including `.env`, `.gitignore`, `requirements.txt`, and all `.py` scripts) are in your desired Git folder.

2.  **Set up a Virtual Environment**:
    It's highly recommended to use a virtual environment to manage project dependencies.
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies**:
    Install all required Python packages using `pip`:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Google Application Default Credentials (ADC) Setup**:
    The `get_soar_case_ids.py` script authenticates using Google Application Default Credentials.
    Authenticate your environment by running:
    ```bash
    gcloud auth application-default login
    ```
    Follow the browser prompts to log in with a Google account that has the necessary permissions to access Google Chronicle.

## Configuration (`.env` file)

The `.env` file stores sensitive information and configuration parameters. **Do not commit this file to your Git repository.** It is already included in `.gitignore`.

Edit the `.env` file to include your specific credentials and platform details:

```dotenv
# Siemplify API Configuration
SIEMPLIFY_HOSTNAME=your_siemplify_hostname.com      # e.g., preview-americas-sdl.siemplify-soar.com
SIEMPLIFY_APP_KEY=your_siemplify_app_key             # Your Siemplify AppKey

# Google Chronicle API Configuration
CHRONICLE_REGION=us                                  # e.g., us, europe, asia-southeast1
CHRONICLE_PROJECT=your_gcp_project_id                # Your Google Cloud Project ID
CHRONICLE_LOCATION=your_gcp_location                 # e.g., us-central1, europe-west1
CHRONICLE_INSTANCE=your_chronicle_instance_id        # Your Chronicle instance ID (usually a UUID)
```

## Usage

Ensure your virtual environment is active (`source venv/bin/activate`) before running any of the scripts.

### 1. `search_cases.py`

This script searches for cases in Siemplify based on tags and a time range.

```bash
python3 search_cases.py --help
```

**Examples**:

*   **Search for cases with tag "VT" in the last 24 hours (using .env for hostname/API key):**
    ```bash
    python3 search_cases.py --tags VT
    ```

*   **Search for cases with tags "VT" and "Malware" within a specific time range:**
    ```bash
    python3 search_cases.py --tags "VT" "Malware" --start_time "2025-11-13T10:00:00" --end_time "2025-11-14T10:00:00"
    ```

### 2. `get_soar_case_ids.py`

This script is an advanced workflow that:
1.  Fetches investigations from Google Chronicle.
2.  Extracts alert IDs from these investigations.
3.  For each alert, retrieves its details, including `caseName`, `ruleName`, and `alertState`.
4.  Uses the `caseName` to find the corresponding Siemplify SOAR Case ID.
5.  Adds a specified tag to the identified Siemplify SOAR case.

```bash
python3 get_soar_case_ids.py --help
```

**Examples**:

*   **Process all found detection IDs and add the tag "Triage Agent":**
    ```bash
    python3 get_soar_case_ids.py --tag "Triage Agent"
    ```

*   **Process the first 5 detection IDs and add the tag "AutomatedReview":**
    ```bash
    python3 get_soar_case_ids.py --limit 5 --tag "AutomatedReview"
    ```

*   **Process with debug output (shows full alert payload when `caseName` is missing):**
    ```bash
    python3 get_soar_case_ids.py --limit 1 --tag "Testing" --debug
    ```

## Troubleshooting

*   **`NameError: name 'argparse' is not defined`**: Ensure `import argparse` is present at the top of the script. This has been addressed in the latest script versions.
*   **`SyntaxError: invalid syntax` / `IndentationError`**: These are often caused by incorrect Python code formatting, especially with `if`/`else` blocks. The scripts have been reviewed for these issues. Ensure you are using a Python-aware editor that highlights such errors.
*   **`Error adding tag... Expecting value: line 1 column 1 (char 0)`**: This indicates an empty (but often successful) response from an API endpoint that the script tried to parse as JSON. The `add_case_tag` function has been updated to handle this gracefully.
*   **`Rate limit exceeded (429)`**: The `get_soar_case_ids.py` script (and its underlying `make_api_request` function) implements exponential backoff with jitter to automatically retry requests when encountering `429 Too Many Requests` errors. This should mitigate most rate-limiting issues.
*   **Missing Environment Variables**: Ensure all required variables (`SIEMPLIFY_HOSTNAME`, `SIEMPLIFY_APP_KEY`, `CHRONICLE_REGION`, `CHRONICLE_PROJECT`, `CHRONICLE_LOCATION`, `CHRONICLE_INSTANCE`) are correctly set in your `.env` file and that you've run `source venv/bin/activate` or `load_dotenv()` within the script.

---
