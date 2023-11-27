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

# IOC Expiration
# - 

# - Match to your online SIEM retention 
SIEM_DATA_RETENTION=-365

IP_ADDRESS_VALID_FROM=SIEM_DATA_RETENTION
IP_ADDRESS_EXPIRES_AFTER=90

DOMAIN_NAME_VALID_FROM=SIEM_DATA_RETENTION
DOMAIN_NAME_EXPIRES_AFTER=30

#TODO(): URLs could be made more fine grained depending on the category, e.g, Phishing is 14 but Malware is 90
URL_VALID_FROM=-SIEM_DATA_RETENTION
URL_EXPIRES_AFTER=30

# Hash
# - Always malicious, and hence are not aged out
FILE_VALID_FROM=SIEM_DATA_RETENTION
FILE_EXPIRES_AFTER=36500 #10 Years

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
      "singapore": "https://asia-southeast1-malachiteingestion-pa.googleapis.com",
      "us": "https://malachiteingestion-pa.googleapis.com",
      "london": "https://europe-west2-malachiteingestion-pa.googleapis.com",
      "sydney": "https://australia-southeast1-malachiteingestion-pa.googleapis.com",
      "telaviv": "https://me-west1-malachiteingestion-pa.googleapis.com",
      "frankfurt": "https://europe-west3-malachiteingestion-pa.googleapis.com",
      "zurich": "https://europe-west6-malachiteingestion-pa.googleapis.com"
  }
  if region not in REGIONS:
      raise ValueError("Invalid region. See https://cloud.google.com/terms/secops/data-residency.")
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
      "limit": 100,
      "include_threat_rating": "true",
      "include_category": "true",
      "include_attribution": "true",
      "include_verdict":"true",
      "include_misp": "false"
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

def is_nested_verdict(object,source):
    """
    Test if a MATI API 'reasoning' object contains a nested verdict,
    and calls the generate_ioc_stats function with either the top level
    or nested 'reasoning' object

    Args:
      object: 'reasoning' object from the MATI API, and the 'source' provider

    Returns:
      Calls generate_ioc_stats
    """  
    is_nested = False
    try:
      for key in object:
        if isinstance(object[key], dict):
          is_nested = True
      if is_nested is True:
        return generate_ioc_stats(object[key],object['name'])
      elif is_nested is False:
        return generate_ioc_stats(object,source)      
    except Exception as e:
      pass

def extract_two_digits(value):
    """
    Converts MATI confidence score from FLOAT to INT for use in UDM,
    Args:
      value: the confidence score from a verdict

    Returns:
      An int representation of the Confidence Score
    """  
    import re
    pattern = r"\.\d{2}"
    match = re.search(pattern, str(value))
    if match:
        return match.group()[1:]
    else:
        return None

def generate_ioc_stats(object,source):
    """
    Converts a MATI API 'reasoning' object into a Chronicle UDM IOC_Stat object

    Args:
      object: the 'reasoning' object from the MATI API

    Returns:
      A dictionary formated as a UDM IOC_Stat type
    """  
    tmp_object = {}
    try:
      tmp_object['benign_count'] = object['benign_count']
      tmp_object['malicious_count'] = object['malicious_count']
      tmp_object['first_level_source'] = source
      tmp_object['second_level_source'] = object['name']
      tmp_object['response_count'] = object['response_count']
      tmp_object['source_count'] = object['source_count']
      if 'confidence' in object:
          if object['confidence'] == "high":
              tmp_object['quality'] = "HIGH_CONFIDENCE"
          elif object['confidence'] == "med":
              tmp_object['quality'] = "MEDIUM_CONFIDENCE"
          elif object['confidence'] == "low":
              tmp_object['quality'] = "LOW_CONFIDENCE"
      return tmp_object
    except KeyError:
      return None




def send_iocs_to_chronicle(iocs):
  import urllib.parse

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

    # Chronicle Detection Engine does not support Bool types
    additionals['is_publishable'] = str(indicator['is_publishable'])

    # Debugging to see original API response - not recommended for production usage
    # additionals['json_log'] = json.dumps(indicator)

    # threat_rating - no suitable UDM 
    if 'threat_rating' in indicator:
      if 'confidence_level' in indicator['threat_rating']:
        additionals['threat_rating.confidence_level'] = indicator['threat_rating']['confidence_level']
      if 'confidence_score' in indicator['threat_rating']:
        additionals['threat_rating.confidence_score'] = str(indicator['threat_rating']['confidence_score'])
      if 'severity_level' in indicator['threat_rating']:
        additionals['threat_rating.severity_level'] = indicator['threat_rating']['severity_level']
      if 'severity_reason' in indicator['threat_rating']:
        for index, reason in enumerate(indicator['threat_rating']['severity_reason']):
          additionals['threat_rating.severity_reason[{}]'.format(index)] = reason                                                             
      if 'threat_score' in indicator['threat_rating']:
        additionals['threat_rating.threat_score'] = str(indicator['threat_rating']['threat_score'])                                                     

    if 'attribution' in indicator:
      for index, attribution in enumerate(indicator['attribution']):
        additionals['attribution[{}]'.format(index)] = attribution

    # if enabled, include MISP values
    try:
      for misp_key, misp_value in indicator['misp'].items():
        # only print MISP sources where the value is True
        if misp_value is True:
          additionals[misp_key] = misp_value
    except KeyError:
      pass

    # >>> METADATA
    metadata['vendor_name'] = "MANDIANT_CUSTOM_IOC "
    metadata['product_name'] = "MANDIANT_CUSTOM_IOC "
    metadata['collected_timestamp'] = str(now())
    metadata['product_entity_id'] = indicator['id']

    # metadata.threat
    threat['confidence_details'] = str(indicator['mscore'])

    threat['first_discovered_time'] = indicator['first_seen']
    threat['last_updated_time'] = indicator['last_updated']

    tmp_category_details = []
    try:    
      for category in indicator['category']:
        tmp_category_details.append(category)

      if tmp_category_details:
        threat['category_details'] = tmp_category_details
    except KeyError:
      pass

    if indicator['verdict']:
      verdict_info = {}
      if indicator['verdict']['authoritativeVerdict']:
        match indicator['verdict']['authoritativeVerdict']:
          case "mlVerdict":
            verdict_info['verdict_type'] = "PROVIDER_ML_VERDICT" 
            # fix timestamp
            # Chronicle SIEM doesn't accept nanoseconds or timezone as 4 digits
            indicator['verdict']['mlVerdict']['timestamp'] = indicator['verdict']['mlVerdict']['timestamp'][:-8]
            if 'verdict_time' in verdict_info: verdict_info['verdict_time'] = indicator['verdict']['mlVerdict']['timestamp'] + "Z" 
            # convert the confidence_score from a float to a two digit integer
            if 'confidence_score' in verdict_info: verdict_info['confidence_score'] = extract_two_digits(indicator['verdict']['mlVerdict']['confidenceScore'])
            if 'verdict_response' in verdict_info: verdict_info['verdict_response'] = indicator['verdict']['mlVerdict']['verdict'].upper()
            if 'malicious_count' in verdict_info: verdict_info['malicious_count'] = indicator['verdict']['mlVerdict']['reasoning']['malicious_count']
            if 'source_count' in verdict_info: verdict_info['source_count'] = indicator['verdict']['mlVerdict']['reasoning']['source_count']
            if 'response_count' in verdict_info: verdict_info['response_count'] = indicator['verdict']['mlVerdict']['reasoning']['response_count']
            if 'benign_count' in verdict_info: verdict_info['benign_count'] = indicator['verdict']['mlVerdict']['reasoning']['benign_count']
            if 'neighbour_influence' in verdict_info: verdict_info['neighbour_influence'] = indicator['verdict']['mlVerdict']['neighbour_influence']

            ioc_stats = []  

            # Mandiant verdicts
            if 'mandiant' in indicator['verdict']['mlVerdict']['reasoning']: 
              for mandiant in indicator['verdict']['mlVerdict']['reasoning']['mandiant']:
                if type(indicator['verdict']['mlVerdict']['reasoning']['mandiant'][mandiant]) is dict:
                  this_ioc_stat = {}
                  this_ioc_stat = generate_ioc_stats(indicator['verdict']['mlVerdict']['reasoning']['mandiant'][mandiant],"Mandiant")
                  ioc_stats.append(this_ioc_stat)

            # Third Party verdicts
            if 'tp' in indicator['verdict']['mlVerdict']['reasoning']: 
              for tp in indicator['verdict']['mlVerdict']['reasoning']['tp']:
                if type(indicator['verdict']['mlVerdict']['reasoning']['tp'][tp]) is dict:
                  this_ioc_stat = {}
                  this_ioc_stat = is_nested_verdict(indicator['verdict']['mlVerdict']['reasoning']['tp'][tp],"Third Party")
                  if this_ioc_stat is not None: ioc_stats.append(this_ioc_stat)

              # Threat Intelligence Feed verdicts
              if 'tif' in indicator['verdict']['mlVerdict']['reasoning']['tp']: 
                for tif in indicator['verdict']['mlVerdict']['reasoning']['tp']['tif']:
                    this_ioc_stat = {}
                    this_ioc_stat = is_nested_verdict(indicator['verdict']['mlVerdict']['reasoning']['tp']['tif'][tif],"Threat Intelligence Feeds")
                    if this_ioc_stat is not None: ioc_stats.append(this_ioc_stat)

            verdict_info['ioc_stats'] = ioc_stats 

          case "analystVerdict":
            verdict_info['verdict_type'] = "ANALYST_VERDICT"

            # fix timestamp
            # Chronicle SIEM doesn't accept nanoseconds or timezone as 4 digits
            indicator['verdict']['analystVerdict']['timestamp'] = indicator['verdict']['analystVerdict']['timestamp'][:-8]
            if 'verdict_time' in verdict_info: verdict_info['verdict_time'] = indicator['verdict']['analyst']['timestamp'] + "Z" 
            # convert the confidence_score from a float to a two digit integer
            if 'confidence_score' in verdict_info: verdict_info['confidence_score'] = extract_two_digits(indicator['verdict']['analyst']['confidenceScore'])
            if 'verdict_response' in verdict_info: verdict_info['verdict_response'] = indicator['verdict']['analyst']['verdict'].upper()
            if 'malicious_count' in verdict_info: verdict_info['malicious_count'] = indicator['verdict']['analyst']['reasoning']['malicious_count']
            if 'source_count' in verdict_info: verdict_info['source_count'] = indicator['verdict']['analyst']['reasoning']['source_count']
            if 'response_count' in verdict_info: verdict_info['response_count'] = indicator['verdict']['analyst']['reasoning']['response_count']
            if 'benign_count' in verdict_info: verdict_info['benign_count'] = indicator['verdict']['analyst']['reasoning']['benign_count']
            if 'neighbour_influence' in verdict_info: verdict_info['neighbour_influence'] = indicator['verdict']['analyst']['neighbour_influence']

            ioc_stats = []  

            # Mandiant verdicts
            if 'mandiant' in indicator['verdict']['analystVerdict']['reasoning']: 
              for mandiant in indicator['verdict']['analystVerdict']['reasoning']['mandiant']:
                if type(indicator['verdict']['analystVerdict']['reasoning']['mandiant'][mandiant]) is dict:

                  this_ioc_stat = {}
                  this_ioc_stat = generate_ioc_stats(indicator['verdict']['analystVerdict']['reasoning']['mandiant'][mandiant],"Mandiant")
                  ioc_stats.append(this_ioc_stat)

            # Third Party verdicts
            if 'tp' in indicator['verdict']['analystVerdict']['reasoning']: 
              for tp in indicator['verdict']['analystVerdict']['reasoning']['tp']:
                if type(indicator['verdict']['analystVerdict']['reasoning']['tp'][tp]) is dict:
                  this_ioc_stat = {}
                  this_ioc_stat = is_nested_verdict(indicator['verdict']['analystVerdict']['reasoning']['tp'][tp],"Third Party")
                  if this_ioc_stat is not None: ioc_stats.append(this_ioc_stat)

              # Threat Intelligence Feed verdicts
              if 'tif' in indicator['verdict']['analystVerdict']['reasoning']['tp']: 
                for tif in indicator['verdict']['analystVerdict']['reasoning']['tp']['tif']:

                    this_ioc_stat = {}
                    this_ioc_stat = is_nested_verdict(indicator['verdict']['analystVerdict']['reasoning']['tp']['tif'][tif],"Threat Intelligence Feeds")
                    if this_ioc_stat is not None: ioc_stats.append(this_ioc_stat)

                verdict_info['ioc_stats'] = ioc_stats

      threat['verdict_info'] = verdict_info

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
        interval['start_time'] = subtract_offset(now(),DOMAIN_NAME_VALID_FROM)
        interval['end_time'] = subtract_offset(now(),DOMAIN_NAME_EXPIRES_AFTER)

      case "ipv4":
        entity['ip'] = indicator['value']
        metadata['entity_type'] = 'IP_ADDRESS'
        interval['start_time'] = subtract_offset(now(),IP_ADDRESS_VALID_FROM)
        interval['end_time'] = subtract_offset(now(),IP_ADDRESS_EXPIRES_AFTER)

      case "url":
        # remove the http or https protovol from URL if your log source doesn't record this
        #sanitized_url = fix_url(indicator['value'],"^http(s)?://")
        #entity['url'] = sanitized_url
        entity['url'] = indicator['value']
        metadata['entity_type'] = 'URL'
        interval['start_time'] = subtract_offset(now(),URL_VALID_FROM)
        interval['end_time'] = subtract_offset(now(),URL_EXPIRES_AFTER)

      case "md5":
        file['md5'] = indicator['value']
        metadata['entity_type'] = 'FILE'
        entity['file'] = file
        interval['start_time'] = subtract_offset(now(),FILE_VALID_FROM)
        interval['end_time'] = subtract_offset(now(),FILE_EXPIRES_AFTER)        
      case "sha1":
        file['sha1'] = indicator['value']
        metadata['entity_type'] = 'FILE'
        entity['file'] = file
        interval['start_time'] = subtract_offset(now(),FILE_VALID_FROM)
        interval['end_time'] = subtract_offset(now(),FILE_EXPIRES_AFTER)
      case "sha256":
        file['sha256'] = indicator['value']
        metadata['entity_type'] = 'FILE'
        entity['file'] = file
        interval['start_time'] = subtract_offset(now(),FILE_VALID_FROM)
        interval['end_time'] = subtract_offset(now(),FILE_EXPIRES_AFTER)          

    # entity.file
    try:
      for hash in indicator['associated_hashes']:
        match hash['type']:
          case "md5":
            file['md5'] = hash['value']
          case "sha1":
            file['sha1'] = hash['value']
          case "sha256":
            file['sha256'] = hash['value']
    except KeyError:
      pass

    threat['url_back_to_product'] = "https://advantage.mandiant.com/search?query={}".format(urllib.parse.quote(indicator['value']))

    # build the top level UDM Objects
    metadata['threat'] = threat
    metadata['interval'] = interval

    #create the final UDM event
    event = {}
    event['metadata'] = metadata
    event['entity'] = entity
    event['additional'] = additionals    
    events.append(event)

  print(json.dumps(events))

  if events:
   create_entity_v2(json.dumps(events),'MANDIANT_CUSTOM_IOC')
   print("IOCs were returned during this iteration.")
  else:
   print("No IOCs were returned during the given interval and filter criteria.")

def main(req):  
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
            print("no more results") # this will never actuall get here
            break
        except KeyError:
          print('No more pages.')
  except KeyError:
    print('No more pages.')

  return "Ingestion completed."
