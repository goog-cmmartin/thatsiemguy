# GTI Digital Threat Monitoring
---
This repo contains an example integration between Google Threat Intelligence (GTI) and Google SecOps.  It uses a GCP Cloud Run Job to poll the DTM API and create UDM Events for your DTM Monitors.

## Setup Intructions

Please refer to each individual sub-folder for component specific setup instructions.

## Contents
* Cloud Run Job
  * main.py
  * requirements.txt
  * Dockerfile

* SecOps Parser
  * gti_dtm_parser.txt

* SecOps (Native) Dashboard
  * GTI Digital Threat Monitoring.json

![GTI DTM Dashboard in Google SecOps](secops_dashboard/gti_dtm_dashboard.png)
