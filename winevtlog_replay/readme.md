## Overview

This Python script replays a Windows Event Log in either binary EVTX or XLM file to a Google SecOps SIEM tenant.  

## Setup Steps

### Python Requirements

```
sudo apt install python3.11-venv
python3 -m venv EVTX
source EVTX/bin/activate
pip3 install python-evtx
pip3 install google-cloud
pip3 install google-auth
pip3 install requests
```

### Download EVTX Samples

Optionally, download EVTX samples or utilize your own exported EVTX files.

```
sudo apt-get install git
git clone https://github.com/Yamato-Security/hayabusa-sample-evtx.git
```

## Create a BYOP SecOps Service Account

Bash variables:
```
SERVICE_ACCOUNT_NAME="sa-secops-siem"
DESCRIPTION="SecOps SIEM Service Account"
DISPLAY_NAME="SecOps SIEM Service Account"
PROJECT_ID="your-secops-gcp-project"
ROLE_NAME="chronicle_log_import"
```

Custom IAM Role YAML File:
```
title: "SecOps Log Import"
description: "Allows importing logs via the Chronicle API."
stage: "GA"
includedPermissions:
  - chronicle.logs.import
```

Create the custom IAM Role:
```
gcloud iam roles create "$ROLE_NAME" \
--project="$PROJECT_ID" \
--file="custom_role.yaml"
```

Create a GCP Service Account:
```
gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
  --description="$DESCRIPTION" \
  --display-name="$DISPLAY_NAME"
```

Grant the custom IAM Role:
```
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="projects/$PROJECT_ID/roles/$ROLE_NAME"
```

Create a Service Account Key:
```
gcloud iam service-accounts keys create chronicle-api-sa-key.json  \
 --iam-account="$SERVICE_
ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com"
```

## Example Script Usage

You can access the following configuration parameters from:
* Customer_id = SIEM Setting > Customer GUID
* Region = the region of your SecOps tenant
 - US (us) or Europe (eu) for multiregion instances, otherwise the region, e.g., "asia-south1"
* Forwarder_id = Create a Chronicle Forwarder, and copy the Config ID

```
python3 evtx2chronicle.py --credentials_file "./config/chronicle-api-sa-key.jsonn" \ 
--customer_id "b3465895-93ec-4db4-84af-e2c13008e537" \ 
--region "eu" \ 
--project_id "thatsiemguy-europe-chronicle" \ 
--forwarder_id "d856c51d-722e-40a6-a320-8bb07df99e07" \ 
--path "~/SecOps/EVTX_to_Chronicle/VT/2047bb9f00b_Zenbox.evtx/Microsoft-Windows-SysmonOperational.xml" \ 
--use_case_name "CATEGORY-USECASE" \
--namespace "TEST" \
--dry_run "true"
```



