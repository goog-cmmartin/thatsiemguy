# SIEM License Utilization

This Chronicle SIEM (Embedded Looker) Dashboard is designed to aide evaluating your current utilization (storage) against your Chronicle SIEM consumption license, i.e., are you under, at, or over your license usage.

This Dashboard is not applicable for per User based licensing, but still may be of interest for general volume utilization insight.

## Usage

The Dashboard uses the Chronicle Datalake (BigQuery dataset) Ingestion Metrics table to display, by default, the last 30 days of Ingested Bytes for all Log Sources; however, if you have a different retention period you can change the 12 month value in the YAML file before importing the Dashboard, or manually by changing each widget in the UI.

- the Scorecard Widgets are shown in GibiBytes (GiB) so you will need to convert this to TebiBytes (TiB) to evaluate against your consumption license
- the Area chart plots in GibiBytes so you will need to also convert this to Tebibytes on the legend (use Google or Bard), and provides a Trend line for inference of if your utilization is increasing, stready state, or decreasing
	- optionally, a static threshold line can be added to this chart as a Maximum value (in Bytes also)
	- you can also download this data to CSV if you wish to analyse in Excel or Sheets
- the Stacked Bar chart shows the GibiBytes utilization by Log Sources to see which log source are consuming against your license

![Chronicle SIEM License Usage Dashboard](https://github.com/goog-cmmartin/thatsiemguy/blob/main/dashboards/siem_license_usage/siem_license_usage.png "SIEM License Usage")

- Chronicle SIEM consumption licensing is sold in TeraBytes, not TebiBytes. 
- If you receive errors on individual widgets then the most likely explanation is that you have days with 0 value entries, of which the default dashboard Trendline will error if it encounters this scenario.  A second copy of the dashboardwith out a Trendline is added for environments where this may happen.
- You can add a Trendline or static threshold by editing a Widgets and the Y axis tab to add a Reference Line or Trend Line.  To show the daily volume, take your annual license in GibiBytes, divide by 365, and plot this as a static value.

![Chronicle SIEM License Usage Dashboard](https://github.com/goog-cmmartin/thatsiemguy/blob/main/dashboards/siem_license_usage/siem_license_usage_threshold.png "Adding a static threshold value")


__Note, this is not an official Google Cloud Chronicle Dashboard.  There is no guarantee the numbers in this Dashboard align or match to those which Google Cloud may use for licensing monitoring purposes.__
