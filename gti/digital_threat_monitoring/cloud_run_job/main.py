import os
import yaml  # For local .env.yml parsing
import requests
import urllib.parse
import json
import base64
import sys
import time
import logging
from datetime import datetime, timezone, timedelta

# Import Google Cloud libraries
from google.cloud import secretmanager
import google.auth
import google.auth.transport.requests

# Import Flask for HTTP trigger if deployed as a Cloud Run service
from flask import Flask, request as flask_request
import re
import random  # For jitter
from urllib.parse import urlparse, parse_qs, urlencode


# --- Load Environment Variables from YAML for LOCAL DEVELOPMENT ---
def load_env_from_yaml_for_local(env_file_path=".env.local.yml"):
    # K_SERVICE is an environment variable automatically set in Cloud Run.
    # Only load local .yml if K_SERVICE is not set (i.e., not running in Cloud Run).
    if not os.environ.get("K_SERVICE") and os.path.exists(env_file_path):
        try:
            with open(env_file_path, 'r') as stream:
                env_config = yaml.safe_load(stream)
            if env_config:
                for key, value in env_config.items():
                    if os.environ.get(key) is None:  # Only set if not already in actual env
                        os.environ[key] = str(value)  # Ensure value is string
                # Re-initialize logging if LOG_LEVEL was set in the YAML
                if 'LOG_LEVEL' in env_config:
                    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(),
                                        format='%(asctime)s - %(levelname)s - %(message)s')
                logging.info(f"LOCAL DEV: Loaded environment variables from {env_file_path}")
        except yaml.YAMLError as e:
            logging.error(f"LOCAL DEV: Error parsing {env_file_path}: {e}")
        except Exception as e:
            logging.error(f"LOCAL DEV: Error loading {env_file_path}: {e}")
    elif not os.environ.get("K_SERVICE"):
        logging.info(f"LOCAL DEV: {env_file_path} not found. Using system environment variables.")


# Load local env vars (if any) before configuring logging and other constants.
load_env_from_yaml_for_local()
# --- End of YAML loading section for local dev ---

# Configure logging (uses LOG_LEVEL from env vars, which might have been set by local YAML)
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(),
                    format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration from Environment Variables ---
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
VT_API_KEY_SECRET_NAME = os.environ.get("VT_API_KEY_SECRET_NAME")
VT_API_KEY_SECRET_VERSION = os.environ.get("VT_API_KEY_SECRET_VERSION", "latest")

CHRONICLE_CUSTOMER_ID = os.environ.get("CHRONICLE_CUSTOMER_ID")
CHRONICLE_FORWARDER_ID = os.environ.get("CHRONICLE_FORWARDER_ID")
CHRONICLE_LOG_TYPE = os.environ.get("CHRONICLE_LOG_TYPE", "GTI_CVE")
CHRONICLE_REGION = os.environ.get("CHRONICLE_REGION", "us")

NAMESPACE = os.environ.get("NAMESPACE", "SDL")
USE_CASE_NAME = os.environ.get("USE_CASE_NAME", "mandiant_dtm_import")

# New Environment Variables for the updated script
VT_BASE_URL = os.environ.get("VT_BASE_URL", "https://www.virustotal.com/api/v3/dtm/alerts")  # Default VT Alerts URL
INITIAL_SINCE = os.environ.get("INITIAL_SINCE", "-15m")  # e.g., -60m or -1h
INITIAL_SIZE = int(os.environ.get("INITIAL_SIZE", "25"))

MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "5"))
BASE_BACKOFF_SECONDS = int(os.environ.get("BASE_BACKOFF_SECONDS", "1"))

MAX_CHUNK_SIZE_BYTES = int(os.environ.get("MAX_CHUNK_SIZE_BYTES", 3200000))
ABSOLUTE_MAX_CHUNK_SIZE_BYTES = int(os.environ.get("ABSOLUTE_MAX_CHUNK_SIZE_BYTES", 4000000))
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", 60))

# --- Helper Functions ---
def get_secret(project_id, secret_id, version_id="latest"):
    """Retrieves a secret from Google Cloud Secret Manager."""
    if not project_id or not secret_id:
        logging.error("GCP_PROJECT_ID and secret_id must be set to retrieve a secret.")
        raise ValueError("Project ID or Secret ID not configured for get_secret.")
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
        response = client.access_secret_version(request={"name": name})
        logging.info(f"Successfully retrieved secret: {secret_id}")
        # Decode and then strip whitespace (including newlines)
        return response.payload.data.decode("UTF-8").strip()
    except Exception as e:
        logging.error(f"Error retrieving secret {secret_id} from project {project_id}: {e}")
        raise


def get_gcp_auth_token():
    """Authenticates using default credentials, returning an OAuth2 access token."""
    try:
        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        credentials, project = google.auth.default(scopes=scopes)
        request = google.auth.transport.requests.Request()
        credentials.refresh(request)
        logging.info("Successfully obtained GCP auth token.")
        return credentials.token
    except Exception as e:
        logging.error(f"Error obtaining GCP auth token: {e}")
        raise


def get_current_utc_timestamp_str():
    """Returns the current UTC datetime as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def prepare_log_entry(log_message_dict, namespace, use_case_name):
    try:
        log_message_json_str = json.dumps(log_message_dict)
        json_bytes = log_message_json_str.encode('utf-8')
        base64_bytes = base64.b64encode(json_bytes)
        base64_str = base64_bytes.decode('utf-8')
        return {
            "data": base64_str,
            "environment_namespace": namespace,
            "labels": {
                "use_case_name": {"value": use_case_name},
                "retrieval_timestamp_utc": {"value": get_current_utc_timestamp_str()}
            }
        }
    except Exception as e:
        logging.error(f"Error preparing log entry: {e}. Original data (first 100 chars): {str(log_message_dict)[:100]}")
        return None


def split_list_by_size(data_list, namespace, use_case_name,
                       max_chunk_size=MAX_CHUNK_SIZE_BYTES,
                       max_limit=ABSOLUTE_MAX_CHUNK_SIZE_BYTES):
    chunks = []
    current_chunk_prepared_items = []
    current_chunk_estimated_size = 0
    forwarder_string = f"projects/{GCP_PROJECT_ID}/locations/{CHRONICLE_REGION}/instances/{CHRONICLE_CUSTOMER_ID}/forwarders/{CHRONICLE_FORWARDER_ID}"
    payload_overhead = len(json.dumps({'inline_source': {'logs': [], "forwarder": forwarder_string}}).encode('utf-8'))

    for item_dict in data_list:
        prepared_item = prepare_log_entry(item_dict, namespace, use_case_name)
        if prepared_item is None:
            logging.warning(f"Skipping item due to preparation error: {item_dict.get('id', 'Unknown ID')}")
            continue
        item_size = len(json.dumps(prepared_item).encode('utf-8')) + 1
        if current_chunk_prepared_items and \
           (current_chunk_estimated_size + item_size + payload_overhead > max_limit or
            current_chunk_estimated_size + item_size + payload_overhead > max_chunk_size):
            chunks.append(current_chunk_prepared_items)
            logging.info(
                f"Chunk created. Size: ~{current_chunk_estimated_size + payload_overhead} bytes, Items: {len(current_chunk_prepared_items)}")
            current_chunk_prepared_items = []
            current_chunk_estimated_size = 0
        if not current_chunk_prepared_items and item_size + payload_overhead > max_chunk_size:
            if item_size + payload_overhead > max_limit:
                logging.error(
                    f"Single item too large after preparation: {item_size + payload_overhead} bytes. Item ID (if available): {item_dict.get('id')}. Skipping.")
                continue
            else:
                chunks.append([prepared_item])
                logging.info(f"Single large item chunked. Size: ~{item_size + payload_overhead} bytes, Items: 1")
                continue
        current_chunk_prepared_items.append(prepared_item)
        current_chunk_estimated_size += item_size
    if current_chunk_prepared_items:
        chunks.append(current_chunk_prepared_items)
        logging.info(
            f"Final chunk added. Size: ~{current_chunk_estimated_size + payload_overhead} bytes, Items: {len(current_chunk_prepared_items)}")
    return chunks


def build_chronicle_payload(project_id, customer_id, forwarder_id, chronicle_region, prepared_log_chunk):
    return {
        'inline_source': {
            'logs': prepared_log_chunk,
            "forwarder": f"projects/{project_id}/locations/{chronicle_region}/instances/{customer_id}/forwarders/{forwarder_id}"
        }
    }


def send_to_chronicle(region, project_id, customer_id, log_type, gcp_auth_token, payload):
    headers = {
        "Authorization": f"Bearer {gcp_auth_token}",
        'Content-Type': 'application/json'
    }
    endpoint = f"https://{region}-chronicle.googleapis.com/v1alpha/projects/{project_id}/locations/{region}/instances/{customer_id}/logTypes/{log_type}/logs:import"
    try:
        payload_size = len(json.dumps(payload))
        num_logs = len(payload.get('inline_source', {}).get('logs', []))
        logging.info(f"Sending payload to Chronicle. Size: {payload_size} bytes, Log entries: {num_logs}")
        submission = requests.post(url=endpoint, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        submission.raise_for_status()
        logging.info(f"Successfully submitted to Chronicle. Response: {submission.status_code}")
        return submission
    except requests.exceptions.RequestException as e:
        logging.error(f"Error sending to Chronicle: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logging.error(f"Chronicle error response status: {e.response.status_code}, body: {e.response.text[:500]}")
        raise


def _parse_offset_to_timedelta(offset_str: str) -> timedelta:
    """
    Parses an offset string (e.g., "-1d", "+30m", "2h") into a timedelta object.
    Also handles "0" for no offset.
    """
    if not offset_str or offset_str == "0":  # Handles empty string or "0" as no offset
        return timedelta()

    # Regex to capture:
    # 1. Optional sign (+ or -) -> group 1
    # 2. Value (digits) -> group 2
    # 3. Unit (h, m, d, w) -> group 3
    # Allows for formats like: "1d", "+1d", "-1d"
    match = re.fullmatch(r"([+-]?)(\d+)([hmdw])", offset_str)

    if not match:
        raise ValueError(
            f"Invalid offset format: '{offset_str}'. "
            "Expected format like '+1h', '-30m', '1d', '2w', or an integer for minutes."
        )

    sign_str, value_str, unit = match.groups()
    value = int(value_str)

    if sign_str == "-":
        value = -value
    # If sign_str is "" (e.g., "30m"), value remains positive, which is correct.

    if unit == "m":  # minutes
        return timedelta(minutes=value)
    elif unit == "h":  # hours
        return timedelta(hours=value)
    elif unit == "d":  # days
        return timedelta(days=value)
    elif unit == "w":  # weeks
        return timedelta(weeks=value)
    else:
        # This case should ideally not be reached if regex is comprehensive for h,m,d,w
        raise ValueError(f"Unknown time unit: {unit}")


def generate_timestamp(offset_expr="0m"):
    """
    Generates a timestamp in the format YYYY-MM-DDTHH:mm:ss.SSSZ (see note on format),
    considering a flexible offset expression.

    Args:
        offset_expr (str or int, optional): The offset expression.
            If string: e.g., "-1d" (1 day ago), "+30m" (30 minutes from now),
                         "2h" (2 hours from now), "1w" (1 week from now).
                         Defaults to "0m" (no offset). "0" also means no offset.
            If int: Interpreted as minutes (e.g., 30 means +30 minutes, -10 means -10 minutes).
                    0 means no offset.

    Returns:
        str: The generated timestamp string.

    Note on timestamp format:
    The original format string "%Y-%m-%dT%H:%M:%S.%fZ" might literally produce ".fZ" at the end.
    If you intend to have milliseconds (e.g., ".123Z"), you might need to format it as:
    timestamp_val.strftime("%Y-%m-%dT%H:%M:%S.") + f"{timestamp_val.microsecond // 1000:03d}Z"
    This solution retains the original strftime call as per the provided script.
    """
    # Imports are typically at the top of the file, but kept here to match original function structure.
    # from datetime import datetime, timedelta # Not needed here if already imported globally

    # Get the current UTC time
    now = datetime.utcnow()

    # Determine the timedelta based on the offset_expr
    time_offset = timedelta()  # Default to no offset

    if isinstance(offset_expr, str):
        time_offset = _parse_offset_to_timedelta(offset_expr)
    elif isinstance(offset_expr, int):
        # Interpret integer as minutes, consistent with original function's behavior for non-zero
        # and allowing "Xm" format for integers via the parser
        if offset_expr == 0:
            time_offset = timedelta()  # No offset
        else:
            # Convert integer to "Xm" string format and parse
            time_offset = _parse_offset_to_timedelta(f"{offset_expr}m")
    else:
        raise TypeError(
            f"offset_expr must be a string (e.g., '-1d', '+30m') or an integer (for minutes). "
            f"Got type: {type(offset_expr)}"
        )

    # Apply the offset
    timestamp_val = now + time_offset

    # Format the timestamp string (using the original format string from your script)
    timestamp_str = timestamp_val.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    return timestamp_str


def parse_next_link_params(headers):
    """
    Parses the Link header, extracts the query parameters from the rel="next" URL.
    Returns a dictionary of parameters if a next link is found, otherwise None.
    """
    link_header = headers.get('Link')
    if link_header:
        match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
        if match:
            next_url_from_header = match.group(1)
            # Parse the URL from the header to extract its query parameters
            parsed_url = urlparse(next_url_from_header)
            query_params = parse_qs(parsed_url.query)
            # parse_qs returns lists for values, e.g. {'size': ['10']}. Convert to single values.
            return {k: v[0] if len(v) == 1 else v for k, v in query_params.items()}
    return None


def clean_and_sort_data(data):
    """
    Recursively sorts dictionary keys and removes items that are None,
    or become empty strings, lists, or dictionaries after cleaning.
    Booleans and numbers (including 0) are preserved.
    """
    if isinstance(data, dict):
        new_dict = {}
        # Iterate over sorted keys of the original dictionary
        for key in sorted(data.keys()):
            value = data[key]
            cleaned_value = clean_and_sort_data(value)  # Recursively clean the value

            # Check if the *cleaned* value should be kept
            if cleaned_value is not None:
                # If it's a collection (str, list, dict), keep if non-empty
                if isinstance(cleaned_value, (str, list, dict)):
                    if bool(cleaned_value):  # bool('')==False, bool([])==False, bool({})==False
                        new_dict[key] = cleaned_value
                # Otherwise (int, float, bool etc.), always keep (as None was already filtered)
                else:
                    new_dict[key] = cleaned_value
        return new_dict  # This dict might be empty if all its cleaned values were "empty"
    elif isinstance(data, list):
        new_list = []
        for item in data:
            cleaned_item = clean_and_sort_data(item)  # Recursively clean the item

            # Check if the *cleaned* item should be kept in the list
            if cleaned_item is not None:
                if isinstance(cleaned_item, (str, list, dict)):
                    if bool(cleaned_item):
                        new_list.append(cleaned_item)
                else:
                    new_list.append(cleaned_item)
        return new_list  # This list might be empty
    else:
        # Base case: non-collection types (numbers, booleans, or strings/items that are not empty)
        return data


# --- Main Handler Logic ---
def main_job_handler():
    """Main function to fetch data from VirusTotal and send to Chronicle."""
    # Validate essential configuration first
    required_env_vars = [
        "GCP_PROJECT_ID", "VT_API_KEY_SECRET_NAME", "CHRONICLE_CUSTOMER_ID",
        "CHRONICLE_LOG_TYPE", "CHRONICLE_REGION", "VT_BASE_URL"
    ]
    missing_vars = [var for var in required_env_vars if not globals().get(var)]
    if missing_vars:
        msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logging.error(msg)
        raise ValueError(msg)

    try:
        logging.info("Starting VirusTotal Alerts to Chronicle ETL process...")
        vt_api_key = get_secret(GCP_PROJECT_ID, VT_API_KEY_SECRET_NAME, VT_API_KEY_SECRET_VERSION)
        gcp_auth_token = get_gcp_auth_token()

        # --- Initial Request Setup ---
        base_url = VT_BASE_URL
        headers = {
            "accept": "application/json",
            "x-apikey": vt_api_key
        }
        # Parameters for the *initial* request ONLY
        current_params = {
            "since": generate_timestamp(INITIAL_SINCE),  # RFC3339 for the last 60 minutes
            "size": str(INITIAL_SIZE),
        }

        page_count = 0
        all_results = []  # Optional: to store all results from all pages
        keep_fetching = True

        # --- Main Loop ---
        while keep_fetching:
            page_count += 1
            current_retries = 0

            while current_retries <= MAX_RETRIES:
                query_string = urlencode(current_params)
                logging.info(
                    f"Fetching page {page_count} (Attempt {current_retries + 1}/{MAX_RETRIES + 1}): {base_url}?{query_string}")
                response = None

                try:
                    response = requests.get(base_url, headers=headers, params=current_params)
                    response.raise_for_status()

                    logging.info(f"Status Code: {response.status_code}")

                    # 1. Get raw JSON data from the current page
                    raw_page_json = response.json()

                    # 2. Determine which part of the JSON contains the list of items
                    items_to_process_raw = None
                    collection_key = None

                    if 'data' in raw_page_json:
                        items_to_process_raw = raw_page_json['data']
                        collection_key = 'data'
                    elif 'alerts' in raw_page_json:  # As per your API context
                        items_to_process_raw = raw_page_json['alerts']
                        collection_key = 'alerts'

                    if items_to_process_raw is not None:
                        if isinstance(items_to_process_raw, list):
                            logging.info(f"Found {len(items_to_process_raw)} raw items in '{collection_key}' on this page.")
                            # Clean each item in the list and only add if it's not empty after cleaning
                            cleaned_items_for_page = []
                            for raw_item in items_to_process_raw:
                                cleaned_item = clean_and_sort_data(raw_item)
                                if cleaned_item:  # Add if the cleaned item is not an empty dict/list
                                    # Secondary API call
                                    monitor_id = cleaned_item.get("monitor_id")
                                    if monitor_id:
                                        monitor_url = f"https://www.virustotal.com/api/v3/dtm/monitors/{monitor_id}"
                                        try:
                                            monitor_response = requests.get(monitor_url, headers=headers)
                                            monitor_response.raise_for_status()
                                            monitor_data = monitor_response.json()
                                            cleaned_item["monitor"] = monitor_data
                                        except requests.exceptions.RequestException as e:
                                            logging.error(f"Error fetching monitor data for ID {monitor_id}: {e}")
                                            # Decide how to handle errors: skip, add with error, etc.
                                            # For now, we'll skip adding the "monitor" key if there's an error.
                                    else:
                                        logging.warning(f"No 'monitor_id' found in item: {cleaned_item.get('id', 'Unknown ID')}")
                                    cleaned_items_for_page.append(cleaned_item)
                            all_results.extend(cleaned_items_for_page)
                            logging.info(f"Added {len(cleaned_items_for_page)} cleaned items to results.")
                        elif isinstance(items_to_process_raw, dict):  # If the key contains a single item dict
                            logging.info(f"Found a single raw item dictionary in '{collection_key}'.")
                            cleaned_item = clean_and_sort_data(items_to_process_raw)
                            if cleaned_item:  # Add if not empty
                                # Secondary API call (same logic as above, but for a single item)
                                monitor_id = cleaned_item.get("monitor_id")
                                if monitor_id:
                                    monitor_url = f"https://www.virustotal.com/api/v3/dtm/monitors/{monitor_id}"
                                    try:
                                        monitor_response = requests.get(monitor_url, headers=headers)
                                        monitor_response.raise_for_status()
                                        monitor_data = monitor_response.json()
                                        cleaned_item["monitor"] = monitor_data
                                    except requests.exceptions.RequestException as e:
                                        logging.error(f"Error fetching monitor data for ID {monitor_id}: {e}")
                                else:
                                    logging.warning(f"No 'monitor_id' found in item: {cleaned_item.get('id', 'Unknown ID')}")
                                all_results.append(cleaned_item)
                                logging.info("Added 1 cleaned item to results.")
                        else:
                            logging.warning(f"Content of '{collection_key}' is not a list or dict: {type(items_to_process_raw)}")
                    else:
                        # If no 'data' or 'alerts', maybe the whole JSON is one item or an error structure
                        # For now, let's try cleaning the whole JSON if it's a dict and adding if non-empty
                        logging.info("No 'data' or 'alerts' collection key found. Attempting to clean entire JSON response.")
                        if isinstance(raw_page_json, dict):
                            cleaned_response_item = clean_and_sort_data(raw_page_json)
                            if cleaned_response_item:  # if the whole response, cleaned, is not empty
                                all_results.append(cleaned_response_item)
                                logging.info("Added cleaned entire JSON response as a single item.")
                        elif isinstance(raw_page_json, list):  # if the whole response is a list
                            cleaned_items_for_page = []
                            for raw_item in raw_page_json:
                                cleaned_item = clean_and_sort_data(raw_item)
                                if cleaned_item:
                                    cleaned_items_for_page.append(cleaned_item)
                            all_results.extend(cleaned_items_for_page)
                            logging.info(f"Cleaned and added {len(cleaned_items_for_page)} from top-level list response.")

                    # Pagination Logic
                    next_page_params = parse_next_link_params(response.headers)
                    if next_page_params:
                        logging.info(f"Next page parameters found: {next_page_params}")
                        current_params = next_page_params
                    else:
                        logging.info("No next page link found. End of results.")
                        keep_fetching = False

                    break  # Successful request, exit retry loop

                except requests.exceptions.HTTPError as http_err:
                    # (Backoff logic as before - omitted for brevity here, ensure it's included)
                    if response is not None and response.status_code == 429:
                        current_retries += 1
                        if current_retries > MAX_RETRIES:
                            logging.error(f"HTTP 429: Max retries ({MAX_RETRIES}) exceeded.")
                            keep_fetching = False;
                            break
                        wait_time = 0
                        retry_after_header = response.headers.get("Retry-After")
                        if retry_after_header:
                            try:
                                wait_time = int(retry_after_header)
                            except ValueError:
                                logging.warning(f"Non-integer Retry-After: {retry_after_header}")
                        if wait_time <= 0:
                            wait_time = (BASE_BACKOFF_SECONDS * (2 ** (current_retries - 1))) + random.uniform(0, 1)
                        logging.info(f"HTTP 429: Retrying in {wait_time:.2f}s.")
                        time.sleep(wait_time)
                    else:
                        logging.error(f"HTTP error: {http_err}");
                        keep_fetching = False;
                        break

                except requests.exceptions.RequestException as req_err:
                    # (Backoff logic as before - omitted for brevity here, ensure it's included)
                    current_retries += 1
                    if current_retries > MAX_RETRIES:
                        logging.error(f"RequestException: Max retries ({MAX_RETRIES}) exceeded.");
                        keep_fetching = False;
                        break
                    wait_time = (BASE_BACKOFF_SECONDS * (2 ** (current_retries - 1))) + random.uniform(0, 1)
                    logging.info(f"RequestException: {req_err}. Retrying in {wait_time:.2f}s.")
                    time.sleep(wait_time)

                except ValueError as json_err:  # Includes JSONDecodeError
                    logging.error(f"JSON decoding error: {json_err}")
                    if response is not None:
                        logging.error(f"Response content: {response.text}")
                    keep_fetching = False;
                    break

                except Exception as e:
                    logging.error(f"An unexpected error: {e}");
                    keep_fetching = False;
                    break

        # --- End of Main Loop ---
        logging.info(
            f"\n--- Total pages fetched: {page_count if not keep_fetching and page_count > 0 and all_results else page_count if keep_fetching else 0} ---")
        if all_results:
            logging.info(f"--- Total results collected (cleaned and sorted): {len(all_results)} ---")

            # Convert the generator to a list to get its length and iterate
            log_chunks_list = list(split_list_by_size(all_results, NAMESPACE, USE_CASE_NAME))

            # Now, check if the list of chunks is empty
            if not log_chunks_list:
                logging.info("No data chunks to send to Chronicle after processing (list was empty).")
                return "No data to send after processing."

            total_chunks = len(log_chunks_list)  # Now this works
            logging.info(f"Preparing to send {total_chunks} chunk(s) to Chronicle.")

            for i, chunk in enumerate(log_chunks_list):  # Iterate over the list of chunks
                if not chunk:  # This check might be redundant if all_results are pre-cleaned, but safe
                    logging.warning(f"Skipping empty chunk at index {i}.")
                    continue

                payload = build_chronicle_payload(GCP_PROJECT_ID, CHRONICLE_CUSTOMER_ID,
                                                CHRONICLE_FORWARDER_ID, CHRONICLE_REGION, chunk)
                logging.info(f"Processing chunk {i + 1} of {total_chunks} with {len(chunk)} log entries.")
                send_to_chronicle(
                    CHRONICLE_REGION, GCP_PROJECT_ID, CHRONICLE_CUSTOMER_ID,
                    CHRONICLE_LOG_TYPE, gcp_auth_token, payload
                )
                if i < total_chunks - 1:  # Pause between sending chunks
                    time.sleep(1)

            success_message = f"Process completed. Successfully processed {len(all_results)} items into {total_chunks} chunk(s) and sent to Chronicle."
            logging.info(success_message)
            return success_message
        else:
            logging.info("--- No results collected. ---")
            return "No results collected from VirusTotal."

    except Exception as e:
        logging.exception(f"An error occurred in the main handler: {e}")
        raise


# --- Flask App for HTTP Trigger (Cloud Run Service) ---
app = Flask(__name__)


@app.route("/", methods=["POST", "GET"])  # Adjust route as needed
def http_entrypoint():
    """HTTP entry point for Cloud Run service."""
    # Example: If triggered by Pub/Sub push, parse message:
    # if flask_request.method == "POST":
    #     envelope = flask_request.get_json()
    #     if not envelope or "message" not in envelope:
    #         logging.error("Invalid Pub/Sub message format received.")
    #         return "Bad Request: Invalid Pub/Sub message", 400
    #     pubsub_message = base64.b64decode(envelope["message"]["data"]).decode("utf-8")
    #     logging.info(f"Received Pub/Sub message: {pubsub_message}")
    #     # You might pass this message to main_job_handler if needed

    try:
        result = main_job_handler()
        return result, 200
    except ValueError as ve:  # Specific error for bad configuration
        logging.error(f"Configuration error: {ve}")
        return str(ve), 400  # Bad Request
    except Exception as e:
        # Log the full exception details if it wasn't a config error
        logging.exception(f"Unhandled exception during HTTP request: {e}")
        return "Internal Server Error", 500


# --- Local Execution ---
if __name__ == "__main__":
    # K_SERVICE is not set when running locally
    if not os.environ.get("K_SERVICE"):
        logging.info("Running script locally...")
        # To run Flask app locally:
        # port = int(os.environ.get("PORT", 8080))
        # app.run(host="0.0.0.0", port=port, debug=True) # debug=True is for dev only

        # To run main_job_handler directly (e.g., for non-HTTP local test):
        try:
            print(f"Local script run result: {main_job_handler()}")
        except Exception as e:
            print(f"Local test run failed: {e}")
            # logging.exception already occurs in main_job_handler if it raises
    else:
        # This part is typically not reached when deployed as a Cloud Run Service,
        # as Gunicorn (or other WSGI server) will be the entry point and call 'app'.
        # However, for a Cloud Run Job, the container might execute this script directly.
        # In that case, we'd want main_job_handler to run.
        # But for a service, this 'else' is mostly a fallback or for clarity.
        logging.info("Script started in Cloud Run environment (likely as a service via Gunicorn).")
