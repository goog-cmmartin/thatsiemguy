import argparse
import json
import logging
import os
import re
import sys
import urllib.parse
import base64
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

import requests
import google.auth
import google.auth.transport.requests


# --- Configuration from Environment Variables ---
API_KEY = os.environ.get("VT_API_KEY")
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
CUSTOMER_ID = os.environ.get("CUSTOMER_ID")
FORWARDER_ID = os.environ.get("FORWARDER_ID")
SECOPS_LOCATION = os.environ.get("SECOPS_LOCATION")
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", 60))

# --- Basic Logging Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# --- Default Values ---
DEFAULT_LIMIT = '5'
DEFAULT_DESCRIPTORS_ONLY = 'true'
DEFAULT_SANDBOX_NAME = 'Zenbox' # Case sensitive
DEFAULT_OFFSET_MINUTES = -10
DEFAULT_NAMESPACE = ""
DEFAULT_USE_CASE = "evtx_replay"
DEFAULT_SECOPS_LOCATION = 'us'
DEFAULT_BATCH_ID = str(uuid.uuid4())

def load_queries_from_config(filepath: str = "queries.json") -> Dict[str, str]:
    """Loads queries from a JSON configuration file."""
    try:
        with open(filepath, 'r') as f:
            queries = json.load(f)
            logging.info(f"Successfully loaded {len(queries)} queries from {filepath}")
            return queries
    except FileNotFoundError:
        logging.error(f"Configuration file not found at: {filepath}")
        sys.exit(1)
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from the configuration file: {filepath}")
        sys.exit(1)

# --- GCP Authentication ---

def get_gcp_auth_token():
    """
    Obtains a GCP authentication token using Application Default Credentials (ADC).
    """
    try:
        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        credentials, project = google.auth.default(scopes=scopes)
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)
        logging.info("Successfully obtained GCP auth token.")
        return credentials.token
    except Exception as e:
        logging.error(f"Error obtaining GCP auth token. Ensure you have run 'gcloud auth application-default login' or that the service account has the correct permissions. Error: {e}")
        raise

# --- Chronicle Ingestion ---

def prepare_log_entry(
    log_xml: str,
    query: str,
    namespace: Optional[str] = None,
    use_case_name: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Prepares a log entry for ingestion, conditionally adding namespace and use case.

    Args:
        log_xml: The raw XML log string.
        query: The VT query string to include as a label.
        namespace: (Optional) The environment namespace string.
        use_case_name: (Optional) The name of the use case.

    Returns:
        A dictionary formatted for the destination API, or None on error.
    """
    try:
        # It's more reliable to encode the raw XML directly
        json_bytes = log_xml.encode('utf-8')
        base64_bytes = base64.b64encode(json_bytes)
        base64_str = base64_bytes.decode('utf-8')

        # Start with the mandatory parts of the payload
        payload = {
            "data": base64_str
            }

        # 2) Conditionally add the namespace if it was provided
        if namespace:
            payload["environment_namespace"] = namespace

        # 3) Conditionally add the use case name if it was provided
        if use_case_name:
            # FIX: Initialize the 'labels' dictionary if it doesn't exist
            if "labels" not in payload:
                payload["labels"] = {}
            # Now it's safe to add the sub-key
            payload["labels"]["use_case_name"] = {"value": use_case_name}
            payload["labels"]["query"] = {"value": query}
            payload["labels"]["replay_batch_id"] = {"value": DEFAULT_BATCH_ID}
             
        return payload

    except Exception as e:
        logging.error(f"Error preparing log entry: {e}. Original data (first 100 chars): {str(log_xml)[:100]}")
        return None

def split_list_by_size(
    data_list: List[str],
    query: str,
    max_chunk_size: int = 1000000
) -> List[List[Dict[str, Any]]]:
    """
    Splits a list of raw logs into chunks based on final payload size.
    Each raw log is first prepared into its final JSON format.

    Args:
        data_list: The list of raw XML logs to be split.
        query: The query string to pass to the log preparation function.
        max_chunk_size: The target maximum size for each chunk in bytes (default: 1.0MB).

    Returns:
        A list of lists, where each sublist is a chunk of prepared log entries.
    """
    chunks = []
    current_chunk = []
    current_chunk_size = 0

    for item_xml in data_list:
        # Prepare the item into its final JSON format before checking size
        prepared_item = prepare_log_entry(item_xml, query, "SDL", "gti_replay")
        # Estimate size of the JSON string
        item_size = len(json.dumps(prepared_item).encode('utf-8'))

        # If adding the item would exceed the max size, store the current chunk and start a new one.
        if current_chunk and current_chunk_size + item_size > max_chunk_size:
            chunks.append(current_chunk)
            current_chunk = []
            current_chunk_size = 0
        
        current_chunk.append(prepared_item)
        current_chunk_size += item_size

    # Add the last chunk if it's not empty
    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def build_chronicle_payload(
    project_id: str,
    customer_id: str,
    forwarder_id: str,
    chronicle_region: str,
    prepared_log_chunk: List[Optional[Dict[str, Any]]],
) -> Dict[str, Any]:
    return {
        'inline_source': {
            'logs': prepared_log_chunk,
            "forwarder": f"projects/{project_id}/locations/{chronicle_region}/instances/{customer_id}/forwarders/{forwarder_id}"
        }
    }

def send_to_chronicle(
    region: str,
    project_id: str,
    customer_id: str,
    log_type: str,
    gcp_auth_token: str,
    payload: Dict[str, Any]
) -> requests.Response:
    """Sends a payload to Chronicle with a retry mechanism for transient errors."""

    headers = {
        "Authorization": f"Bearer {gcp_auth_token}",
        'Content-Type': 'application/json'
    }
    endpoint = f"https://{region}-chronicle.googleapis.com/v1alpha/projects/{project_id}/locations/{region}/instances/{customer_id}/logTypes/{log_type}/logs:import"

    # --- Retry Logic ---
    retries = 3
    delay = 2  # Start with a 2-second delay

    for attempt in range(retries):
        try:
            payload_size = len(json.dumps(payload))
            num_logs = len(payload.get('inline_source', {}).get('logs', []))
            
            logging.info(f"Sending payload (Attempt {attempt + 1}/{retries}). Size: {payload_size} bytes, Logs: {num_logs}")
            
            submission = requests.post(url=endpoint, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
            submission.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
            
            logging.info(f"Successfully submitted to Chronicle. Status: {submission.status_code}")
            return submission # Exit the function on success

        except requests.exceptions.Timeout as e:
            logging.warning(f"Request timed out: {e}")
        except requests.exceptions.RequestException as e:
            # This catches other connection errors or HTTP error statuses from raise_for_status()
            logging.warning(f"Request failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logging.error(f"Chronicle error response status: {e.response.status_code}, body: {e.response.text[:500]}")

        # If we are here, the request failed. Wait before the next attempt.
        if attempt < retries - 1:
            logging.info(f"Waiting {delay} seconds before retrying...")
            time.sleep(delay)
            delay *= 2  # Double the delay for the next attempt (exponential backoff)
        else:
            logging.error("All retry attempts failed.")
            raise Exception("Failed to send data to Chronicle after multiple retries.")

# --- Core Functions ---

def search_virustotal(
    api_key: str, 
    query: str, 
    limit: str, 
    descriptors_only: str
) -> Optional[Dict[str, Any]]:

    """Searches VirusTotal Intelligence for file hashes based on a query."""
    if not api_key:
        print("Error: VirusTotal API key is not configured. Set the VT_API_KEY environment variable.", file=sys.stderr)
        return None

    encoded_query = urllib.parse.quote(query)
    url = f"https://www.virustotal.com/api/v3/intelligence/search?query={encoded_query}&limit={limit}&descriptors_only={descriptors_only}"
    headers = {"accept": "application/json", "x-apikey": api_key}

    print(f"Executing VirusTotal search with URL: {url}")
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"An error occurred during VirusTotal search: {e}", file=sys.stderr)
        return None

def get_file_behavior(
    api_key: str, 
    file_hash: str, 
    sandbox_name: str
) -> Optional[str]:
    
    """Retrieves the EVTX data from a file's behavior report."""
    if not api_key:
        print("Error: VirusTotal API key is not configured. Set the VT_API_KEY environment variable.", file=sys.stderr)
        return None

    url = f'https://www.virustotal.com/api/v3/file_behaviours/{file_hash}_{sandbox_name}/evtx'
    headers = {"accept": "application/octet-stream", "x-apikey": api_key}

    print(f"Fetching EVTX data for file hash: {file_hash} from sandbox: {sandbox_name}")
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"An error occurred while fetching file behavior: {e}", file=sys.stderr)
        return None

# --- Log Processing Functions ---

def extract_event_logs(
    evtx_data: str
) -> List[str]:    

    """
    Parses raw EVTX XML data to extract each full <Event> block.

    Args:
        evtx_data: A string containing one or more <Event> XML blocks.

    Returns:
        A list of strings, where each string is a full <Event>...</Event> block.
    """
    if not evtx_data:
        return []
    # The pattern is non-greedy (.*?) to ensure it stops at the first </Event>.
    # re.DOTALL allows '.' to match newlines, crucial for multi-line XML blocks.
    pattern = r"<Event\s.*?<\/Event>"
    regex = re.compile(pattern, re.DOTALL)
    return regex.findall(evtx_data)

def replace_computer_name(logs: List[str], new_computer_name: str) -> List[str]:
    """
    Replaces all occurrences of the original computer name with a new one.
    The original computer name is determined from the <Computer> tag in each log.

    Args:
        logs: A list of log strings.
        new_computer_name: The new computer name to use.

    Returns:
        A new list of log strings with the computer name replaced.
    """
    updated_logs = []
    for log in logs:
        # Find the original computer name from the <Computer> tag
        match = re.search(r"<Computer>(.*?)</Computer>", log, re.DOTALL)
        if match:
            original_computer_name = match.group(1).strip()
            # Replace all occurrences of the original name with the new one
            if original_computer_name:
                updated_log = log.replace(original_computer_name, new_computer_name)
                updated_logs.append(updated_log)
            else:
                updated_logs.append(log) # Append unmodified if original name is empty
        else:
            # If no <Computer> tag is found, append the log unmodified
            updated_logs.append(log)
    return updated_logs

def sort_logs(
    logs: List[str]
) -> List[str]:
    """
    Sorts a list of event log strings based on their SystemTime timestamp.

    Args:
        logs: A list of log strings.

    Returns:
        A new list of log strings sorted chronologically.
    """
    def get_timestamp(log_entry):
        # Extracts the timestamp for use as a sort key.
        try:
            timestamp_str = log_entry.split('SystemTime="')[1].split('"')[0]
            # Handle fractional seconds of varying length
            if '.' in timestamp_str:
                ts_part, frac_part = timestamp_str.rsplit('.', 1)
                frac_part = frac_part.replace('Z', '')
                frac_part = frac_part[:6] # Truncate to microseconds
                timestamp_str = f"{ts_part}.{frac_part}Z"
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except (IndexError, ValueError):
            # If a log entry is malformed, return a very old date to sort it first.
            return datetime.min.replace(tzinfo=None)

    return sorted(logs, key=get_timestamp)


def update_log_times(
    logs: List[str], 
    offset_minutes: int = -60
) -> List[str]:
    """
    Updates the timestamps in a list of logs to make them more recent.

    Args:
        logs: A list of log strings, each containing a "TimeCreated SystemTime" entry.
        offset_minutes: An offset in minutes to apply relative to the current time.

    Returns:
        A new list of log strings with updated timestamps.
    """
    if not logs:
        return []

    logs = sort_logs(logs)

    # Get the last log entry and extract its timestamp
    last_log = logs[-1]
    last_timestamp_str = last_log.split('SystemTime="')[1].split('"')[0]
    last_timestamp = datetime.fromisoformat(last_timestamp_str.replace('Z', '+00:00'))

    # Calculate the new "now" timestamp with the desired offset
    now = datetime.now(last_timestamp.tzinfo) + timedelta(minutes=offset_minutes)

    # Calculate the time difference to shift all logs
    time_delta = now - last_timestamp

    updated_logs = []
    for log in logs:
        updated_log = log
        # --- Update SystemTime (standard for all events) ---
        try:
            timestamp_str = log.split('SystemTime="')[1].split('"')[0]
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            new_timestamp = timestamp + time_delta
            new_timestamp_str = new_timestamp.isoformat(timespec='microseconds').replace('+00:00', 'Z')
            updated_log = updated_log.replace(timestamp_str, new_timestamp_str)
        except (IndexError, ValueError):
            # Skip timestamp update if format is unexpected
            pass

        # --- Update UtcTime (for Sysmon events) ---
        if '<Data Name="UtcTime">' in log:
            try:
                sysmon_timestamp_str = log.split('<Data Name="UtcTime">')[1].split('<')[0]
                sysmon_timestamp = datetime.strptime(sysmon_timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
                new_sysmon_timestamp = sysmon_timestamp + time_delta
                new_sysmon_timestamp_str = new_sysmon_timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")
                updated_log = updated_log.replace(sysmon_timestamp_str, new_sysmon_timestamp_str)
            except (IndexError, ValueError):
                # Skip UtcTime update if format is unexpected
                pass
        
        updated_logs.append(updated_log)

    return updated_logs


def check_evtx_type(evtx: str) -> str:
    """
    Checks a string for specific identifiers and returns a corresponding type.

    Args:
        evtx: The string to check.

    Returns:
        The detected Chronicle Ingestion Label based upon the Channel.
        Returns WINEVTLOG if no exact match is found.
    """
    # Sysmon (checked first as it's specific)
    if "Microsoft-Windows-Sysmon/Operational" in evtx:
        return "WINDOWS_SYSMON"
    # PowerShell
    elif "PowerShell" in evtx: # More general check for PowerShell logs
        return "POWERSHELL"
    # Security, System, Application, Setup (all map to WINEVTLOG)
    elif "Microsoft-Windows-Security-Auditing" in evtx:
        return "WINEVTLOG"
    elif "<Channel>System</Channel>" in evtx:
        return "WINEVTLOG"
    elif "<Channel>Application</Channel>" in evtx:
        return "WINEVTLOG"
    elif "<Channel>Setup</Channel>" in evtx:
        return "WINEVTLOG"
    # Catch-all
    else:
        return "WINEVTLOG"

def process_file_hash(
    file_hash: str, 
    args: argparse.Namespace, 
    gcp_auth_token: str,
    query: str
) -> bool:
    """Fetches, processes, and sends logs for a single file hash. Returns True on success."""
    evtx_data = get_file_behavior(API_KEY, file_hash, args.sandbox_name)
    if not evtx_data:
        logging.warning(f"Could not retrieve EVTX data for hash: {file_hash}.")
        return False

    logging.info(f"--- Processing EVTX Data for {file_hash} ---")

    event_logs = extract_event_logs(evtx_data)

    if args.computer_name:
        logging.info(f"Replacing computer name in logs with '{args.computer_name}'")
        event_logs = replace_computer_name(event_logs, args.computer_name)

    updated_logs = update_log_times(event_logs, offset_minutes=args.offset_minutes)
    log_types = list(map(check_evtx_type, updated_logs))

    grouped_logs = {}
    for log, log_type in zip(updated_logs, log_types):
        grouped_logs.setdefault(log_type, []).append(log)

    for log_type, logs in grouped_logs.items():
        chunks = split_list_by_size(logs, query)
        logging.info(f"Split {len(logs)} '{log_type}' logs into {len(chunks)} chunk(s).")

        for i, prepared_chunk in enumerate(chunks):
            logging.info(f"Processing chunk {i + 1}/{len(chunks)} for log_type '{log_type}'...")

            payload = build_chronicle_payload(
                GCP_PROJECT_ID, CUSTOMER_ID, FORWARDER_ID,
                args.secops_location, prepared_chunk
            )

            try:
                send_to_chronicle(
                    args.secops_location, GCP_PROJECT_ID, CUSTOMER_ID,
                    log_type, gcp_auth_token, payload
                )
                success_message = f"Successfully sent chunk {i + 1}/{len(chunks)}, containing {len(prepared_chunk)} log entries."
                logging.info(success_message)
                time.sleep(1)

            except Exception as e:
                logging.error(f"Failed to process chunk {i + 1}/{len(chunks)} for file hash {file_hash}. Error: {e}")
                return False

    logging.info(f"--- Finished Processing {file_hash} ---")
    return True

def main():
    """Main function to orchestrate the script's execution."""
    # 1. Load queries from the external file FIRST
    queries = load_queries_from_config()
    default_query_name = "gootloader" # Choose a default from your JSON keys

    # 2. Update the parser
    parser = argparse.ArgumentParser(description="Search VirusTotal, retrieve file behavior logs, update timestamps, and classify.")
    parser.add_argument(
        "--query-name",
        default=default_query_name,
        choices=queries.keys(), # This cleverly limits choices to only the names you defined!
        help="The name of the query to run, as defined in queries.json."
    )
    parser.add_argument("--limit", default=os.environ.get("VT_LIMIT", DEFAULT_LIMIT), help="Maximum number of search results.")
    parser.add_argument("--descriptors-only", default=os.environ.get("VT_DESCRIPTORS_ONLY", DEFAULT_DESCRIPTORS_ONLY), help="Return only file descriptors.")
    parser.add_argument("--sandbox-name", default=os.environ.get("VT_SANDBOX_NAME", DEFAULT_SANDBOX_NAME), help="The sandbox name for behavior reports.")
    parser.add_argument("--offset-minutes", type=int, default=os.environ.get("VT_OFFSET_MINUTES", DEFAULT_OFFSET_MINUTES), help="Offset in minutes to apply to event timestamps.")
    parser.add_argument("--computer-name", default=None, help="Optional. Replace the hostname in the event logs with this value.")
    parser.add_argument("--namespace", default=os.environ.get("NAMESPACE", DEFAULT_NAMESPACE), help="Optional, SecOps NAMESPACE for logs.")
    parser.add_argument("--use-case", default=os.environ.get("USE_CASE", DEFAULT_USE_CASE), help="Optional, custom ingestion_label to tag events with.")
    parser.add_argument("--secops-location", default=os.environ.get("SECOPS_LOCATION", DEFAULT_SECOPS_LOCATION))
    args = parser.parse_args()

    # 3. Get the actual query string using the name provided by the user
    query_to_run = queries[args.query_name]
    logging.info(f"Running selected query '{args.query_name}': {query_to_run}")

    # --- Step 0: Pre-flight checks and Authentication ---
    if not all([GCP_PROJECT_ID, CUSTOMER_ID, FORWARDER_ID]):
        logging.error("One or more required environment variables are not set: GCP_PROJECT_ID, CUSTOMER_ID, FORWARDER_ID. Exiting.")
        sys.exit(1)

    gcp_auth_token = get_gcp_auth_token()

    # --- Step 1: Search for files ---
    # 4. Use the selected query string in your search call
    search_result = search_virustotal(API_KEY, query_to_run, args.limit, args.descriptors_only)
    if not search_result or not search_result.get("data"):
        print("No files found or an error occurred during search. Exiting.")
        sys.exit(1)

    print(f"Successfully found {len(search_result['data'])} potential file matches.")

    # --- Step 2: Process each unique found file ---
    successful_processing = False
    for item in search_result["data"]:
        file_hash = item.get("id")
        if not file_hash:
            logging.warning(f"Skipping item due to missing 'id': {item}")
            continue

        if process_file_hash(file_hash, args, gcp_auth_token, query_to_run):
            successful_processing = True
            break  # Exit the loop after successfully processing one file

    if not successful_processing:
        logging.error("Failed to retrieve and process EVTX data for all candidate hashes.")
        sys.exit(1)


if __name__ == "__main__":
    main()
