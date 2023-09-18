import requests
import json
import re
import time
import datetime
import os
import google.cloud.logging
import logging

URL = "https://cloud.google.com/feeds/chronicle-release-notes.xml"

CHRONICLE_REGION = os.environ['CHRONICLE_REGION']
CHRONICLE_CUSTOMER_ID = os.environ['CHRONICLE_CUSTOMER_ID']
SERVICE_ACCOUNT_FILE = os.environ['SERVICE_ACCOUNT_FILE']
VALID_EVENTS_RANGE = os.environ['VALID_EVENTS_RANGE']
GCP_PROJECT = os.environ['GCP_PROJECT']
DEBUG = os.environ['DEBUG']

def main(req):
  """Downloads and parses Chronicle release notes, and sends them to Chronicle UDM as events.

  Args:
    req: A Cloud Function request object.

  Returns:
    A Cloud Function response object with a status of 200 and a data of "OK".
  """

  # Create a Cloud Logging client.
  client = google.cloud.logging.Client(project=GCP_PROJECT)
  client.setup_logging()

  # Download and convert the Chronicle release notes XML file to JSON.
  result = download_and_convert_xml_to_json(URL)

  # Remove the top-level object from the JSON data.
  result, top_level_object = remove_top_level_object(result)

  # Split the JSON object into a list of events.
  split_json_object(top_level_object)

  # Return a Cloud Function response object with a status of 200 and a data of "OK".
  return '{"status":"200", "data": "OK"}'


def get_secret(secret_id):
  """Retrieves a secret from Secret Manager.

  Args:
    secret_id: The ID of the secret to retrieve.

  Returns:
    The secret value.
  """

  import google.cloud.secretmanager as secretmanager
  client = secretmanager.SecretManagerServiceClient()
  response = client.access_secret_version(request={"name": secret_id})
  payload = response.payload.data.decode("utf-8")
  return payload



def download_and_convert_xml_to_json(url):
  """Downloads and converts an XML file to JSON.

  Args:
    url: The URL of the XML file to download.

  Returns:
    A JSON object representing the XML data.

  Raises:
    Exception: If the XML file cannot be downloaded or converted to JSON.
  """

  import xmltodict

  response = requests.get(url, stream=True)
  if response.status_code != 200:
    raise Exception("Error downloading XML file")

  xml_data = response.content
  json_data = xmltodict.parse(xml_data)

  return json_data


def remove_top_level_object(dictionary):
  """Removes the top-level object from a dictionary.

  Args:
    dictionary: A dictionary.

  Returns:
    A tuple containing the dictionary without the top-level object and the top-level object itself.
  """

  top_level_object = dictionary.pop('feed')
  return dictionary, top_level_object



def generate_guid():
  """Generates a globally unique identifier (GUID).

  Returns:
    A GUID as a hexadecimal string.
  """

  import uuid
  return uuid.uuid4().hex



def region(region):
  """Returns the Chronicle region URL for the given region.

  Args:
    region: The Chronicle region.

  Returns:
    The Chronicle region URL.

  Raises:
    ValueError: If the region is invalid.
  """

  REGIONS = {
      "europe": "https://europe-malachiteingestion-pa.googleapis.com",
      "asia": "https://asia-southeast1-malachiteingestion-pa.googleapis.com",
      "us": "https://malachiteingestion-pa.googleapis.com",
  }

  if region not in REGIONS:
    raise ValueError("Invalid region")
  return REGIONS[region]


def sleep(seconds):
  """Pauses the execution of the program for the given number of seconds.

  Args:
    seconds: The number of seconds to sleep.

  Returns:
    A string indicating that the function is sleeping for the given number of seconds.
  """

  time.sleep(seconds)
  return "Sleeping for {} seconds".format(seconds)


def create_udm_event(event):
    """Creates a UDM event.

    Args:
        event: A JSON string representing the UDM event.

    Returns:
        A JSON object representing the response from the Chronicle UDM API.
    """

    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession    
    from googleapiclient import _auth
    import http

    SCOPES = ['https://www.googleapis.com/auth/malachite-ingestion']

    session = requests.Session()
    data = {}
    data["customer_id"] = CHRONICLE_CUSTOMER_ID
    data["events"] = []
    data["events"].append(json.loads(event, strict=False))
    json_data = json.dumps(data)
    
    try:
        credentials = service_account.Credentials.from_service_account_info(json.loads(get_secret(SERVICE_ACCOUNT_FILE)), scopes=SCOPES)
        http_client = _auth.authorized_http(credentials)
        session = AuthorizedSession(credentials)
        http_endpoint = '{}/v2/udmevents:batchCreate'.format(region(CHRONICLE_REGION))    

        resp = http_client.request(http_endpoint, "POST", body=json_data)
        json_resp = json.loads(resp[1])
        if resp[0].status != http.HTTPStatus.OK:
            logging.info(json_resp.get('error').get('message'))
        else:
            logging.info(json_resp)
    
    except requests.exceptions.RequestException as e:
        logging.info('Error creating UDM event:', e)
        raise e


def now(format, offset):
    """Returns the current date and time in the specified format, with the given offset.

    Args:
      format: The format to return the date and time in. Valid values are "iso8601" and "epoch".
      offset: The offset in seconds to apply to the date and time.

    Returns:
      The current date and time in the specified format, with the given offset.

    Raises:
      ValueError: If the format is invalid or the offset is negative.
    """

    from datetime import timedelta, datetime

    # Cache the result of datetime.now().
    now = datetime.now()

    # Handle invalid values for format.
    if format not in ["iso8601", "epoch"]:
        raise ValueError("Invalid format")

    # Handle invalid values for offset.
    if offset < 0:
        raise ValueError("Invalid offset")

    # Return the date in the desired format.
    if format == "iso8601":
        return now.isoformat() + 'Z'
    elif format == "epoch":
        return int(now.timestamp())


def is_within_interval(timestamp, interval):
    """Checks if the given timestamp is within the given interval.

    Args:
      timestamp: A timestamp in the format `YYYY-MM-DDTHH:MM:SSZ`.
      interval: The interval in seconds.

    Returns:
      True if the timestamp is within the interval, False otherwise.
    """

    # Get the current time in seconds.
    current_time_sec = int(time.time())

    # Convert the timestamp to seconds.
    timestamp_sec = int(datetime.datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S%z').timestamp())

    # Check if the timestamp is within the interval.
    if (timestamp_sec >= current_time_sec - int(interval)) and (timestamp_sec <= current_time_sec + int(interval)):
        if DEBUG == True: 
          logging.info("is_within_interval: true")
        return True
    else:
        return False


def split_json_object(dictionary):

    """Splits the given JSON object into a list of UDM events.

    Args:
      dictionary: A JSON object representing the Chronicle Release notes.

    Returns:
      A list of UDM events.
    """

    # The Chronicle Release notes are in an unstructured format
    # - it requires greping and splitting the text based upon  known keywords
    pattern = re.compile(r'(Feature|Changed|Announcement|Deprecated)')

    events = []
    event = {}

    for entry in dictionary['entry']:

        # remove HTML characters
        update_with_html_chars_removed = re.sub(r'<[^>]+>', '', entry['content']['#text'])

        matches = pattern.split(update_with_html_chars_removed)

        # remove any empty capture groups
        matches = list(filter(None, matches))

        # Create a unique UDM event for each kvp from the unstructured release notes
        # - e.g., [0]Changed, [1]Feature X blah blah blah
        for i in range(0, len(matches), 2):
            if(is_within_interval(entry['updated'],VALID_EVENTS_RANGE)):
                event.update(
                    {"metadata":
                        {
                            "product_log_id": entry['id'],
                            "vendor_name": "Google Cloud",
                            "product_name": "Chronicle SIEM Release Notes",
                            "url_back_to_product": entry['link']['@href'],
                            "event_timestamp": entry['updated'],
                            "collected_timestamp": now("iso8601",0),
                            "event_type": "GENERIC_EVENT",
                            "product_event_type": matches[i],
                            "description": matches[i+1]
                        }
                    },
                )
                events.append(event)
                event = {}

    if bool(events) == True:
        if DEBUG == True:
          logging.info(json.dumps(events))
        create_udm_event(json.dumps(events))
        sleep(1)
        events = []
