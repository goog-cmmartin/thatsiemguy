# Deploy GTI Digital Threat Monitoring into SecOps Cloud Rub Job

state: draft

## Set environment variables before deployment as a Cloud Run Job

```
GCP_PROJECT="your-gcp-project"
SA_NAME="your-gcp-sa" #e.g., "sa-vt-threat-feed-to-secops"
SA_DESCRIPTION="Export GTI DTM Alerts to Google SecOps"
SA_DISPLAY_NAME="GTI DTM to Google SecOps"
REGION="your-gcp-region" #e.g., "us-central1"
CLOUD_RUN_JOB_NAME="gti-dtm-to-secops" #this will require a Cloud Run Job per GTI Categorized Threat feed type
GTI_DTM_TO_SECOPS="DTM-to-SecOps"
```

## Copy and configure the .env.yaml
Copy the template .env.example file as .env.yaml, and update parameters accordingly.


### Build the Docker image

```
docker build -t $REGION-docker.pkg.dev/$GCP_PROJECT/cloud-run-source-deploy/$CLOUD_RUN_JOB_NAME:latest .
docker push $REGION-docker.pkg.dev/$GCP_PROJECT/cloud-run-source-deploy/$CLOUD_RUN_JOB_NAME:latest
```

### Create a GCP Secret for the GTI API Key

```
SECRET_NAME="vt-api-key"
API_KEY_VALUE="your-gti-api-key
echo -n "${API_KEY_VALUE}" | gcloud secrets create "${SECRET_NAME}"   --project="${GCP_PROJECT}"   --data-file=-
```


### Deploy the Cloud Rub Job

```
gcloud auth login
gcloud run jobs deploy $CLOUD_RUN_JOB_NAME-$GTI_DTM_TO_SECOPS --image $REGION-docker.pkg.dev/$GCP_PROJECT/cloud-run-source-deploy/$CLOUD_RUN_JOB_NAME:latest --project $GCP_PROJECT --region $REGION --service-account $SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com --set-env-file env.yaml"
```

### Schedule the Cloud Run Job

```
SCHEDULER_JOB_NAME="invoke-$CLOUD_RUN_JOB_NAME-job-hourly-$GTI_DTM_TO_SECOPS"
gcloud scheduler jobs create http $SCHEDULER_JOB_NAME   --schedule="0 * * * *"   --uri="https://$(echo $REGION)-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$(echo $GCP_PROJECT)/jobs/$(echo $CLOUD_RUN_JOB_NAME-$GTI_DTM_TO_SECOPS):run"   --http-method=POST   --oauth-service-account-email=$SA_NAME@$GCP_PROJECT.iam.gserviceaccount.com   --location=$REGION
```

 
