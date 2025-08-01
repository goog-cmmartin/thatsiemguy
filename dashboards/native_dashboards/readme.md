# Google SecOps License Utilization Dashboard

This dashboard provides a comprehensive view of your Google SecOps license usage, focusing on the volume of data being ingested. It helps you monitor costs, understand data sources, and track ingestion trends over time.

---

## Key Components

The dashboard is composed of three main sections:

### 📊 Ingestion Volume Overview
This section gives you a quick, high-level summary of your data usage.

* **KPI Scorecards:** Show the **total gigabytes (GB) ingested** over the last 1, 7, 30, and 365 days.
* **Daily Ingestion Chart:** A bar chart that visualizes the amount of data ingested each day, with color-coding to highlight days that exceed a set threshold. Note, you will need to customize this based upon your license level.

---

### 🔎 Log Source Breakdown
This section helps for cost management and optimization.

* **Log Volume by Type Table:** This table breaks down the total data volume by **log source** (e.g., `GCP_CLOUDDNS`, `GCP_FIREWALL`, `WINDOWS_EVENTLOG`). It shows exactly which logs are consuming the most of your license, allowing you to investigate and manage noisy sources.

---

### ⚙️ Performance & Activity Metrics
These gauges provide additional context on the rate and consistency of data ingestion.

* **Average Events Per Second (EPS):** Shows the average rate of logs being ingested.
* **Used Partitions (Days):** Indicates the number of days data was actively ingested.

---

![Google SecOps License Utilisation](secops_license_utilization/gus_secops_license_utilization.png)
