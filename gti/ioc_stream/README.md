# GTI IOC_STREAM Custom Parser for Google SecOps

## Overview

An example Python script that can be run either standalone, or else as a GCP Cloud Function, that retrieves results from Virus Total (aka Google Threat Intelligence) IOC Stream, and sends them to Google SecOps.

Live Hunt enables cybersecurity professionals and researchers to proactively hunt for malware and other malicious files in real-time.  When a YARA rules in Livehunt matches a newly submitted file, domain, ip, or url, this match is considered an Indicator of Compromise (IOC). Livehunt generates a notification, effectively creating a stream of IOCs that are relevant to your hunting rules. 

Benefits of implementing this custom integration include:
* Visualization of Live Hunt results using Google SecOps Native Dashboards
* Correlation of IOC_STREAM data with existing UDM Event data in Google SecOps

## Requirements

* Google SecOps (any license Edition)
* Google Threat Intelligence (Enterprise or Enterprise+)
* Google Cloud Platform
- if using GCP Cloud Run

## Python Script Overview

A Python script is used to collect IOC Stream responses from the `ioc_stream` API endpoint in GTI, and send the results into the `logs:import` API endpoint in Google SecOps:

- Configuration: Loads configuration from environment variables, supporting local development via a `.env.local.yml` file.
- Secret Management: Retrieves the VirusTotal API key from Google Cloud Secret Manager.
- Authentication: Obtains a Google Cloud authentication token for Chronicle.
- Data Extraction: Fetches vulnerability data from the VirusTotal API, handling pagination.
- Data Processing: Cleans and sorts the data recursively, removing empty values.
- Data Chunking: Splits the processed data into chunks to comply with Chronicle's size limits.
- Data Submission: Sends the data to Chronicle SIEM.
- Error Handling: Includes retry logic for API requests and comprehensive error logging.
- HTTP Trigger (Cloud Run): Exposes a Flask endpoint for HTTP-triggered execution.

The script was developed and tested using Python version 3.12.

The following Python PIP libraries are used:
- Flask>=2.0
- gunicorn>=20.0
- requests>=2.25
- PyYAML>=5.4
- google-cloud-secret-manager>=2.5
- google-auth>=2.0

---

# Google SecOps Setup

0. Find your Google SecOps GUID

The GUID for your Google SecOps tenant is required as an API parameter.  This can be found from within the UX under Settings > SIEM Settings.

1. Create a Chronicle Forwarder

The Chronicle REST API endpoint `logs:import` requires a Chronicle Forwarder GUID be provided as part of the payload in order to ingest logs programatically.

This will be added to the `CHRONICLE_CUSTOMER_ID` env value later on.

Instructions for adding a Forwarder are availble [here](https://cloud.google.com/chronicle/docs/install/forwarder-management-configurations).  

The `CONFIG ID` will be added to the `CHRONICLE_FORWARDER_ID` env value later on.


---

# Virus Total (GTI) Setup

0. Create a VT API Key

Instructions for creating a VT API key are available [here](https://docs.virustotal.com/docs/please-give-me-an-api-key)

Note, creating a Live Hunt is beyond the scope of this guide, but it is assumed existing Live Hunts are available.  More information on Live Hunts can be found [here](https://docs.virustotal.com/docs/livehunt)

---

# Setup the GCP Cloud Run Function

0. Download this repo from GitHub

Download this repo to your GCP Cloud Shell or local environment if `gcloud` is available.


1. Create a Servicee Account for the Cloud Run Function

Configure the following environment variables in your GCP Cloud Shell:
```
GCP_PROJECT="your-gcp-project"
SA_NAME="sa-gti-ioc-stream-to-secops"
SA_DESCRIPTION="Export GTI IOC Stream to Google SecOps"
SA_DISPLAY_NAME="GTI IOC Stream to Google SecOps"
```

Note, if you are setting up additional GTI to SecOps integrations as listed in this repo, you may wish to genericize this Service Account

Create a Service Account:
```
gcloud iam service-accounts create $SA_NAME --display-name="$SA_DISPLAY_NAME" --description="$SA_DESCRIPTION" --project="$GCP_PROJECT"
```

2. Create a custom GCP IAM Role for Ingesting into Google SecOps

A custom least privilege GCP IAM role is recommended as a best practice rather than using the broad default Google SecOps IAM Roles, e.g., Chronicle API Admin.

Create a text file with the following contents, e.g., chronicle_importer_role.yaml:

```
title: "Chronicle Importer"
description: "Grants permissions to import entities and logs into Chronicle"
stage: "GA"
includedPermissions:
  - chronicle.entities.import
  - chronicle.logs.import
```

Set the following environment variable:
```
SECOPS_CUSTOM_ROLE="ChronicleImporter"
```

Create the custom GCP IAM Role:
```
gcloud iam roles create $SECOPS_CUSTOM_ROLE \
  --project=$GCP_PROJECT \
  --file=chronicle_importer_role.yaml
```

3. Grant the Service Account IAM Roles

Ability to post logs to Google SecOps Ingestion API (via the newer Chronicle REST API) 
```
gcloud projects add-iam-policy-binding $GCP_PROJECT \
    --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" \
    --role="projects/$GCP_PROJECT/roles/$SECOPS_CUSTOM_ROLE"
```

Ability to run Cloud Run Functions
```
gcloud projects add-iam-policy-binding $GCP_PROJECT \
    --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" \
    --role="roles/run.invoker"
```

Ability to run the Cloud Run Function as a Scheduled Job
```
gcloud projects add-iam-policy-binding $GCP_PROJECT \
    --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" \
    --role="roles/cloudscheduler.jobRunner"
```

4. Deploy the GCP Cloud Run Function

Modify the env.local.yaml parameters as needed to match your environment:

```
GCP_PROJECT_ID: "GCP_PROJECT_ID"
VT_API_KEY_SECRET_NAME: "VT_API_KEY_SECRET_NAME"
VT_API_KEY_SECRET_VERSION: "latest"
CHRONICLE_CUSTOMER_ID: "GUID"
CHRONICLE_FORWARDER_ID: "GUID"
CHRONICLE_LOG_TYPE: "INSTANCE_GTI_CVE"
CHRONICLE_REGION: "us"
NAMESPACE: ""
USE_CASE_NAME: "virustotal_cve_import"
VT_FILTERS: "collection_type:vulnerability last_modification_date:60m+"
VT_ORDER: "last_modification_date+"
VT_LIMIT: "10"

```


Set the following environment variables.  Note, change the GCP region as needed.
```
CLOUD_RUN_FUNCTION_NAME="cf-p-gti-ioc-stream-to-secops"
CLOUD_RUN_REGION="us-central1"
```

Deploy as a GCP Cloud Run Function:
```
gcloud run deploy $CLOUD_RUN_FUNCTION_NAME \
    --source . \
    --platform managed \
    --region $CLOUD_RUN_REGION \
    --service-account $SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com \
    --env-vars-file ./.env.local.yml \
    --no-allow-unauthenticated \
    --timeout=3600 \
    --memory=1024Mi
```

5. Set a Cloud Scheduler task to run the Cloud Run Function 

Set the following environment variables.  Note, the SERVICE_URL you can copy from the GCP Cloud Run Function page.

```
SERVICE_URL="https://cf-p-gti-ioc-stream-to-secops-12345678910.us-central1.run.app"
INVOKER_SA_EMAIL="$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com"
```

Create a scheduled task to run the Cloud Run Function.

```
gcloud scheduler jobs create http trigger-$CLOUD_RUN_FUNCTION_NAME \ 
    --schedule="0 * * * *"  \
    --time-zone="Europe/Amsterdam" \
    --uri="${SERVICE_URL}/" \
    --http-method="POST" \ 
    --oidc-service-account-email="${INVOKER_SA_EMAIL}" \
    --description="Triggers the VirusTotal to Chronicle Cloud Run Service endpoint every hour" \
    --location="$CLOUD_RUN_REGION"
```

The schedule parameter is set to every hour, and should match the lookback period as specified in the `VT_DATE_FILTER` env variable:

```
VT_DATE_FILTER: "-1h"
```

If you want to customize the internal you can use [crontab.guru](https://crontab.guru/) to calculate a new cron parameter accordingly.

---

# Setup the IOC Stream log source and parser in Google SecOps

1. Create a new Custom Log Type

A custom `LOG_TYPE` is required for this integration, and the instructions for creating one in Google SecOps are available [here](https://cloud.google.com/chronicle/docs/event-processing/request-log-type).

It is recommended to prefix any custom `LOG_TYPE` with a unique code for your tenant as they are globally unique, e.g., `ACME_IOC_STREAM`.

Note, at the time of writing, there is a delay between a custom Log Type being created and being available.  This has been observed to be in the area of 1 to 2 hours.


2. Add a custom Parser

A custom Parser is required for this integration to normalize the IOC Stream data into Google SecOps UDM mode.

Instructions for creating a custom Parser are available [here](https://cloud.google.com/chronicle/docs/event-processing/manage-parser-updates#manage_custom_parser_updates)

A copy of the custom parser is availeble [here](custom_parser/ioc_stream.parser)


3. Optionally, modify Auto Extraction

Auto Extraction is a feature whereby Google SecOps will extract out key value pairs for supported formats, such as JSON, into the UDM top level object `extracted["key"] = "value"` format.

Not all values from the original IOC Stream field are mapped to UDM, and so it is recommended to review these mappings and customize accordingly.




# Troubleshooting

*   **Cloud Run Function Errors:** Check the Cloud Run function logs in the Google Cloud Console for any errors.
*   **Cloud Scheduler Task Failures:** Check the Cloud Scheduler task history in the Google Cloud Console for any failures.
*   **Data Not Ingested:** Verify that the custom log type is available and that the parser is correctly configured.
*   **API Key Issues:** Ensure that the VirusTotal API key is valid and has sufficient quota.
