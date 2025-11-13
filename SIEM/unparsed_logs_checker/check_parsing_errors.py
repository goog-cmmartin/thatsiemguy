# -*- coding: utf-8 -*-
"""Executes a dashboard query to find log sources with parsing errors."""

import argparse
import csv
import io
import json
import os
import sys

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


def _extract_value_from_union(value_union: dict, debug: bool = False):
    """
    Helper function to extract the actual data from the SecOps "union field" object
    based on the documented possible value types.
    """
    
    # Priority list of simple, primitive-like types
    VALUE_KEYS = [
        'stringVal',
        'int64Val',
        'uint64Val',
        'doubleVal',
        'boolVal',
        'timestampVal',
        'bytesVal'
    ]

    # Check for simple types first
    for key in VALUE_KEYS:
        if key in value_union:
            return value_union[key]

    # --- Handle special and complex types ---
    
    # Handle null values
    if 'nullVal' in value_union and value_union['nullVal']:
        return None  # csv.writer correctly handles None as an empty field

    # Handle Date objects
    if 'dateVal' in value_union:
        date_obj = value_union.get('dateVal', {})
        # Format as YYYY-MM-DD for a standard CSV representation
        return f"{date_obj.get('year', 'YYYY')}-{date_obj.get('month', 'MM')}-{date_obj.get('day', 'DD')}"

    # Handle generic Proto objects
    if 'protoVal' in value_union:
        # Serialize the complex object to a JSON string.
        # The csv.writer will automatically quote this string if it
        # contains commas or other special characters.
        return json.dumps(value_union.get('protoVal'))

    # Handle list objects
    if 'list' in value_union:
        if debug:
            print(f"--- Debug: Raw List Object ---\n{json.dumps(value_union, indent=2)}\n--------------------------")
        list_values = value_union.get('list', {}).get('values', [])
        extracted_items = []
        for i, item in enumerate(list_values):
            if debug:
                print(f"--- Debug: Processing List Item {i+1} ---\n{json.dumps(item, indent=2)}\n---------------------------------")
            # Each item in the list is another union, so we recursively call
            extracted_val = _extract_value_from_union(item, debug=debug)
            if extracted_val: # Only append if a value was actually extracted
                extracted_items.append(str(extracted_val))
        
        if debug:
            print(f"--- Debug: Extracted List Items ---\n{extracted_items}\n---------------------------------")
            
        # Join the items into a single pipe-separated string for the CSV
        return " | ".join(extracted_items)
        
    # Fallback if no known value key is found
    return None

def convert_secops_json_to_csv(api_response: dict, debug: bool = False) -> str:
    """
    Converts a verbose, columnar Google SecOps API JSON response
    into a compact, row-oriented CSV string.
    
    Args:
        api_response (dict): The parsed JSON response from the API.
        errors_only (bool): If True, only include rows with parsing errors.
        debug (bool): If True, enable debug printing.
            
    Returns:
        str: A string containing the data in CSV format.
    """
    
    # Check for an empty or invalid response
    if 'results' not in api_response or not api_response['results']:
        return "" # Return an empty string if there are no results

    try:
        # 1. Extract Headers (Column Names)
        headers = [item['column'] for item in api_response['results']]
        
        # 2. Extract Data (Column-wise) and find the max number of rows
        columnar_data = []
        max_rows = 0
        for item in api_response['results']:
            column_values = []
            values = item.get('values', [])
            for value_obj in values:
                # The union can be directly in 'value' or the object itself can be a list
                value_union = value_obj.get('value', value_obj) 
                extracted_val = _extract_value_from_union(value_union, debug)
                column_values.append(extracted_val)
            columnar_data.append(column_values)
            if len(column_values) > max_rows:
                max_rows = len(column_values)

        # 3. Pad shorter columns with None to ensure all have the same length
        for column in columnar_data:
            while len(column) < max_rows:
                column.append(None)

        # 4. Transpose Columnar Data to Row Data
        rows = list(zip(*columnar_data))

        # 5. Write to an in-memory CSV file
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        if rows:
            writer.writerows(rows)
            
        return output.getvalue()

    except Exception as e:
        # Handle potential errors, e.g., malformed JSON
        print(f"Error converting JSON to CSV: {e}")
        return "" # Return empty string on failure


def get_base_url() -> str:
    """Constructs the base URL from environment variables."""
    region = os.getenv("REGION")
    if not region:
        raise ValueError("REGION environment variable not set.")
    return f"https://{region}-chronicle.googleapis.com"


def get_authorized_session() -> AuthorizedSession:
    """Get an authorized session for making Chronicle API requests."""
    return chronicle_auth.get_authorized_session()


def execute_dashboard_query(session: AuthorizedSession, output_file: str = None, debug: bool = False, past_days: int = 7):
    """Executes the hardcoded dashboard query and prints or saves the results."""
    print("Executing dashboard query to check for parsing errors...")
    base_url = get_base_url()
    project_id = os.getenv("PROJECT_ID")
    region = os.getenv("REGION")
    instance_id = os.getenv("INSTANCE_ID")
    instance_path = f"projects/{project_id}/locations/{region}/instances/{instance_id}"
    url = f"{base_url}/v1alpha/{instance_path}/dashboardQueries:execute"


    query_body = {
        "query": {
            "query": '''stage baseline {
    $LogType = $event.ingestion.log_type
    $LogType != ""
    $Date = timestamp.get_date($event.ingestion.start_time) 
    match:
        $Date, $LogType
    outcome:
        $Total_Logs = sum(if($event.ingestion.component = "Ingestion API", $event.ingestion.log_count, 0))
        $Total_Normalized_Events = sum(if($event.ingestion.component = "Normalizer" AND $event.ingestion.state = "validated", $event.ingestion.event_count, 0))
        $Total_Parsing_Error_Events = sum(if($event.ingestion.component = "Normalizer" AND $event.ingestion.state = "failed_parsing", $event.ingestion.log_count, 0))
        $Total_Validation_Error_Events = sum(if($event.ingestion.component = "Normalizer" AND $event.ingestion.state = "failed_validation", $event.ingestion.event_count, 0))
        $Total_Indexing_Error_Events = sum(if($event.ingestion.component = "Normalizer" AND $event.ingestion.state = "failed_indexing", $event.ingestion.log_count, 0))
        $Drop_Reasons = array_distinct($event.ingestion.drop_reason_code) 
    limit:
        1000
}
$Date = $baseline.Date
$logType = $baseline.LogType
$totalLogs = $baseline.Total_Logs
$totalNormalizedEvents = $baseline.Total_Normalized_Events 
$totalParsingErrorEvents = $baseline.Total_Parsing_Error_Events
$totalValidationErrorEvents = $baseline.Total_Validation_Error_Events
$totalIndexingErrorEvents = $baseline.Total_Indexing_Error_Events 
match: 
    $Date, $logType, $totalLogs, $totalNormalizedEvents, $totalParsingErrorEvents, $totalValidationErrorEvents, $totalIndexingErrorEvents
outcome:
    $totalParsingErrorEventsPercent = math.round( (max($baseline.Total_Parsing_Error_Events / $baseline.Total_Logs) * 100 ),2) 
    $dropReasons = array_distinct($baseline.Drop_Reasons)
condition:
    $totalParsingErrorEventsPercent > 0    
order:
    $logType, $Date asc
    ''',
            "input": {
                "relativeTime": {
                    "timeUnit": "DAY",
                    "startTimeVal": str(past_days)
                }
            }
        }
    }

    if debug:
        print(f"--- Debug: Request Body ---\n{json.dumps(query_body, indent=2)}\n--------------------------")

    try:
        response = session.post(url, json=query_body, timeout=60)
        response.raise_for_status()
        results = response.json()

        if debug:
            print("\n--- Raw API Response (JSON) ---")
            print(json.dumps(results, indent=2))
            print("--------------------------------\n")
        
        csv_output = convert_secops_json_to_csv(results, debug)

        if output_file:
            try:
                with open(output_file, "w", newline="") as f:
                    f.write(csv_output)
                print(f"\nSuccessfully saved CSV results to '{output_file}'.")
            except IOError as e:
                print(f"Error writing to file '{output_file}': {e}", file=sys.stderr)
        else:
            print("\n--- Query Results (CSV) ---")
            if csv_output:
                print(csv_output)
            else:
                print("No results to display.")
            print("---------------------------\n")

    except Exception as e:
        print(f"An error occurred during the dashboard query: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(
        description="Check for log sources with parsing errors using a dashboard query."
    )
    parser.add_argument(
        "--output",
        help="Optional: The file path to save the CSV results to.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="If specified, prints the raw JSON API response before converting to CSV.",
    )
    parser.add_argument(
        "--past-days",
        type=int,
        default=7,
        help="Number of days back to query for parsing errors (default: 7, min: 1, max: 30).",
    )
    args = parser.parse_args()

    if not 1 <= args.past_days <= 30:
        print("Error: --past-days must be an integer between 1 and 30.", file=sys.stderr)
        sys.exit(1)

    try:
        session = get_authorized_session()
        execute_dashboard_query(session, args.output, args.debug, args.past_days)
        print("Script finished successfully.")

    except TransportError as e:
        print(f"Network error during authentication: {e}", file=sys.stderr)
        print("Please check your network connection and try again.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
