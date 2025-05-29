import os
import yaml # For local .env.yml parsing
import requests
import urllib.parse
import json
import base64
import sys
import time
import logging
from datetime import datetime, timezone, timedelta
import random # For jitter in backoff
from email.utils import parsedate_to_datetime # For Retry-After header
import re

# Import Google Cloud libraries
from google.cloud import secretmanager
import google.auth
import google.auth.transport.requests

# Import Flask for HTTP trigger if deployed as a Cloud Run service
from flask import Flask, request as flask_request

# --- Load Environment Variables from YAML for LOCAL DEVELOPMENT ---
def load_env_from_yaml_for_local(env_file_path=".env.local.yml"):
    if not os.environ.get("K_SERVICE") and os.path.exists(env_file_path):
        try:
            with open(env_file_path, 'r') as stream:
                env_config = yaml.safe_load(stream)
            if env_config:
                for key, value in env_config.items():
                    if os.environ.get(key) is None:
                        os.environ[key] = str(value)
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

load_env_from_yaml_for_local()

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper(),
                    format='%(asctime)s - %(levelname)s - %(message)s')

# --- Configuration from Environment Variables ---
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID")
VT_API_KEY_SECRET_NAME = os.environ.get("VT_API_KEY_SECRET_NAME")
VT_API_KEY_SECRET_VERSION = os.environ.get("VT_API_KEY_SECRET_VERSION", "latest")

CHRONICLE_CUSTOMER_ID = os.environ.get("CHRONICLE_CUSTOMER_ID")
CHRONICLE_FORWARDER_ID = os.environ.get("CHRONICLE_FORWARDER_ID")
CHRONICLE_LOG_TYPE = os.environ.get("CHRONICLE_LOG_TYPE", "SDL_GTI_IOC_STREAM")
CHRONICLE_REGION = os.environ.get("CHRONICLE_REGION", "us")

NAMESPACE = os.environ.get("NAMESPACE", "SDL")
USE_CASE_NAME = os.environ.get("USE_CASE_NAME", "gti_ioc_stream")

VT_FILTERS = os.environ.get("VT_FILTERS", "origin:hunting")
VT_DATE_FILTER = os.environ.get("VT_DATE_FILTER", "-1d")
VT_ORDER = os.environ.get("VT_ORDER", "date-")
VT_LIMIT = int(os.environ.get("VT_LIMIT", 40)) # This limit is per page

MAX_CHUNK_SIZE_BYTES = int(os.environ.get("MAX_CHUNK_SIZE_BYTES", 3200000))
ABSOLUTE_MAX_CHUNK_SIZE_BYTES = int(os.environ.get("ABSOLUTE_MAX_CHUNK_SIZE_BYTES", 4000000))
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", 60))

# Retry configuration for API calls
API_MAX_RETRIES = int(os.environ.get("API_MAX_RETRIES", 5))
API_BASE_BACKOFF_SECONDS = float(os.environ.get("API_BASE_BACKOFF_SECONDS", 1.0))

# --- Helper Functions ---
def get_secret(project_id, secret_id, version_id="latest"):
    if not project_id or not secret_id:
        logging.error("GCP_PROJECT_ID and secret_id must be set to retrieve a secret.")
        raise ValueError("Project ID or Secret ID not configured for get_secret.")
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
        response = client.access_secret_version(request={"name": name})
        secret_value = response.payload.data.decode("UTF-8").strip()
        logging.info(f"Successfully retrieved secret: {secret_id}")
        return secret_value
    except Exception as e:
        logging.error(f"Error retrieving secret {secret_id} from project {project_id}: {e}")
        raise

def get_gcp_auth_token():
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
    return datetime.now(timezone.utc).isoformat()

def _get_retry_after_seconds(response_headers):
    """Helper to parse Retry-After header, returns seconds or None."""
    retry_after_value = response_headers.get("Retry-After")
    if retry_after_value:
        try:
            return int(retry_after_value)  # If it's seconds
        except ValueError:
            try: # If it's an HTTP-date
                retry_date = parsedate_to_datetime(retry_after_value)
                if retry_date:
                    delay = (retry_date - datetime.now(timezone.utc)).total_seconds()
                    return max(0, delay) # ensure non-negative
            except Exception:
                logging.warning(f"Could not parse Retry-After date: {retry_after_value}")
    return None

def make_api_request_with_retry(url, headers, method="GET", 
                                max_retries=API_MAX_RETRIES, 
                                base_backoff=API_BASE_BACKOFF_SECONDS, 
                                timeout=REQUEST_TIMEOUT_SECONDS):
    """Makes an HTTP request with retry logic for specific status codes."""
    for attempt in range(max_retries):
        try:
            response = requests.request(method, url, headers=headers, timeout=timeout)
            
            if response.status_code == 200:
                return response
            elif response.status_code == 429: # Too Many Requests
                logging.warning(f"Rate limit hit (429) for URL {url}. Attempt {attempt + 1}/{max_retries}.")
                delay_seconds = _get_retry_after_seconds(response.headers)
                if delay_seconds is None: # Calculate our own backoff if no header
                    delay_seconds = base_backoff * (2 ** attempt) + random.uniform(0, 0.1 * (2 ** attempt))
                
                if attempt < max_retries - 1:
                    logging.info(f"Retrying in {delay_seconds:.2f} seconds...")
                    time.sleep(delay_seconds)
                    continue
                else: # Last attempt failed
                    logging.error(f"Max retries reached for 429 error on URL {url}.")
                    response.raise_for_status() # Raise the 429 error
            
            elif response.status_code >= 500: # Server-side errors
                logging.warning(f"Server error ({response.status_code}) for URL {url}. Attempt {attempt + 1}/{max_retries}.")
                delay_seconds = base_backoff * (2 ** attempt) + random.uniform(0, 0.1 * (2 ** attempt))
                if attempt < max_retries - 1:
                    logging.info(f"Retrying in {delay_seconds:.2f} seconds...")
                    time.sleep(delay_seconds)
                    continue
                else: # Last attempt failed
                    logging.error(f"Max retries reached for server error {response.status_code} on URL {url}.")
                    response.raise_for_status() # Raise the 5xx error
            else:
                # For other client errors (400, 401, 403, 404, etc.), don't retry by default
                response.raise_for_status() # Will raise HTTPError for non-2xx
                return response # Should not be reached if raise_for_status() works

        except requests.exceptions.RequestException as e:
            logging.error(f"Request failed for URL {url} on attempt {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                delay_seconds = base_backoff * (2 ** attempt) + random.uniform(0, 0.1 * (2 ** attempt))
                logging.info(f"Retrying in {delay_seconds:.2f} seconds due to connection error/timeout...")
                time.sleep(delay_seconds)
            else:
                logging.error(f"Max retries reached. Request failed for URL {url} after {max_retries} attempts.")
                raise # Re-raise the last exception
    # Should not be reached if max_retries > 0
    raise Exception(f"API request failed definitively after {max_retries} retries for URL {url}")


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
            logging.info(f"Chunk created. Size: ~{current_chunk_estimated_size + payload_overhead} bytes, Items: {len(current_chunk_prepared_items)}")
            current_chunk_prepared_items = []
            current_chunk_estimated_size = 0
        if not current_chunk_prepared_items and item_size + payload_overhead > max_chunk_size:
            if item_size + payload_overhead > max_limit:
                logging.error(f"Single item too large after preparation: {item_size + payload_overhead} bytes. Item ID (if available): {item_dict.get('id')}. Skipping.")
                continue
            else:
                chunks.append([prepared_item])
                logging.info(f"Single large item chunked. Size: ~{item_size + payload_overhead} bytes, Items: 1")
                continue
        current_chunk_prepared_items.append(prepared_item)
        current_chunk_estimated_size += item_size
    if current_chunk_prepared_items:
        chunks.append(current_chunk_prepared_items)
        logging.info(f"Final chunk added. Size: ~{current_chunk_estimated_size + payload_overhead} bytes, Items: {len(current_chunk_prepared_items)}")
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

def clean_and_sort_dict_recursively(data):
    """
    Recursively sorts dictionary keys alphabetically and removes keys with
    empty string, None, empty list, or empty dictionary values.
    Also processes dictionaries within lists.
    """
    if isinstance(data, dict):
        cleaned_dict = {}
        for key in sorted(data.keys()): # 1) Sort keys alphabetically
            value = data[key]
            
            # Recursively process nested dictionaries
            if isinstance(value, dict):
                cleaned_value = clean_and_sort_dict_recursively(value)
                if cleaned_value: # Only add if the cleaned dict is not empty
                    cleaned_dict[key] = cleaned_value
            # Recursively process dictionaries within lists
            elif isinstance(value, list):
                cleaned_list = []
                for item in value:
                    processed_item = clean_and_sort_dict_recursively(item)
                    # Add item if it's not considered "empty" after processing
                    if isinstance(processed_item, dict) and processed_item:
                        cleaned_list.append(processed_item)
                    elif isinstance(processed_item, list) and processed_item: # if list contains lists
                        cleaned_list.append(processed_item)
                    elif not isinstance(processed_item, (dict, list)) and \
                         processed_item is not None and processed_item != "": # Add non-empty simple types
                        cleaned_list.append(processed_item)
                if cleaned_list: # Only add if the cleaned list is not empty
                    cleaned_dict[key] = cleaned_list
            # Check for empty/None values for other types
            elif value is not None and value != "" and value != [] and value != {}: # 2) Remove empty/null values
                cleaned_dict[key] = value
        return cleaned_dict
    elif isinstance(data, list): # If the top-level call is a list (though your VT data items are dicts)
        cleaned_main_list = []
        for item in data:
            processed_item = clean_and_sort_dict_recursively(item)
            if isinstance(processed_item, dict) and processed_item:
                cleaned_main_list.append(processed_item)
            elif isinstance(processed_item, list) and processed_item:
                 cleaned_main_list.append(processed_item)
            elif not isinstance(processed_item, (dict, list)) and \
                 processed_item is not None and processed_item != "":
                cleaned_main_list.append(processed_item)
        return cleaned_main_list
    return data # Return non-dict/non-list items as is (e.g., strings, numbers in a list)

def _parse_offset_to_timedelta(offset_str: str) -> timedelta:
    """
    Parses an offset string (e.g., "-1d", "+30m", "2h") into a timedelta object.
    Also handles "0" for no offset.
    """
    if not offset_str or offset_str == "0": # Handles empty string or "0" as no offset
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
    time_offset = timedelta() # Default to no offset

    if isinstance(offset_expr, str):
        time_offset = _parse_offset_to_timedelta(offset_expr)
    elif isinstance(offset_expr, int):
        # Interpret integer as minutes, consistent with original function's behavior for non-zero
        # and allowing "Xm" format for integers via the parser
        if offset_expr == 0:
            time_offset = timedelta() # No offset
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
    #timestamp_str = timestamp_val.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    timestamp_str = timestamp_val.strftime('%Y-%m-%dT%H:%M:%S') + "+"
    return timestamp_str


# --- Main Handler Logic ---
def main_job_handler():
    required_env_vars = [
        "GCP_PROJECT_ID", "VT_API_KEY_SECRET_NAME", "CHRONICLE_CUSTOMER_ID",
        "CHRONICLE_FORWARDER_ID", "CHRONICLE_LOG_TYPE", "CHRONICLE_REGION"
    ]
    missing_vars = [var for var in required_env_vars if not globals().get(var)]
    if missing_vars:
        msg = f"Missing required environment variables: {', '.join(missing_vars)}"
        logging.error(msg)
        raise ValueError(msg)

    try:
        logging.info("Starting VirusTotal to Chronicle ETL process...")
        vt_api_key = get_secret(GCP_PROJECT_ID, VT_API_KEY_SECRET_NAME, VT_API_KEY_SECRET_VERSION)
        gcp_auth_token = get_gcp_auth_token()

        vt_headers = {"accept": "application/json", "x-apikey": vt_api_key}
        
        VT_DATE_FORMAT=generate_timestamp(VT_DATE_FILTER)
        UPDATED_VT_FILTERS=f"{VT_FILTERS} date:{VT_DATE_FORMAT}"

        raw_vulns_data = [] # Changed name to reflect it's raw
        current_vt_url = f"https://www.virustotal.com/api/v3/ioc_stream?filter={urllib.parse.quote(UPDATED_VT_FILTERS)}&order={VT_ORDER}&limit={VT_LIMIT}"        
        page_num = 1

        while current_vt_url:
            logging.info(f"Fetching page {page_num} from VirusTotal. URL (first part): {current_vt_url.split('?')[0]}...")
            
            response = make_api_request_with_retry(current_vt_url, headers=vt_headers, timeout=REQUEST_TIMEOUT_SECONDS)
            response_data = response.json()
            
            page_data = response_data.get('data', [])
            if page_data:
                raw_vulns_data.extend(page_data) # Extend raw data
                logging.info(f"Retrieved {len(page_data)} items from page {page_num}. Total raw items so far: {len(raw_vulns_data)}.")
            else:
                logging.info(f"No 'data' found on page {page_num}. This might be the end of results or an empty page.")

            current_vt_url = response_data.get('links', {}).get('next')
            if current_vt_url:
                page_num += 1
                time.sleep(0.5) 
            else:
                logging.info("No 'next' link found. Reached the end of VirusTotal results.")
                break
        
        if not raw_vulns_data:
            logging.info("No new items found in VirusTotal matching the criteria after checking all pages.")
            return "No new items found."
        logging.info(f"Retrieved a total of {len(raw_vulns_data)} raw items from VirusTotal across all pages.")

        # --- NEW: Process each vulnerability item ---
        processed_vulns_data = []
        logging.info(f"Cleaning and sorting {len(raw_vulns_data)} fetched items...")
        for index, vuln_item in enumerate(raw_vulns_data):
            if not isinstance(vuln_item, dict):
                logging.warning(f"Item at index {index} is not a dictionary, skipping cleaning for this item: {type(vuln_item)}")
                processed_vulns_data.append(vuln_item) # Add as is or decide to skip
                continue

            cleaned_item = clean_and_sort_dict_recursively(vuln_item)
            if cleaned_item: # Ensure the top-level item itself isn't empty after cleaning
                processed_vulns_data.append(cleaned_item)
            else:
                logging.info(f"Item at index {index} became empty after cleaning and was removed. Original ID (if present): {vuln_item.get('id')}")
        
        if not processed_vulns_data:
            logging.info("No items remaining after cleaning process.")
            return "No items to send after cleaning."
        logging.info(f"Total items after cleaning and sorting: {len(processed_vulns_data)}.")
        # --- END NEW ---

        # Use processed_vulns_data from here on
        log_chunks = split_list_by_size(processed_vulns_data, NAMESPACE, USE_CASE_NAME)
        if not log_chunks:
            logging.info("No data chunks to send to Chronicle after processing.")
            return "No data to send after processing."

        total_chunks = len(log_chunks)
        for i, chunk in enumerate(log_chunks):
            if not chunk: continue
            payload = build_chronicle_payload(GCP_PROJECT_ID, CHRONICLE_CUSTOMER_ID,
                                              CHRONICLE_FORWARDER_ID, CHRONICLE_REGION, chunk)
            logging.info(f"Processing chunk {i+1} of {total_chunks} with {len(chunk)} log entries.")
            send_to_chronicle(
                CHRONICLE_REGION, GCP_PROJECT_ID, CHRONICLE_CUSTOMER_ID,
                CHRONICLE_LOG_TYPE, gcp_auth_token, payload
            )
            if i < total_chunks - 1:
                time.sleep(1)

        success_message = f"Process completed. Successfully processed {len(processed_vulns_data)} items into {total_chunks} chunk(s) and sent to Chronicle."
        logging.info(success_message)
        return success_message

    except Exception as e:
        logging.error(f"An error occurred in the main handler: {e}", exc_info=True)
        raise



# --- Flask App for HTTP Trigger (Cloud Run Service) ---
app = Flask(__name__)

@app.route("/", methods=["POST", "GET"])
def http_entrypoint():
    try:
        result = main_job_handler()
        return result, 200
    except ValueError as ve:
        logging.error(f"Configuration error: {ve}")
        return str(ve), 400
    except Exception as e:
        logging.error(f"Unhandled exception during HTTP request: {e}", exc_info=True)
        return "Internal Server Error", 500

# --- Local Execution ---
if __name__ == "__main__":
    if not os.environ.get("K_SERVICE"):
        logging.info("Running script locally...")
        try:
            print(f"Local script run result: {main_job_handler()}")
        except Exception as e:
            print(f"Local test run failed: {e}")
    else:
        logging.info("Script started in Cloud Run environment (likely as a service via Gunicorn).")
