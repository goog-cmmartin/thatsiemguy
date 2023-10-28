# Mandiant Advanced Threat Intelligence (MATI) to Chronicle SIEM Integration

<br>

## Overview

This repo provides an example integration between MATI and Chronicle SIEM to automate IOC matching using Chronicle SIEM's Entity Graph, and YARA-L Detection Engine.  The integration is provided as a demonstration of how to connect to a 3rd party API, in this case MATI, and using Python to create a native UDM Object to be ingested directly to the Chronicle Ingestion API udm event endpoint, aka, no CBN parser required.  The integration uses several Cloud Function environment variables to provide customization for features such as:
* MATI IOC confidenc score threshold filtering.  The default is 80 and above.
* Aging (decay) of IOCs.  While MATI includes a Confidence Score you can configure the Expiry value to set the interval start and interval end date for when the IOC should be considered valid.

The key point of this example is that you can use other programming or scripting languages to create UDM Events or UDM Entities, for example the main body of Python code that converts a MATI API response into a UDM Entity IOC Event is as follows.  An advantage of using a programming or scripting language, such as Python, is the power and flexibility mean you can format data into Chronicle SIEM's schema with a small amount of code, but also perform functions that are not possible in Parsing via CBN, e.g., date addition, or perform functions in an easier manner, e.g., parsing nested JSON.

<img src="https://github.com/goog-cmmartin/thatsiemguy/blob/main/mati/chronicle_dashboards/mati_ioc_dashboard_example.png" />

## Pre-requisites

To utilize this integration requires the following pre-requisites:
* You are a MATI API Key and Secret
* Your Chronicle SIEM instance region
* Chronicle Customer GUID
* Chronicle Ingestion API JSON Developer Service Account

## Integration Notes

### Create a service account for the Cloud Function

<pre>
GCP_PROJECT="<your GCP Project>"

SA_NAME="sa-mati-to-chronicle"
SA_DESCRIPTION="Export MATI IOCs to Chronicle SIEM"
SA_DISPLAY_NAME="SA MATI to Chronicle SIEM"

gcloud iam service-accounts create $SA_NAME --description="$SA_DESCRIPTION" --display-name="$SA_DISPLAY_NAME"

</pre>

### Create SECRETS

Note, if you have an Chronicle Ingestion API Key as a secret already, re-use that.

<pre>
gcloud secrets create MATI-KEY-ID --data-file=/home/user/mati-key-id
gcloud secrets create MATI-SECRET --data-file=/home/user/mati-secret
gcloud secrets create CHRONICLE-INGESTION-API --data-file=/home/user/chronicle-ingestion-key.json
</pre>

### Grant Access to Secrets

Grant the SA access to all secrets above, e.g., 

<pre>
gcloud secrets add-iam-policy-binding MATI-KEY-ID --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --project=$GCP_PROJECT --role='roles/secretmanager.secretAccessor'
gcloud secrets add-iam-policy-binding MATI-SECRET --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --project=$GCP_PROJECT --role='roles/secretmanager.secretAccessor'
gcloud secrets add-iam-policy-binding CHRONICLE-INGESTION-API --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --project=$GCP_PROJECT --role='roles/secretmanager.secretAccessor'
</pre>

### Grant service account access to run a Cloud Function

<pre>
gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com"   --role='roles/cloudfunctions.developer'
</pre>

### Edit the Cloud Function .Env file

Configure `.env.yml` by replacing the values that match your environment.

### Deploy the Cloud Function

<pre>
REGION="us-central1"
MEMORY="4096MB"
MIN_INSTANCES="1"

gcloud functions deploy mati-to-chronicle --entry-point main --trigger-http --runtime python311 --env-vars-file .env.yml --region $REGION  --memory $MEMORY --min-instances $MIN_INSTANCES --service-account $SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com
</pre>

### Add a Cloud Scheduler Task to run the Cloud Function at scheduled intervals

<pre>
SA_NAME="sa-mati-to-chronicle"
GCP_PROJECT="<your GCP Project>"
JOB_NAME='MATI_Chronicle_SIEM_Test'
JOB_URI='https://<region>-<project>.cloudfunctions.net/mati-to-chronicle'
JOB_LOCATION='us-central1'

gcloud scheduler jobs create http "$JOB_NAME" --schedule="0 * * * *" --uri="$JOB_URI" --http-method=POST --oidc-service-account-email="$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --oidc-token-audience="$JOB_URI" --location=$JOB_LOCATION  
</pre>
