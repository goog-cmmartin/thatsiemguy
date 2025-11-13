import sys
import argparse
import json
import os
import time
from collections import defaultdict
from typing import Dict, Any, List, Optional

import requests

# Import the necessary function from your existing script
# from run_parser import APIError # This import is not used in the provided snippet, but keep it if it's used elsewhere in the full script.

# Add the parent directory to the path to import chronicle_auth
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import chronicle_auth
from google.auth.transport.requests import AuthorizedSession
from google.auth.exceptions import DefaultCredentialsError # Added for clarity in error handling

# Load environment variables from the parent directory's .env file
from dotenv import load_dotenv
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(dotenv_path=dotenv_path)

# Get Chronicle API credentials from environment variables
PROJECT_ID = os.getenv("PROJECT_ID")
REGION = os.getenv("REGION")
INSTANCE_ID = os.getenv("INSTANCE_ID")

# Define APIError if it's not imported from run_parser
class APIError(Exception):
    """Custom exception for API errors."""
    pass

def get_base_url() -> str:
    """Constructs the base URL from environment variables."""
    region = os.getenv("REGION")
    if not region:
        raise ValueError("REGION environment variable not set.")
    return f"https://{region}-chronicle.googleapis.com"


def start_extension_job(
    session: requests.Session,
    region: str,
    instance_path: str,
    log_type: str,
    raw_log: str,
    error_message: str, # This is used to construct the instruction
    debug: bool = False,
) -> str:
    """
    Starts a long-running operation to generate a parser extension.

    Returns:
        The name of the long-running operation to be polled.
    """
    base_url = get_base_url()
    url = f"{base_url}/v1alpha/{instance_path}/labsExperiments/automatic_parser_extension:execute"

    # The instruction is now directly the error_message provided by the user/input file
    instruction = error_message

    payload = {
        "context": {
            "stages": [
                {
                    "name": "User input form",
                    "current": True,
                    "inputs": {
                        "logType": log_type,
                        "rawLog": raw_log,
                        "userInstruction": instruction,
                    },
                    "outputs": [],
                }
            ]
        }
    }

    if debug:
        print(f"Starting extension job with URL: {url}")
        print(f"Payload: {json.dumps(payload, indent=2)}")

    response = session.post(url, json=payload, timeout=60)
    if response.status_code != 200:
        raise APIError(
            f"Failed to start job: Status {response.status_code}, "
            f"Response: {response.text}"
        )

    # The operation name to poll is in the 'name' field of the nested 'response' object
    response_data = response.json()
    # CORRECTED: Get the name from the nested 'response' object
    operation_name = response_data.get("response", {}).get("name")
    if not operation_name:
        raise APIError(f"Could not find operation name in response: {json.dumps(response_data, indent=2)}")

    return operation_name


def poll_extension_job(
    session: requests.Session, region: str, operation_name: str, debug: bool = False
) -> Dict[str, Any]:
    """
    Polls a long-running operation until it completes.

    Returns:
        The final JSON response of the completed operation.
    """
    base_url = get_base_url()
    # The operation name is the full path, but the base_url doesn't include the version
    url = f"{base_url}/v1alpha/{operation_name}"

    while True:
        response = session.get(url, timeout=60)
        if response.status_code != 200:
            raise APIError(
                f"Failed to poll job status: Status {response.status_code}, "
                f"Response: {response.text}"
            )

        result = response.json()
        state = result.get("state", "STATE_UNSPECIFIED")

        print(f"  Polling job '{operation_name}': current state is {state}")
        if debug:
            print(f"  Full poll response:\n{json.dumps(result, indent=2)}")

        # Terminal states: SUCCEEDED, FAILED, CANCELLED
        if state in ["SUCCEEDED", "FAILED", "CANCELLED"]:
            return result
        # Continue polling for these states
        elif state in ["QUEUED", "RUNNING", "STATE_UNSPECIFIED"]:
            time.sleep(5)
        else:
            # Handle unexpected states, log a warning and continue polling
            print(f"  Warning: Unexpected job state '{state}'. Continuing to poll.", file=sys.stderr)
            time.sleep(5)

        time.sleep(5)  # Wait before polling again


def propose_extensions_for_errors(
    input_file: Optional[str], # Made optional
    single_log_type: Optional[str], # New parameter
    single_raw_log: Optional[str], # New parameter
    single_error_message: Optional[str], # New parameter
    project_id: str,
    instance_id: str,
    region: str,
    debug: bool = False,
):
    """
    Main orchestration function.
    """
    logs_by_type = defaultdict(list)

    if single_log_type and single_raw_log and single_error_message:
        print("Processing a single log provided via command-line arguments.")
        logs_by_type[single_log_type].append({
            "rawLog": single_raw_log,
            "error": single_error_message
        })
    elif input_file:
        # --- 1. Read and group failed logs from file ---
        try:
            with open(input_file, 'r') as f:
                failed_logs_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            print(f"Error reading input file '{input_file}': {e}", file=sys.stderr)
            return

        for log_entry in failed_logs_data:
            log_type = log_entry.get("logType")
            raw_log = log_entry.get("rawLog")
            error_message = log_entry.get("error")
            if log_type and raw_log and error_message:
                logs_by_type[log_type].append({
                    "rawLog": raw_log,
                    "error": error_message
                })
    else:
        print("Error: Either an input file or single log parameters (--single-log-type, --single-raw-log, --single-error-message) must be provided.", file=sys.stderr)
        return


    if not logs_by_type:
        print("No failed logs with valid 'logType', 'rawLog', and 'error' found for processing.")
        return

    # --- 2. Authenticate ---
    try:
        # Using chronicle_auth.get_authorized_session() as per other scripts
        authed_session = chronicle_auth.get_authorized_session()
    except DefaultCredentialsError:
        print("Authentication failed. Please configure Application Default Credentials.", file=sys.stderr)
        return

    instance_path = f"projects/{project_id}/locations/{region}/instances/{instance_id}"
    final_proposals = {}

    # --- 3. Iterate through failed logs and propose fixes ---
    for log_type, failed_logs in logs_by_type.items():
        print(f"\n--- Processing Failed Logs for Log Type: {log_type} ---")

        for i, failed_log_entry in enumerate(failed_logs):
            raw_log = failed_log_entry["rawLog"]
            error_message = failed_log_entry["error"]

            print(f"\n- Processing failed log {i+1}/{len(failed_logs)} for {log_type}...")
            print(f"  Original Error: {error_message}")
            print("  Attempting to generate a parser extension...")

            try:
                op_name = start_extension_job(
                    authed_session, region, instance_path, log_type, raw_log, error_message, debug
                )
                final_result = poll_extension_job(authed_session, region, op_name, debug)
                
                if log_type not in final_proposals:
                    final_proposals[log_type] = []
                final_proposals[log_type].append(final_result)

            except APIError as e:
                print(f"  An API error occurred while proposing extension for this log: {e}", file=sys.stderr)

    # --- 4. Save final combined results ---
    output_file = "suggested_extensions.json"
    if final_proposals:
        with open(output_file, "w") as f:
            json.dump(final_proposals, f, indent=2)
        print(f"\nSuccessfully saved proposed extensions to '{output_file}'.")
    else:
        print("No parsing errors were found that required a proposal.")

def main():
    print("DEBUG: Entered main function.") # DEBUG
    parser = argparse.ArgumentParser(
        description="For logs that failed parsing, propose a parser extension using the Labs API."
    )
    
    # --- Input Source Arguments ---
    # These are now regular arguments, not in a mutually exclusive group
    parser.add_argument(
        "--input-file",
        help="Path to the JSON file containing logs that failed parsing (e.g., 'failed_logs.json').",
    )
    parser.add_argument(
        "--single-log-type",
        help="Log type for a single raw log to process (e.g., 'NIX_SYSTEM'). Requires --single-raw-log and --single-error-message.",
    )
    parser.add_argument(
        "--single-raw-log",
        help="The raw log content for a single log to process. Requires --single-log-type and --single-error-message.",
    )
    parser.add_argument(
        "--single-error-message",
        help="The error message associated with the single raw log. Used to construct the user instruction. Requires --single-log-type and --single-raw-log.",
    )

    # --- Configuration Arguments ---
    parser.add_argument("--project_id", help="GCP Project ID. Overrides .env.")
    parser.add_argument("--instance_id", help="Chronicle instance ID. Overrides .env.")
    parser.add_argument("--region", help="Chronicle region (e.g., 'us'). Overrides .env.")
    parser.add_argument("--debug", action="store_true", help="Enable debug printing.")
    
    args = parser.parse_args()

    # --- Manual Validation of Input Arguments ---
    using_input_file = args.input_file is not None
    using_single_log = any([args.single_log_type, args.single_raw_log, args.single_error_message])

    if using_input_file and using_single_log:
        parser.error("Argument error: --input-file cannot be used with --single-* arguments.")
    
    if not using_input_file and not using_single_log:
        # Default behavior: use 'failed_logs.json' if it exists and no other input is specified
        args.input_file = "failed_logs.json"
        if not os.path.exists(args.input_file):
             parser.error("Argument error: You must provide an input source. Either specify --input-file, or provide all --single-* arguments, or have 'failed_logs.json' in the current directory.")

    if using_single_log and not all([args.single_log_type, args.single_raw_log, args.single_error_message]):
        parser.error("Argument error: When using any --single-* argument, all three must be provided: --single-log-type, --single-raw-log, and --single-error-message.")

    # --- Load Environment and Configuration ---
    load_dotenv()
    project_id = args.project_id or os.getenv("PROJECT_ID")
    instance_id = args.instance_id or os.getenv("INSTANCE_ID")
    region = args.region or os.getenv("REGION")

    if not all([project_id, instance_id, region]):
        print("Error: Missing configuration for project_id, instance_id, or region in arguments or .env file.", file=sys.stderr)
        return

    propose_extensions_for_errors(
        input_file=args.input_file,
        single_log_type=args.single_log_type,
        single_raw_log=args.single_raw_log,
        single_error_message=args.single_error_message,
        project_id=project_id,
        instance_id=instance_id,
        region=region,
        debug=args.debug,
    )

    print("\nExtension proposal process complete. Check 'suggested_extensions.json' for results.")


if __name__ == "__main__":
    main()
