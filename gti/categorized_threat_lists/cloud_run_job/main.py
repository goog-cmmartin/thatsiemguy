import os
import sys
import json
from typing import Optional, Dict, Any, List
from google.cloud import secretmanager
from google.api_core import exceptions as google_exceptions
from datetime import datetime, timezone, timedelta
import google.auth
from google.auth.transport import requests as google_auth_requests
from google.oauth2 import service_account
import urllib.parse
import requests
import base64
import traceback

# --- CONSTANTS ---
BATCH_SIZE = 100


# ==============================================================================
# CONFIGURATION
# ==============================================================================

def load_and_validate_config() -> Dict[str, str]:
    """
    Loads required configuration from environment variables and validates their presence.
    Exits with a clear error message if any required variables are missing.

    Returns:
        A dictionary containing the loaded configuration values.
    """
    # Define all environment variables your script requires to run.
    required_vars = [
        'GCP_PROJECT_ID',
        'SECOPS_INSTANCE_GUID',
        'SECOPS_INSTANCE_LOCATION',
        'SECOPS_LOG_TYPE',
        'SECOPS_FORWARDER_ID',
        'VT_API_KEY_SECRET_PATH',
        'VT_THREAT_FEED',
        'VT_QUERY',
        'VT_ITEM_LIMIT'
    ]

    config = {}
    missing_vars = []

    print("Loading and validating configuration from environment variables...")

    for var_name in required_vars:
        value = os.environ.get(var_name)
        if not value:
            missing_vars.append(var_name)
        else:
            config[var_name] = value

    # If the missing_vars list is not empty, at least one variable was not set.
    if missing_vars:
        print("\n--- FATAL ERROR: Missing required environment variables ---")
        for var_name in missing_vars:
            print(f"  - Please set the '{var_name}' environment variable.")
        print("\n--------------------------------------------------------\n")
        sys.exit(1)

    print(f"Fetching VT API Key from Secret Manager path...")
    api_key = get_secret(config['VT_API_KEY_SECRET_PATH'])

    if not api_key:
        print("\n--- FATAL ERROR: Could not retrieve the VirusTotal API key from Secret Manager ---")
        print(f"Path used: {config['VT_API_KEY_SECRET_PATH']}")
        print("Please ensure the secret path is correct and the service account has the 'Secret Manager Secret Accessor' role.")
        print("-------------------------------------------------------------------------------------\n")
        sys.exit(1)

    # Add the fetched key to the config dictionary so other functions can use it seamlessly.
    config['VT_API_KEY'] = api_key
    # ----------------------------------------------------

    print("✅ Configuration validated and API key fetched successfully.")
    return config

def auth() -> google_auth_requests.AuthorizedSession:
    """
    Obtains an authorized session using Application Default Credentials (ADC).

    This works seamlessly for local development (using gcloud auth or a
    service account file) and in production on Cloud Run (using the
    attached service account).
    
    Raises:
        google.auth.exceptions.DefaultCredentialsError: If no credentials can be found.
    """
    print("Authenticating using Application Default Credentials...")
    try:
        scopes = ['https://www.googleapis.com/auth/cloud-platform']
        
        # google.auth.default() finds the credentials automatically
        creds, project_id = google.auth.default(scopes=scopes)
        
        # Check what kind of credentials we found (optional but informative)
        if hasattr(creds, 'service_account_email'):
            print(f"✅ Authenticated as Service Account: {creds.service_account_email}")
        else:
            print("✅ Authenticated as a User Account (from gcloud).")

        return google_auth_requests.AuthorizedSession(creds)

    except google.auth.exceptions.DefaultCredentialsError:
        print("\n--- FATAL AUTHENTICATION ERROR ---")
        print("Could not find Application Default Credentials.")
        print("Please authenticate using one of the following methods for local development:")
        print("  1. Set the GOOGLE_APPLICATION_CREDENTIALS environment variable to the path of your service account JSON key.")
        print("  2. Run 'gcloud auth application-default login' in your terminal.")
        print("When running on Cloud Run, ensure the service has a service account with the necessary permissions attached.")
        print("------------------------------------\n")
        # Exit the script because no further API calls can be made.
        sys.exit(1)


# ==============================================================================
# STATE MANAGEMENT (Secret Manager)
# ==============================================================================

def get_secret(secret_path: str) -> Optional[str]:
    """
    NEW: Retrieves the payload for the given secret version path.

    Args:
        secret_path: The full resource name of the secret version.
                     e.g., projects/p/secrets/s/versions/v

    Returns:
        The secret string, or None if an error occurs.
    """
    try:
        print(f"Accessing secret version: {secret_path}")
        client = secretmanager.SecretManagerServiceClient()
        response = client.access_secret_version(request={"name": secret_path})
        secret_value = response.payload.data.decode("UTF-8")
        print("✅ Successfully accessed secret.")
        return secret_value
    except google_exceptions.NotFound:
        print(f"❌ Secret not found at path: {secret_path}")
        return None
    except Exception as e:
        print(f"❌ An unexpected error occurred while accessing secret {secret_path}: {e}")
        traceback.print_exc()
        return None

def get_threat_feed_state(gcp_project_id: str, threat_feed_id: str) -> Dict[str, Any]:
    """
    Reads the state for a SPECIFIC VT Threat Feed from Secret Manager.
    """
    default_state = {"lastBookmark": None}
    
    if not gcp_project_id:
        raise ValueError("gcp_project_id must be provided.")

    client = secretmanager.SecretManagerServiceClient()
    
    # Dynamically create the secret ID based on the VT Threat Feed ID
    secret_id = f"threat-feed-id-{threat_feed_id.lower()}"
    secret_name = f"projects/{gcp_project_id}/secrets/{secret_id}/versions/latest"
    print(f"Attempting to read state from secret: '{secret_id}'")

    try:
        response = client.access_secret_version(request={"name": secret_name})
        state = json.loads(response.payload.data.decode("UTF-8"))
        print("Successfully accessed and parsed stored state.")
        return state
    except google_exceptions.NotFound:
        print("State secret not found. Will start with a fresh state.")
        return default_state
    except (json.JSONDecodeError, KeyError):
        print("Could not parse stored state. Starting with a fresh state.")
        return default_state
    except Exception as e:
        print(f"An unexpected error occurred while accessing secret: {e}")
        return default_state

def save_threat_feed_state(gcp_project_id: str, threat_feed_id: str, new_bookmark: str) -> None:
    """
    Saves the state for a SPECIFIC Threat Feed to Secret Manager.
    """
    if not all([gcp_project_id, threat_feed_id, new_bookmark]):
        raise ValueError("All parameters must be provided.")

    state = {"lastBookmark": new_bookmark}
    payload_bytes = json.dumps(state, indent=2).encode("UTF-8")

    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{gcp_project_id}"
    
    # Dynamically create the secret ID based on the threat type
    secret_id = f"threat-feed-id-{threat_feed_id.lower()}"
    secret_path = f"{parent}/secrets/{secret_id}"
    print(f"Attempting to save state to secret: '{secret_id}'")

    try:
        # Add the new version (which becomes the new 'latest')
        client.add_secret_version(
            request={"parent": secret_path, "payload": {"data": payload_bytes}}
        )
        print("Successfully added new state version to existing secret.")

        # Manage the old versions to disable the prior one and destroy any before that.
        manage_old_versions(client, secret_path)

    except google_exceptions.NotFound:
        # This block only runs on the very first execution
        print(f"Secret '{secret_id}' not found. Creating it for the first time...")
        client.create_secret(
            request={"parent": parent, "secret_id": secret_id, "secret": {"replication": {"automatic": {}}}}
        )
        client.add_secret_version(
            request={"parent": secret_path, "payload": {"data": payload_bytes}}
        )
        print("Successfully added the first state version to the new secret.")
    except Exception as e:
        print(f"An unexpected error occurred while saving state: {e}")
        raise

def manage_old_versions(client: secretmanager.SecretManagerServiceClient, secret_path: str):
    """
    Disables the immediate prior version of a secret and destroys any versions
    before that. This keeps the latest version enabled, the previous version
    disabled (as a backup), and all other versions destroyed to stay under the
    version limit.

    Args:
        client: An active SecretManagerServiceClient.
        secret_path: The full path to the secret (e.g., projects/p/secrets/s).
    """
    try:
        # List all versions of the secret that are not already destroyed
        versions = [
            v for v in client.list_secret_versions(request={"parent": secret_path})
            if v.state != secretmanager.SecretVersion.State.DESTROYED
        ]

        # The list is returned newest-first.
        if len(versions) > 1:
            # The version at index 1 is the one just before the new 'latest'.
            # We will disable it if it is currently enabled.
            prior_version = versions[1]
            if prior_version.state == secretmanager.SecretVersion.State.ENABLED:
                print(f"Disabling prior version: {prior_version.name.split('/')[-1]}")
                client.disable_secret_version(request={"name": prior_version.name})

        if len(versions) > 2:
            # All versions from index 2 onwards are older and can be destroyed.
            versions_to_destroy = versions[2:]
            print(f"Found {len(versions_to_destroy)} older version(s) to destroy.")
            for version in versions_to_destroy:
                print(f"  - Destroying version: {version.name.split('/')[-1]}")
                client.destroy_secret_version(request={"name": version.name})

    except Exception as e:
        # Don't let cleanup failure stop the main process. Just log it.
        print(f"Could not manage old secret versions: {e}")


# ==============================================================================
# VT THREAT FEED
# ==============================================================================

def download_iocs_from_vt(
    threat_list_id: str,
    time_param: str,
    limit: str,
    query: str
) -> dict | None:
    """
    Performs a GET request to the Google Threat Feed API's threat_list endpoint
    using an authorized session.
    """

    encoded_query = urllib.parse.quote(query)
    url = (
        f"https://www.virustotal.com/api/v3/threat_lists/{threat_list_id}/{time_param}"
        f"?limit={limit}&query={encoded_query}"
    )
    headers = {"accept": "application/json", "x-apikey": config['VT_API_KEY']}

    try:
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)

        # --- Data Processing ---
        data = response.json()
        item_count = len(data.get("iocs", []))
        print(f"Successfully received API response. Found {item_count} items.")
        # print(json.dumps(data, indent=2)) # Uncomment to see the full response
        # -----------------------
        return data


    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error fetching data for {time_param}: {e.response.status_code} {e.response.text}")
        print("Stopping execution to avoid incorrect bookmarking. Will retry on the next scheduled run.")
        #break  # Stop the loop on failure
    except requests.exceptions.RequestException as e:
        print(f"Request Error fetching data for {time_param}: {e}")
        print("Stopping execution. Will retry on the next scheduled run.")
        #break # Stop the loop on failure

# ==============================================================================
# GOOGLE SECOPS (UDM) INGESTION
# ==============================================================================

def prepare_log_entry(log_message: str) -> Dict[str, Any]:
    """
    Encodes a log message into a base64-encoded JSON string.

    Args:
        log_message: The original log entry as a JSON string.
        thread_feed_id: The ID of the threat feed for labeling.

    Returns:
        A dictionary in the Telemetry Log format.
    """
    json_bytes = log_message.encode('utf-8')
    base64_bytes = base64.b64encode(json_bytes)
    base64_str = base64_bytes.decode('utf-8')
    return {
        "data": base64_str
    }

def ingest_logs_batch(auth_session: Any, config: Dict[str, Any], log_batch: List[Dict[str, Any]]):
    """
    Constructs the final payload and ingests a BATCH of logs
    into Google SecOps.
    """
    # *** CORRECTION ***
    # The 'logs' key should directly contain the list of log entries,
    # not a list containing the list (i.e., log_batch, not [log_batch]).
    full_payload = {
        "inline_source": {
            "logs": log_batch,
            "forwarder": f"{config['PARENT_SECOPS']}/forwarders/{config['SECOPS_FORWARDER_ID']}"
        }
    }

    url = (f"https://{config['SECOPS_INSTANCE_LOCATION']}-chronicle.googleapis.com/"
           f"v1alpha/{config['PARENT_SECOPS']}/logTypes/{config['SECOPS_LOG_TYPE']}/logs:import")
    print(f"url:{url}")

    try:
        # In a real scenario, auth_session would be a google_auth_requests.AuthorizedSession
        response = auth_session.post(url, data=json.dumps(full_payload), headers={"Content-Type": "application/json"})
        print(response)

        response.raise_for_status()
        print(f"  - Successfully ingested a batch of {len(log_batch)} logs.")
        return response
    except Exception as e:
        print(f"  - FAILED: {e}")
        # In a production system, you might want to log the failed batch for retry
        # print(json.dumps(full_payload, indent=2))
        return None

if __name__ == '__main__':
    # --- 1. LOAD, VALIDATE, AND AUTHENTICATE ---
    config = load_and_validate_config()
    config['PARENT_SECOPS'] = f"projects/{config['GCP_PROJECT_ID']}/locations/{config['SECOPS_INSTANCE_LOCATION']}/instances/{config['SECOPS_INSTANCE_GUID']}"
    auth_session = auth()

    # --- 2. SETUP TIME & STATE LOGIC BASED ON API RULES (T-2h DELAY) ---
    threat_feed_id = config['VT_THREAT_FEED']
    print(f"Processing threat feed: '{threat_feed_id}'")

    # Determine the latest hour we are allowed to query (T-2h, floored to the hour)
    now_utc = datetime.now(timezone.utc)
    safe_query_time = now_utc - timedelta(hours=2)
    latest_hour_to_query = safe_query_time.replace(minute=0, second=0, microsecond=0)

    # Get the last successfully processed hour from our bookmark
    state = get_threat_feed_state(config['GCP_PROJECT_ID'], threat_feed_id)
    last_bookmark_str = state.get("lastBookmark")

    # Determine the first hour we need to start querying from
    if last_bookmark_str:
        try:
            # Parse the last saved hour string into a datetime object
            last_processed_hour = datetime.strptime(last_bookmark_str, "%Y%m%d%H").replace(tzinfo=timezone.utc)
            first_hour_to_query = last_processed_hour + timedelta(hours=1)
            print(f"✅ Found bookmark for hour '{last_bookmark_str}'. Starting next query from hour '{first_hour_to_query.strftime('%Y%m%d%H')}'.")
        except ValueError:
            # Handle malformed bookmark
            print(f"⚠️ Malformed bookmark '{last_bookmark_str}'. Defaulting to the latest available hour.")
            first_hour_to_query = latest_hour_to_query
    else:
        # This is the very first run. We will only process the single latest available hour.
        print("⚠️ No bookmark found. Will process the latest available hour only.")
        first_hour_to_query = latest_hour_to_query

    # --- 3. LOOP THROUGH EACH HOUR THAT NEEDS TO BE PROCESSED ---
    hour_to_process = first_hour_to_query
    while hour_to_process <= latest_hour_to_query:
        current_hour_str = hour_to_process.strftime("%Y%m%d%H")
        print("\n" + "="*80)
        print(f"Processing batch for hour: {current_hour_str}")
        print("="*80)

        # Download indicators for the specific hour
        ioc_results = download_iocs_from_vt(
            threat_feed_id,
            current_hour_str,
            config['VT_ITEM_LIMIT'],
            config['VT_QUERY']
        )

        if ioc_results:
            all_logs = ioc_results.get("iocs", [])

            if not all_logs:
                print(f"No new IOCs found for hour {current_hour_str}.")
            else:
                print(f"Found {len(all_logs)} logs to process for hour {current_hour_str}.")
                # --- Processing and Ingestion Logic ---
                prepared_logs = []
                for log_entry in all_logs:
                    log_entry['threat_feed_id'] = threat_feed_id
                    log_as_json_string = json.dumps(log_entry)
                    prepared_entry = prepare_log_entry(log_as_json_string)
                    prepared_logs.append(prepared_entry)

                for i in range(0, len(prepared_logs), BATCH_SIZE):
                    batch = prepared_logs[i:i + BATCH_SIZE]
                    ingest_logs_batch(auth_session, config, batch)

            # --- INCREMENTAL BOOKMARK SAVE ---
            # After successfully processing (or finding no logs for) an hour, save the bookmark.
            print(f"✅ Successfully processed hour {current_hour_str}. Saving as the new bookmark.")
            save_threat_feed_state(config['GCP_PROJECT_ID'], threat_feed_id, current_hour_str)

        else:
            # If the download for this hour fails, stop the loop.
            # The bookmark will not be updated, so the next run will retry this hour.
            print(f"❌ Download of IOCs failed for hour {current_hour_str}. Halting run.")
            break

        # Move to the next hour for the next loop iteration
        hour_to_process += timedelta(hours=1)

    print("\nScript finished.")
