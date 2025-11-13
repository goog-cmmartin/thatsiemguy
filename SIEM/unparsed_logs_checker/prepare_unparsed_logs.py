# -*- coding: utf-8 -*-
"""Consolidates the first steps of the unparsed log analysis workflow.

This script replaces the functionality of:
- `list_log_types.py`
- `raw_log_search.py`
- `process_parsers.py`
- `enrich_raw_logs.py`

It provides a guided workflow to:
1.  List available log types from Chronicle.
2.  Fetch unparsed logs for a *specific* log type.
3.  Control the number of logs fetched to avoid excessive API calls.
4.  Download the single active parser corresponding to that log type.
5.  Save the collected logs to a file for the next step in the workflow.
"""

import argparse
import base64
import json
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

# Add the parent directory to the path to import chronicle_auth
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import chronicle_auth
from google.auth.exceptions import TransportError
from google.auth.transport.requests import AuthorizedSession

# Load environment variables from the current directory's .env file
from dotenv import load_dotenv
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path)

# Get Chronicle API credentials from environment variables
PROJECT_ID = os.getenv("PROJECT_ID")
REGION = os.getenv("REGION")
INSTANCE_ID = os.getenv("INSTANCE_ID")


def get_base_url() -> str:
    """Constructs the base URL from environment variables."""
    region = os.getenv("REGION")
    if not region:
        raise ValueError("REGION environment variable not set.")
    return f"https://{region}-chronicle.googleapis.com"


def get_authorized_session() -> AuthorizedSession:
    """Get an authorized session for making Chronicle API requests."""
    return chronicle_auth.get_authorized_session()


MANUAL_MAPPINGS_FILE = "manual_log_type_mappings.json"

def load_manual_log_type_mappings() -> Dict[str, str]:
    """Loads manual log type mappings from a JSON file."""
    file_path = os.path.join(os.path.dirname(__file__), MANUAL_MAPPINGS_FILE)
    if not os.path.exists(file_path):
        print(f"Warning: Manual mappings file '{file_path}' not found. Skipping manual mappings.", file=sys.stderr)
        return {}
    
    with open(file_path, 'r') as f:
        manual_mappings = json.load(f)
    print(f"Loaded {len(manual_mappings)} manual log type mappings from '{MANUAL_MAPPINGS_FILE}'.")
    return manual_mappings

def get_log_type_map(session: AuthorizedSession) -> Dict[str, str]:
    """
    Fetches all log types and creates a map of displayName to internal logType,
    then merges with manual mappings.
    """
    print("Fetching log type mapping...")
    base_url = get_base_url()
    project_id = os.getenv("PROJECT_ID")
    region = os.getenv("REGION")
    instance_id = os.getenv("INSTANCE_ID")
    url = f"{base_url}/v1alpha/projects/{project_id}/locations/{region}/instances/{instance_id}/logTypes"
    
    log_type_map = {}
    page_token = None

    while True:
        params = {"pageSize": 1000}
        if page_token:
            params["pageToken"] = page_token

        response = session.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        for lt in data.get("logTypes", []):
            display_name = lt.get("displayName")
            name = lt.get("name")
            if display_name and name:
                try:
                    internal_name = name.split("/logTypes/")[1]
                    log_type_map[display_name] = internal_name
                except IndexError:
                    continue
        
        page_token = data.get("nextPageToken")
        if not page_token:
            break
            
    print(f"Successfully built map for {len(log_type_map)} log types from API.")
    
    manual_mappings = load_manual_log_type_mappings()
    # Manual mappings override API mappings
    log_type_map.update(manual_mappings)
    
    return log_type_map


def search_raw_logs(
    session: AuthorizedSession,
    log_type: Optional[str],
    internal_to_display_map: Dict[str, str],
    limit: int,
    start_time: datetime,
    end_time: datetime,
    debug: bool = False,
) -> List[Dict[str, Any]]:
    """
    Performs a raw log search for unparsed logs.
    """
    base_query = "raw = /.+/ parsed = false"
    log_types_for_payload = []

    if log_type:
        display_name = internal_to_display_map.get(log_type)
        if not display_name:
            print(f"Error: Internal log type '{log_type}' not found.", file=sys.stderr)
            sys.exit(1)
        print(f"Searching for up to {limit} unparsed logs for log type '{display_name}'...")
        base_query += f" log_source IN [\"{display_name}\"]"
    else:
        print(f"Searching for up to {limit} unparsed logs across all log types...")

    project_id = os.getenv("PROJECT_ID")
    region = os.getenv("REGION")
    instance_id = os.getenv("INSTANCE_ID")
    instance_path = f"projects/{project_id}/locations/{region}/instances/{instance_id}"
    
    url = f"{get_base_url()}/v1alpha/{instance_path}:searchRawLogs"

    start_time_str = start_time.isoformat(timespec='milliseconds').replace("+00:00", "Z")
    end_time_str = end_time.isoformat(timespec='milliseconds').replace("+00:00", "Z")

    payload = {
        "baselineQuery": base_query,
        "baselineTimeRange": {
            "startTime": start_time_str,
            "endTime": end_time_str,
        },
        "snapshotQuery": "",
        "caseSensitive": False,
        "logTypes": log_types_for_payload, # This should be an empty list
        "maxAggregationsPerField": 60,
        "pageSize": limit,
    }

    if debug:
        print(f"Request URL: {url}")
        print(f"Request Payload: {json.dumps(payload, indent=2)}")

    response = session.post(url, json=payload, timeout=60)
    response.raise_for_status()
    results = response.json()

    # Save the full response for debugging
    with open("raw_log_search_response.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Saved full API response to 'raw_log_search_response.json' for debugging.")

    # The API returns a list of objects (streamed response). We need to iterate
    # through them and collect all 'matches'.
    all_matches = []
    if isinstance(results, list):
        for item in results:
            if isinstance(item, dict) and "matches" in item:
                all_matches.extend(item.get("matches", []))

    if not all_matches:
        print("No unparsed logs found for the specified criteria.")
        return []
    else:
        # The API can return duplicates, so we'll deduplicate based on the 'id' field
        unique_logs = {match['id']: match for match in all_matches}.values()
        unique_logs_list = list(unique_logs)
        print(f"Found {len(unique_logs_list)} unique unparsed log(s).")
        return unique_logs_list


def download_all_parsers(session: AuthorizedSession, parsers_dir: str):
    """
    Fetches all active parsers from the Chronicle API, handling pagination,
    and saves each parser's code and metadata to separate files.
    """
    print("Downloading all available active parsers and their metadata...")
    project_id = os.getenv("PROJECT_ID")
    region = os.getenv("REGION")
    instance_id = os.getenv("INSTANCE_ID")
    
    base_url = get_base_url()
    instance_path = f"projects/{project_id}/locations/{region}/instances/{instance_id}"
    url = f"{base_url}/v1alpha/{instance_path}/logTypes/-/parsers"
    
    os.makedirs(parsers_dir, exist_ok=True)
    page_token = None
    parser_count = 0
    metadata_count = 0

    while True:
        params = {
            "pageSize": 1000,
            "filter": 'state="ACTIVE"'
        }
        if page_token:
            params["pageToken"] = page_token

        response = session.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        for parser_data in data.get("parsers", []):
            name = parser_data.get("name", "")
            content = parser_data.get("cbn")
            
            # Extract log_type from the 'name' field, e.g., .../logTypes/AUDITD/parsers/...
            try:
                log_type = name.split("/logTypes/")[1].split("/")[0]
            except IndexError:
                continue # Skip if the name format is unexpected

            if log_type and content:
                # Save the parser code (.conf)
                try:
                    parser_file_path = os.path.join(parsers_dir, f"{log_type}.conf")
                    with open(parser_file_path, "w") as f:
                        f.write(content)
                    parser_count += 1
                except IOError as e:
                    print(f"Error saving parser code for '{log_type}': {e}", file=sys.stderr)

                # Save the metadata (.metadata.json)
                try:
                    metadata_file_path = os.path.join(parsers_dir, f"{log_type}.metadata.json")
                    metadata = parser_data.copy()
                    if "cbn" in metadata:
                        del metadata["cbn"]
                    
                    with open(metadata_file_path, "w") as f:
                        json.dump(metadata, f, indent=2)
                    metadata_count += 1
                except (IOError, TypeError) as e:
                    print(f"Error saving parser metadata for '{log_type}': {e}", file=sys.stderr)

        page_token = data.get("nextPageToken")
        if not page_token:
            break
    
    print(f"Successfully downloaded {parser_count} active parsers and {metadata_count} metadata files to '{parsers_dir}'.")


def batch_download_raw_logs(session: AuthorizedSession, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Downloads the full raw logs for a given list of log matches in batches
    and updates the matches with the full log content.
    """
    log_ids = [match['id'] for match in matches]
    print(f"Starting batch download for {len(log_ids)} raw logs...")
    base_url = get_base_url()
    project_id = os.getenv("PROJECT_ID")
    region = os.getenv("REGION")
    instance_id = os.getenv("INSTANCE_ID")
    instance_path = f"projects/{project_id}/locations/{region}/instances/{instance_id}"
    url = f"{base_url}/v1alpha/{instance_path}/legacy:legacyFindRawLogs"

    # Create a map from snippet to the original match object for easy lookup
    snippet_to_match = {match['snippet']['snippet']: match for match in matches}
    
    batch_size = 100
    for i in range(0, len(log_ids), batch_size):
        batch_ids = log_ids[i:i + batch_size]
        print(f"  Processing batch {i//batch_size + 1}...")
        
        params = {
            "ids": batch_ids,
            "query": ".+",
            "regexSearch": "true",
            "maxResponseByteSize": 300000000,
        }

        try:
            response = session.get(url, params=params, timeout=120)
            response.raise_for_status()
            results = response.json()

            for log_group in results.get("rawLogs", []):
                for raw_log_entry in log_group.get("rawLogs", []):
                    log_bytes = raw_log_entry.get("logBytes")
                    if log_bytes:
                        try:
                            decoded_log = base64.b64decode(log_bytes).decode('utf-8', errors='replace')
                            # Find the original match by checking if the full log starts with the snippet
                            for snippet, match in snippet_to_match.items():
                                if decoded_log.startswith(snippet):
                                    match['snippet']['snippet'] = decoded_log
                                    break
                        except (base64.binascii.Error, UnicodeDecodeError) as e:
                            print(f"  Error decoding log: {e}", file=sys.stderr)
        except Exception as e:
            print(f"  Error during batch download: {e}", file=sys.stderr)
            
    return matches


def clean_up_files(parsers_dir: str, output_file: str):
    """Removes the parsers directory and the output logs file."""
    print("Initiating cleanup...")
    if os.path.exists(parsers_dir):
        try:
            shutil.rmtree(parsers_dir)
            print(f"Removed directory: '{parsers_dir}'")
        except OSError as e:
            print(f"Error removing directory '{parsers_dir}': {e}", file=sys.stderr)
    
    if os.path.exists(output_file):
        try:
            os.remove(output_file)
            print(f"Removed file: '{output_file}'")
        except OSError as e:
            print(f"Error removing file '{output_file}': {e}", file=sys.stderr)
    print("Cleanup complete.")


def main():
    """Main function to orchestrate the preparation of unparsed logs."""
    parser = argparse.ArgumentParser(
        description="Prepare unparsed logs for testing by fetching logs and their active parser."
    )
    parser.add_argument(
        "--log-type",
        help="Optional: The log type to search for (e.g., 'NIX_SYSTEM'). If not provided, searches all log types.",
    )
    parser.add_argument(
        "--start-time",
        help="Start time for the query in ISO 8601 UTC format (e.g., '2023-10-26T10:00:00Z'). Defaults to 24 hours ago.",
    )
    parser.add_argument(
        "--end-time",
        help="End time for the query in ISO 8601 UTC format. Defaults to the current time.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10000,
        help="Maximum number of unparsed logs to fetch (default: 10000).",
    )
    parser.add_argument(
        "--output-file",
        default="logs_to_test.json",
        help="The file to save the fetched logs to (default: 'logs_to_test.json').",
    )
    parser.add_argument(
        "--parsers-dir",
        default="active_parsers",
        help="Directory to save the downloaded parser configuration (default: 'active_parsers').",
    )
    parser.add_argument(
        "--tidy-up",
        action="store_true",
        help="If specified, removes the 'active_parsers' directory and 'logs_to_test.json' file.",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Use a quick time range: last 7 days, ending 1 hour ago.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug printing for API requests.",
    )

    args = parser.parse_args()
    
    try:
        session = get_authorized_session()
    except TransportError as e:
        print(f"Network error during authentication: {e}", file=sys.stderr)
        print("Please check your network connection and try again.", file=sys.stderr)
        sys.exit(1)

    if args.tidy_up:
        clean_up_files(args.parsers_dir, args.output_file)
        return

    # --- Time Range ---
    if args.quick:
        print("Using --quick mode: searching logs from the last 7 days, ending 1 hour ago, with a limit of 10 logs.")
        end_time = datetime.now(timezone.utc) - timedelta(hours=1)
        start_time = end_time - timedelta(days=7)
        args.limit = 10 # Set limit to 10 for quick mode
    elif args.end_time:
        end_time = datetime.fromisoformat(args.end_time.replace("Z", "+00:00"))
    else:
        end_time = datetime.now(timezone.utc)

    if not args.quick: # Only process start_time if --quick is not set
        if args.start_time:
            start_time = datetime.fromisoformat(args.start_time.replace("Z", "+00:00"))
        else:
            start_time = end_time - timedelta(days=1)

    if args.quick:
        print("\n--- Quick Mode Parameters ---")
        print(f"python3 {sys.argv[0]} --start-time \"{start_time.isoformat(timespec='seconds').replace("+00:00", "Z")}\" --end-time \"{end_time.isoformat(timespec='seconds').replace("+00:00", "Z")}\" --limit {args.limit}")
        print("-----------------------------")

    try:
        # Step 1: Create mappings for display names and internal names
        log_type_map = get_log_type_map(session)
        internal_to_display_map = {v: k for k, v in log_type_map.items()}

        # Step 2: Search for unparsed logs to get snippets and IDs
        logs = search_raw_logs(session, args.log_type, internal_to_display_map, args.limit, start_time, end_time, args.debug)
        if not logs:
            return

        # Step 3: Download the full raw logs using the IDs
        logs = batch_download_raw_logs(session, logs)

        # Step 4: Group logs by their internal type name using the map
        logs_by_type = defaultdict(list)
        for match in logs:
            log_type_display = match.get("logType", {}).get("displayName")
            raw_log = match.get("snippet", {}).get("snippet")
            
            if log_type_display and raw_log:
                internal_log_type = log_type_map.get(log_type_display)
                if internal_log_type:
                    logs_by_type[internal_log_type].append({"rawLog": raw_log})
                else:
                    print(f"Warning: Could not find internal name for display name '{log_type_display}'. Skipping log.", file=sys.stderr)

        if not logs_by_type:
            print("Found events, but could not map them to internal log types. Cannot proceed.", file=sys.stderr)
            return

        print(f"\nFound logs for the following internal types: {', '.join(logs_by_type.keys())}")
        
        # Step 5: Save the grouped logs to the output file
        with open(args.output_file, "w") as f:
            json.dump(logs_by_type, f, indent=2)
        print(f"\nSaved {len(logs)} log(s) grouped by internal type to '{args.output_file}'.")

        # Step 6: Download all active parsers for the next script to use
        download_all_parsers(session, args.parsers_dir)

        print("\nPreparation complete. You can now run the testing script.")

    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
