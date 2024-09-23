# Windows Event Log Replay Utility

## Overview

This Python script replays a Windows Event Log, in either binary EVTX or XLM file, to a Google SecOps SIEM tenant.

The script automatically:
* can convert binary EVTX files into XML files
* identify the appropriate Ingestion Label by evaluating the Windows Event Log Channel
* update Timestamps to the time of running, with a configurable offset, while maintaining the original interval between events
* batch ingest into SecOps SIEM

## Setup Steps

### Python Requirements

You can configure a Python environment with the following commands:

```
sudo apt install python3.11-venv
python3 -m venv EVTX
source EVTX/bin/activate
pip3 install python-evtx
pip3 install google-auth
pip3 install requests
```

### EVTX and XML Samples

You can download binary EVTX files from various online sources, for example:

```
sudo apt-get install git
git clone https://github.com/Yamato-Security/hayabusa-sample-evtx.git
```

Or you can download Event Logs from Sandbox sources on VirusTotal, e.g., Zenbox, CAPE.

## Example Usage

The script is called with the following parameters:

```
# Required arguments
parser.add_argument('--credentials_file', required=True, help='Path to Chronicle SIEM credentials JSON file')
parser.add_argument('--customer_id', required=True, help='Chronicle SIEM Customer ID')
parser.add_argument('--region', required=True, help='Chronicle SIEM Ingestion API Region')
parser.add_argument('--path', required=True, help='Path to EVTX or XML input file')
parser.add_argument('--use_case_name', required=True, help='The Use Case name, added to the Ingestion Labels')

# Optional arguments with default values
parser.add_argument('--namespace', default="untagged", help="Chronicle SIEM Namespace")
parser.add_argument('--test_mode', default="false", help="If true then Events are not replayed to SIEM")
```

To ingest an XML file:
```
python3 evtx2chronicle.py --credentials_file "./config/creds.json" --customer_id "889af7ee-9a1e-41a2-8901-830838bc12b8" --region "us" --path "/tmp/evtx_samples/88da89_Zenbox.evtx/Microsoft-Windows-SysmonOperational.xml" --use_case_name "RANSOMWARE-LOCKBIT.V2" --namespace "Cymbal" --test_mode="true"
```

Example output:

```
<INFO>2024-09-23T20:12:05+0200: Credentials File: ./config/creds.json
<INFO>2024-09-23T20:12:05+0200: Customer Id: 889af7ee-9a1e-41a2-8901-830838bc12b8
<INFO>2024-09-23T20:12:05+0200: Region: us
<INFO>2024-09-23T20:12:05+0200: Path: /tmp/evtx_samples/88da89_Zenbox.evtx/Microsoft-Windows-SysmonOperational.xml
<INFO>2024-09-23T20:12:05+0200: Use Case Name: RANSOMWARE-LOCKBIT.V2
<INFO>2024-09-23T20:12:05+0200: Namespace: Cymbal
<INFO>2024-09-23T20:12:05+0200: Test Mode: true
<INFO>2024-09-23T20:12:05+0200: Valid file extension: xml
<INFO>2024-09-23T20:12:05+0200: EVTX filename = Microsoft-Windows-SysmonOperational.xml
<INFO>2024-09-23T20:12:05+0200: Unique Ingestion Labels count = 1
<INFO>2024-09-23T20:12:05+0200: Event count = 7679
<INFO>2024-09-23T20:12:05+0200: Estimated size of the list: 11544255 bytes
<INFO>2024-09-23T20:12:05+0200: dry_run mode = true
<INFO>2024-09-23T20:12:05+0200: Exiting.
```

## SecOps Integration


The following SecOps SIEM Ingestion Labels are supported:
* POWERSHELL
* WINDOWS_SYSMON
* WINEVTLOG



