# GTI Use Case Generator

This script automates the process of generating security use cases by fetching behavioral data from VirusTotal (VT) and ingesting it into Google Chronicle. It searches for malicious files using predefined queries, retrieves their associated EVTX (Windows Event Log) data from sandbox runs, normalizes the timestamps, and sends the logs to a specified Chronicle instance.

## Features

- **Dynamic Querying**: Leverages a `queries.json` file to manage and select complex VirusTotal Intelligence queries by a simple name.
- **Chronicle Ingestion**: Formats and sends logs to the Google Chronicle Ingestion API, correctly handling different log types like Sysmon and PowerShell.
- **Timestamp Normalization**: Updates timestamps in fetched logs to be recent, making them relevant for testing real-time detection rules.
- **Intelligent Chunking**: Automatically splits large sets of logs into payloads that respect the Chronicle API's 1MB size limit.
- **Robust Error Handling**: Includes retry logic with exponential backoff for network requests to Chronicle.
- **GCP Authentication**: Uses Google Cloud's Application Default Credentials (ADC) for secure authentication.

---

## Workflow

The script executes the following steps:

1.  **Initialization**:
    -   Loads VirusTotal queries from the `queries.json` file.
    -   Parses command-line arguments to select a query and other options.
    -   Checks for required environment variables.
    -   Authenticates with Google Cloud and obtains an OAuth2 token.

2.  **VirusTotal Search**:
    -   Executes the selected query against the VirusTotal Intelligence API to find matching file hashes.

3.  **Process First Successful Hash**:
    -   The script iterates through the list of file hashes returned by VT.
    -   For the **first hash** that can be successfully processed, it performs the following actions:
        -   **Fetch Behavior**: Retrieves the raw EVTX data from the specified sandbox behavior report.
        -   **Extract Logs**: Parses the raw XML data to extract individual `<Event>` blocks.
        -   **Update Timestamps**: Sorts the logs chronologically and shifts their timestamps to be recent (defaulting to 10 minutes ago). This ensures the events are fresh for testing detections.
        -   **Group by Log Type**: Classifies each event log (e.g., `WINDOWS_SYSMON`, `POWERSHELL`, `WINEVTLOG`) and groups them.
        -   **Chunk and Ingest**: For each log type group, the script:
            -   Splits the logs into chunks, ensuring each payload is under 1MB.
            -   Constructs a Chronicle API payload.
            -   Sends each chunk to the appropriate Chronicle log importer endpoint.
    -   Once a file hash has been fully processed and all its logs ingested, the script exits successfully.

4.  **Exit**: If the script iterates through all found hashes and fails to process any of them, it exits with an error.

---

## Configuration

### Environment Variables

The following environment variables must be set before running the script:

| Variable                  | Description                                                              |
| ------------------------- | ------------------------------------------------------------------------ |
| `VT_API_KEY`              | **Required.** Your VirusTotal API key.                                   |
| `GCP_PROJECT_ID`          | **Required.** Your Google Cloud Project ID.                              |
| `CUSTOMER_ID`             | **Required.** Your Chronicle Customer ID (UUID).                         |
| `FORWARDER_ID`            | **Required.** The Chronicle Forwarder ID (UUID) to associate logs with.  |
| `SECOPS_LOCATION`         | The Google Cloud region for your Chronicle instance (e.g., `us`, `eu`).    |
| `REQUEST_TIMEOUT_SECONDS` | Timeout for HTTP requests in seconds. Default: `60`.                     |

### `queries.json` File

This file stores the VirusTotal Intelligence queries. You can add as many as you need, each with a unique key. The `--query-name` argument uses these keys.

*Example `queries.json`:*
```json
{
  "gootloader": "entity:file collection:malware--0c0760b0-976d-5331-82e9-bcee24040d39 has:evtx gti_score:80+ tag:long-sleeps",
  "beacon": "entity:file collection:malware--448e822d-8496-5021-88cb-599062f74176 has:evtx gti_score:80+",
  "systembc": "entity:file collection:malware--17784955-af55-5462-877f-feaba0c8d80a has:evtx gti_score:100+ fs:10+ size:1mb+",
  "macros_7d": "(type:doc OR type:docx) tag:macros generated:7d+ (sandbox_name:\"zenbox\") has:evtx gti_score:70+"
}
```

---

## Usage

### Prerequisites

1.  **Python 3**: Ensure you have Python 3 installed.
2.  **Google Cloud SDK**: You must have `gcloud` CLI installed and authenticated. Run the following command to set up Application Default Credentials:
    ```bash
    gcloud auth application-default login
    ```

### Installation

1.  Clone the repository and navigate into the directory.
2.  Create and activate a virtual environment:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
3.  Install the required Python packages:
    ```bash
    pip install -r requirements.txt
    ```

### Execution

Run the script from the command line, specifying the query to use.

**Basic Example:**

This command will run the `gootloader` query defined in `queries.json`.

```bash
python main.py --query-name gootloader
```

**Example with Custom Arguments:**

This command runs the `macros_7d` query, limits the VT search to 10 results, and sets the replayed log timestamps to be 30 minutes in the past.

```bash
python main.py --query-name macros_7d --limit 10 --offset-minutes -30
```

### Command-Line Arguments

| Argument             | Description                                                                 | Default        |
| -------------------- | --------------------------------------------------------------------------- | -------------- |
| `--query-name`       | The name of the query to run, as defined in `queries.json`.                 | `gootloader`   |
| `--limit`            | Maximum number of search results to fetch from VirusTotal.                  | `5`            |
| `--descriptors-only` | If `true`, returns only file descriptors from VT.                           | `true`         |
| `--sandbox-name`     | The sandbox name for behavior reports (case-sensitive).                     | `Zenbox`       |
| `--offset-minutes`   | The time offset in minutes to apply to event timestamps (use negative for past). | `-10`          |
| `--namespace`        | Optional Chronicle namespace for logs.                                      | `""` (empty)   |
| `--use-case`         | Optional `use_case_name` label to tag events with.                          | `evtx_replay`  |
| `--secops-location`  | The Chronicle instance region. Overrides `SECOPS_LOCATION` env var.          | `us`           |
