from google.auth.transport import requests
from google.oauth2 import service_account

import argparse
import sys
import os
import logging
import base64
import json

import google.auth.transport.requests
import requests


def auth(credentials_file):
    """
    Authenticates a Google API client session using service account credentials.

    This function sets up an authorized session, necessary for making authenticated
    requests to Google APIs that require the Chronicle Backstory and Malachite Ingestion scopes.

    Args:
        credentials_file (str): Path to the service account JSON credentials file.

    Returns:
        requests.AuthorizedSession: A Requests session object authorized with the
                                    provided service account credentials.
    """

    AUTHORIZATION_SCOPES = [
        "https://www.googleapis.com/auth/chronicle-backstory",
        "https://www.googleapis.com/auth/malachite-ingestion"
    ]

    credentials = service_account.Credentials.from_service_account_file(
        str(credentials_file),
        scopes=AUTHORIZATION_SCOPES
    )

    return requests.AuthorizedSession(credentials)

def ingestion_api_region(region):
    """
    Retrieves the corresponding base URL for a given region.

    This function is used to determine the correct API endpoint
    based on the specified region.

    Args:
        region (str): The abbreviated region name (e.g., "us", "europe", "asia")

    Returns:
        str: The base URL associated with the specified region.

    Raises:
        ValueError: If the provided region is invalid or not found in the mapping.
    """

    REGIONS = {
        "europe": "https://europe-malachiteingestion-pa.googleapis.com",
        "asia": "https://asia-southeast1-malachiteingestion-pa.googleapis.com",
        "us": "https://malachiteingestion-pa.googleapis.com",
    }

    if region not in REGIONS:  # Check if the region is supported
        raise ValueError("Invalid region")

    return REGIONS[region]  # Return the corresponding URL


import json

def create_unstructuredlogentry(auth,customer_id,region,log_type,log_entry,labels,namespace="untagged"):

    authenticated = auth

    data = {}
    if namespace:
        data['namespace'] = namespace        
    data['labels'] = labels
    data['log_type'] = log_type
    data["customer_id"] = customer_id
    data['entries'] = []
    for log in log_entry:
      data['entries'].append({'log_text': log})      
    #data['entries'].append({'log_text': log_entry,'ts_epoch_microseconds':ts_epoch_microseconds})

    json_data = json.dumps(data)

    print ('Event to send:\n' + json_data)

    http_endpoint = '{}/v2/unstructuredlogentries:batchCreate'.format(ingestion_api_region(region))
    headers = {'content-type': 'application/json'}
    r = authenticated.post(url=http_endpoint, data=json_data, headers=headers)

    print(r.text)
    return r

# ---

def get_authorized_session(credentials_file):
    """
    Authenticates a Google API client session using service account credentials.
    """

    AUTHORIZATION_SCOPES = [
        "https://www.googleapis.com/auth/cloud-platform"
    ]

    credentials = service_account.Credentials.from_service_account_file(
        str(credentials_file),
        scopes=AUTHORIZATION_SCOPES
    )

    request = google.auth.transport.requests.Request()
    credentials.refresh(request)

    return credentials.token    


def build_payload(project_id, customer_id, forwarder_id, log_entry):
    """Constructs the payload for the Chronicle ingestion API."""
    return {
        'inline_source': {
            'logs': [log_entry],
            "forwarder": f"projects/{project_id}/locations/us/instances/{customer_id}/forwarders/{forwarder_id}"
        }
    }


def send_to_chronicle(region, project_id, customer_id, log_type, auth_token, payload):
    """Sends the log data to the Chronicle ingestion API."""
    headers = {
        "Authorization": f"Bearer {auth_token}",
        'Content-Type': 'application/json'
    }

    endpoint = f"https://{region}-chronicle.googleapis.com/v1alpha/projects/{project_id}/locations/us/instances/{customer_id}/logTypes/{log_type}/logs:import"

    submission = requests.post(url=endpoint, headers=headers, json=payload)
    return submission
