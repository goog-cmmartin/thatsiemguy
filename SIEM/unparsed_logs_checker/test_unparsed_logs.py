# -*- coding: utf-8 -*-
"""Tests unparsed logs against their active parsers and saves failed logs.

This script takes the output from `prepare_unparsed_logs.py` (`logs_to_test.json`)
and performs the actual parsing test for each log using the downloaded parser.
Logs that fail to parse are saved to `failed_logs.json`.
"""

import argparse
import base64
import json
import os
import sys
from typing import Any, Dict, List

# Add the parent directory to the path to import chronicle_auth
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import chronicle_auth
from google.auth.transport.requests import AuthorizedSession

# Import the run_parser function from the same directory
from run_parser import run_parser, APIError

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


def test_logs_against_parser(
    session: AuthorizedSession,
    log_type: str,
    parser_code: str,
    logs: List[Dict[str, Any]],
    project_id: str,
    region: str,
    instance_id: str,
    debug: bool = False,
) -> Dict[str, Any]:
    """
    Tests a list of logs against a given parser code and returns the full result.

    Args:
        session: Authenticated session.
        log_type: The log type being tested.
        parser_code: The parser configuration code.
        logs: List of raw log dictionaries.
        project_id: Google Cloud project ID.
        region: Chronicle region.
        instance_id: Chronicle instance ID.
        debug: Enable debug output.

    Returns:
        The full JSON response from the runParser API.
    """
    instance_path = f"projects/{project_id}/locations/{region}/instances/{instance_id}"
    raw_logs_for_api = [log.get("rawLog") for log in logs if log.get("rawLog")]

    print(f"\n--- Testing {len(raw_logs_for_api)} logs for Log Type: {log_type} ---")
    
    try:
        results = run_parser(
            session=session,
            region=region,
            instance_path=instance_path,
            log_type=log_type,
            parser_code=parser_code,
            logs=raw_logs_for_api,
            debug=debug,
        )
        print("  Successfully received response from parser API.")
        if debug:
            print("--- API Response ---")
            print(json.dumps(results, indent=2))
            print("--------------------")
        return results

    except APIError as e:
        print(f"  API Error during parsing test: {e}", file=sys.stderr)
        return {"error": f"API Error: {e}"}
    except Exception as e:
        print(f"  Unexpected error during parsing test: {e}", file=sys.stderr)
        return {"error": f"Unexpected Error: {e}"}


def main():
    """Main function to orchestrate the testing of unparsed logs."""
    parser = argparse.ArgumentParser(
        description="Test unparsed logs against their active parsers."
    )
    parser.add_argument(
        "--input-file",
        default="logs_to_test.json",
        help="Path to the JSON file containing logs to test (default: 'logs_to_test.json').",
    )
    parser.add_argument(
        "--parsers-dir",
        default="active_parsers",
        help="Directory containing the downloaded parser configurations (default: 'active_parsers').",
    )
    parser.add_argument(
        "--output-file",
        default="failed_logs.json",
        help="The file to save logs that failed parsing (default: 'failed_logs.json').",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug printing for API requests."
    )

    args = parser.parse_args()

    if not os.path.exists(args.input_file):
        print(f"Error: Input file not found at '{args.input_file}'. Please run prepare_unparsed_logs.py first.", file=sys.stderr)
        sys.exit(1)

    session = get_authorized_session()

    try:
        with open(args.input_file, 'r') as f:
            input_data = json.load(f)
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{args.input_file}'.", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(f"Error: Input file not found at '{args.input_file}'.", file=sys.stderr)
        sys.exit(1)

    all_results = {}
    total_logs_tested = 0
    total_logs_failed = 0

    for log_type, logs_to_test in input_data.items():
        total_logs_tested += len(logs_to_test)
        parser_file_path = os.path.join(args.parsers_dir, f"{log_type}.conf")

        if not os.path.exists(parser_file_path):
            print(f"Warning: Parser file for log type '{log_type}' not found at '{parser_file_path}'. Skipping testing for this log type.", file=sys.stderr)
            continue

        try:
            with open(parser_file_path, 'r') as f:
                parser_code = f.read()
        except FileNotFoundError:
            print(f"Error: Parser file not found at '{parser_file_path}'. Skipping.", file=sys.stderr)
            continue

        # Get the full results from the API call
        results = test_logs_against_parser(
            session=session,
            log_type=log_type,
            parser_code=parser_code,
            logs=logs_to_test,
            project_id=PROJECT_ID,
            region=REGION,
            instance_id=INSTANCE_ID,
            debug=args.debug,
        )
        
        # Create a more detailed output for each log
        detailed_results = []
        if "runParserResults" in results:
            for i, result in enumerate(results["runParserResults"]):
                original_log = logs_to_test[i]['rawLog']
                detailed_result = {
                    "rawLog": original_log,
                    "rawLog_base64": base64.b64encode(original_log.encode('utf-8')).decode('utf-8'),
                    "parsingResult": result
                }
                detailed_results.append(detailed_result)
                if "error" in result:
                    total_logs_failed += 1
        else:
            # Handle cases where the entire API call failed
            detailed_results.append({"error": results.get("error", "Unknown API error")})

        all_results[log_type] = detailed_results
    
    # Save the complete, structured results to the output file
    with open(args.output_file, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSuccessfully saved full parsing results to '{args.output_file}'.")

    if total_logs_failed > 0:
        print(f"\nSummary: Tested {total_logs_tested} logs. {total_logs_failed} failed parsing.")
    else:
        print("\nNo logs failed parsing.")
        
    print("Testing complete. You can now optionally run the extension proposal script.")


if __name__ == "__main__":
    main()
