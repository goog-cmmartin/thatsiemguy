import requests
import os
import argparse
from datetime import datetime, timedelta
import json
from dotenv import load_dotenv


def search_cases(hostname, api_key, tags, start_time, end_time):
    """
    Calls the Siemplify API to search for cases.
    """
    url = f"https://{hostname}/api/external/v1/search/CaseSearchEverything?format=camel"

    if start_time and end_time:
        start_time_iso = start_time.isoformat() + "Z"
        end_time_iso = end_time.isoformat() + "Z"
    else:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=1)
        start_time_iso = start_time.isoformat() + "Z"
        end_time_iso = end_time.isoformat() + "Z"

    payload = {
        "tags": tags,
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
        "pageSize": 50,
        "title": "",
        "startTime": start_time_iso,
        "endTime": end_time_iso,
        "requestedPage": 0,
        "timeRangeFilter": 1
    }

    headers = {
        'Content-Type': 'application/json',
        'AppKey': api_key
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()  # Raise an exception for bad status codes
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error making API request: {e}")
        return None

if __name__ == "__main__":
    load_dotenv()
    parser = argparse.ArgumentParser(description="Search for cases in Siemplify.")
    parser.add_argument("--hostname", help="Siemplify hostname.")
    parser.add_argument("--api_key", help="Siemplify API key.")
    parser.add_argument("--tags", nargs='+', required=True, help="A list of tags to search for.")
    parser.add_argument("--start_time", help="Start time in YYYY-MM-DDTHH:MM:SS format.")
    parser.add_argument("--end_time", help="End time in YYYY-MM-DDTHH:MM:SS format.")

    args = parser.parse_args()

    hostname = args.hostname or os.environ.get("SIEMPLIFY_HOSTNAME")
    api_key = args.api_key or os.environ.get("SIEMPLIFY_APP_KEY")

    if not hostname:
        hostname = input("Enter Siemplify hostname: ")
    if not api_key:
        api_key = input("Enter Siemplify API key: ")


    start_time_obj = datetime.fromisoformat(args.start_time) if args.start_time else None
    end_time_obj = datetime.fromisoformat(args.end_time) if args.end_time else None

    if (start_time_obj and not end_time_obj) or (not start_time_obj and end_time_obj):
        raise ValueError("Both start_time and end_time must be provided if one is specified.")

    cases = search_cases(hostname, api_key, args.tags, start_time_obj, end_time_obj)

    if cases:
        print(json.dumps(cases, indent=4))
