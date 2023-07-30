# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""Fetch data from MISP API."""

from typing import Optional

import time
import requests
import json
import datetime
from datetime import timedelta

from common import env_constants
from common import ingest
from common import status
from common import utils


# Environment variable constants.
ENV_API_KEY = "API_KEY"
ENV_TARGET_SERVER = "TARGET_SERVER"
ENV_ORG_NAME = "ORG_NAME"

# Log type to push data into Chronicle.
CHRONICLE_DATA_TYPE = "MISP_IOC"

# - ip-src -> IP_ADDRESS
# - ip-dst -> IP_ADDRESS
# - ip-dst|port -> IP_ADDRESS
# - ip-src|port -> IP_ADDRESS
# - domain|ip -> DOMAIN_NAME 
# - domain -> DOMAIN_NAME
# - hostname -> DOMAIN_NAME
# - url -> URL
# - filename|md5 -> FILE
# - filename|sha1 -> FILE
# - filename|sha256 -> FILE
# - md5 -> FILE
# - sha1 -> FILE
# - sha256 -> FILE
# - filename -> FILE
# - email -> USER
# - email-src -> USER
# - email-dst -> USER
# - whois-registrant-email -> USER

# Configure per MISP type IOC expiration
IP_ADDRESS_EXPIRATION=365
DOMAIN_NAME_EXPIRATION=365
URL_EXPIRATION=365
FILE_EXPIRATION=365
USER_EXPIRATION=365
CATCH_ALL_EXPIRATION=365

def now():

  # Get the current time
  current_time = datetime.datetime.now()

  # Format the current time
  formatted_time = current_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')

  return formatted_time

def subtract_epoch(epoch, offset):
    datetime_object = datetime.datetime.fromtimestamp(epoch)
    datetime_object = datetime_object + timedelta(days=offset)
    return str(round(datetime_object.timestamp()))

def get_and_ingest_events(api_key: str,
                          target_server: str,
                          start_time: str,
                          org_name: Optional[str] = None):
  """Get logs from 3p resources.

  Args:
    api_key(str): key for authentication.
    target_server(str): 3p resource ip address.
    start_time(str): add time interval in minutes.
    org_name(Optional[str]): organization name to filter data.
  """
  headers = {
      "Authorization": api_key,
      "Accept": "application/json",
      "Content-Type": "application/json",
  }

  params = {
      #"timestamp": f"{start_time}m",
      "publish_timestamp": f"{start_time}m"
  }
  print(f"Retrieving event data from last {start_time}m.")

  # If organization name provided, update params.
  if org_name is not None:
    params["org_name"] = org_name

  misp_event_list = []
  response_events = None

  try:
    url = f"https://{target_server}/events/restSearch"
    req = requests.post(url, json=params, headers=headers, verify=False)

    response_events = req.json()

    if req.status_code != status.STATUS_OK:
      print(f"HTTP Error: {req.status_code}, Reason: {response_events}")

    req.raise_for_status()

    for response in response_events["response"]:
      # response is a dict that stores each MISP Event (Event)
      for key, value in response.items():

        # a dictionary to store the top level MISP fields
        misp_event = {}

        # the first pass through the MISP event builds the base MISP event
        for key2, value2 in value.items():

          # copy all the top level MISP key values into the temporary misp_event 
          # that will hold a single Attribute 
          if type(value2) == type(str()):
            misp_event[key2] = value2

          if key2 == "Org":
            org = {}
            org = value2.copy()
            misp_event[key2] = org.copy()

          if key2 == "Orgc":
            orgc = {}
            orgc = value2.copy()
            misp_event[key2] = orgc.copy()

          # the Tag includes TLPs and other useful fields for filtering and context in YARA-L rules
          if key2 == "Tag":
            tags = {}
            tags = value2.copy()
            misp_event[key2] = tags.copy()

        # once the base misp event is created we re-loop through the same misp event
        # and create a new misp event per individual attribute
        for key2, value2 in value.items():

          if key2 == "Attribute":
            for idx, attr in enumerate(value2):

              # # - if this is 0 then use the current timestamp
              if attr['timestamp'] == "0":
                attribute_timestamp = round(time.time())
              else:
                attribute_timestamp = int(attr['timestamp'])
            
              attribute_dict = {}

              # IP_ADDRESS
              if attr['type'] in ("ip-src","ip-dst","ip-dst|port","ip-src|port"): 
                  attr['interval_start'] = subtract_epoch(attribute_timestamp,-IP_ADDRESS_EXPIRATION)
                  attr['interval_end'] = subtract_epoch(attribute_timestamp,IP_ADDRESS_EXPIRATION)

              # DOMAIN
              elif attr['type'] in ("domain|ip","domain","hostname"): 
                  attr['interval_start'] = subtract_epoch(attribute_timestamp,-DOMAIN_NAME_EXPIRATION)
                  attr['interval_end'] = subtract_epoch(attribute_timestamp,DOMAIN_NAME_EXPIRATION)

              # URL
              elif attr['type'] in ("url"): 
                  attr['interval_start'] = subtract_epoch(attribute_timestamp,-URL_EXPIRATION)
                  attr['interval_end'] = subtract_epoch(attribute_timestamp,URL_EXPIRATION)

              # HASH & FILE
              elif attr['type'] in ("filename|md5","filename|sha1","filename|sha256","md5","sha1","sha256","filename"): 
                  attr['interval_start'] = subtract_epoch(attribute_timestamp,-FILE_EXPIRATION)
                  attr['interval_end'] = subtract_epoch(attribute_timestamp,FILE_EXPIRATION)

              # USER, e.g., email
              elif attr['type'] in ("email","email-src","email-dst","whois-registrant-email"): 
                  attr['interval_start'] = subtract_epoch(attribute_timestamp,-USER_EXPIRATION)
                  attr['interval_end'] = subtract_epoch(attribute_timestamp,USER_EXPIRATION)

              # CATCH ALL for everything else
              else:
                  attr['interval_start'] = subtract_epoch(attribute_timestamp,-CATCH_ALL_EXPIRATION)
                  attr['interval_end'] = subtract_epoch(attribute_timestamp,CATCH_ALL_EXPIRATION)

              # start to create a new MISP event with a single attribute by copying the base fields
              attribute_dict = misp_event.copy()
              attribute_dict["Attribute"] = attr
              
              misp_event_list.append(attribute_dict)

          # Object represents nested Attributes that are grouped together
          # - https://github.com/MISP/misp-objects/tree/main/objects
          if key2 == "Object":

            for i in range(len(value2)):

              misp_object_event = {}
              misp_object_event = misp_event.copy()

              for key3, value3 in value2[i].items():
                
                # Set the interval_start and interval_end
                # Unlike a single MISP Event Attribute, we set the same end and start range for the Array
                if key3 == "timestamp":
                  if value3 == "0":
                    attribute_timestamp = round(time.time())
                  else:
                    attribute_timestamp = int(value3)

                misp_object_event['interval_start'] = subtract_epoch(attribute_timestamp,-CATCH_ALL_EXPIRATION)
                misp_object_event['interval_end'] = subtract_epoch(attribute_timestamp,CATCH_ALL_EXPIRATION)


                # for each Object it will have multiple related attributes
                # get the Object level ID to group related attributes together
                if key3 == "id":
                  this_object_id = value3

                if type(value3) == type(str()):
                  misp_object_event[key3] = value3
          

                # Unlike a single MISP Event Attribute for a MISP Event Object Attribute we copy the entire Array
                if key3 == "Attribute":
                  misp_object_event[key3] = value3.copy()          

              misp_event_list.append(misp_object_event)

    print(f"Retrieved {len(misp_event_list)} MISP events from the last API call.")

    # Ingest the logs to the Chronicle.
    ingest.ingest(misp_event_list, CHRONICLE_DATA_TYPE)

  except Exception as error:
    print(
        "ERROR: Unexpected error occured while fetching events from the MISP"
        " API."
    )
    raise error


def main(req):  # pylint: disable=unused-argument
  """Entrypoint.

  Args:
    req: Request to execute the cloud function.

  Returns:
    string: "Ingestion completed."
  """

  api_key = utils.get_env_var(ENV_API_KEY, is_secret=True)
  # remove newline or carriage return in the MISP secret to avoid auth failures
  api_key = api_key.replace("\n", "").replace("\r", "")
  target_server = utils.get_env_var(ENV_TARGET_SERVER)
  poll_interval = utils.get_env_var(
      env_constants.ENV_POLL_INTERVAL, required=False, default=5)
  org_name = utils.get_env_var(ENV_ORG_NAME)

  get_and_ingest_events(api_key, target_server, poll_interval, org_name)

  return "Ingestion completed."
