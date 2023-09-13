# SIEM Utilization

This Chronicle SIEM Embedded Looker Dashboard is designed to aide evaluating your current utilization (storage) against your Chronicle SIEM license, i.e., are you under, at, or over your license usage.

## Usage

The Dashboard uses the Chronicle Datalake (BigQuery dataset) Ingestion Metrics table to display, by default, the last 12 months of Ingested Bytes for all Log Sources.  If you have a different retention period, i.e., greater or lower, you can change the 12 month value in the YAML file before importing the Dashboard.

![Chronicle SIEM License USage](siem_license_usage.png?raw=true "SIEM License Usage")

Note, this is not an official Google Cloud Chronicle Dashboard.
