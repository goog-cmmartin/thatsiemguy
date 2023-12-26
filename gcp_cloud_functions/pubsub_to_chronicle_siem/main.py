import argparse
import typing
from typing import Optional
import logging
from concurrent import futures
from google.cloud import pubsub_v1
import ast
import os
import sys
import json
import requests

logging.basicConfig(level=logging.INFO)

def main(req):
    global CHRONICLE_INGESTION_API_KEY, CHRONICLE_DATA_TYPE, REGION, CHRONICLE_NAMESPACE

    global PAYLOAD_SIZE, PAYLOAD
    PAYLOAD_SIZE = 0
    PAYLOAD = {}

    # Region - set to None (not 'None') for US
    REGION = os.environ.get('REGION', None)

    CHRONICLE_NAMESPACE = str(os.environ.get('CHRONICLE_NAMESPACE'))
    CHRONICLE_DATA_TYPE = str(os.environ.get('CHRONICLE_DATA_TYPE'))
    CHRONICLE_INGESTION_API_KEY = str(os.environ.get('CHRONICLE_INGESTION_API_KEY'))

    project_id = str(os.environ.get('PROJECT_ID'))

    subscription_id = str(os.environ.get('SUBSCRIPTION_ID'))

    subscriber = pubsub_v1.SubscriberClient()
    # The `subscription_path` method creates a fully qualified identifier
    # in the form `projects/{project_id}/subscriptions/{subscription_id}`
    subscription_path = subscriber.subscription_path(project_id, subscription_id)

    def callback(message: pubsub_v1.subscriber.message.Message) -> None:
        message.ack()
        data = (message.data).decode('utf-8')
        data = json.loads(data)
        build_payload(data)

    future = subscriber.subscribe(subscription_path, callback=callback)

    with subscriber:
        try:
            future.result(timeout=5)
        except futures.TimeoutError:
            future.cancel()  # Trigger the shutdown.
            future.result()  # Block until the shutdown is complete.

    if PAYLOAD_SIZE > 0:
        send_to_chronicle(PAYLOAD,REGION)

    return 'OK'

def build_payload(log):
    global PAYLOAD_SIZE, PAYLOAD, CHRONICLE_DATA_TYPE, REGION, CHRONICLE_NAMESPACE

    if PAYLOAD_SIZE == 0:
        # Build a new object
        PAYLOAD = {}
        PAYLOAD['namespace'] = CHRONICLE_NAMESPACE
        PAYLOAD['log_type'] = CHRONICLE_DATA_TYPE
        PAYLOAD['entries'] = []
        log = json.dumps(log)
        PAYLOAD['entries'].append({'log_text':log})
        PAYLOAD_SIZE = PAYLOAD_SIZE + (sys.getsizeof(json.dumps(PAYLOAD)))
    else:
        log = json.dumps(log)
        logsize = sys.getsizeof(json.dumps(log))
        #send when the payload hits a certain size
        if PAYLOAD_SIZE + logsize > 500000:
            send_to_chronicle(PAYLOAD,REGION)
            PAYLOAD_SIZE = 0
            PAYLOAD = {}
            PAYLOAD['namespace'] = CHRONICLE_NAMESPACE
            PAYLOAD['log_type'] = CHRONICLE_DATA_TYPE
            PAYLOAD['entries'] = []
        # Append the event
        PAYLOAD['entries'].append({'log_text':log})
        PAYLOAD_SIZE = PAYLOAD_SIZE + (sys.getsizeof(json.dumps(log)))

    return 'ok'


def send_to_chronicle(data,region):
    global CHRONICLE_INGESTION_API_KEY
    if region:
        http_endpoint = ('https://' + region.lower() + '-malachiteingestion-pa.googleapis.com/v1/unstructuredlogentries?key=' + CHRONICLE_INGESTION_API_KEY)
    else:
        http_endpoint = ('https://malachiteingestion-pa.googleapis.com/v1/unstructuredlogentries?key=' + CHRONICLE_INGESTION_API_KEY)
    headers = {'content-type': 'application/json'}
    try:
        r = requests.post(url = http_endpoint, data = json.dumps(data), headers = headers)
    except ConnectionError as e:
        print(e)
        send_to_chronicle(data,region)

    print ("Chronicle API Response: " + r.text)

    return 'OK'
