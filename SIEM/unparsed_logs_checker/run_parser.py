import argparse
import base64
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
# Add the parent directory to the path to import chronicle_auth
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import chronicle_auth
from google.auth.transport.requests import AuthorizedSession
import requests


class APIError(Exception):
    """Custom exception for API-related errors."""
    pass


def run_parser(
    session: requests.Session,
    region: str,
    instance_path: str,
    log_type: str,
    parser_code: str,
    logs: List[str],
    debug: bool = False,
) -> Dict[str, Any]:
    """
    Runs a parser configuration against sample logs.

    Args:
        session: An authenticated requests.Session object.
        region: The region of the Chronicle instance.
        instance_path: The full path to the Chronicle instance.
        log_type: The log type of the parser (e.g., "AUDITD").
        parser_code: The content of the parser configuration file (base64 encoded).
        logs: A list of raw log strings to test against the parser.
        debug: If True, print debug information for the request.

    Returns:
        A dictionary containing the results from the API.

    Raises:
        APIError: If the API request fails or returns a non-200 status code.
    """
    base_url = f"https://{region}-chronicle.googleapis.com/v1alpha"
    url = f"{base_url}/{instance_path}/logTypes/{log_type}:runParser"

    # The parser code is already base64 encoded from the file
    parser = {"cbn": parser_code}

    # Base64 encode the raw log strings
    base64_logs = [base64.b64encode(log.encode("utf-8")).decode("utf-8") for log in logs]

    payload = {
        "parser": parser,
        "log": base64_logs,
    }

    if debug:
        print(f"Request URL: {url}")
        # We can print the payload now as it's structured correctly
        print(f"Request Payload: {json.dumps(payload, indent=2)}")

    try:
        response = session.post(url, json=payload, timeout=90)

        if response.status_code != 200:
            error_msg = (
                f"Error running parser: Status {response.status_code}, "
                f"Response: {response.text}"
            )
            raise APIError(error_msg)

        return response.json()

    except requests.exceptions.RequestException as e:
        error_msg = f"HTTP Request failed: {e}"
        raise APIError(error_msg) from e


def main():
    """Main function to parse arguments and execute the run parser request."""
    parser = argparse.ArgumentParser(
        description="Run a Chronicle parser configuration against sample logs."
    )
    parser.add_argument(
        "--project_id", help="Your Google Cloud project ID. Overrides .env file."
    )
    parser.add_argument(
        "--instance_id", help="Your Chronicle instance ID. Overrides .env file."
    )
    parser.add_argument(
        "--region",
        help="The region of the Chronicle instance (e.g., 'us'). Overrides .env file.",
    )
    parser.add_argument(
        "--log_type",
        required=True,
        help="The target log type for the parser (e.g., 'AUDITD').",
    )
    parser.add_argument(
        "--parser_file",
        required=True,
        help="Path to the file containing the parser configuration code.",
    )
    parser.add_argument(
        "--log_file",
        required=True,
        help="Path to a file containing raw log entries to test, one per line.",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug printing for the request."
    )

    args = parser.parse_args()

    # --- Load configuration ---
    load_dotenv()
    project_id = args.project_id or os.getenv("PROJECT_ID")
    instance_id = args.instance_id or os.getenv("INSTANCE_ID")
    region = args.region or os.getenv("REGION")

    if not all([project_id, instance_id, region]):
        print(
            "Error: Missing configuration. Please provide project_id, instance_id, "
            "and region via command-line arguments or a .env file."
        )
        return

    # --- Read input files ---
    try:
        with open(args.parser_file, 'r') as f:
            parser_code = f.read()
    except FileNotFoundError:
        print(f"Error: Parser file not found at '{args.parser_file}'")
        return

    try:
        with open(args.log_file, 'r') as f:
            # Read lines and strip any trailing newlines
            logs = [line.strip() for line in f.readlines() if line.strip()]
        if not logs:
            print(f"Error: Log file '{args.log_file}' is empty or contains no valid log lines.")
            return
    except FileNotFoundError:
        print(f"Error: Log file not found at '{args.log_file}'")
        return

    # --- Authentication ---
    try:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        authed_session = google.auth.transport.requests.AuthorizedSession(credentials)
    except google.auth.exceptions.DefaultCredentialsError:
        print("Authentication failed. Please configure Application Default Credentials.")
        return

    # --- Call the API ---
    instance_path = f"projects/{project_id}/locations/{region}/instances/{instance_id}"
    try:
        results = run_parser(
            session=authed_session,
            region=region,
            instance_path=instance_path,
            log_type=args.log_type,
            parser_code=parser_code,
            logs=logs,
            debug=args.debug,
        )
        print(json.dumps(results, indent=2))

    except APIError as e:
        print(f"An API error occurred:\n{e}")


if __name__ == "__main__":
    main()
