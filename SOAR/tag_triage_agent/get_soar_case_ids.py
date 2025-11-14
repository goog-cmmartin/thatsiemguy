import os
import json
import requests
from dotenv import load_dotenv
import google.auth
import google.auth.transport.requests
import argparse
import time
import random

MAX_RETRIES = 5
INITIAL_BACKOFF = 1  # seconds

def make_api_request(method, url, headers, params=None, data=None):
    """
    Makes an API request with exponential backoff and jitter for rate limiting.
    """
    retries = 0
    backoff_time = INITIAL_BACKOFF

    while retries < MAX_RETRIES:
        try:
            if method.upper() == 'GET':
                response = requests.get(url, headers=headers, params=params)
            elif method.upper() == 'POST':
                response = requests.post(url, headers=headers, params=params, data=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    wait_time = int(retry_after)
                    print(f"Rate limit exceeded. Server requested a wait of {wait_time} seconds.")
                else:
                    wait_time = backoff_time + random.uniform(0, 1)
                    print(f"Rate limit exceeded. Retrying in {wait_time:.2f} seconds...")
                    backoff_time *= 2  # Exponential backoff

                time.sleep(wait_time)
                retries += 1
                continue

            response.raise_for_status()

            if response.text:
                return response.json()
            else:
                return True  # Success with no content

        except requests.exceptions.RequestException as e:
            print(f"API request failed for {url}: {e}")
            if e.response is not None:
                print(f"Response content: {e.response.text}")
            else:
                print("Response content: N/A")
            return None # Stop retrying on other request errors
    
    print(f"Max retries reached for {url}. Aborting.")
    return None

def get_access_token():
    """Fetches the ADC access token."""
    credentials, project = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    auth_req = google.auth.transport.requests.Request()
    credentials.refresh(auth_req)
    return credentials.token

def list_investigations(region, parent):
    """
    Calls the Chronicle API to list investigations.
    """
    token = get_access_token()
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }
    url = f"https://chronicle.{region}.rep.googleapis.com/v1alpha/{parent}/investigations"
    params = {'orderBy': 'start_time desc'}
    
    print(f"Fetching investigations from: {url} with params: {params}")

    return make_api_request('GET', url, headers=headers, params=params)

def get_alert(region, parent, detection_id):
    """
    Calls the Chronicle API to get a specific alert.
    """
    token = get_access_token()
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }
    url = f"https://chronicle.{region}.rep.googleapis.com/v1alpha/{parent}/legacy:legacyGetAlert"
    params = {'alertId': detection_id, 'includeDetections': 'false'}
    
    print(f"Fetching alert with detectionId: {detection_id}")

    return make_api_request('GET', url, headers=headers, params=params)

def get_case_details(region, parent, case_name):
    """
    Calls the Chronicle API to get case details by caseName.
    """
    token = get_access_token()
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }
    url = f"https://chronicle.{region}.rep.googleapis.com/v1alpha/{parent}/legacy:legacyBatchGetCases"
    params = {'names': case_name}

    print(f"Fetching case details for caseName: {case_name}")

    return make_api_request('GET', url, headers=headers, params=params)

def add_case_tag(siemplify_hostname, siemplify_app_key, case_id, tag):
    """
    Calls the Siemplify API to add a tag to a case.
    """
    url = f"https://{siemplify_hostname}/api/external/v1/dynamic-cases/AddCaseTag"
    params = {'format': 'camel'}
    payload = {
        "caseId": int(case_id),
        "tag": tag
    }
    headers = {
        'Content-Type': 'application/json',
        'AppKey': siemplify_app_key
    }

    print(f"Adding tag '{tag}' to Siemplify Case ID: {case_id}")

    return make_api_request('POST', url, headers=headers, params=params, data=json.dumps(payload))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Chronicle alert case names and tag them in Siemplify.")
    parser.add_argument("--limit", type=int, help="Optional: Limit the number of detection IDs to process.")
    parser.add_argument("--tag", required=True, help="The tag to add to the Siemplify case.")
    parser.add_argument("--debug", action='store_true', help="Enable debug logging to print full JSON payloads on certain errors.")
    args = parser.parse_args()
    load_dotenv()

    # --- Load Environment Variables ---
    chronicle_region = os.getenv("CHRONICLE_REGION")
    chronicle_project = os.getenv("CHRONICLE_PROJECT")
    chronicle_location = os.getenv("CHRONICLE_LOCATION")
    chronicle_instance = os.getenv("CHRONICLE_INSTANCE")
    siemplify_hostname = os.getenv("SIEMPLIFY_HOSTNAME")
    siemplify_app_key = os.getenv("SIEMPLIFY_APP_KEY")

    # --- Validate Environment Variables ---
    if not all([chronicle_region, chronicle_project, chronicle_location, chronicle_instance]):
        print("Error: Please make sure CHRONICLE_REGION, CHRONICLE_PROJECT, CHRONICLE_LOCATION, and CHRONICLE_INSTANCE are set in your .env file.")
        exit(1)
    
    if not all([siemplify_hostname, siemplify_app_key]):
        print("Error: Please make sure SIEMPLIFY_HOSTNAME and SIEMPLIFY_APP_KEY are set in your .env file.")
        exit(1)
    
    # --- Main Logic ---
    parent_path = f"projects/{chronicle_project}/locations/{chronicle_location}/instances/{chronicle_instance}"
    investigations_data = list_investigations(chronicle_region, parent_path)

    if investigations_data and 'investigations' in investigations_data:
        processed_count = 0
        for investigation in investigations_data['investigations']:
            if args.limit and processed_count >= args.limit:
                break
            
            if 'alerts' in investigation and 'ids' in investigation['alerts']:
                for detection_id in investigation['alerts']['ids']:
                    if args.limit and processed_count >= args.limit:
                        print(f"Limit of {args.limit} detection IDs reached. Stopping.")
                        break
                    
                    alert_data = get_alert(chronicle_region, parent_path, detection_id)
                    if alert_data:
                        if 'alert' in alert_data and 'caseName' in alert_data['alert']:
                            case_name = alert_data['alert']['caseName']
                            case_details = get_case_details(chronicle_region, parent_path, case_name)
                            
                            if case_details and 'cases' in case_details and len(case_details['cases']) > 0:
                                soar_case_id = case_details['cases'][0]['soarPlatformInfo']['caseId']
                                
                                # Extract additional fields for output
                                rule_name = "N/A"
                                alert_state = "N/A"
                                if 'detection' in alert_data['alert'] and len(alert_data['alert']['detection']) > 0:
                                    first_detection = alert_data['alert']['detection'][0]
                                    rule_name = first_detection.get('ruleName', 'N/A')
                                    alert_state = first_detection.get('alertState', 'N/A')

                                print(f"Detection ID: {detection_id}, Rule Name: {rule_name}, Alert State: {alert_state}, Case Name: {case_name}, SOAR Case ID: {soar_case_id}")

                                # Add tag to Siemplify case
                                tag_response = add_case_tag(siemplify_hostname, siemplify_app_key, soar_case_id, args.tag)
                                if tag_response:
                                    print(f"Successfully added tag '{args.tag}' to Siemplify Case ID: {soar_case_id}")
                                else:
                                    print(f"Failed to add tag '{args.tag}' to Siemplify Case ID: {soar_case_id}")
                            else:
                                print(f"Warning: Could not retrieve SOAR Case ID for Detection ID: {detection_id}, Case Name: {case_name}.")
                        else:
                            print(f"Warning: Alert data for detection ID {detection_id} found, but 'caseName' is missing in 'alert' object.")
                            if args.debug:
                                print("--- Full Alert Data (Debug Mode) ---")
                                print(json.dumps(alert_data, indent=2))
                                print("------------------------------------")
                    else:
                        print(f"Error: Failed to retrieve alert data for detection ID: {detection_id}. Skipping.")
                    
                    processed_count += 1
    else:
        print("No investigations found or an error occurred.")
