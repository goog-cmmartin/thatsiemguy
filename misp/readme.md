# MISP (JSON) to Chronicle SIEM Integration

</br>

## Overview

This repo provides an integration between the MISP Threat Intelligence Platform and Chronicle SIEM to automate IOC matching using Chronicle SIEM's Entity Graph and YARA-L Detection Engine.  The integration is a fork of the [Chronicle SIEM 3rd Party Ingestion script](https://github.com/chronicle/ingestion-scripts) for MISP, with updates to improve the ingestion of the JSON MISP format.

* Cloud Function
* Chronicle SIEM
    * Parser
    * YARA-L Detection Rules
    * Dashboard

Each Attribute within a MISP Event will be created as a Entity Graph IOC context record:

```
metadata.product_entity_id"6f030595-65a3-4ec1-9a8d-fafe54ebe89b"
metadata.collected_timestamp"2023-07-30T13:00:29.270910Z"
metadata.vendor_name"misp-project.org"
metadata.product_name"MISP Threat Sharing"
metadata.entity_type"FILE"
metadata.description"Test Event 40"
metadata.interval.start_time"2022-07-30T12:43:26Z"
metadata.interval.end_time"2024-07-29T12:43:26Z"
metadata.threat[0].severity"HIGH"
metadata.threat[0].severity_details"1"
metadata.threat[0].url_back_to_product"https://misp.demo.altostrat.com/events/view/3728505"
metadata.threat[0].threat_feed_name"ORGNAME"
metadata.threat[1].category_details[0]"Payload delivery"
metadata.threat[1].description"filename:foobar.exe"
metadata.threat[1].threat_id"cc7632a0-ab61-4e55-993f-969d51128872"
metadata.threat[2].category_details[0]"Other"
metadata.threat[2].description"text:FooBar Installer"
metadata.threat[2].threat_id"982516be-edaf-451b-bb91-77ff89ed7c15"
metadata.threat[3].category_details[0]"Payload delivery"
metadata.threat[3].description"md5:a8f5f167f44f4964e6c998dee827110c"
metadata.threat[3].threat_id"6f030595-65a3-4ec1-9a8d-fafe54ebe89b"
metadata.event_metadata.base_labels.log_types[0]"MISP_IOC"
metadata.event_metadata.base_labels.namespaces[0]""
entity.file.md5"a8f5f167f44f4964e6c998dee827110c"
entity.file.full_path"foobar.exe"
additional.fields["attribute_count"]"3"
additional.fields["distribution_string"]"5 - Inherit Event"
```

</br>

## Pre-requisites

To utilize this integration requires the following pre-requisites:
* Your Chronicle SIEM instance region
    * Within the Cloud Function environment variable enter 'us' for a North America instance, or the base URL without the hyphen for a non-us instance, e.g., for `foo-europe` the region value is `europe`.
* Chronicle Customer ID
    * A GUID found under Settings within the Chronicle UI
* Ingestion JSON Developer Service Account
    * If you do not have this contact your Account team or Partner.  Usually a JSON Developer Service account file including the string `ing` if a Chroncle provisioned service account.

</br>

## Integration Notes

### Supported MISP Attribute Types

The Cloud Function will export all MISP Attributes within an Event; however, the Chronicle Parser only supports specific Attribute types as follows:

| MISP Attribyte Type    | Chronicle UDM Entity Metadata Type |
|------------------------|------------------------------------|
| ip-src                 | IP_ADDRESS                         |
| ip-dst                 | IP_ADDRESS                         |
| ip-dst\|port           | IP_ADDRESS                         |
| ip-src\|port           | IP_ADDRESS                         |
| domain\|ip             | DOMAIN_NAME                        |
| domain                 | DOMAIN_NAME                        |
| hostname               | DOMAIN_NAME                        |
| url                    | URL                                |
| filename\|md5          | FILE                               |
| filename\|sha1         | FILE                               |
| filename\|sha256       | FILE                               |
| md5                    | FILE                               |
| sha1                   | FILE                               |
| sha256                 | FILE                               |
| filename               | FILE                               |
| email                  | USER                               |
| email-src              | USER                               |
| email-dst              | USER                               |
| whois-registrant-email | USER                               |

### Indicator Start and End Dates

Chronicle SIEM's Entity Graph supports a start and end date for when an IOC is considered valid. During this time, the IOC will be actively matched against UDM Event Data. However, the start and end range of when an IOC should be considered valid is subjective. Therefore, this integration attempts to make that a user configurable option.

While a MISP Event Attribute can include a first and last seen value, this is not a suitable time value for the range of when you should match the IOC against your Event data. This is because not all IOCs are of equal value. You may wish to age out certain indicators quicker than others. For example, you may want to age out an IP address IOC in X days, Domains after Y days, and never age out Hashes.

You can configure the following variables in the Cloud Function code as needed to set historical and future aging values.  The default value is 365 days, i.e., a an IOC published today will be valid for -365 days and +365 days.


```
# Configure per MISP type IOC expiration
IP_ADDRESS_EXPIRATION=365
DOMAIN_NAME_EXPIRATION=365
URL_EXPIRATION=365
FILE_EXPIRATION=365
USER_EXPIRATION=365
CATCH_ALL_EXPIRATION=365
```

Optionally, you can overwrite these with static values if you require different start and end dates by chaning the <type>_EXPIRATION value for interval_start or interval_end:

```
     # IP_ADDRESS
     if attr['type'] in ("ip-src","ip-dst","ip-dst|port","ip-src|port"): 
         attr['interval_start'] = subtract_epoch(attribute_timestamp,-IP_ADDRESS_EXPIRATION)
         attr['interval_end'] = subtract_epoch(attribute_timestamp,IP_ADDRESS_EXPIRATION)
```


### Chronicle SIEM's Ingestion API Limits 
The Chronicle SIEM Ingestion API Limits has a limit of 1 Megabyte per log message.  A single MISP Event in JSON format can exceed this, and a batch of MISP Events will nearly always exceed the 1 Megabyte limit.  The Cloud Function used in this integration takes each individual Attribute within a MISP Event and creates a unique UDM Entity Event to ensure staying within the 1MB limit. 

### MISP RestSearch Query

The Cloud Function  updated to use the `publish_timestamp` over `timestamp` and can be udpated int the `params` variable.

</br>

## Setup Notes

The following notes are high level guidance, and not a complete step by step guide.  You will have to adapt to your environment accordingly.

1. Install MISP on GCP

Use the official MISP installation guide to install MISP on an Ubuntu 22 LTS VM:
http://misp.github.io/MISP/xINSTALL.ubuntu2204.html

A 2+ core VM with 8GB to 16GB of RAM is recommended: 
https://www.misp-project.org/sizing-your-misp-instance

Tips:
* When running the installatio bash script you can redirect the script output to a text file, e.g., `bash /tmp/INSTALL.sh -A | tee setup.log`.  Make sure to remove and securely store the credentials in this output file.
* You can use Chrome Remote Desktop to quickly access the VM - https://cloud.google.com/architecture/chrome-desktop-remote-on-compute-engine

2. Create a MISP API key

You can create an API key within the MISP UI under `Administration > List Auth Keys`.

3. Create Secrets in GCP Secret Manager

The Cloud Function uses GCP's Secret Manager to securely store API credentials for both a) Chronicle Ingestion API Credentials and b) MISP API Key.

```
gcloud secrets create MISP-API --data-file=/home/user/misp.key 
gcloud secrets create CHRONICLE-INGESTION-API --data-file=/home/user/chronicle-ingestion-key.json
```

Remember to grant Secret Manager Secret Accessor to the GCP Secret your Cloud Function service account.  Make sure there are no trailing line feed or carriage returns in the MISP API secret.

4) Create a serverless VPC

A [Serverless VPC](https://cloud.google.com/functions/docs/networking/connecting-vpc) is required for the Cloud Function to be able to access your MISP instance, e.g., within Cloud Shell:

```
CONNECTOR_NAME="eu4-vpcaccess" 
REGION="europe-west4"
SUBNET="prod-security-vpcaccess"
HOST_PROJECT_ID="prod-shared-vpc"

gcloud compute networks vpc-access connectors create $CONNECTOR_NAME \
--region $REGION \
--subnet $SUBNET \
--subnet-project HOST_PROJECT_ID
```

5) Deploy the Cloud Function

Before dpeloying the Cloud Function edit the `.env.yml` file:

```
CHRONICLE_CUSTOMER_ID: <guid found under settings in the Chronicle UI>
CHRONICLE_REGION: <region, us for North America or the region in the URL minus the hypen>
CHRONICLE_SERVICE_ACCOUNT: projects/<gcp-project>/secrets/<secret-name>/versions/<version>
CHRONICLE_NAMESPACE: <optional>
API_KEY: projects/<gcp-project>/secrets/<secret-name>/versions/<version>
TARGET_SERVER: <MISP IP or FQDN>
# Keeping the default value as 5 minutes considering the frequency of data.
POLL_INTERVAL: "5"
ORG_NAME: <your MISP Organization, e.g.,ORGNAME>
```

Deploy the Cloud Function using gcloud:

```
REGION="europe-west4"
VPCCONNECTOR="eu4-vpcaccess"
MEMORY="4096MB"
MIN_INSTANCES="1"

gcloud functions deploy misp-to-chronicle --gen2 --entry-point main --trigger-http --runtime python39 --env-vars-file .env.yml --region $REGION  --vpc-connector $VPCCONNECTOR --memory $MEMORY --min-instances $MIN_INSTANCES
```

6) Create and Publish a Test Event in MISP

Before you can submit the custom MISP Parser into Chronicle SIEM there must be at least one event ingested.  Create and publish a test MISP Event to verify te Cloud Function is working as expected.

In MISP create a manual test event as follows:
```
Category: Payload Delivery
Type: url
value: www.example.com
```

Test the MISP Cloud Function using the Testing tab in the Cloud Functions GCP Console.  

If successful you will see a log message as follows:
```
textPayload: "1 log(s) pushed successfully to Chronicle."
```

if there is are errors, review the logs accordingly, e.g., permission errors, missing environment variables, networking access issues.



