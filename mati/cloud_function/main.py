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
"""Fetch data from MATI API."""

from typing import Optional

import datetime
import requests
import json
import urllib.parse

from common import env_constants
from common import status
from common import utils

# Environment variables
ENV_CHRONICLE_CUSTOMER_ID = "CHRONICLE_CUSTOMER_ID"
ENV_CHRONICLE_REGION = "CHRONICLE_REGION"
ENV_CHRONICLE_SERVICE_ACCOUNT = "CHRONICLE_SERVICE_ACCOUNT"
ENV_MATI_KEY_ID = "MATI_KEY_ID"
ENV_MATI_SECRET = "MATI_SECRET"
ENV_APP_NAME = "APP_NAME"
ENV_GTE_SCORE = "GTE_SCORE"
ENV_COLLECTION_INTERVAL_MINUTES = "COLLECTION_INTERVAL_MINUTES"

customer_id = utils.get_env_var(ENV_CHRONICLE_CUSTOMER_ID)
region = utils.get_env_var(ENV_CHRONICLE_REGION)
credentials_file = utils.get_env_var(ENV_CHRONICLE_SERVICE_ACCOUNT, is_secret=True)
# load the secret into a dictionary for auth later on
credentials_file = json.loads(credentials_file)

secret_id = utils.get_env_var(ENV_MATI_KEY_ID, is_secret=True)
# remove end of line characters that will error otherwise
secret_id = secret_id.replace("\n", "").replace("\r", "")
secret_key = utils.get_env_var(ENV_MATI_SECRET, is_secret=True)
secret_key = secret_key.replace("\n", "").replace("\r", "")
app_name = utils.get_env_var(ENV_APP_NAME)
gte_score = utils.get_env_var(ENV_GTE_SCORE)
collection_interval_minutes = utils.get_env_var(ENV_COLLECTION_INTERVAL_MINUTES)


# Generate Access Token
def generate_bearer_token(secret_id,secret_key,app_name):

  url = "https://api.intelligence.mandiant.com/token"
  headers = {
      "Content-Type": "application/x-www-form-urlencoded",
      "Accept": "application/json",
      "X-App-Name": "MATI to Chronicle",
  }

  data = {
      "grant_type": "client_credentials",
  }

  auth = requests.auth.HTTPBasicAuth(secret_id, secret_key)

  response = requests.post(url, headers=headers, data=data, auth=auth)

  if response.status_code == 200:
      return response
  else:
      return response.status_code

def generate_epoch_timestamp(offset_minutes):
  """Generates an epoch timestamp.

  Args:
    offset_minutes: The number of minutes to offset the epoch timestamp.

  Returns:
    A float representing the number of seconds since the Unix epoch.
  """
  from time import time
  return int(time() - offset_minutes * 60)

def instance_region(region):
  # note, new regions will need to be added here
  REGIONS = {
      "europe": "https://europe-malachiteingestion-pa.googleapis.com",
      "asia": "https://asia-southeast1-malachiteingestion-pa.googleapis.com",
      "us": "https://malachiteingestion-pa.googleapis.com",
  }
  if region not in REGIONS:
      raise ValueError("Invalid region")
  return str(REGIONS[region])


def get_indicators_first_page(access_token: str, start_epoch: int, gte_score: int):

  url = "https://api.intelligence.mandiant.com/v4/indicator"
  headers = {
      "Authorization": "Bearer {}".format(access_token),
      "Accept": "application/json",
      "X-App-Name": "MATI to Chronicle",
  }

  params = {
      "start_epoch": start_epoch,
      "gte_mscore": gte_score,
      "source": "mandiant",
      "exclude_osint": "True",
      "limit": 1000
  }

  response = requests.get(url, headers=headers, params=params)

  if response.status_code == 200:
      return response
  else:
      return response.status_code

def get_indicators_next_page(access_token: str, next_page: str):
  import requests

  url = "https://api.intelligence.mandiant.com/v4/indicator"
  headers = {
      "Authorization": "Bearer {}".format(access_token),
      "Accept": "application/json",
      "X-App-Name": "MATI to Chronicle",
  }

  params = {
      "next": next_page
    }

  response = requests.get(url, headers=headers, params=params)

  if response.status_code == 200:
      return response
  elif response.status_code == 204:
      return response
  else:
      return response


def auth(credentials):
  from google.auth.transport import requests
  from google.oauth2 import service_account

  AUTHORIZATION_SCOPES = ["https://www.googleapis.com/auth/chronicle-backstory","https://www.googleapis.com/auth/malachite-ingestion"]

  credentials = service_account.Credentials.from_service_account_info(
        credentials,
        scopes=AUTHORIZATION_SCOPES)
  return requests.AuthorizedSession(credentials)


def create_entity_v2(entity_json,log_type):

  authenticated = auth(credentials_file)

  data = {}
  data["customer_id"] = customer_id
  data["log_type"] = log_type
  data["entities"] = []

  data['entities'].append(json.loads(entity_json))

  json_data = json.dumps(data)

  http_endpoint = '{}/v2/entities:batchCreate'.format(instance_region(region))
  headers = {'content-type': 'application/json'}

  r = authenticated.post(url=http_endpoint, data=json_data, headers=headers)

  print(r.text)
  return r

def now():

  # Get the current time
  current_time = datetime.datetime.now()

  # Format the current time
  formatted_time = current_time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')

  return formatted_time

def subtract_offset(timestamp, offset):
  """
  Subtracts the offset from the timestamp and returns the resulting timestamp.

  Args:
    timestamp: The timestamp to subtract the offset from.
    offset: The offset to subtract from the timestamp.

  Returns:
    The resulting timestamp.
  """

  # Convert the timestamp to a datetime object.
  datetime_object = datetime.datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")

  # Convert the offset to a timedelta object.
  timedelta_object = datetime.timedelta(days=-offset)

  # Subtract the offset from the datetime object.
  new_datetime_object = datetime_object - timedelta_object

  # Convert the new datetime object to a timestamp.
  #new_timestamp = new_datetime_object.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
  new_timestamp = new_datetime_object.isoformat(timespec='milliseconds') + "Z"

  return new_timestamp

def fix_url(url,replacement_string):
  """
  Removes specified values from a string, e.g., remove protocol from a URL

  Args:
    timestamp: the URL to update
    replacement_string: the gsub operation you want apply on the URL

  Returns:
    The updated URL as a string.
  """
  import re
  updated_url = re.sub(replacement_string, '', url)
  return updated_url


def send_iocs_to_chronicle(iocs):
  events = []

  for indicator in iocs['indicators']:

    # temporary Dictionaries and Lists to build UDM Nouns
    metadata = {}
    file = {}
    threat = {}
    interval = {}
    entity = {}
    associations = []
    additionals = []

    # >>> ADDITIONAL
    additionals = {}
    additionals['mscore'] = indicator['mscore']
    # Chronicle Detection Engine does not support Bool types, so we convert to String
    additionals['is_publishable'] = str(indicator['is_publishable'])
    for misp_key, misp_value in indicator['misp'].items():
      # only print MISP sources where the value is True
      # - usually for Mandiant sources this is always False
      if misp_value is True:
        additionals[misp_key] =  str(misp_value)

    # >>> METADATA
    metadata['vendor_name'] = "MANDIANT_IOC"
    metadata['product_name'] = "MANDIANT_IOC"
    metadata['collected_timestamp'] = str(now())
    metadata['product_entity_id'] = indicator['id']
    # metadata.interval
    # - these are hardcoded as we rely on the confidence score value to show when an IOC has decayed
    interval['start_time'] = "2000-01-01T00:00:00Z"
    interval['end_time'] = "2100-01-01T00:00:00Z"
    # metadata.threat
    threat['confidence_details'] = str(indicator['mscore'])

    tmp_source_category = []
    for source in indicator['sources']: 
      for category in source['category']:
        tmp_source_category.append(category)

    threat['first_discovered_time'] = indicator['first_seen']
    threat['last_updated_time'] = indicator['last_updated']

    if tmp_source_category:
      threat['category_details'] = tmp_source_category

    try:
      for association in indicator['attributed_associations']:
        tmp_association = {}
        tmp_association['id'] = association['id']
        tmp_association['name'] = association['name']
        tmp_association['type'] = association['type'] 
        associations.append(tmp_association)

      threat['associations'] = associations
    except KeyError:
      pass

    # >>> ENTITY
    # - entity.type
    match indicator['type']:
      case "fqdn":
        entity['hostname'] = indicator['value']
        metadata['entity_type'] = 'DOMAIN_NAME'
        threat['url_back_to_product'] = "https://advantage.mandiant.com/indicator/fqdn/{}".format(indicator['value'])
      case "ipv4":
        entity['ip'] = indicator['value']
        metadata['entity_type'] = 'IP_ADDRESS'
        threat['url_back_to_product'] = "https://advantage.mandiant.com/indicator/ipv4/{}".format(indicator['value'])
      case "url":
        # remove the http or https protovol from the URL as our log sources don't log this
        sanitized_url = fix_url(indicator['value'],"^http(s)?://")
        #entity['url'] = sanitized_url
        entity['url'] = indicator['value']
        threat['url_back_to_product'] = "https://advantage.mandiant.com/indicator/url/{}".format(urllib.parse.quote(indicator['value']))
        metadata['entity_type'] = 'URL'
      case "md5":
        file['md5'] = indicator['value']
        metadata['entity_type'] = 'FILE'
        entity['file'] = file
        threat['url_back_to_product'] = "https://advantage.mandiant.com/indicator/md5/{}".format(indicator['value'])
      case "sha1":
        file['sha1'] = indicator['value']
        metadata['entity_type'] = 'FILE'
        entity['file'] = file
        threat['url_back_to_product'] = "https://advantage.mandiant.com/indicator/sha1/{}".format(indicator['value'])        
      case "sha256":
        file['sha256'] = indicator['value']
        metadata['entity_type'] = 'FILE'
        entity['file'] = file
        threat['url_back_to_product'] = "https://advantage.mandiant.com/indicator/sha256/{}".format(indicator['value'])        
    # entity.file
    try:
      for hash in indicator['associated_hashes']:
        match hash['type']:
          case "md5":
            file['md5'] = hash['value']
            threat['url_back_to_product'] = "https://advantage.mandiant.com/indicator/md5/{}".format(indicator['value'])                    
          case "sha1":
            file['sha1'] = hash['value']
          case "sha256":
            file['sha256'] = hash['value']
    except KeyError:
      pass
    # build the top level UDM Objects
    metadata['threat'] = threat
    metadata['interval'] = interval
    #create the final UDM event
    event = {}
    event['metadata'] = metadata
    event['entity'] = entity
    event['additional'] = additionals    
    events.append(event)

  if events:
    create_entity_v2(json.dumps(events),'MANDIANT_IOC')
    print("IOCs were returned during this iteration.")
  else:
    print("No IOCs were returned during the given interval and filter criteria.")



def main(req):  # pylint: disable=unused-argument
  """Entrypoint.

  Args:
    req: Request to execute the cloud function.

  Returns:
    string: "Ingestion completed."
  """

  bearer_token = generate_bearer_token(secret_id,secret_key,app_name)

  access_token = bearer_token.json()

  epoch = generate_epoch_timestamp(int(collection_interval_minutes)) 

  # get Indicators from MATI API
  # - this is hard coded to retrieve Mandiant sources indicators only
  # - i.e,. the open source indicators are already in Chronicle SIEM
  mati_api_results = get_indicators_first_page(access_token=access_token['access_token'], start_epoch=epoch, gte_score=gte_score)

  next_page = mati_api_results.json()

  send_iocs_to_chronicle(next_page)

  try:
    if next_page['next'] is not None:
      while True:
        response = get_indicators_next_page(access_token=access_token['access_token'], next_page=next_page['next'])
        next_page = response.json()
        send_iocs_to_chronicle(next_page)
        import time
        time.sleep(1)
        try:
          if next_page['next'] is None:
            break
        except KeyError:
          print('No more pages.')
  except KeyError:
    print('No more pages.')

  return "Execution complete."
