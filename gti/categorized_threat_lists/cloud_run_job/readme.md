# Deploy GTI Categorized Threat Feeds into SecOps Cloud Rub Job

state: draft

GCP Cloud Run Jobs are used to poll the [`/api/v3/threat_lists/{threat_list_id}/{time}`](https://gtidocs.virustotal.com/reference/get-hourly-threat-list)  GTI API endpoint.  A Cloud Run Job is created for each individual `Category name`.

## Set environment variables before deployment as a Cloud Run Job

```
GCP_PROJECT="your-gcp-project"
SA_NAME="your-gcp-sa" #e.g., "sa-vt-threat-feed-to-secops"
SA_DESCRIPTION="Export VT Threat Feed IOCs to Google SecOps"
SA_DISPLAY_NAME="GTI IOC Stream to Google SecOps"
REGION="your-gcp-region" #e.g., "us-central1"
CLOUD_RUN_JOB_NAME="vt-threat-feed" #this will require a Cloud Run Job per GTI Categorized Threat feed type

SECOPS_INSTANCE_GUID="your-secops-guid"
SECOPS_INSTANCE_LOCATION="your-secops-regions" #e.g., us
SECOPS_LOG_TYPE="ACME_GTI_THREAT_FEED" # e.g., your custom SecOps Log Type
SECOPS_FORWARDER_ID="a-secops-forwarder-id"

VT_QUERY="positives:5+ gti_score:2+"
VT_ITEM_LIMIT="400"
VT_API_KEY_SECRET_PATH="projects/your-gcp-project/secrets/vt-api-key-name/versions/latest"
VT_ITEM_LIMIT="4000"
VT_THREAT_FEED="infostealer"
```

## Build the Docker image

```
docker build -t $REGION-docker.pkg.dev/$GCP_PROJECT/cloud-run-source-deploy/$CLOUD_RUN_JOB_NAME:latest .
docker push $REGION-docker.pkg.dev/$GCP_PROJECT/cloud-run-source-deploy/$CLOUD_RUN_JOB_NAME:latest
```

## Create a GCP Secret for the GTI API Key

```
SECRET_NAME="vt-api-key"
API_KEY_VALUE="your-gti-api-key
echo -n "${API_KEY_VALUE}" | gcloud secrets create "${SECRET_NAME}"   --project="${GCP_PROJECT}"   --data-file=-
```


## Deploy the Cloud Rub Job

```
gcloud auth login
gcloud run jobs deploy $CLOUD_RUN_JOB_NAME-$VT_THREAT_FEED --image $REGION-docker.pkg.dev/$GCP_PROJECT/cloud-run-source-deploy/$CLOUD_RUN_JOB_NAME:latest --project $GCP_PROJECT --region $REGION --service-account $SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com --set-env-vars="GCP_PROJECT_ID=$GCP_PROJECT,SECOPS_INSTANCE_GUID=$SECOPS_INSTANCE_GUID,SECOPS_INSTANCE_LOCATION=$SECOPS_INSTANCE_LOCATION,SECOPS_LOG_TYPE=$SECOPS_LOG_TYPE,SECOPS_FORWARDER_ID=$SECOPS_FORWARDER_ID,VT_API_KEY_SECRET_PATH=$VT_API_KEY_SECRET_PATH,VT_THREAT_FEED=$VT_THREAT_FEED,VT_QUERY=$VT_QUERY,VT_ITEM_LIMIT=$VT_ITEM_LIMIT"
```

## Schedule the Cloud Run Job

```
SCHEDULER_JOB_NAME="invoke-$CLOUD_RUN_JOB_NAME-job-hourly-$VT_THREAT_FEED"
gcloud scheduler jobs create http $SCHEDULER_JOB_NAME   --schedule="0 * * * *"   --uri="https://$(echo $REGION)-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$(echo $GCP_PROJECT)/jobs/$(echo $CLOUD_RUN_JOB_NAME-$VT_THREAT_FEED):run"   --http-method=POST   --oauth-service-account-email=$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com   --location=$REGION
```

 
