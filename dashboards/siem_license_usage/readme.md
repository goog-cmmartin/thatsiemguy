# SIEM License Utilization

This Chronicle SIEM (Embedded Looker) Dashboard is designed to aide evaluating your current utilization (storage) against your Chronicle SIEM consumption license, i.e., are you under, at, or over your license usage.

This Dashboard is not applicable for per User based licensing, but still may be of interest for general volume utilization insight.

## Usage

The Dashboard uses the Chronicle Datalake (BigQuery dataset) Ingestion Metrics table to display, by default, the last 12 months of Ingested Bytes for all Log Sources; however, if you have a different retention period you can change the 12 month value in the YAML file before importing the Dashboard, or manually by changing each widget in the UI.

- the Scorecard Widgets are shown in GigaBytes so you will need to convert this to TeraBytes to evaluate against your consumption license
- the Area chart plots in GigaBytes so you will need to also convert this to Terabytes on the legend (use Google or Bard), and provides a Trend line for inference of if your utilization is increasing, stready state, or decreasing
	- optionally, a static threshold line can be added to this chart as a Maximum value (in Bytes also)
	- you can also download this data to CSV if you wish to analyse in Excel or Sheets
- the Stacked Bar chart shows the GigaBytes utilization by Log Sources to see which log source are consuming against your license

![Chronicle SIEM License Usage Dashboard](https://github.com/goog-cmmartin/thatsiemguy/blob/main/dashboards/siem_license_usage/siem_license_usage.png "SIEM License Usage")

- Chronicle SIEM consumption licensing is sold in TeraBytes, not TebiBytes. 

__Note, this is not an official Google Cloud Chronicle Dashboard.  There is no guarantee the numbers in this Dashboard align or match to those which Google Cloud may use for licensing monitoring purposes.__
