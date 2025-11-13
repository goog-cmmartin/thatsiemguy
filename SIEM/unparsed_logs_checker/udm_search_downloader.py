# -*- coding: utf-8 -*-
"""
Performs a UDM search and downloads the full raw logs for the events found.
"""

import argparse
import base64
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from urllib.parse import urlencode

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








def udm_search(
    session: AuthorizedSession,
    query: str,
    start_time: datetime,
    end_time: datetime,
    limit: int,
    debug: bool = False,
) -> List[str]:
    """Performs a UDM search and returns a list of raw log IDs."""
    print("\nPerforming UDM search...")
    base_url = get_base_url()
    project_id = os.getenv("PROJECT_ID")
    region = os.getenv("REGION")
    instance_id = os.getenv("INSTANCE_ID")
    instance_path = f"projects/{project_id}/locations/{region}/instances/{instance_id}"
    
    start_time_str = start_time.isoformat()
    end_time_str = end_time.isoformat()

    params = {
        "query": query,
        "timeRange.startTime": start_time_str,
        "timeRange.endTime": end_time_str,
        "limit": limit,
    }
    
    url = f"{base_url}/v1alpha/{instance_path}:udmSearch?{urlencode(params)}"

    if debug:
        print(f"Request URL: {url}")

    try:
        response = session.get(url, timeout=60)
        response.raise_for_status()
        results = response.json()

        if debug:
            print("\n--- UDM Search API Response ---")
            print(json.dumps(results, indent=2))
            print("-------------------------------\n")

    except Exception as e:
        print(f"  Error during UDM search API call: {e}", file=sys.stderr)
        try:
            print(f"  Response Body: {response.text}", file=sys.stderr)
        except NameError:
            pass 
        return []

    events = results.get("events", [])
    print(f"Found {len(events)} UDM events.")
    return events








def batch_download_raw_logs(session: AuthorizedSession, events: List[Dict[str, Any]], debug: bool = False) -> Dict[str, str]:
    """Downloads the full raw logs for a given list of events and returns a map of ID to raw log."""
    if not events:
        return {}

    log_ids = [event.get("udm", {}).get("metadata", {}).get("id") for event in events]
    log_ids = [log_id for log_id in log_ids if log_id] # Filter out any None values

    if debug:
        print(f"\n--- Log IDs sent to batch_download_raw_logs ---\n{log_ids}\n-------------------------------------------------")

    print(f"\nStarting batch download for {len(log_ids)} raw logs...")
    base_url = get_base_url()
    project_id = os.getenv("PROJECT_ID")
    region = os.getenv("REGION")
    instance_id = os.getenv("INSTANCE_ID")
    instance_path = f"projects/{project_id}/locations/{region}/instances/{instance_id}"
    url = f"{base_url}/v1alpha/{instance_path}/legacy:legacyFindRawLogs"

    id_to_log_map = {}
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

            if debug:
                print(f"\n--- Batch Download API Response (Batch {i//batch_size + 1}) ---")
                print(json.dumps(results, indent=2))
                print("---------------------------------------------------\n")

            for i, log_group in enumerate(results.get("rawLogs", [])):
                # The response is ordered according to the request's batch_ids
                log_id = batch_ids[i]
                for raw_log_entry in log_group.get("rawLogs", []):
                    log_bytes = raw_log_entry.get("logBytes")
                    if log_bytes and log_id:
                        try:
                            decoded_log = base64.b64decode(log_bytes).decode('utf-8', errors='replace')
                            id_to_log_map[log_id] = decoded_log
                            # Since there's typically one log per ID, we can break after finding it
                            break 
                        except (base64.binascii.Error, UnicodeDecodeError) as e:
                            print(f"  Error decoding log for ID {log_id}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"  Error during batch download: {e}", file=sys.stderr)
            
    print(f"Successfully downloaded {len(id_to_log_map)} raw log(s).")
    return id_to_log_map





def main():
    """Main function to orchestrate the UDM search and raw log download."""
    parser = argparse.ArgumentParser(
        description="Perform a UDM search and download the corresponding raw logs."
    )
    parser.add_argument(
        "--query",
        required=True,
        help="The UDM boolean query to search for.",
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
        default=100,
        help="Maximum number of UDM events to return (default: 100).",
    )
    parser.add_argument(
        "--output-file",
        default="downloaded_raw_logs.json",
        help="The file to save the downloaded raw logs to (default: 'downloaded_raw_logs.json').",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug printing for API requests and responses.",
    )

    args = parser.parse_args()

    try:
        session = get_authorized_session()
    except TransportError as e:
        print(f"Network error during authentication: {e}", file=sys.stderr)
        print("Please check your network connection and try again.", file=sys.stderr)
        sys.exit(1)

    # --- Time Range ---
    if args.end_time:
        end_time = datetime.fromisoformat(args.end_time.replace("Z", "+00:00"))
    else:
        end_time = datetime.now(timezone.utc)

    if args.start_time:
        start_time = datetime.fromisoformat(args.start_time.replace("Z", "+00:00"))
    else:
        start_time = end_time - timedelta(days=1)

    try:
        # Step 1: Perform the UDM search to get the full event details
        events = udm_search(
            session=session,
            query=args.query,
            start_time=start_time,
            end_time=end_time,
            limit=args.limit,
            debug=args.debug,
        )

        if not events:
            print("No UDM events found for the given query. Exiting.")
            return

        # Step 2: Download the full raw logs for the found events
        id_to_log_map = batch_download_raw_logs(
            session=session,
            events=events,
            debug=args.debug,
        )

        # Step 3: Group logs by type and format for the output file
        logs_by_type = defaultdict(list)
        for event in events:
            log_id = event.get("udm", {}).get("metadata", {}).get("id")
            log_type = event.get("udm", {}).get("metadata", {}).get("logType")
            
            if log_id in id_to_log_map and log_type:
                logs_by_type[log_type].append({"rawLog": id_to_log_map[log_id]})

        # Step 4: Save the grouped logs to the output file
        try:
            with open(args.output_file, "w") as f:
                json.dump(logs_by_type, f, indent=2)
            print(f"\nSuccessfully saved logs grouped by type to '{args.output_file}'.")
        except IOError as e:
            print(f"Error writing to output file '{args.output_file}': {e}", file=sys.stderr)

        print("\nScript finished successfully.")

    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
