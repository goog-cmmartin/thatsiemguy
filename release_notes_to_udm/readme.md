# Chronicle Release Notes to UDM

This example Cloud Function integration polls the Chronicle SIEM Release Notes RSS Feed and converts the XML response into a UDM JSON Object ingested via the Chronicle Ingestion API.

## Usage

The integration consists of:
* a Cloud Function - used to poll the RSS feed and create a UDM object in Chronicle SIEM
* a YARA-L rule - used to generate an alert for new features, or updates to monitored integrations, e.g., parsers for log sources in your instance
* an embedded Looker Dashboard - visualize and lookback at prior feature releases

![Chronicle SIEM Release Notes](https://github.com/goog-cmmartin/thatsiemguy/blob/main/release_notes_to_udm/chronicle_release_notes.png "Chronicle SIEM Release Notes")


## Setup Notes

Configure the .yanl file as required:



### Create a service account for the Cloud Function

<pre>
GCP_PROJECT="<your GCP Project>"

SA_NAME="sa-chronicle-release-notes-to-udm"
SA_DESCRIPTION="Export Chronicle Release Notes as UDM"
SA_DISPLAY_NAME="Chronicle Release Notes to UDM"

gcloud iam service-accounts create $SA_NAME --description="$SA_DESCRIPTION" --display-name="$SA_DISPLAY_NAME"

</pre>

### Create SECRETS

Note, if you have an Chronicle Ingestion API Key as a secret already, re-use that.

<pre>
gcloud secrets create CHRONICLE-INGESTION-API --data-file=/home/user/chronicle-ingestion-key.json
</pre>

### Grant Access to Secrets

Grant the SA access to all secrets above, e.g., 

<pre>
gcloud secrets add-iam-policy-binding MATI-KEY-ID --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --project=$GCP_PROJECT --role='roles/secretmanager.secretAccessor'
</pre>

### Grant service account access to run a Cloud Function

<pre>
gcloud projects add-iam-policy-binding $GCP_PROJECT --member="serviceAccount:$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com"   --role='roles/cloudfunctions.developer'
</pre>

### Edit the Cloud Function .Env file

Configure `.env.yml` by replacing the values that match your environment.

CHRONICLE_REGION: # e.g., europe.  Check the Cloud Function for support regions, and add if region is not listed
SERVICE_ACCOUNT_FILE: # the path to your Ingestion API secret, e.g., projects/12345678910/secrets/chronicle_service_account_ingestion/versions/1
CHRONICLE_CUSTOMER_ID: # your guid, can be found under UI in Settings
# Check the last two days as from observation Release Notes can be back dated
VALID_EVENTS_RANGE: 172800 # set as two days as Release Notes as it appears release notes can be back dated
DEBUG: False
GCP_PROJECT: # gcp project ID, not GCP project name


### Deploy the Cloud Function

<pre>
REGION="europe-west4"
MEMORY="4096MB"
MIN_INSTANCES="1"

gcloud functions deploy mati-to-chronicle --entry-point main --trigger-http --runtime python311 --env-vars-file .env.yml --region $REGION  --memory $MEMORY --min-instances $MIN_INSTANCES --service-account $SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com
</pre>

### Add a Cloud Scheduler Task to run the Cloud Function at scheduled intervals

<pre>
SA_NAME="sa-mati-to-chronicle"
GCP_PROJECT="<your GCP Project>"
JOB_NAME='Chronicle_Release_Notes_to_UDM'
JOB_URI='https://<region>-<project>.cloudfunctions.net/mati-to-chronicle'
GCP_PROJECT='<Your GCP Project>'
JOB_LOCATION='us-central1'

gcloud scheduler jobs create http "$JOB_NAME" --schedule="0 * * * *" --uri="$JOB_URI" --http-method=POST --oidc-service-account-email="$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --oidc-token-audience="$JOB_URI" --location=$JOB_LOCATION  
</pre>


### Disclaimer

 Note, this is not an official integration, and is not guaranteed to collect and submit all Release Notes into your SIEM instance , but rather is provided as an educational example of how to build an integration with a 3rd party application.
