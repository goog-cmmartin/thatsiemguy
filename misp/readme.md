# MISP (JSON) to Chronicle SIEM Integration

## Overview

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

Under `Administration > List Auth Keys` within your MISP UI.

3. Create Secrets in GCP Secret Manager

The Cloud Function uses GCP's Secret Manager to securely store API credentials.  For both a) Chronicle Ingestion API Credentials and b) MISP API Key create a GCP Secret.  You can use GCP Cloud Shell within the same project as the 

```
gcloud secrets create MISP-API --data-file=/home/admin_/ingestion-scripts/misp/misp.deleteme 
gcloud secrets create CHRONICLE-INGESTION-API --data-file=/home/admin_/ingestion-scripts/misp/chronicle-ingestion-key.json
```
