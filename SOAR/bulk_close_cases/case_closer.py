#!/usr/bin/env python3
"""
A command-line script to find and bulk-close cases from an API.

This script connects to a specified API instance, searches for open cases
with a given title across all environments, and closes them in bulk.
It queries each environment individually.
"""

# Imports
import requests
import json
import logging
import sys
import time
import argparse
import os
from datetime import datetime, timedelta

# --- Script Constants ---
DEFAULT_LOG_FILE = "overflow_case_closer.log"

# This payload serves as a template; its values will be updated by command-line args.
SEARCH_CASE_PAYLOAD = {
    "tags": [],
    "ruleGenerator": [],
    "caseSource": [],
    "stage": [],
    "environments": [],
    "assignedUsers": [],
    "products": [],
    "ports": [],
    "categoryOutcomes": [],
    "status": [],
    "caseIds": [],
    "incident": [],
    "importance": [],
    "priorities": [],
    "pageSize": 100,
    "isCaseClosed": False,
    "title": "Overflow Case",
    "startTime": None,
    "endTime": None,
    "requestedPage": 0,
    "timeRangeFilter": 0
}

# --- Core Functions ---

def setup_logging(log_level: int, log_file: str):
    """Configures logging with file and console handlers."""
    logger = logging.getLogger()
    logger.setLevel(log_level)
    log_format = logging.Formatter("%(asctime)s [%(levelname)-8s] %(message)s")

    # File handler
    try:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(log_format)
        logger.addHandler(file_handler)
    except IOError as e:
        print(f"Error: Unable to write to log file {log_file}. {e}", file=sys.stderr)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)

    logging.debug("Logging initialized.")

def get_envs(api_root: str, session: requests.Session) -> list:
    """Fetches a list of environment names from the API."""
    logging.debug("Getting environments...")
    url = f'{api_root}api/external/v1/settings/GetEnvironments'
    body = {"searchTerm": "", "requestedPage": 0, "pageSize": 100}
    try:
        r = session.post(url, json=body)
        r.raise_for_status()
        envs = [env['name'] for env in r.json().get('objectsList', [])]
        logging.debug(f"Found {len(envs)} environments.")
        if envs:
            logging.debug(f"Environment names: {', '.join(envs)}")
        return envs
    except requests.exceptions.RequestException as e:
        logging.error(f"Error getting environments: {e}")
        if e.response:
            logging.error(f"Error Response: {e.response.text}")
        raise

def bulk_close_cases(case_ids: list, api_root: str, session: requests.Session):
    """Closes a list of cases using the bulk API endpoint."""
    if not case_ids:
        logging.debug("No case IDs provided to bulk_close_cases.")
        return
    logging.debug(f"Requesting to close {len(case_ids)} cases.")
    url = f'{api_root}api/external/v1/cases-queue/bulk-operations/ExecuteBulkCloseCase'
    body = {
        "casesIds": case_ids,
        "closeComment": 'Closed by Automation',
        "closeReason": 2,
        "rootCause": "Lab test"
    }
    try:
        r = session.post(url, json=body)
        r.raise_for_status()
        logging.debug(f"Successfully closed {len(case_ids)} cases.")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error closing cases: {e}")
        if e.response:
            logging.error(f"Error Response: {e.response.text}")
        raise

def process_cases(api_root: str, session: requests.Session, days_to_search: int, title: str):
    """Main logic to search for and close overflow cases."""
    logging.info("Starting case processing run...")
    search_url = f'{api_root}api/external/v1/search/CaseSearchEverything'
    
    try:
        all_environments = get_envs(api_root, session)
        if not all_environments:
            logging.warning("No environments found. Nothing to process.")
            return
            
        total_closed_in_run = 0

        # Loop over each environment to query it individually
        for env_name in all_environments:
            logging.info(f"--- Processing environment: '{env_name}' ---")
            
            search_body = SEARCH_CASE_PAYLOAD.copy()
            
            # Update payload from command-line arguments
            search_body['title'] = title

            # Generate timestamps with specific precision
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=days_to_search)
            search_body['endTime'] = end_time.isoformat(timespec='seconds') + 'Z'
            search_body['startTime'] = start_time.isoformat(timespec='seconds') + 'Z'
            
            search_body['environments'] = [env_name]
            
            # Update logging to be more descriptive
            title_text = f"'{title}'" if title else "any title"
            logging.info(f"Searching for open cases with title {title_text} from {search_body['startTime']} to {search_body['endTime']}")

            page = 0
            is_more_pages = True
            
            while is_more_pages:
                search_body['requestedPage'] = page
                
                logging.debug(f"Searching page {page + 1} for environment '{env_name}'...")
                logging.debug(f"Search payload for page {page + 1}: {json.dumps(search_body, indent=2)}")

                r = session.post(search_url, json=search_body)
                r.raise_for_status()

                page_results = r.json().get('results', [])
                logging.debug(f"API results for this page: {json.dumps(page_results, indent=2)}")

                if not page_results:
                    if page == 0:
                        logging.debug("No cases found on the first page for this environment.")
                    is_more_pages = False
                    continue

                case_ids = [case['id'] for case in page_results]
                logging.info(f"Found {len(case_ids)} cases on page {page + 1}. Closing them...")
                bulk_close_cases(case_ids, api_root, session)
                total_closed_in_run += len(case_ids)

                page += 1

        # Final summary logging after all environments are processed
        if total_closed_in_run == 0:
            logging.info("--- Run Finished: No matching open cases were found to close. ---")
        else:
            logging.info(f"--- Run Finished: Total cases closed across all environments: {total_closed_in_run} ---")

    except requests.exceptions.RequestException as e:
        logging.error(f"An API request error stopped the process: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}", exc_info=True)


def main():
    """Main function to parse arguments and orchestrate the script."""
    parser = argparse.ArgumentParser(
        description='Find and bulk-close open cases based on specified criteria.',
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Example Usage:
  Close cases with the default title 'Overflow Case':
    python3 case_closer.py -u <URL> -k <KEY>

  Close all cases with any title from the last 24 hours (use with caution!):
    python3 case_closer.py -u <URL> -k <KEY> --title "" --days 1
"""
    )
    # --- MODIFIED: Removed --include-closed argument ---
    parser.add_argument('-u', '--url', help='The instance URL. Can also be set via INSTANCE_URL env var.', default=os.environ.get('INSTANCE_URL'))
    parser.add_argument('-k', '--key', help='The API key. Can also be set via API_KEY env var.', default=os.environ.get('API_KEY'))
    parser.add_argument('-d', '--days', type=int, default=30, help='Number of past days to search for cases. Default: 30')
    parser.add_argument('--title', default='Overflow Case', help='Case title to search for. Use "" to match any title. Default: "Overflow Case"')
    parser.add_argument('-c', '--continuous', action='store_true', help='Run continuously in a loop. Default is to run once.')
    parser.add_argument('-i', '--interval', type=int, default=300, help='Wait interval in seconds for continuous mode. Default: 300 (5 mins)')
    parser.add_argument('--log-file', default=DEFAULT_LOG_FILE, help=f'Path to the log file. Default: {DEFAULT_LOG_FILE}')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose DEBUG level logging.')

    args = parser.parse_args()

    # Setup
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(log_level, args.log_file)

    if not args.url or not args.key:
        logging.error("Instance URL and API Key are required. Please provide them via arguments or environment variables.")
        parser.print_help()
        sys.exit(1)

    api_root = args.url if args.url.endswith('/') else f'{args.url}/'

    session = requests.Session()
    session.headers.update({
        'Appkey': args.key,
        'Content-Type': 'application/json'
        })
    
    # --- MODIFIED: Pass updated arguments to process_cases ---
    try:
        if args.continuous:
            logging.info(f"Starting in continuous mode. Interval: {args.interval}s. Press Ctrl+C to stop.")
            while True:
                process_cases(api_root, session, args.days, args.title)
                logging.info(f"Waiting for {args.interval} seconds...")
                time.sleep(args.interval)
        else:
            logging.info("Starting in single-run mode.")
            process_cases(api_root, session, args.days, args.title)
            
    except KeyboardInterrupt:
        logging.info("Process interrupted by user. Shutting down.")
    except Exception as e:
        logging.error(f"A critical error occurred: {e}", exc_info=True)
        sys.exit(1)
        
    logging.info("Script finished.")


if __name__ == "__main__":
    main()
