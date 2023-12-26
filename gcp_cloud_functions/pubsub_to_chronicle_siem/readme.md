# PubSub to Chronicle Ingestion API (v2)

### Create a service account for the Cloud Function

<pre>
GCP_PROJECT="<your GCP Project>"

SA_NAME="sa-gcp-pubsub-to-chronicle"
SA_DESCRIPTION="Used for sending logs to Chronicle SIEM via GCP PubSub Pull Subscription"
SA_DISPLAY_NAME="SA GCP PubSub to Chronicle SIEM"

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
CLOUD_FUNCTION_NAME="pubsub-to-chronicle"

gcloud functions deploy $CLOUD_FUNCTION_NAME --entry-point main --trigger-http --runtime python311 --env-vars-file .env.yml --region $REGION  --memory $MEMORY --min-instances $MIN_INSTANCES --service-account $SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com
</pre>

### Add a Cloud Scheduler Task to run the Cloud Function at scheduled intervals

<pre>
SA_NAME="sa-mati-to-chronicle"
GCP_PROJECT="<your GCP Project>"
JOB_NAME='MATI_Chronicle_SIEM_Test'
JOB_URI='https://<region>-<project>.cloudfunctions.net/$CLOUD_FUNCTION_NAME'
JOB_LOCATION='us-central1'

gcloud scheduler jobs create http "$JOB_NAME" --schedule="0 * * * *" --uri="$JOB_URI" --http-method=POST --oidc-service-account-email="$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com" --oidc-token-audience="$JOB_URI" --location=$JOB_LOCATION
</pre>
